import AVFoundation
import Foundation
import Observation
import Speech

/// 语音输入 + 语音播报。
///
/// 关键点：
/// 1. 录音（.record）与播报（.playback）会争抢 AVAudioSession，所有切换收敛在 `activate(_:)` 里。
/// 2. 授权检查必须排在 `recognizer.isAvailable` 之前——未授权时可用性也会是 false，顺序反了会误报「设备不支持」。
/// 3. 首次点麦克风才申请权限，避免 App 一启动连弹三个授权框。
@MainActor
@Observable
final class SpeechService: NSObject {

    enum Listening: Equatable {
        case idle
        case active
        case denied(String)
        case failed(String)
    }

    private(set) var listening: Listening = .idle
    /// 实时识别结果，用于输入框的预览
    private(set) var liveTranscript = ""
    private(set) var isSpeaking = false
    /// 用户可在设置里关掉自动播报
    var autoSpeak = true

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
    private let audioEngine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()

    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var isRecording = false
    private var usedOnDevice = false
    private var retriedWithoutOnDevice = false
    /// 用户点了麦克风但权限还没谈完，谈完自动起录
    private var pendingStart = false
    /// 每次会话递增，用来丢弃已作废任务的迟到回调
    private var generation = 0

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    // MARK: - 授权（按需调用）

    func prepare() {
        SFSpeechRecognizer.requestAuthorization { [weak self] _ in
            Task { @MainActor [weak self] in self?.maybeAutoStart() }
        }
        AVAudioApplication.requestRecordPermission { [weak self] _ in
            Task { @MainActor [weak self] in self?.maybeAutoStart() }
        }
    }

    /// 语音识别与麦克风是两个独立授权框，两个都到位后才自动起录。
    /// 只拿到一个就贸然启动会撞上麦克风未授权，用户看到的又是「按了没反应」。
    private func maybeAutoStart() {
        guard pendingStart else { return }
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else { return }
        guard AVAudioApplication.shared.recordPermission == .granted else { return }
        pendingStart = false
        startListening()
    }

    // MARK: - 语音输入

    func startListening() {
        guard !isRecording else { return }
        guard let recognizer else {
            listening = .failed("当前设备不支持中文语音识别")
            return
        }

        // 授权状态优先判断
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            pendingStart = false
            break
        case .denied, .restricted:
            pendingStart = false
            listening = .denied("语音识别未授权，请到「设置 → 隐私与安全性 → 语音识别」开启")
            return
        default:
            pendingStart = true
            prepare()
            return
        }

        guard recognizer.isAvailable else {
            listening = .failed("语音识别服务暂不可用，稍后再试")
            return
        }

        stopSpeaking()
        liveTranscript = ""
        begin(recognizer: recognizer, onDevice: recognizer.supportsOnDeviceRecognition)
    }

    private func begin(recognizer: SFSpeechRecognizer, onDevice: Bool) {
        teardownSession()
        generation &+= 1
        let current = generation
        usedOnDevice = onDevice
        retriedWithoutOnDevice = false

        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.taskHint = .dictation
        req.requiresOnDeviceRecognition = onDevice
        request = req

        do {
            try activate(.record)
            let input = audioEngine.inputNode
            let format = input.outputFormat(forBus: 0)
            input.removeTap(onBus: 0)
            input.installTap(onBus: 0, bufferSize: 2048, format: format) { buffer, _ in
                req.append(buffer)
            }
            audioEngine.prepare()
            try audioEngine.start()
        } catch {
            teardownSession()
            listening = .failed("麦克风启动失败：\(error.localizedDescription)")
            return
        }

        isRecording = true
        listening = .active

        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            Task { @MainActor [weak self] in
                guard let self, self.generation == current, self.isRecording else { return }

                if let result {
                    self.liveTranscript = result.bestTranscription.formattedString
                    if result.isFinal { self.finishListening() }
                    return
                }

                guard let error else { return }

                // 设备支持端上识别但中文语音模型尚未下载时，请求会立刻失败。
                // 这时退回联网识别重试一次，用户侧只感觉慢了一点。
                if self.usedOnDevice, !self.retriedWithoutOnDevice {
                    self.retriedWithoutOnDevice = true
                    let carried = self.liveTranscript
                    self.begin(recognizer: recognizer, onDevice: false)
                    self.liveTranscript = carried
                    return
                }

                self.finishListening(failure: error.localizedDescription)
            }
        }
    }

    /// 结束录音并返回最终文本
    @discardableResult
    func stopListening() -> String {
        guard isRecording else { return liveTranscript }
        let text = liveTranscript
        finishListening()
        return text
    }

    func cancelListening() {
        liveTranscript = ""
        finishListening()
    }

    private func finishListening(failure: String? = nil) {
        generation &+= 1
        teardownSession()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)

        if let failure, liveTranscript.isEmpty {
            listening = .failed(failure)
        } else {
            // 识别到了内容就不报错，交给用户判断要不要改
            listening = .idle
        }
    }

    private func teardownSession() {
        isRecording = false
        task?.cancel()
        task = nil
        request?.endAudio()
        request = nil
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
    }

    // MARK: - 语音播报

    func speak(_ text: String, force: Bool = false) {
        let cleaned = Self.sanitize(text)
        guard !cleaned.isEmpty else { return }
        guard autoSpeak || force else { return }

        if isRecording { finishListening() }

        let utterance = AVSpeechUtterance(string: cleaned)
        utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
        utterance.rate = 0.50
        utterance.pitchMultiplier = 1.0
        utterance.postUtteranceDelay = 0.1

        do {
            try activate(.playback)
        } catch {
            listening = .failed("音频通道占用：\(error.localizedDescription)")
            return
        }
        isSpeaking = true
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking {
            synthesizer.stopSpeaking(at: .immediate)
        }
        isSpeaking = false
    }

    // MARK: - Session

    private enum Channel { case record, playback }

    private func activate(_ channel: Channel) throws {
        let session = AVAudioSession.sharedInstance()
        switch channel {
        case .record:
            try session.setCategory(.record, mode: .measurement, options: [.duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        case .playback:
            try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        }
    }

    /// 去掉 markdown 记号与大段数字串，让 TTS 读起来自然
    private static func sanitize(_ text: String) -> String {
        var s = text
        s = s.replacingOccurrences(of: "**", with: "")
        s = s.replacingOccurrences(of: "##", with: "")
        s = s.replacingOccurrences(of: "`", with: "")
        s = s.replacingOccurrences(of: "- ", with: "")
        s = s.replacingOccurrences(of: "\n", with: "。")
        s = s.replacingOccurrences(of: "。。", with: "。")
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - AVSpeechSynthesizerDelegate

extension SpeechService: AVSpeechSynthesizerDelegate {

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            self?.isSpeaking = false
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            self?.isSpeaking = false
        }
    }
}
