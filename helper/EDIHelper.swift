// EDI Helper — vive en la barra de menú de macOS.
//  • Di "Hey EDI" o "EDI" en cualquier momento (reconocimiento de voz de Apple, en el dispositivo cuando se puede).
//  • ⌥ + Espacio para hablarle al instante desde cualquier app.
//  • Burbuja flotante tipo Siri con lo que dices y la respuesta; EDI contesta en voz alta (voz neural del servidor).
// Se compila en tu Mac con scripts/04_instalar_helper.sh (usa swiftc de las Command Line Tools).
import AVFoundation
import Carbon.HIToolbox
import Cocoa
import Speech

let SERVER = "http://127.0.0.1:8765"
let PURPLE = NSColor(calibratedRed: 0.70, green: 0.40, blue: 1.0, alpha: 1)
let WAKE = try! NSRegularExpression(pattern: "\\b(?:(?:hey|oye|ok|ey)\\s+)?(?:edi|eddie|eddy|edy|heidi|e d i)\\b[\\s,.:!]*", options: [])

func fold(_ s: String) -> String {
    s.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "es_MX")).lowercased()
}

// MARK: - Atajo global ⌥ + Espacio (Carbon: no requiere permisos de accesibilidad)
var hotKeyAction: (() -> Void)?
var hotKeyRef: EventHotKeyRef?

func registerHotKey() {
    let id = EventHotKeyID(signature: OSType(0x4544_4921), id: 1)
    RegisterEventHotKey(UInt32(kVK_Space), UInt32(optionKey), id, GetApplicationEventTarget(), 0, &hotKeyRef)
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
        DispatchQueue.main.async { hotKeyAction?() }
        return noErr
    }, 1, &spec, nil, nil)
}

// MARK: - Cliente del servidor de EDI
enum EDIClient {
    static func request(_ path: String, method: String = "GET", json: [String: Any]? = nil, timeout: TimeInterval = 40,
                        done: @escaping (Data?, Int) -> Void) {
        var req = URLRequest(url: URL(string: SERVER + path)!, timeoutInterval: timeout)
        req.httpMethod = method
        if let json = json {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: json)
        }
        URLSession.shared.dataTask(with: req) { data, resp, _ in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            DispatchQueue.main.async { done(data, code) }
        }.resume()
    }

    static func health(_ done: @escaping (Bool) -> Void) {
        request("/api/health", timeout: 3) { _, code in done(code == 200) }
    }
}

// MARK: - Burbuja flotante (estilo Siri, vidrio + morado neón)
final class HUD {
    private let panel: NSPanel
    private let title = NSTextField(labelWithString: "EDI")
    private let label = NSTextField(wrappingLabelWithString: "")
    private let orb = CALayer()
    private var hideWork: DispatchWorkItem?
    private let width: CGFloat = 380

    init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: width, height: 96),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: false)
        panel.level = .statusBar
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]

        let fx = NSVisualEffectView(frame: panel.contentView!.bounds)
        fx.material = .hudWindow
        fx.blendingMode = .behindWindow
        fx.state = .active
        fx.wantsLayer = true
        fx.layer?.cornerRadius = 22
        fx.layer?.masksToBounds = true
        fx.layer?.borderWidth = 1
        fx.layer?.borderColor = PURPLE.withAlphaComponent(0.45).cgColor
        fx.autoresizingMask = [.width, .height]
        panel.contentView = fx

        orb.frame = NSRect(x: 18, y: 32, width: 32, height: 32)
        orb.cornerRadius = 16
        orb.backgroundColor = PURPLE.cgColor
        orb.shadowColor = PURPLE.cgColor
        orb.shadowRadius = 12
        orb.shadowOpacity = 0.9
        orb.shadowOffset = .zero
        fx.layer?.addSublayer(orb)

        title.font = .systemFont(ofSize: 11, weight: .semibold)
        title.textColor = PURPLE
        title.frame = NSRect(x: 64, y: 66, width: width - 80, height: 16)
        fx.addSubview(title)

        label.font = .systemFont(ofSize: 14, weight: .regular)
        label.textColor = .labelColor
        label.maximumNumberOfLines = 5
        label.frame = NSRect(x: 64, y: 12, width: width - 80, height: 52)
        fx.addSubview(label)
    }

    func show(_ text: String, state: String = "EDI", autoHide: TimeInterval? = nil) {
        hideWork?.cancel()
        title.stringValue = state
        label.stringValue = text
        let size = label.cell?.cellSize(forBounds: NSRect(x: 0, y: 0, width: width - 80, height: 400)) ?? NSSize(width: width - 80, height: 40)
        let h = max(96, min(200, size.height + 52))
        label.frame = NSRect(x: 64, y: 14, width: width - 80, height: h - 48)
        title.frame.origin.y = h - 30
        orb.frame.origin.y = h - 50
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            panel.setFrame(NSRect(x: f.maxX - width - 16, y: f.maxY - h - 12, width: width, height: h), display: true)
        }
        pulse(state != "EDI")
        if !panel.isVisible {
            panel.alphaValue = 0
            panel.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup { $0.duration = 0.18; panel.animator().alphaValue = 1 }
        }
        if let t = autoHide { hide(after: t) }
    }

    func hide(after t: TimeInterval = 0) {
        hideWork?.cancel()
        let w = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            NSAnimationContext.runAnimationGroup({ $0.duration = 0.25; self.panel.animator().alphaValue = 0 },
                                                 completionHandler: { self.panel.orderOut(nil) })
        }
        hideWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + t, execute: w)
    }

    private func pulse(_ on: Bool) {
        orb.removeAllAnimations()
        guard on else { return }
        let a = CABasicAnimation(keyPath: "transform.scale")
        a.fromValue = 0.85; a.toValue = 1.12; a.duration = 0.6
        a.autoreverses = true; a.repeatCount = .infinity
        orb.add(a, forKey: "pulse")
    }
}

// MARK: - Voz: palabra clave + comando
final class Voice: NSObject {
    enum Mode { case off, wake, command, busy }
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "es-MX"))
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private(set) var mode: Mode = .off
    private var commandStart = 0          // en caracteres del texto doblado
    private var consumed = 0              // hasta dónde ya se buscó la palabra clave
    private var lastText = ""
    private var silence: Timer?
    private var restart: Timer?
    var wakeEnabled = true
    var onState: ((Mode) -> Void)?
    var onPartial: ((String) -> Void)?
    var onCommand: ((String) -> Void)?
    var onListening: (() -> Void)?

    func authorize(_ done: @escaping (Bool, String?) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            AVCaptureDevice.requestAccess(for: .audio) { mic in
                DispatchQueue.main.async {
                    if status != .authorized { done(false, "Permite el Reconocimiento de voz para EDI Helper en Ajustes del Sistema → Privacidad.") }
                    else if !mic { done(false, "Permite el Micrófono para EDI Helper en Ajustes del Sistema → Privacidad.") }
                    else { done(true, nil) }
                }
            }
        }
    }

    /// Escucha continua esperando "Hey EDI"
    func startWake() {
        guard wakeEnabled else { stop(); return }
        begin(.wake)
    }

    /// Escucha directa de un comando (atajo o menú)
    func startCommand() {
        begin(.command)
        commandStart = 0
        onListening?()
        armSilence(initial: true)
    }

    func stop() {
        silence?.invalidate(); restart?.invalidate()
        task?.cancel(); task = nil
        request?.endAudio(); request = nil
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
        setMode(.off)
    }

    func pauseBusy() { stop(); setMode(.busy) }

    private func setMode(_ m: Mode) { mode = m; onState?(m) }

    private func begin(_ m: Mode) {
        stop()
        guard let recognizer = recognizer, recognizer.isAvailable else {
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in if m == .wake { self?.startWake() } }
            return
        }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        if recognizer.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true }
        req.taskHint = .dictation
        request = req
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else { return }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buf, _ in self?.request?.append(buf) }
        engine.prepare()
        do { try engine.start() } catch { return }
        consumed = 0; lastText = ""
        setMode(m)
        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            DispatchQueue.main.async { self?.handle(result: result, error: error) }
        }
        // El reconocimiento por servidor dura ~1 min: reinicio periódico en modo espera
        restart?.invalidate()
        restart = Timer.scheduledTimer(withTimeInterval: 50, repeats: false) { [weak self] _ in
            if self?.mode == .wake { self?.startWake() }
        }
    }

    private func handle(result: SFSpeechRecognitionResult?, error: Error?) {
        if let result = result {
            let original = result.bestTranscription.formattedString
            let text = fold(original)
            lastText = original
            switch mode {
            case .wake:
                let from = min(consumed, text.count)
                let tail = String(text.dropFirst(from))
                let ns = tail as NSString
                if let m = WAKE.firstMatch(in: tail, range: NSRange(location: 0, length: ns.length)) {
                    let endInTail = tail.distance(from: tail.startIndex, to: Range(m.range, in: tail)!.upperBound)
                    commandStart = from + endInTail
                    consumed = text.count
                    setMode(.command)
                    onListening?()
                    armSilence(initial: true)
                    updateCommand(original)
                } else {
                    consumed = max(0, text.count - 12)   // deja margen para palabras cortadas
                }
            case .command:
                updateCommand(original)
            default: break
            }
            if result.isFinal, mode == .wake { startWake() }
        }
        if error != nil {
            if mode == .wake { DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in self?.startWake() } }
            else if mode == .command { finishCommand() }
        }
    }

    private func updateCommand(_ original: String) {
        let cmd = String(original.dropFirst(min(commandStart, original.count))).trimmingCharacters(in: .whitespacesAndNewlines)
        if !cmd.isEmpty { onPartial?(cmd); armSilence(initial: false) }
    }

    private func armSilence(initial: Bool) {
        silence?.invalidate()
        silence = Timer.scheduledTimer(withTimeInterval: initial ? 7 : 1.5, repeats: false) { [weak self] _ in self?.finishCommand() }
    }

    private func finishCommand() {
        guard mode == .command else { return }
        let cmd = String(lastText.dropFirst(min(commandStart, lastText.count))).trimmingCharacters(in: .whitespacesAndNewlines)
        pauseBusy()
        onCommand?(cmd)
    }
}

// MARK: - App
final class AppDelegate: NSObject, NSApplicationDelegate, AVAudioPlayerDelegate {
    private var item: NSStatusItem!
    private let hud = HUD()
    private let voice = Voice()
    private var player: AVAudioPlayer?
    private var online = false
    private var statusLine: NSMenuItem!
    private var wakeItem: NSMenuItem!
    private var timer: Timer?
    private let defaults = UserDefaults.standard
    private var ediDir: String { Bundle.main.object(forInfoDictionaryKey: "EDIDir") as? String ?? NSHomeDirectory() + "/Documents/GitHub/EDI" }

    func applicationDidFinishLaunching(_ n: Notification) {
        defaults.register(defaults: ["wake": true])
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        setIcon(listening: false)
        buildMenu()

        voice.wakeEnabled = defaults.bool(forKey: "wake")
        voice.onState = { [weak self] m in self?.setIcon(listening: m == .command) }
        voice.onListening = { [weak self] in
            NSSound(named: "Tink")?.play()
            self?.hud.show("Te escucho…", state: "EDI · escuchando")
        }
        voice.onPartial = { [weak self] t in self?.hud.show(t, state: "EDI · escuchando") }
        voice.onCommand = { [weak self] c in self?.ask(c) }

        hotKeyAction = { [weak self] in self?.listenNow() }
        registerHotKey()

        voice.authorize { [weak self] ok, msg in
            guard let self = self else { return }
            if ok { self.voice.startWake() } else { self.hud.show(msg ?? "", state: "EDI · permisos", autoHide: 9) }
        }
        timer = Timer.scheduledTimer(withTimeInterval: 8, repeats: true) { [weak self] _ in self?.checkHealth() }
        checkHealth()
    }

    // ---- barra de menú ----
    private func setIcon(listening: Bool) {
        guard let b = item.button else { return }
        let name = listening ? "waveform.circle.fill" : "waveform.circle"
        b.image = NSImage(systemSymbolName: name, accessibilityDescription: "EDI")
        b.image?.isTemplate = !listening
        b.contentTintColor = listening ? PURPLE : nil
        b.alphaValue = online || listening ? 1 : 0.5
        b.toolTip = online ? "EDI en línea — di “Hey EDI” o ⌥Espacio" : "EDI apagado"
    }

    private func buildMenu() {
        let m = NSMenu()
        statusLine = NSMenuItem(title: "Revisando EDI…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        m.addItem(statusLine)
        m.addItem(.separator())
        let talk = NSMenuItem(title: "Hablar con EDI", action: #selector(listenNow), keyEquivalent: " ")
        talk.keyEquivalentModifierMask = [.option]
        m.addItem(talk)
        wakeItem = NSMenuItem(title: "Responder a “Hey EDI”", action: #selector(toggleWake), keyEquivalent: "")
        wakeItem.state = defaults.bool(forKey: "wake") ? .on : .off
        m.addItem(wakeItem)
        m.addItem(.separator())
        m.addItem(NSMenuItem(title: "Abrir EDI", action: #selector(openUI), keyEquivalent: "o"))
        m.addItem(NSMenuItem(title: "Usar en el celular…", action: #selector(openDevices), keyEquivalent: ""))
        m.addItem(.separator())
        m.addItem(NSMenuItem(title: "Encender servidor", action: #selector(startServer), keyEquivalent: ""))
        m.addItem(NSMenuItem(title: "Apagar servidor", action: #selector(stopServer), keyEquivalent: ""))
        m.addItem(.separator())
        m.addItem(NSMenuItem(title: "Salir de EDI Helper", action: #selector(quit), keyEquivalent: "q"))
        m.items.forEach { $0.target = self }
        item.menu = m
    }

    private func checkHealth() {
        EDIClient.health { [weak self] ok in
            guard let self = self else { return }
            self.online = ok
            self.statusLine.title = ok ? "● EDI en línea" : "○ EDI apagado"
            self.setIcon(listening: self.voice.mode == .command)
        }
    }

    // ---- acciones ----
    @objc func listenNow() {
        player?.stop()
        voice.authorize { [weak self] ok, msg in
            guard let self = self else { return }
            if ok { self.voice.startCommand() } else { self.hud.show(msg ?? "", state: "EDI · permisos", autoHide: 8) }
        }
    }

    @objc func toggleWake() {
        let on = wakeItem.state != .on
        wakeItem.state = on ? .on : .off
        defaults.set(on, forKey: "wake")
        voice.wakeEnabled = on
        if on { voice.startWake() } else if voice.mode == .wake { voice.stop() }
        hud.show(on ? "Listo: di “Hey EDI” cuando me necesites." : "Ya no respondo a “Hey EDI”. Usa ⌥Espacio.", autoHide: 3)
    }

    @objc func openUI() { run("open") }
    @objc func openDevices() { NSWorkspace.shared.open(URL(string: SERVER + "/#/settings/devices")!) }
    @objc func startServer() {
        let app = NSHomeDirectory() + "/Desktop/EDI.app"
        if FileManager.default.fileExists(atPath: app) { NSWorkspace.shared.open(URL(fileURLWithPath: app)) } else { run("start") }
    }
    @objc func stopServer() { run("stop"); hud.show("Apagando EDI…", autoHide: 3) }
    @objc func quit() { NSApp.terminate(nil) }

    private func run(_ cmd: String) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [ediDir + "/scripts/edi.sh", cmd]
        try? p.run()
    }

    // ---- conversación ----
    private func ask(_ text: String) {
        guard !text.isEmpty else { hud.hide(); resume(); return }
        guard online else {
            hud.show("EDI está apagado. Lo estoy encendiendo; vuelve a pedírmelo en un momento.", state: "EDI", autoHide: 6)
            startServer(); resume(); return
        }
        hud.show(text, state: "EDI · pensando")
        var body: [String: Any] = ["text": text]
        let sid = defaults.integer(forKey: "session")
        if sid > 0 { body["session_id"] = sid }
        EDIClient.request("/api/ask", method: "POST", json: body) { [weak self] data, code in
            guard let self = self else { return }
            guard code == 200, let data = data,
                  let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let reply = j["reply"] as? String else {
                self.hud.show("No pude comunicarme con EDI.", state: "EDI", autoHide: 5); self.resume(); return
            }
            if let s = j["session_id"] as? Int { self.defaults.set(s, forKey: "session") }
            self.hud.show(reply, state: "EDI")
            if let action = j["action"] as? [String: Any], let open = action["open"] as? String {
                let tab = action["tab"] as? String ?? ""
                NSWorkspace.shared.open(URL(string: SERVER + "/#/\(open)/\(tab)?new=1")!)
            }
            self.speak(reply)
        }
    }

    private func speak(_ text: String) {
        EDIClient.request("/api/tts", method: "POST", json: ["text": text], timeout: 25) { [weak self] data, code in
            guard let self = self else { return }
            guard code == 200, let data = data, let p = try? AVAudioPlayer(data: data) else {
                self.hud.hide(after: 6); self.resume(); return
            }
            self.player = p
            p.delegate = self
            p.play()
        }
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        hud.hide(after: 2.5)
        resume()
    }

    private func resume() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
            guard let self = self else { return }
            if self.voice.wakeEnabled { self.voice.startWake() } else { self.voice.stop() }
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
