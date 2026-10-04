import Foundation
import Observation
import SwiftUI
import UIKit

/// 聊天编排：消息流、请求分发、卡片舞台、语音联动。
@MainActor
@Observable
final class ChatViewModel {

    // 聊天
    var messages: [ChatMessage] = []
    var input = ""
    var isWorking = false
    var errorBanner: String?

    // 卡片舞台（界面中间的弹窗）
    struct StageItem: Identifiable {
        let id = UUID()
        let card: ResultCard
    }
    private(set) var stage: [StageItem] = []
    var stageIndex = 0
    var isStageVisible = false

    // 依赖
    let location = LocationService()
    let speech = SpeechService()
    private let api: APIClient

    // 后端地址设置
    var serverAddressDraft = ServerSettings.rawValue
    var serverCheckResult: String?
    var isCheckingServer = false
    private(set) var serverIsCustomized = ServerSettings.isCustomized

    private let sessionId = UUID().uuidString
    /// 上一轮出现过的地点，供「去第一个」这类指代消解
    private var recentPlaces: [String] = []
    private var pendingTask: Task<Void, Never>?

    init(api: APIClient = .shared) {
        self.api = api
        messages = [
            ChatMessage(role: .assistant,
                        text: "我是你的生活助手。可以直接问我怎么走、附近有什么，也可以拍张照片给我看。")
        ]
    }

    // MARK: - 后端地址

    func saveServerAddress() {
        guard ServerSettings.save(serverAddressDraft) != nil else {
            serverCheckResult = "地址格式不对，示例：http://192.168.1.20:8000"
            return
        }
        serverAddressDraft = ServerSettings.rawValue
        serverIsCustomized = ServerSettings.isCustomized
        serverCheckResult = "已保存，正在测试连接…"
        Task { await self.testServerConnection() }
    }

    func testServerConnection() async {
        isCheckingServer = true
        defer { isCheckingServer = false }
        let result = await api.healthCheck()
        serverCheckResult = result.ok ? result.message : "连接失败：" + result.message
    }

    func resetServerAddress() {
        ServerSettings.reset()
        serverAddressDraft = ServerSettings.rawValue
        serverIsCustomized = ServerSettings.isCustomized
        serverCheckResult = nil
    }

    // MARK: - 生命周期

    func onAppear() {
        // 语音权限等用户第一次点麦克风时再申请，避免一启动连弹三个授权框
        location.requestPermission()
    }

    // MARK: - 发送文字

    func send(_ raw: String? = nil) {
        let text = (raw ?? input).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isWorking else { return }
        input = ""
        speech.stopSpeaking()

        messages.append(ChatMessage(role: .user, text: text, locationLabel: locationLabelOrNil))

        let request = ChatRequest(
            text: text,
            location: currentGeoPoint,
            address: location.label.isEmpty ? nil : location.label,
            citycode: nil,
            sessionId: sessionId,
            contextHint: recentPlaces.isEmpty ? nil : recentPlaces.joined(separator: "、")
        )

        isWorking = true
        pendingTask = Task { [weak self] in
            guard let self else { return }
            defer { self.isWorking = false }
            do {
                let response = try await self.api.chat(request)
                self.consume(response.reply, cards: response.cards, speech: response.speech)
            } catch is CancellationError {
                return
            } catch {
                self.fail(error)
            }
        }
    }

    // MARK: - 发送图片

    func sendImage(_ image: UIImage, question: String) {
        guard !isWorking else { return }
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        speech.stopSpeaking()
        errorBanner = nil

        messages.append(ChatMessage(
            role: .user,
            text: trimmed.isEmpty ? "看看这张照片" : trimmed,
            locationLabel: locationLabelOrNil,
            thumbnail: ImagePipeline.thumbnail(image)
        ))

        isWorking = true
        pendingTask = Task { [weak self] in
            guard let self else { return }
            defer { self.isWorking = false }

            // 端上 OCR 与压缩可以并行，省掉一次串行等待
            async let ocrText = ImagePipeline.recognizeText(in: image)
            let compressed = ImagePipeline.compressed(image)
            let ocr = await ocrText

            guard let data = compressed else {
                self.fail(AssistantError.decoding("图片压缩失败"))
                return
            }

            do {
                let response = try await self.api.analyzeImage(
                    imageData: data,
                    question: trimmed,
                    clientOCRText: ocr.isEmpty ? nil : ocr,
                    location: self.currentGeoPoint,
                    address: self.location.label.isEmpty ? nil : self.location.label,
                    citycode: nil,
                    sessionId: self.sessionId
                )
                self.consume(response.reply, cards: response.cards, speech: response.speech)
            } catch is CancellationError {
                return
            } catch {
                self.fail(error)
            }
        }
    }

    // MARK: - 语音输入

    func toggleVoiceInput() {
        switch speech.listening {
        case .active:
            let text = speech.stopListening()
            if !text.trimmingCharacters(in: .whitespaces).isEmpty { input = text }
        case .idle, .denied, .failed:
            speech.stopSpeaking()
            speech.startListening()   // 首次会自动走权限申请，拿到后直接开录
        }
    }

    func speakLast() {
        guard let last = messages.last(where: { if case .assistant = $0.role { return true } else { return false } })
        else { return }
        speech.speak(last.text, force: true)
    }

    func cancelWork() {
        pendingTask?.cancel()
        pendingTask = nil
        isWorking = false
    }

    // MARK: - 卡片舞台

    /// 从气泡上的「查看卡片」按钮重新打开结果
    func openStage(_ cards: [ResultCard]) {
        guard !cards.isEmpty else { return }
        stage = cards.map { StageItem(card: $0) }
        stageIndex = 0
        withAnimation(.spring(response: 0.46, dampingFraction: 0.78)) {
            isStageVisible = true
        }
    }

    func dismissStage() {
        isStageVisible = false
        // 等退场动画走完再清空，避免卡片在缩小时闪现空内容
        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(280))
            guard let self, !self.isStageVisible else { return }
            self.stage = []
            self.stageIndex = 0
        }
    }

    func moveStage(by delta: Int) {
        guard !stage.isEmpty else { return }
        stageIndex = min(max(stageIndex + delta, 0), stage.count - 1)
    }

    // MARK: - 内部

    private func consume(_ reply: String, cards: [ResultCard], speech spokenText: String?) {
        messages.append(ChatMessage(role: .cards(cards), text: reply))

        if !cards.isEmpty {
            openStage(cards)
        }

        recentPlaces = cards
            .flatMap(\.places)
            .prefix(5)
            .map(\.name)

        let toSpeak = spokenText ?? reply
        if !cards.isEmpty || !toSpeak.isEmpty {
            speech.speak(toSpeak)
        }
    }

    private func fail(_ error: Error) {
        let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        errorBanner = message
        messages.append(ChatMessage(role: .assistant, text: "出了点问题：\(message)"))
    }

    private var currentGeoPoint: GeoPoint? {
        guard let coordinate = location.coordinate else { return nil }
        return GeoPoint(latitude: coordinate.latitude,
                        longitude: coordinate.longitude,
                        accuracyM: location.accuracyM)
    }

    private var locationLabelOrNil: String? {
        location.label.isEmpty ? nil : location.label
    }
}
