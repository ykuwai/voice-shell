import Foundation
import AVFoundation
import Speech

// Resident helper that lets voice-shell use the macOS 26 SpeechAnalyzer / SpeechTranscriber.
//
// It takes one request per line on stdin (a WAV path) and answers with one line of JSON.
//   What it takes
//     /path/to/utterance.wav\n     … recognize that audio
//     QUIT\n                       … quit
//   What it gives back
//     {"text":"...","language":"ja-JP"}\n
//     {"error":"..."}\n
// Once startup is done it puts out one line, {"ready":true,"locale":"ja-JP"}.
//
// Usage is as follows.
//   ./speech_helper [--locale ja-JP]
//
// ## It never touches the mic
//
// Recording and the utterance boundaries (VAD) belong to the Python side. This
// only takes audio in and turns it into text. Never touching the mic means no
// TCC permission and no .app wrapper, so a bare swiftc binary runs as it is.
//
// ## Files are handed over rather than a stream fed in
//
// SpeechAnalyzer also has an API for pouring audio into an AsyncStream, but in
// this setup (an unsigned CLI) start(inputSequence:) died with nilError.
// analyzeSequence(from: AVAudioFile) works fine under the same conditions, so
// one utterance is written to a WAV and handed over. Recognition runs at about
// RTF 0.03, so re-recognizing the whole utterance again and again for partials
// keeps up with room to spare.

@main
struct SpeechHelper {
    static func main() async {
        let args = CommandLine.arguments
        let localeID = args.firstIndex(of: "--locale").flatMap {
            $0 + 1 < args.count ? args[$0 + 1] : nil
        } ?? "ja-JP"

        guard let locale = await SpeechTranscriber.supportedLocale(
            equivalentTo: Locale(identifier: localeID)) else {
            emit(["error": "\(localeID) は SpeechTranscriber が対応していません"])
            exit(1)
        }

        // Model assets get downloaded here if the machine lacks them (tens of
        // seconds, first time only). status can drop back to .supported on any
        // launch, so judge by whether installationRequest hands back nil.
        do {
            if let request = try await AssetInventory.assetInstallationRequest(
                supporting: [makeTranscriber(locale)]) {
                FileHandle.standardError.write(
                    "音声認識モデルを用意しています…\n".data(using: .utf8)!)
                try await request.downloadAndInstall()
            }
        } catch {
            emit(["error": "モデル資産の用意に失敗しました。\(error)"])
            exit(1)
        }

        emit(["ready": true, "locale": locale.identifier(.bcp47)])

        while let line = readLine(strippingNewline: true) {
            let path = line.trimmingCharacters(in: .whitespaces)
            if path.isEmpty { continue }
            if path == "QUIT" { break }
            do {
                let (text, lang) = try await transcribe(path: path, locale: locale)
                emit(["text": text, "language": lang])
            } catch {
                emit(["error": "\(error)"])
            }
        }
    }

    static func makeTranscriber(_ locale: Locale) -> SpeechTranscriber {
        // Only final results are used, so volatileResults is not needed.
        // Partials come from the Python side re-recognizing what has piled up.
        SpeechTranscriber(locale: locale,
                          transcriptionOptions: [],
                          reportingOptions: [],
                          attributeOptions: [])
    }

    /// Recognize one WAV and hand back the final text and the language.
    ///
    /// SpeechTranscriber and SpeechAnalyzer are rebuilt every time. results is
    /// an AsyncSequence that ends with a single analysis, so reusing it means
    /// the second round never arrives. The model assets stay warm inside the
    /// process, so rebuilding costs only a few milliseconds.
    static func transcribe(path: String, locale: Locale) async throws -> (String, String) {
        let transcriber = makeTranscriber(locale)
        let analyzer = SpeechAnalyzer(modules: [transcriber])

        let collector = Task { () -> String in
            var text = ""
            for try await result in transcriber.results where result.isFinal {
                text += String(result.text.characters)
            }
            return text
        }

        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        if let last = try await analyzer.analyzeSequence(from: file) {
            try await analyzer.finalizeAndFinish(through: last)
        } else {
            await analyzer.cancelAndFinishNow()
        }
        let text = try await collector.value
        return (text.trimmingCharacters(in: .whitespacesAndNewlines),
                locale.identifier(.bcp47))
    }

    /// Write the JSON on one line. Python reads line by line, so always flush it out.
    static func emit(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              var line = String(data: data, encoding: .utf8) else { return }
        line += "\n"
        FileHandle.standardOutput.write(line.data(using: .utf8)!)
    }
}
