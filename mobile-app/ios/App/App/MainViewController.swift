import Capacitor
import UIKit
import WebKit

/// Capacitor's bridge view controller plus the app's own glue script (`www/in-app.js`, bundled as `public/in-app.js`),
/// injected at document start into every page so the shell can tell it runs inside the app before its first paint.
class MainViewController: CAPBridgeViewController {

    override func capacitorDidLoad() {
        super.capacitorDidLoad()
        guard let url = Bundle.main.url(forResource: "in-app", withExtension: "js", subdirectory: "public"),
              let source = try? String(contentsOf: url, encoding: .utf8) else {
            NSLog("[zaelar] in-app.js missing from the bundle")
            return
        }
        let script = WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        webView?.configuration.userContentController.addUserScript(script)
    }
}
