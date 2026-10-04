import SwiftUI

/// 结果卡片舞台：在聊天界面正中间浮起弹窗，不跳转任何外部 App。
struct CardStage: View {

    let items: [ChatViewModel.StageItem]
    @Binding var index: Int
    let onClose: () -> Void

    @State private var dragOffset: CGFloat = 0

    private var current: ChatViewModel.StageItem? {
        guard items.indices.contains(index) else { return items.first }
        return items[index]
    }

    var body: some View {
        ZStack {
            backdrop

            GeometryReader { proxy in
                VStack(spacing: 12) {
                    if let current {
                        cardShell(current, available: proxy.size)
                    }
                    if items.count > 1 {
                        pager
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.horizontal, 20)
                .padding(.vertical, 40)
            }
        }
        .gesture(swipe)
    }

    // MARK: - 遮罩

    private var backdrop: some View {
        Rectangle()
            .fill(.ultraThinMaterial)
            .overlay(Palette.ink.opacity(0.20))
            .ignoresSafeArea()
            .contentShape(Rectangle())
            .onTapGesture { onClose() }
    }

    // MARK: - 卡片

    private func cardShell(_ item: ChatViewModel.StageItem, available: CGSize) -> some View {
        ZStack(alignment: .topTrailing) {
            ScrollView {
                CardRouter(card: item.card)
                    .padding(20)
            }
            .scrollBounceBehavior(.basedOnSize)
            .background(
                RoundedRectangle(cornerRadius: 26, style: .continuous).fill(Palette.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .strokeBorder(Palette.hairline, lineWidth: 0.8)
            )
            .shadow(color: Palette.shadow, radius: 26, x: 0, y: 16)

            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Palette.inkSecondary)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(Palette.canvasDeep))
            }
            .buttonStyle(.plain)
            .padding(10)
        }
        .frame(maxWidth: min(available.width - 40, 420))
        .frame(maxHeight: available.height * 0.74)
        .id(item.id)
        .transition(.asymmetric(
            insertion: .move(edge: .trailing).combined(with: .opacity),
            removal: .move(edge: .leading).combined(with: .opacity)
        ))
        .offset(x: dragOffset)
        .animation(.spring(response: 0.38, dampingFraction: 0.86), value: index)
    }

    // MARK: - 翻页

    private var pager: some View {
        HStack(spacing: 14) {
            arrowButton(system: "chevron.left", enabled: index > 0) { step(-1) }

            HStack(spacing: 6) {
                ForEach(items.indices, id: \.self) { i in
                    Capsule()
                        .fill(i == index ? Palette.accent : Palette.inkTertiary.opacity(0.4))
                        .frame(width: i == index ? 18 : 6, height: 6)
                        .animation(.spring(response: 0.3, dampingFraction: 0.8), value: index)
                }
            }

            arrowButton(system: "chevron.right", enabled: index < items.count - 1) { step(1) }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(Capsule().fill(Palette.surface.opacity(0.94)))
        .overlay(Capsule().strokeBorder(Palette.hairline, lineWidth: 0.8))
    }

    @ViewBuilder
    private func arrowButton(system: String, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: system)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(enabled ? Palette.ink : Palette.inkTertiary.opacity(0.4))
                .frame(width: 26, height: 26)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    private func step(_ delta: Int) {
        let next = index + delta
        guard items.indices.contains(next) else { return }
        withAnimation(.spring(response: 0.38, dampingFraction: 0.86)) { index = next }
    }

    // MARK: - 手势

    private var swipe: some Gesture {
        DragGesture(minimumDistance: 24)
            .onChanged { value in
                dragOffset = value.translation.width * 0.35
            }
            .onEnded { value in
                let threshold: CGFloat = 56
                if value.translation.width < -threshold {
                    step(1)
                } else if value.translation.width > threshold {
                    step(-1)
                }
                withAnimation(.spring(response: 0.3, dampingFraction: 0.9)) { dragOffset = 0 }
            }
    }
}

/// 按卡片类型分发到具体视图
struct CardRouter: View {
    let card: ResultCard

    var body: some View {
        switch card.type {
        case .placeList:
            PlaceCardView(card: card)
        case .route:
            RouteCardView(card: card)
        case .imageAnalysis:
            ImageAnalysisCardView(card: card)
        case .text:
            TextCardView(card: card)
        }
    }
}

/// 卡片通用头部
struct CardHeader: View {
    let symbol: String
    let title: String
    let subtitle: String?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Palette.accentSoft)
                    .frame(width: 40, height: 40)
                Image(systemName: symbol)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Palette.accentDeep)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(Typeface.display(18, .bold))
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let subtitle {
                    Text(subtitle)
                        .font(Typeface.body(12.5))
                        .foregroundStyle(Palette.inkTertiary)
                }
            }
            Spacer(minLength: 0)
        }
    }
}
