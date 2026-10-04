import SwiftUI
import UIKit

struct ChatView: View {

    @State private var vm = ChatViewModel()
    @State private var sourceDialog = false
    @State private var showCamera = false
    @State private var showLibrary = false
    @State private var showServerSheet = false
    /// 待确认的图片：先让用户补一句问题，再发出去
    @State private var pendingImage: UIImage?

    var body: some View {
        // @Observable 对象的属性绑定需要 @Bindable 投影
        @Bindable var vm = vm

        ZStack {
            CanvasBackground()

            VStack(spacing: 0) {
                transcript
            }
            .safeAreaInset(edge: .top, spacing: 0) { header }
            .safeAreaInset(edge: .bottom, spacing: 0) { composer }

            if vm.isStageVisible {
                CardStage(
                    items: vm.stage,
                    index: $vm.stageIndex,
                    onClose: { vm.dismissStage() }
                )
                .zIndex(20)
                .transition(.asymmetric(
                    insertion: .opacity.combined(with: .scale(scale: 0.94, anchor: .center)),
                    removal: .opacity.combined(with: .scale(scale: 0.98, anchor: .center))
                ))
            }
        }
        .animation(.spring(response: 0.42, dampingFraction: 0.82), value: vm.isStageVisible)
        .onAppear { vm.onAppear() }
        .confirmationDialog("添加图片", isPresented: $sourceDialog, titleVisibility: .visible) {
            Button("拍照") { showCamera = true }
            Button("从相册选择") { showLibrary = true }
            Button("取消", role: .cancel) {}
        }
        .fullScreenCover(isPresented: $showCamera) {
            CameraPicker { pendingImage = $0 }
                .ignoresSafeArea()
        }
        .sheet(isPresented: $showLibrary) {
            LibraryPicker { pendingImage = $0 }
                .ignoresSafeArea()
        }
        .sheet(isPresented: $showServerSheet) {
            ServerSettingsSheet(vm: vm)
        }
        .sheet(item: Binding(
            get: { pendingImage.map { ImageEnvelope(image: $0) } },
            set: { if $0 == nil { pendingImage = nil } }
        )) { envelope in
            ImageQuestionSheet(image: envelope.image) { question in
                pendingImage = nil
                vm.sendImage(envelope.image, question: question)
            } onCancel: {
                pendingImage = nil
            }
        }
    }

    // MARK: - 顶栏

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle().fill(Palette.accentSoft).frame(width: 38, height: 38)
                Image(systemName: "map.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Palette.accentDeep)
            }

            VStack(alignment: .leading, spacing: 1) {
                Text("生活助手")
                    .font(Typeface.display(17, .bold))
                    .foregroundStyle(Palette.ink)
                HStack(spacing: 5) {
                    Circle()
                        .fill(locationDotColor)
                        .frame(width: 6, height: 6)
                    Text(locationSummary)
                        .font(Typeface.body(11.5))
                        .foregroundStyle(Palette.inkTertiary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 8)

            Button {
                vm.speech.autoSpeak.toggle()
            } label: {
                Image(systemName: vm.speech.autoSpeak ? "speaker.wave.2.fill" : "speaker.slash.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(vm.speech.autoSpeak ? Palette.accentDeep : Palette.inkTertiary)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(vm.speech.autoSpeak ? Palette.accentSoft : Palette.canvasDeep))
            }
            .buttonStyle(.plain)

            Button {
                vm.serverAddressDraft = ServerSettings.rawValue
                vm.serverCheckResult = nil
                showServerSheet = true
            } label: {
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(vm.serverIsCustomized ? Palette.accentDeep : Palette.inkTertiary)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(vm.serverIsCustomized ? Palette.accentSoft : Palette.canvasDeep))
            }
            .buttonStyle(.plain)

            Button {
                vm.location.requestPermission()
            } label: {
                Image(systemName: "location.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Palette.accentDeep)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(Palette.accentSoft))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 12)
        .background(.ultraThinMaterial)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Palette.hairline).frame(height: 0.7)
        }
    }

    private var locationDotColor: Color {
        switch vm.location.status {
        case .ready: Palette.moss
        case .locating: Palette.accent
        case .denied, .failed: Color(red: 0.72, green: 0.24, blue: 0.22)
        case .idle: Palette.inkTertiary
        }
    }

    private var locationSummary: String {
        switch vm.location.status {
        case .ready:
            vm.location.label.isEmpty ? "已定位" : vm.location.label
        case .locating: "定位中…"
        case .denied: "定位被拒绝，点右侧按钮重试"
        case .failed(let message): message
        case .idle: "尚未定位"
        }
    }

    // MARK: - 消息列表

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 14) {
                    ForEach(vm.messages) { message in
                        MessageBubble(message: message) { cards in
                            vm.openStage(cards)
                        }
                        .id(message.id)
                    }

                    if vm.isWorking {
                        TypingIndicator()
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.leading, 4)
                    }

                    Color.clear.frame(height: 1).id(Self.bottomAnchor)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: vm.messages.count) {
                withAnimation(.easeOut(duration: 0.25)) {
                    proxy.scrollTo(Self.bottomAnchor, anchor: .bottom)
                }
            }
            .onChange(of: vm.isWorking) {
                withAnimation(.easeOut(duration: 0.25)) {
                    proxy.scrollTo(Self.bottomAnchor, anchor: .bottom)
                }
            }
        }
    }

    private static let bottomAnchor = "transcript-bottom"

    // MARK: - 输入栏

    private var composer: some View {
        @Bindable var vm = vm
        return ComposerBar(
            text: $vm.input,
            isWorking: vm.isWorking,
            listening: vm.speech.listening,
            liveTranscript: vm.speech.liveTranscript,
            isSpeaking: vm.speech.isSpeaking,
            onAttach: { sourceDialog = true },
            onSend: { vm.send() },
            onToggleVoice: { vm.toggleVoiceInput() },
            onStopSpeaking: { vm.speech.stopSpeaking() }
        )
    }
}

/// 让 UIImage 能作为 sheet(item:) 的绑定载体
private struct ImageEnvelope: Identifiable {
    let id = UUID()
    let image: UIImage
}

/// 拍照/选图后的确认页：让用户在发送前补一句想问什么
private struct ImageQuestionSheet: View {
    let image: UIImage
    let onSend: (String) -> Void
    let onCancel: () -> Void

    @State private var question = ""
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 18) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxHeight: 320)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .strokeBorder(Palette.hairline, lineWidth: 0.8)
                    )

                TextField("想问点什么？例如「这个还能吃吗」", text: $question, axis: .vertical)
                    .font(Typeface.body(16))
                    .lineLimit(2...4)
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Palette.canvas)
                    )
                    .focused($focused)

                Spacer(minLength: 0)
            }
            .padding(20)
            .background(Palette.surface)
            .navigationTitle("分析图片")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { onCancel() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("发送") { onSend(question) }
                        .fontWeight(.semibold)
                }
            }
        }
        .onAppear { focused = true }
    }
}

/// 等待助手响应时的三点呼吸指示
private struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Palette.inkTertiary)
                    .frame(width: 7, height: 7)
                    .opacity(0.35 + 0.55 * pulse(i))
                    .scaleEffect(0.85 + 0.2 * pulse(i))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Palette.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(Palette.hairline, lineWidth: 0.8)
        )
        .onAppear {
            withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
                phase = 1
            }
        }
    }

    private func pulse(_ index: Int) -> Double {
        let shifted = (phase + Double(index) * 0.22).truncatingRemainder(dividingBy: 1.0)
        return sin(shifted * .pi)
    }
}
