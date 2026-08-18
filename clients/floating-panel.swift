// 手前に浮かべる小窓。ビューア(既定 http://127.0.0.1:8090)をそのまま表示する。
//
//   swiftc -O clients/floating-panel.swift -o build/floating-panel
//   ./build/floating-panel            # 既定のURL
//   ./build/floating-panel http://127.0.0.1:8091
//
// ビューア側には Chrome の Document Picture-in-Picture を使う道もあり、そちらは
// 追加の実行環境が要らない。この殻はブラウザを開いていなくても使いたい場合のもの。
// 独立したウィンドウなので、Chrome を閉じても、Space を移動しても残る。
//
// .app にはしない。speech_helper.swift と同じく素の swiftc で作る実行ファイルにして、
// この repo に新しいツールチェーンを増やさない。

import AppKit
import WebKit

let defaultURL = "http://127.0.0.1:8090"

final class Panel: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let url: URL
    // 立ち上げ直後はビューアがまだ起動していないことがある。何度か静かに試す。
    var retriesLeft = 40

    init(url: URL) { self.url = url }

    func applicationDidFinishLaunching(_ note: Notification) {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()       // テーマや言語の選択を憶えるため

        web = WKWebView(frame: .zero, configuration: cfg)
        web.uiDelegate = self
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")   // 角丸の外に白が出ないように

        // 幅は「横に並べない細長い板」として決め打ち、高さだけ画面に合わせる。
        let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let w: CGFloat = 400
        let h = min(760, visible.height - 40)
        let frame = NSRect(x: visible.maxX - w - 24, y: visible.maxY - h - 24, width: w, height: h)

        window = NSWindow(contentRect: frame,
                          styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "voice-shell"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.isMovableByWindowBackground = true
        window.backgroundColor = .clear
        window.hasShadow = true
        // ここがこの殻の存在理由。常に他のウィンドウの手前に居座る。
        window.level = .floating
        // Space を移動しても付いてくる。全画面のアプリの上にも出る。
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.setFrameAutosaveName("voice-shell-panel")   // 位置と大きさを憶える
        window.contentView = web
        window.makeKeyAndOrderFront(nil)

        load()
    }

    func load() { web.load(URLRequest(url: url)) }

    // ビューアがまだ起きていないだけなら、黙って待って繋ぎ直す。
    func webView(_ w: WKWebView, didFail nav: WKNavigation!, withError e: Error) { retry(e) }
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) { retry(e) }

    func retry(_ e: Error) {
        guard retriesLeft > 0 else {
            let m = "つながりません: \(url.absoluteString)\n\nビューアを起動してから開いてください。"
            web.loadHTMLString(errorPage(m), baseURL: nil)
            return
        }
        retriesLeft -= 1
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.load() }
    }

    // マイクは渡さない。音量はデーモンが流す rms を使う設計なので、ここで許可を
    // 求めると TCC の帰属が実行ファイルに移り、面倒なだけで得るものが無い。
    // ページ側は取得に失敗したらデーモンの値へ落ちる。
    func webView(_ w: WKWebView,
                 requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo,
                 type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(.deny)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    private func errorPage(_ message: String) -> String {
        """
        <meta charset="utf-8">
        <style>
          html,body{height:100%;margin:0}
          body{display:grid;place-items:center;background:#080C11;color:#93A4B4;
               font:14px/1.7 -apple-system,system-ui,sans-serif;text-align:center;padding:2rem}
          p{white-space:pre-line;max-width:22rem}
        </style>
        <p>\(message)</p>
        """
    }
}

let arg = CommandLine.arguments.dropFirst().first ?? defaultURL
guard let url = URL(string: arg) else {
    FileHandle.standardError.write("URL として読めません: \(arg)\n".data(using: .utf8)!)
    exit(2)
}

let app = NSApplication.shared
let panel = Panel(url: url)
app.delegate = panel
// Dock には出さない。常駐する小窓なので、アプリ切り替えの列に並ぶと邪魔になる。
app.setActivationPolicy(.accessory)
app.run()
