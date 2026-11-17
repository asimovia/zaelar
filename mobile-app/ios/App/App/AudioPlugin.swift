import AVFoundation
import Capacitor

/// The voice's audio as the phone sees it (`window.ZaelarNative.audio`, through `www/in-app.js`): where the sound goes,
/// forcing the loudspeaker, and the events that stop the conversation from outside — a call, Siri, another app.
///
/// What it does NOT do, on purpose: set a level. iOS has no public way to scale what a WKWebView plays, and the system
/// volume is the person's; the agent's voice level is a Web Audio gain inside the page (engine `services/volume.js`).
/// The session's category is set once by `AppDelegate.swift` and driven by WebKit while the page captures; this plugin
/// reads it, overrides only the output port when asked, and never changes its category or activates it.
@objc(AudioPlugin)
public class AudioPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AudioPlugin"
    public let jsName = "ZaelarAudio"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "available", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "route", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "setSpeaker", returnType: CAPPluginReturnPromise),
    ]

    private var speakerForced = false

    override public func load() {
        let center = NotificationCenter.default
        let session = AVAudioSession.sharedInstance()
        center.addObserver(self, selector: #selector(routeChanged(_:)),
                           name: AVAudioSession.routeChangeNotification, object: session)
        center.addObserver(self, selector: #selector(interrupted(_:)),
                           name: AVAudioSession.interruptionNotification, object: session)
        center.addObserver(self, selector: #selector(servicesReset(_:)),
                           name: AVAudioSession.mediaServicesWereResetNotification, object: session)
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    @objc func available(_ call: CAPPluginCall) {
        call.resolve(["available": true, "level": false, "route": true, "speaker": true, "interruptions": true])
    }

    @objc func route(_ call: CAPPluginCall) {
        call.resolve(Self.describe(AVAudioSession.sharedInstance(), forced: speakerForced))
    }

    /// `{on: true}` sends the voice to the loudspeaker even with the earpiece as the session's default; `false` hands
    /// the choice back (a connected headset or AirPods win again). Only meaningful while the session plays and records.
    @objc func setSpeaker(_ call: CAPPluginCall) {
        let on = call.getBool("on") ?? true
        let session = AVAudioSession.sharedInstance()
        do {
            try session.overrideOutputAudioPort(on ? .speaker : .none)
            speakerForced = on
            call.resolve(Self.describe(session, forced: speakerForced))
        } catch {
            call.reject("speaker override refused: \(error.localizedDescription)", "speaker_refused", error,
                        ["category": session.category.rawValue])
        }
    }

    @objc private func routeChanged(_ note: Notification) {
        let raw = (note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt) ?? 0
        let reason = AVAudioSession.RouteChangeReason(rawValue: raw)
        var data = Self.describe(AVAudioSession.sharedInstance(), forced: speakerForced)
        data["reason"] = Self.reasonName(reason)
        notifyListeners("audioRoute", data: data)
    }

    @objc private func interrupted(_ note: Notification) {
        guard let info = note.userInfo, let raw = info[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        var data: [String: Any] = ["phase": type == .began ? "began" : "ended", "t": Date().timeIntervalSince1970 * 1000]
        if type == .ended, let o = info[AVAudioSessionInterruptionOptionKey] as? UInt {
            data["shouldResume"] = AVAudioSession.InterruptionOptions(rawValue: o).contains(.shouldResume)
        }
        if type == .began, let r = info[AVAudioSessionInterruptionReasonKey] as? UInt {
            data["reason"] = r == AVAudioSession.InterruptionReason.builtInMicMuted.rawValue ? "mic_muted" : "default"
        }
        notifyListeners("audioInterruption", data: data)
    }

    @objc private func servicesReset(_ note: Notification) {
        speakerForced = false
        notifyListeners("audioInterruption", data: ["phase": "reset", "t": Date().timeIntervalSince1970 * 1000])
    }

    /// The current output as one word the page can act on, plus what iOS calls it (e.g. «AirPods Pro de Ana»).
    static func describe(_ session: AVAudioSession, forced: Bool) -> [String: Any] {
        let out = session.currentRoute.outputs.first
        return ["output": out.map { outputKind($0.portType) } ?? "none", "name": out?.portName ?? "",
                "input": session.currentRoute.inputs.first.map { outputKind($0.portType) } ?? "none",
                "speakerForced": forced, "category": session.category.rawValue]
    }

    static func outputKind(_ p: AVAudioSession.Port) -> String {
        switch p {
        case .builtInSpeaker: return "speaker"
        case .builtInReceiver: return "earpiece"
        case .builtInMic: return "mic"
        case .bluetoothA2DP, .bluetoothHFP, .bluetoothLE: return "bluetooth"
        case .headphones, .headsetMic: return "headphones"
        case .airPlay: return "airplay"
        case .carAudio: return "car"
        case .usbAudio: return "usb"
        default: return "other"
        }
    }

    static func reasonName(_ r: AVAudioSession.RouteChangeReason?) -> String {
        switch r {
        case .newDeviceAvailable: return "device_added"
        case .oldDeviceUnavailable: return "device_removed"
        case .categoryChange: return "category"
        case .override: return "override"
        case .wakeFromSleep: return "wake"
        case .noSuitableRouteForCategory: return "no_route"
        case .routeConfigurationChange: return "configuration"
        default: return "other"
        }
    }
}
