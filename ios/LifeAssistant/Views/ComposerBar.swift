import Foundation
import SwiftUI

struct ComposerBar: View {

    @Binding var text: String
    let isWorking: Bool
    let listening: SpeechService.Listening
    let liveTranscript: String
    let isSpeaking: Bool

    var onAttach: () -> Void
    var onSend: () -> Void
    var onToggleVoice: () -> Void
    var onStopSpeaking: () -> Void

    @FocusState private var focused: Bool

    private var isListening: Bool { listening == .active }
    private var canSend: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isWorking }

    var body: some View {
        VStack(spacing: 8) {
            if let notice = microphoneNotice {
                Text(notice)
                    .font(Typeface.body(12))
                    .foregroundStyle(Palette.inkTertiary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 4)
            }

            HStack(alignment: .bottom, spacing: 10) {
                iconButton(system: "camera.fill", tint: Palette.inkSecondary, action: onAttach)
                    .disabled(isWorking)

                inputArea

                if canSend {
                    iconButton(system: "arrow.up", tint: .white, background: Palette.accent, action: onSend)
                        .transition(.scale.combined(with: .opacity))
                } else {
                    iconButton(
                        system: isListening ? "stop.fill" : "mic.fill",
                        tint: isListening ? .white : Palette.inkSecondary,
                        background: isListening ? Color(red: 0.72, green: 0.24, blue: 0.22) : Palette.canvasDeep,
                        action: onToggleVoice
                    )
                    .disabled(isWorking)
                    .transition(.scale.combined(with: .opacity))
                }
            }

            if isSpeaking {
                Button(action: onStopSpeaking) {
                    HStack(spacing: 6) {
                        Image(systemName: "speaker.wave.2.fill").font(.system(size: 11, weight: .bold))
                        Text("正在播报，点击停止").font(Typeface.body(12, .medium))
                    }
                    .foregroundStyle(Palette.accentDeep)
                    .padding(.horizontal, 11)
                    .padding(.vertical, 6)
                    .background(Capsule().fill(Palette.accentSoft))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 8)
        .animation(.easeInOut(duration: 0.2), value: isListening)
        .animation(.easeInOut(duration: 0.2), value: canSend)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle().fill(Palette.hairline).frame(height: 0.7)
        }
    }

    // MARK: - 输入区

    private var inputArea: some View {
        ZStack(alignment: .leading) {
            if isListening {
                HStack(spacing: 10) {
                    WaveformIndicator()
                    Text(liveTranscript.isEmpty ? "正在听…" : liveTranscript)
                        .font(Typeface.body(15.5))
                        .foregroundStyle(liveTranscript.isEmpty ? Palette.inkTertiary : Palette.ink)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .background(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(Palette.accentSoft)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .strokeBorder(Palette.accent.opacity(0.35), lineWidth: 1)
                )
            } else {
                TextField("问点什么，比如「附近有火锅店吗」", text: $text, axis: .vertical)
                    .font(Typeface.body(15.5))
                    .foregroundStyle(Palette.ink)
                    .lineLimit(1...5)
                    .focused($focused)
                    .submitLabel(.send)
                    .onSubmit { if canSend { onSend() } }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(Palette.surface)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .strokeBorder(focused ? Palette.accent.opacity(0.45) : Palette.hairline,
                                          lineWidth: focused ? 1.4 : 0.8)
                    )
            }
        }
        .frame(minHeight: 44)
    }

    private var microphoneNotice: String? {
        switch listening {
        case .denied(let message), .failed(let message): message
        default: nil
        }
    }

    @ViewBuilder
    private func iconButton(
        system: String,
        tint: Color,
        background: Color? = nil,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 44, height: 44)
                .background(Circle().fill(background ?? Palette.canvasDeep))
        }
        .buttonStyle(.plain)
        .contentShape(Circle())
    }
}

/// 录音时的柱状律动
private struct WaveformIndicator: View {
    @State private var level: CGFloat = 0.35

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<4, id: \.self) { i in
                Capsule()
                    .fill(Palette.accent)
                    .frame(width: 3, height: barHeight(i))
            }
        }
        .frame(width: 22)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.42).repeatForever(autoreverses: true)) {
                level = 1.0
            }
        }
    }

    private func barHeight(_ index: Int) -> CGFloat {
        let offsets: [CGFloat] = [0.45, 0.9, 0.65, 1.0]
        return 6 + 12 * offsets[index] * level
    }
}
