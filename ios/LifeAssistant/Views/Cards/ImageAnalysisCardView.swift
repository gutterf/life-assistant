import SwiftUI

/// 图片分析卡片：结论 + 结构化线索 + OCR 原文
struct ImageAnalysisCardView: View {

    let card: ResultCard

    @State private var showRawText = false

    private var analysis: ImageAnalysis? { card.image }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CardHeader(symbol: "text.viewfinder", title: card.title, subtitle: card.subtitle)

            if let analysis {
                Text(analysis.analysis)
                    .font(Typeface.body(15))
                    .foregroundStyle(Palette.ink)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if !analysis.tags.isEmpty {
                    tags(analysis.tags)
                }

                if !analysis.ocrText.isEmpty {
                    rawText(analysis.ocrText)
                }

                if let confidence = analysis.confidence, confidence < 0.5 {
                    Label("图片文字较少，结论仅供参考", systemImage: "exclamationmark.triangle.fill")
                        .font(Typeface.body(12))
                        .foregroundStyle(Color(red: 0.72, green: 0.45, blue: 0.10))
                        .padding(.horizontal, 11)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Color(red: 0.99, green: 0.95, blue: 0.87))
                        )
                }
            } else {
                Text("没有解析出结果")
                    .font(Typeface.body(14))
                    .foregroundStyle(Palette.inkTertiary)
            }
        }
    }

    private func tags(_ items: [String]) -> some View {
        FlowRow(spacing: 7) {
            ForEach(items, id: \.self) { tag in
                Text(tag)
                    .font(Typeface.metric(12, .semibold))
                    .foregroundStyle(Palette.accentDeep)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Capsule().fill(Palette.accentSoft))
            }
        }
    }

    private func rawText(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.22)) { showRawText.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 12, weight: .semibold))
                    Text(showRawText ? "收起识别原文" : "查看识别原文（\(text.count) 字）")
                        .font(Typeface.body(13, .semibold))
                    Spacer(minLength: 0)
                    Image(systemName: showRawText ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10, weight: .bold))
                }
                .foregroundStyle(Palette.inkSecondary)
                .padding(.horizontal, 13)
                .padding(.vertical, 11)
            }
            .buttonStyle(.plain)

            if showRawText {
                Text(text)
                    .font(Typeface.body(13))
                    .foregroundStyle(Palette.inkSecondary)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 13)
                    .padding(.bottom, 13)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Palette.canvas)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Palette.hairline, lineWidth: 0.8)
        )
    }
}

/// 纯文本卡片（常识问答等）
struct TextCardView: View {
    let card: ResultCard

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CardHeader(symbol: "text.bubble.fill", title: card.title, subtitle: card.subtitle)

            Text(card.text ?? "")
                .font(Typeface.body(15))
                .foregroundStyle(Palette.ink)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// 自动换行的标签流容器
struct FlowRow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if rowWidth + size.width > maxWidth, rowWidth > 0 {
                totalHeight += rowHeight + spacing
                rowWidth = 0
                rowHeight = 0
            }
            rowWidth += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth == .infinity ? rowWidth : maxWidth,
                      height: totalHeight + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
