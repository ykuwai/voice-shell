import Foundation
import AVFoundation
import Speech

// macOS 26 の SpeechAnalyzer / SpeechTranscriber を voice-shell から使うための常駐ヘルパ。
//
// stdin から 1 行 1 リクエスト（WAV のパス）を受け取り、認識結果を JSON 1 行で返す。
//   入力: /path/to/utterance.wav\n     … その音声を認識する
//         QUIT\n                        … 終了
//   出力: {"text":"...","language":"ja-JP"}\n
//         {"error":"..."}\n
// 起動が済むと {"ready":true,"locale":"ja-JP"} を 1 行出す。
//
// 使い方:
//   ./speech_helper [--locale ja-JP]
//
// ## マイクは触らない
//
// 録音と発話の区切り（VAD）は Python 側が持っている。ここは音声を受け取って
// 文字にするだけ。マイクを触らなければ TCC の許可も .app 化も要らず、
// swiftc で作った素の実行ファイルのまま動く。
//
// ## ストリーム給餌ではなくファイル渡しにしている
//
// SpeechAnalyzer には AsyncStream に音声を流し込む API もあるが、
// この構成（署名なしの CLI）では start(inputSequence:) が nilError で落ちた。
// analyzeSequence(from: AVAudioFile) は同じ条件で問題なく動くので、
// 発話 1 つ分を WAV に書いて渡す形にしている。認識は RTF 0.03 ほどなので、
// 途中経過のために発話全体を何度も認識し直しても十分に間に合う。

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

        // モデル資産は端末に無ければここで落としてくる（初回のみ数十秒）。
        // status は毎回の起動で .supported に戻ることがあるので、
        // installationRequest が nil を返すかどうかで判断する。
        do {
            if let request = try await AssetInventory.assetInstallationRequest(
                supporting: [makeTranscriber(locale)]) {
                FileHandle.standardError.write(
                    "音声認識モデルを用意しています…\n".data(using: .utf8)!)
                try await request.downloadAndInstall()
            }
        } catch {
            emit(["error": "モデル資産の用意に失敗しました: \(error)"])
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
        // 確定結果しか使わないので volatileResults は要らない。
        // 途中経過は Python 側が「溜まったぶんを認識し直す」形で作る。
        SpeechTranscriber(locale: locale,
                          transcriptionOptions: [],
                          reportingOptions: [],
                          attributeOptions: [])
    }

    /// WAV 1 本を認識して、確定テキストと言語を返す。
    ///
    /// SpeechTranscriber と SpeechAnalyzer は毎回作り直す。results は
    /// 1 回の解析で終わる AsyncSequence なので、使い回すと 2 回目が取れない。
    /// モデル資産はプロセス内で温まったままなので、作り直しても数ミリ秒で済む。
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

    /// JSON を 1 行で書き出す。Python 側が 1 行ずつ読むので、必ず流し切る。
    static func emit(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              var line = String(data: data, encoding: .utf8) else { return }
        line += "\n"
        FileHandle.standardOutput.write(line.data(using: .utf8)!)
    }
}
