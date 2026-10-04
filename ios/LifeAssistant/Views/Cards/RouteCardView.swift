import Foundation
import SwiftUI

/// 路线规划卡片：总览指标 + 分段指引时间轴
struct RouteCardView: View {

    let card: ResultCard

    private var plan: RoutePlan? { card.routes.first }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CardHeader(symbol: modeSymbol, title: card.title, subtitle: card.subtitle)

            if let plan {
                metrics(plan)

                Rectangle().fill(Palette.hairline).frame(height: 0.8)

                if plan.legs.isEmpty {
                    Text(plan.summary)
                        .font(Typeface.body(14))
                        .foregroundStyle(Palette.inkSecondary)
                } else {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(plan.legs.enumerated()), id: \.element.id) { index, leg in
                            LegRow(leg: leg, isLast: index == plan.legs.count - 1)
                        }
                    }
                }
            } else {
                Text("没有可用的路线方案")
                    .font(Typeface.body(14))
                    .foregroundStyle(Palette.inkTertiary)
            }
        }
    }

    private var modeSymbol: String {
        switch plan?.mode {
        case .transit: "bus.fill"
        case .walking: "figure.walk"
        case .driving: "car.fill"
        default: "arrow.triangle.turn.up.right.diamond.fill"
        }
    }

    private func metrics(_ plan: RoutePlan) -> some View {
        HStack(alignment: .top, spacing: 0) {
            metricCell(title: "预计耗时", value: Format.duration(plan.totalDurationS), emphasis: true)
            divider
            metricCell(title: "全程距离", value: Format.distance(plan.totalDistanceM))
            if let transfers = plan.transferCount {
                divider
                metricCell(title: "换乘", value: transfers == 0 ? "直达" : "\(transfers) 次")
            }
            if let cost = plan.costYuan, cost > 0 {
                divider
                metricCell(title: costLabel(plan.mode), value: String(format: "¥%.0f", cost))
            }
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 6)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Palette.canvas)
        )
    }

    /// 同一个 cost_yuan 字段在不同出行方式下含义不同：
    /// 公交是票价、驾车是过路费（高德分别用 transits[].cost 与 paths[].tolls 表示）。
    private func costLabel(_ mode: TravelMode) -> String {
        switch mode {
        case .transit: "票价"
        case .driving: "过路费"
        case .walking: "费用"
        }
    }

    private var divider: some View {
        Rectangle()
            .fill(Palette.hairline)
            .frame(width: 0.8, height: 30)
    }

    private func metricCell(title: String, value: String, emphasis: Bool = false) -> some View {
        VStack(spacing: 5) {
            Text(value)
                .font(Typeface.metric(emphasis ? 19 : 16, .bold))
                .foregroundStyle(emphasis ? Palette.accentDeep : Palette.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(title)
                .font(Typeface.body(11))
                .foregroundStyle(Palette.inkTertiary)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct LegRow: View {
    let leg: RouteLeg
    let isLast: Bool

    private var isTransit: Bool { leg.mode == "transit" }

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            VStack(spacing: 0) {
                ZStack {
                    Circle()
                        .fill(isTransit ? Palette.accent : Palette.canvasDeep)
                        .frame(width: 22, height: 22)
                    Image(systemName: isTransit ? "bus.fill" : "figure.walk")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(isTransit ? .white : Palette.inkSecondary)
                }
                if !isLast {
                    Rectangle()
                        .fill(Palette.hairline)
                        .frame(width: 1.6)
                        .frame(maxHeight: .infinity)
                }
            }
            .frame(width: 22)

            VStack(alignment: .leading, spacing: 4) {
                if isTransit, let line = leg.lineName, !line.isEmpty {
                    Text(line)
                        .font(Typeface.body(13.5, .semibold))
                        .foregroundStyle(Palette.accentDeep)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(leg.instruction)
                    .font(Typeface.body(13.5))
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    if let d = leg.distanceM, d > 0 {
                        Text(Format.distance(d))
                    }
                    if let t = leg.durationS, t > 0 {
                        Text(Format.duration(t))
                    }
                }
                .font(Typeface.metric(11.5))
                .foregroundStyle(Palette.inkTertiary)
            }
            .padding(.bottom, isLast ? 0 : 14)

            Spacer(minLength: 0)
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}
