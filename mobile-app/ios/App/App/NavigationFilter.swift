import Capacitor
import WebKit

/// Sits between the WebView and Capacitor's `WebViewDelegationHandler` as the navigation delegate. Every message is
/// passed on untouched except two, where Capacitor would show the bundled error page (`server.errorPath`) when it
/// should not, or would not when it should:
///
///   · a load that FAILED because another navigation replaced it (`NSURLErrorCancelled`, -999) or because a policy
///     decision stopped it (WebKit 102, e.g. a link handed to Safari) is not an error: the page that replaced it is
///     already on its way. Capacitor 7 loads `errorPath` for any `didFail` / `didFailProvisionalNavigation`.
///   · a main-frame answer of 502, 503 or 504 means the engine's origin is up but what is behind it is not answering
///     yet (an engine still starting). It gets the bundled page, which retries on its own — the same as Android
///     (`GatewayErrorWebViewClient`). Every other HTTP status is a page the engine meant to show, and is shown.
///
/// The WebView holds its navigation delegate weakly: `MainViewController` keeps this object alive.
final class NavigationFilter: NSObject, WKNavigationDelegate {
    private weak var inner: WebViewDelegationHandler?
    private let errorURL: URL?

    static let gatewayStatuses: Set<Int> = [502, 503, 504]

    init(inner: WebViewDelegationHandler, errorURL: URL?) {
        self.inner = inner
        self.errorURL = errorURL
    }

    /// True for a failure that only means "this load was superseded or stopped on purpose".
    static func isSuperseded(_ error: Error) -> Bool {
        let e = error as NSError
        if e.domain == NSURLErrorDomain && e.code == NSURLErrorCancelled { return true }
        if e.domain == "WebKitErrorDomain" && e.code == 102 { return true }   // frame load interrupted by policy change
        return false
    }

    // MARK: - Forwarding: everything this class does not implement goes to Capacitor's handler as it is.

    override func responds(to aSelector: Selector!) -> Bool {
        super.responds(to: aSelector) || (inner?.responds(to: aSelector) ?? false)
    }

    override func forwardingTarget(for aSelector: Selector!) -> Any? {
        (inner?.responds(to: aSelector) ?? false) ? inner : nil
    }

    // MARK: - The filtered messages

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if navigationResponse.isForMainFrame,
           let http = navigationResponse.response as? HTTPURLResponse,
           Self.gatewayStatuses.contains(http.statusCode),
           let errorURL {
            NSLog("[zaelar] main frame answered \(http.statusCode): showing the retry page")
            decisionHandler(.cancel)
            webView.load(URLRequest(url: errorURL))
            return
        }
        decisionHandler(.allow)
    }

    // swiftlint:disable:next implicitly_unwrapped_optional
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        if Self.isSuperseded(error) { return }
        inner?.webView(webView, didFail: navigation, withError: error)
    }

    // swiftlint:disable:next implicitly_unwrapped_optional
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if Self.isSuperseded(error) { return }
        inner?.webView(webView, didFailProvisionalNavigation: navigation, withError: error)
    }
}
