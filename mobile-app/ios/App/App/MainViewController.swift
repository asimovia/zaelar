import Capacitor
import UIKit
import WebKit

/// Capacitor's bridge view controller plus the app's own glue script (`www/in-app.js`, bundled as `public/in-app.js`),
/// injected at document start into every main-frame page. The script acts only on the configured server's origin,
/// which it receives here as `ZAELAR_APP_ORIGIN`. It also puts `NavigationFilter` in front of Capacitor's navigation
/// delegate, so a superseded load or an engine that is still starting are handled as such.
class MainViewController: CAPBridgeViewController {

    private var navigationFilter: NavigationFilter?   // the WebView holds its navigation delegate weakly

    override func capacitorDidLoad() {
        super.capacitorDidLoad()
        bridge?.registerPluginInstance(DevicePlugin())   // the device bridge (V2-890): sensors for the shell
        // capacitorDidLoad runs inside loadView, before the first page is requested: no load escapes the filter.
        // At this point the WebView's navigation delegate is still Capacitor's handler (set in prepareWebView).
        if let handler = webView?.navigationDelegate as? WebViewDelegationHandler {
            let filter = NavigationFilter(inner: handler, errorURL: bridge?.config.errorPathURL)
            navigationFilter = filter
            webView?.navigationDelegate = filter
        }
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
