import Capacitor
import CoreBluetooth
import CoreLocation
import CoreMotion
import UIKit

/// The device bridge (V2-890): the phone's sensors as ONE first-party plugin the engine's shell talks to.
///
/// Two calls matter:
///   · `capabilities()` — what THIS device can do right now (hardware present, permission state). The engine reads it
///     once per session and tells the agent, so nothing ever asks for a sensor the device does not have.
///   · `startSession({ sensors, background })` — an activity the person started (a ride, a run, a walk, a drive).
///     Samples are buffered here, natively, so they keep coming with the screen locked: iOS freezes the WebView in
///     the background, never this code. The shell drains the buffer with `drain()` and also receives each sample as a
///     `sample` event while it is awake.
///
/// Design rules:
///   · Nothing starts by itself. Every sensor runs only inside a session the person asked for, and stops with it.
///   · Background location runs only inside such a session and always shows the system's blue indicator
///     (`showsBackgroundLocationIndicator`). It needs When-In-Use only, never Always.
///   · Heart rate is read from the standard Bluetooth Heart Rate Service (GATT 0x180D, measurement 0x2A37), which chest
///     straps and watches in "broadcast heart rate" mode expose. No vendor SDK, no HealthKit.
///   · Generated user apps never call this plugin. Only the shell's own code does, and an app receives the values
///     the engine hands it (see the module doc `zaelar-device-bridge.md`).
@objc(DevicePlugin)
public class DevicePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "DevicePlugin"
    public let jsName = "ZaelarDevice"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "capabilities", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startSession", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stopSession", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getSession", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "drain", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "scanHeartRate", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "forgetHeartRate", returnType: CAPPluginReturnPromise),
    ]

    static let knownSensors: Set<String> = ["location", "heart_rate", "motion_activity", "altitude"]
    static let bufferLimit = 20_000            // ~5.5 h of 1 Hz samples from four sensors; oldest dropped first
    static let savedStrapKey = "zaelar.device.heartRateStrap"

    private let location = CLLocationManager()
    private let activity = CMMotionActivityManager()
    private let altimeter = CMAltimeter()
    private var central: CBCentralManager?
    private var strap: CBPeripheral?
    private var scanCall: CAPPluginCall?
    private var seenStraps: [String: String] = [:]

    private var session: [String: Any]?        // { id, sensors, background, startedAt }
    private var buffer: [[String: Any]] = []
    private var seq = 0
    private let lock = NSLock()

    override public func load() {
        location.delegate = self
    }

    // MARK: capabilities

    @objc func capabilities(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let device = UIDevice.current
            let bt: String
            switch CBManager.authorization {
            case .allowedAlways: bt = "granted"
            case .denied, .restricted: bt = "denied"
            default: bt = "not_asked"
            }
            call.resolve([
                "platform": "ios",
                "form": device.userInterfaceIdiom == .pad ? "tablet" : "phone",
                "os_version": device.systemVersion,
                "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
                "app_build": Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "",
                "background_sessions": true,
                "sensors": [
                    "location": ["available": CLLocationManager.locationServicesEnabled(),
                                 "permission": Self.locationPermission(self.location.authorizationStatus),
                                 "background": true],
                    "heart_rate": ["available": true, "permission": bt, "via": "bluetooth_hrs",
                                   "saved_strap": UserDefaults.standard.string(forKey: Self.savedStrapKey) != nil],
                    "motion_activity": ["available": CMMotionActivityManager.isActivityAvailable(),
                                        "permission": Self.motionPermission()],
                    "altitude": ["available": CMAltimeter.isRelativeAltitudeAvailable(),
                                 "permission": Self.motionPermission()],
                    "haptics": ["available": device.userInterfaceIdiom == .phone],
                    "microphone": ["available": true],
                    "camera": ["available": false],          // no feature uses it yet: no permission sentence shipped
                    "push": ["available": false],            // needs APNs + the cloud sender (INI-057)
                ],
            ])
        }
    }

    // MARK: session

    @objc func startSession(_ call: CAPPluginCall) {
        let asked = Set(call.getArray("sensors", String.self) ?? [])
        let sensors = asked.intersection(Self.knownSensors)
        if sensors.isEmpty {
            call.reject("no known sensor requested", "NO_SENSORS")
            return
        }
        let background = call.getBool("background") ?? true
        DispatchQueue.main.async {
            self.stopAll()
            let id = UUID().uuidString
            self.session = ["id": id, "sensors": Array(sensors).sorted(), "background": background,
                            "started_at": Date().timeIntervalSince1970 * 1000,
                            "label": call.getString("label") ?? ""]
            if sensors.contains("location") { self.startLocation(background: background,
                                                                 activity: call.getString("activity") ?? "fitness") }
            if sensors.contains("motion_activity") { self.startActivity() }
            if sensors.contains("altitude") { self.startAltitude() }
            if sensors.contains("heart_rate") { self.startHeartRate() }
            self.notifyListeners("session", data: ["state": "started", "session": self.session ?? [:]])
            call.resolve(["session": self.session ?? [:]])
        }
    }

    @objc func stopSession(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let ended = self.session
            self.stopAll()
            self.notifyListeners("session", data: ["state": "stopped", "session": ended ?? [:]])
            call.resolve(["session": ended ?? [:]])
        }
    }

    @objc func getSession(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            call.resolve(["session": self.session as Any, "buffered": self.bufferCount(),
                          "heart_rate_connected": self.strap?.state == .connected])
        }
    }

    /// Returns the samples after `after` (a sequence number) and forgets the ones the caller confirms with it.
    @objc func drain(_ call: CAPPluginCall) {
        let after = call.getInt("after") ?? -1
        let limit = max(1, min(call.getInt("limit") ?? 2000, 5000))
        lock.lock()
        buffer.removeAll { ($0["seq"] as? Int ?? 0) <= after }
        let out = Array(buffer.prefix(limit))
        let more = buffer.count > out.count
        lock.unlock()
        call.resolve(["samples": out, "more": more])
    }

    private func stopAll() {
        location.stopUpdatingLocation()
        location.allowsBackgroundLocationUpdates = false
        activity.stopActivityUpdates()
        altimeter.stopRelativeAltitudeUpdates()
        if let strap { central?.cancelPeripheralConnection(strap) }
        central?.stopScan()
        session = nil
    }

    private func record(_ kind: String, _ values: [String: Any], at date: Date = Date()) {
        lock.lock()
        seq += 1
        var sample = values
        sample["kind"] = kind
        sample["seq"] = seq
        sample["t"] = Int(date.timeIntervalSince1970 * 1000)
        buffer.append(sample)
        if buffer.count > Self.bufferLimit { buffer.removeFirst(buffer.count - Self.bufferLimit) }
        lock.unlock()
        if UIApplication.shared.applicationState == .active { notifyListeners("sample", data: sample) }
    }

    private func bufferCount() -> Int { lock.lock(); defer { lock.unlock() }; return buffer.count }

    // MARK: location

    private func startLocation(background: Bool, activity kind: String) {
        location.desiredAccuracy = kCLLocationAccuracyBest
        location.distanceFilter = 5
        location.activityType = kind == "driving" ? .automotiveNavigation : .fitness
        location.pausesLocationUpdatesAutomatically = false
        if location.authorizationStatus == .notDetermined { location.requestWhenInUseAuthorization() }
        // Background only inside a session, and always with the blue indicator: the person sees it is running.
        location.allowsBackgroundLocationUpdates = background
        location.showsBackgroundLocationIndicator = true
        location.startUpdatingLocation()
    }

    static func locationPermission(_ s: CLAuthorizationStatus) -> String {
        switch s {
        case .authorizedWhenInUse, .authorizedAlways: return "granted"
        case .denied, .restricted: return "denied"
        default: return "not_asked"
        }
    }

    // MARK: motion

    static func motionPermission() -> String {
        switch CMMotionActivityManager.authorizationStatus() {
        case .authorized: return "granted"
        case .denied, .restricted: return "denied"
        default: return "not_asked"
        }
    }

    private func startActivity() {
        guard CMMotionActivityManager.isActivityAvailable() else { return }
        activity.startActivityUpdates(to: .main) { [weak self] a in
            guard let a else { return }
            let mode = a.automotive ? "driving" : a.cycling ? "cycling" : a.running ? "running"
                : a.walking ? "walking" : a.stationary ? "stationary" : "unknown"
            let confidence = ["low", "medium", "high"][min(max(a.confidence.rawValue, 0), 2)]
            self?.record("motion_activity", ["mode": mode, "confidence": confidence], at: a.startDate)
        }
    }

    private func startAltitude() {
        guard CMAltimeter.isRelativeAltitudeAvailable() else { return }
        altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] d, _ in
            guard let d else { return }
            self?.record("altitude", ["relative_m": d.relativeAltitude.doubleValue,
                                      "pressure_kpa": d.pressure.doubleValue])
        }
    }

    // MARK: heart rate (Bluetooth Heart Rate Service)

    static let hrService = CBUUID(string: "180D")
    static let hrMeasurement = CBUUID(string: "2A37")

    private func ensureCentral() {
        if central == nil {
            central = CBCentralManager(delegate: self, queue: .main,
                                       options: [CBCentralManagerOptionRestoreIdentifierKey: "zaelar.device.hr"])
        }
    }

    private func startHeartRate() {
        ensureCentral()
        if central?.state == .poweredOn { connectSavedOrScan() }
    }

    private func connectSavedOrScan() {
        guard let central else { return }
        if let saved = UserDefaults.standard.string(forKey: Self.savedStrapKey), let uuid = UUID(uuidString: saved),
           let p = central.retrievePeripherals(withIdentifiers: [uuid]).first {
            connect(p)
            return
        }
        if let p = central.retrieveConnectedPeripherals(withServices: [Self.hrService]).first {
            connect(p)
            return
        }
        central.scanForPeripherals(withServices: [Self.hrService], options: nil)
    }

    private func connect(_ p: CBPeripheral) {
        strap = p
        p.delegate = self
        central?.stopScan()
        central?.connect(p, options: nil)
    }

    /// Lists the straps in range for a few seconds; `{ id }` from the list makes `startSession` pick that one.
    @objc func scanHeartRate(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            if let pick = call.getString("pick") {
                UserDefaults.standard.set(pick, forKey: Self.savedStrapKey)
                call.resolve(["saved": pick])
                return
            }
            self.seenStraps = [:]
            self.scanCall = call
            self.ensureCentral()
            if self.central?.state == .poweredOn {
                self.central?.scanForPeripherals(withServices: [Self.hrService], options: nil)
            }
            let seconds = Double(max(2, min(call.getInt("seconds") ?? 6, 20)))
            DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in
                guard let self, let pending = self.scanCall else { return }
                if self.session == nil || self.strap != nil { self.central?.stopScan() }
                self.scanCall = nil
                pending.resolve(["straps": self.seenStraps.map { ["id": $0.key, "name": $0.value] }])
            }
        }
    }

    @objc func forgetHeartRate(_ call: CAPPluginCall) {
        UserDefaults.standard.removeObject(forKey: Self.savedStrapKey)
        call.resolve()
    }

    /// GATT 0x2A37: flags byte; bit0 = 16-bit value; bit3 = energy expended present; bit4 = RR intervals present.
    static func parseHeartRate(_ data: Data) -> (bpm: Int, rr: [Double])? {
        let b = [UInt8](data)
        guard b.count >= 2 else { return nil }
        let flags = b[0]
        var i = 1
        let bpm: Int
        if flags & 0x01 != 0 {
            guard b.count >= 3 else { return nil }
            bpm = Int(b[1]) | Int(b[2]) << 8
            i = 3
        } else {
            bpm = Int(b[1])
            i = 2
        }
        if flags & 0x08 != 0 { i += 2 }
        var rr: [Double] = []
        if flags & 0x10 != 0 {
            while i + 1 < b.count {
                rr.append(Double(Int(b[i]) | Int(b[i + 1]) << 8) / 1024.0 * 1000.0)   // 1/1024 s → ms
                i += 2
            }
        }
        return (bpm, rr)
    }
}

extension DevicePlugin: CLLocationManagerDelegate {
    public func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard session != nil else { return }
        for l in locations where l.horizontalAccuracy >= 0 {
            var v: [String: Any] = ["lat": l.coordinate.latitude, "lon": l.coordinate.longitude,
                                    "accuracy_m": l.horizontalAccuracy]
            if l.verticalAccuracy >= 0 { v["altitude_m"] = l.altitude }
            if l.speed >= 0 { v["speed_mps"] = l.speed }
            if l.course >= 0 { v["course_deg"] = l.course }
            record("location", v, at: l.timestamp)
        }
    }

    public func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        NSLog("[zaelar] location: \(error.localizedDescription)")
    }

    public func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        notifyListeners("permission", data: ["sensor": "location",
                                             "permission": Self.locationPermission(manager.authorizationStatus)])
    }
}

extension DevicePlugin: CBCentralManagerDelegate, CBPeripheralDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        notifyListeners("permission", data: ["sensor": "heart_rate",
                                             "permission": central.state == .unauthorized ? "denied" : "granted",
                                             "bluetooth_on": central.state == .poweredOn])
        guard central.state == .poweredOn else { return }
        if scanCall != nil { central.scanForPeripherals(withServices: [Self.hrService], options: nil) }
        if let s = session, (s["sensors"] as? [String] ?? []).contains("heart_rate"), strap == nil {
            connectSavedOrScan()
        }
    }

    public func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        if let p = (dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral])?.first {
            strap = p
            p.delegate = self
        }
    }

    public func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                               advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let name = peripheral.name ?? (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? "Heart rate"
        if scanCall != nil {
            seenStraps[peripheral.identifier.uuidString] = name
            return
        }
        if session != nil, strap == nil { connect(peripheral) }
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        UserDefaults.standard.set(peripheral.identifier.uuidString, forKey: Self.savedStrapKey)
        notifyListeners("heart_rate_strap", data: ["state": "connected", "name": peripheral.name ?? ""])
        peripheral.discoverServices([Self.hrService])
    }

    public func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                               error: Error?) {
        notifyListeners("heart_rate_strap", data: ["state": "disconnected", "name": peripheral.name ?? ""])
        // A strap that drops mid-ride (out of range, sweat on the contacts) is reconnected as soon as it is back.
        if session != nil { central.connect(peripheral, options: nil) }
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        for s in peripheral.services ?? [] where s.uuid == Self.hrService {
            peripheral.discoverCharacteristics([Self.hrMeasurement], for: s)
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                           error: Error?) {
        for c in service.characteristics ?? [] where c.uuid == Self.hrMeasurement {
            peripheral.setNotifyValue(true, for: c)
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard session != nil, let data = characteristic.value, let hr = Self.parseHeartRate(data) else { return }
        var v: [String: Any] = ["bpm": hr.bpm]
        if !hr.rr.isEmpty { v["rr_ms"] = hr.rr }
        record("heart_rate", v)
    }
}
