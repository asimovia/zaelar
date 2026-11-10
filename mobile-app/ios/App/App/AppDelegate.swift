import AVFoundation
import Capacitor
import UIKit

/// The app is one full-screen WKWebView (Capacitor's bridge view controller) showing the engine's `/m` shell.
/// Native code here is limited to the phone's "hands"; today that is the audio session for in-WebView voice.
@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        configureAudioSession()
        return true
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Another app (a call, music) may have taken the session while we were away: claim it again on foreground.
        configureAudioSession()
    }

    /// Voice v1 runs inside the WebView (WebRTC). Without this the session stays `soloAmbient`: the agent's voice
    /// comes out of the earpiece at call volume once the mic opens, and Bluetooth headsets are ignored.
    /// `voiceChat` turns on the system echo cancellation, which a hands-free voice agent needs.
    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setActive(true)
        } catch {
            NSLog("[zaelar] audio session not configured: \(error)")
        }
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }
}
