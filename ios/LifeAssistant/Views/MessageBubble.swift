import SwiftUI
import UIKit

struct MessageBubble: View {

    let message: ChatMessage
    var onOpenCards: ([ResultCard]) -> Void

    var body: some View {
        switch message.role {
        case .user:
            userBubble
        case .assistant:
            assistantBubble
        case .cards(let cards):
            cardsBubble(cards)
        }
    }

    // MARK: - 用户

    private var userBubble: some View {
        HStack {
            Spacer(minLength: 52)
            VStack(alignment: .trailing, spacing: 7) {
                if let data = message.thumbnail, let image = UIImage(data: data) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 148, height: 148)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .strokeBorder(Palette.accentDeep.opacity(0.25), lineWidth: 0.8)
                        )
                }
                Text(message.text)
                    .font(Typeface.body(16))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 15)
                    .padding(.vertical, 11)
                    .background(
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(
                                LinearGradient(
                                    colors: [Palette.accent, Palette.accentDeep],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                    )
                if let label = message.locationLabel {
                    Label(label, systemImage: "location.fill")
                        .font(Typeface.body(11))
                        .foregroundStyle(Palette.inkTertiary)
                        .lineLimit(1)
                        .padding(.trailing, 2)
                }
            }
        }
    }

    // MARK: - 助手

    private var assistantBubble: some View {
        HStack {
            VStack(alignment: .leading, spacing: 0) {
                markdownText(message.text)
                    .font(Typeface.body(15.5))
                    .foregroundStyle(Palette.ink)
                    .padding(.horizontal, 15)
                    .padding(.vertical, 12)
            }
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Palette.hairline, lineWidth: 0.8)
            )
            .shadow(color: Palette.shadow.opacity(0.6), radius: 8, x: 0, y: 3)
            Spacer(minLength: 40)
        }
    }

    // MARK: - 带卡片的结果

    private func cardsBubble(_ cards: [ResultCard]) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 11) {
                markdownText(message.text)
                    .font(Typeface.body(15.5))
                    .foregroundStyle(Palette.ink)

                if !cards.isEmpty {
                    Button {
                        onOpenCards(cards)
                    } label: {
                        HStack(spacing: 7) {
                            Image(systemName: cardSymbol(cards))
                                .font(.system(size: 12, weight: .bold))
                            Text(cards.count > 1 ? "查看 \(cards.count) 张卡片" : "查看卡片")
                                .font(Typeface.body(13, .semibold))
                            Image(systemName: "chevron.up")
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(Palette.accentDeep)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .background(
                            Capsule().fill(Palette.accentSoft)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 15)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous).fill(Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Palette.accent.opacity(0.22), lineWidth: 1)
            )
            .shadow(color: Palette.shadow.opacity(0.6), radius: 8, x: 0, y: 3)

            Spacer(minLength: 40)
        }
    }

    // MARK: - 辅助

    private func cardSymbol(_ cards: [ResultCard]) -> String {
        switch cards.first?.type {
        case .placeList: "list.bullet.rectangle.fill"
        case .route: "arrow.triangle.turn.up.right.diamond.fill"
        case .imageAnalysis: "text.viewfinder"
        default: "rectangle.on.rectangle"
        }
    }

    /// 后端会在文本里用 **强调**，交给 SwiftUI 的 markdown 解析渲染
    private func markdownText(_ raw: String) -> Text {
        if let attributed = try? AttributedString(
            markdown: raw,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            return Text(attributed)
        }
        return Text(raw)
    }
}
