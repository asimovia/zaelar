import Capacitor
import UIKit
import WebKit

/// Capacitor's bridge view controller plus the app's own glue script (`www/in-app.js`, bundled as `public/in-app.js`),
/// injected at document start into every main-frame page. The script acts only on the configured server's origin,
/// which it receives here as `ZAELAR_APP_ORIGIN`.
class MainViewController: CAPBridgeViewController {

    override func capacitorDidLoad() {
        super.capacitorDidLoad()
        guard let url = Bundle.main.url(forResource: "in-app", withExtension: "js", subdirectory: "public"),
              let glue = try? String(contentsOf: url, encoding: .utf8) else {
            NSLog("[zaelar] in-app.js missing from the bundle")
            return
        }
        let origin = Self.origin(of: bridge?.config.serverURL)
        let literal = (try? JSONEncoder().encode(origin)).flatMap { String(data: $0, encoding: .utf8) } ?? "\"\""
        let source = "(function (ZAELAR_APP_ORIGIN) {\n\(glue)\n})(\(literal));"
        let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        webView?.configuration.userContentController.addUserScript(script)
    }

    /// `scheme://host[:port]` — the same string a page reads as `location.origin`.
    static func origin(of url: URL?) -> String {
        guard let url, let scheme = url.scheme, let host = url.host else { return "" }
        return "\(scheme)://\(host)" + (url.port.map { ":\($0)" } ?? "")
    }
}
