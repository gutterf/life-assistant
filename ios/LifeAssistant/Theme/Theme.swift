import Foundation
import SwiftUI

/// 视觉语言：暖陶土 + 纸张质感。
/// 刻意避开「紫白渐变」这类默认科技感配色，让生活助手读起来像一本便签本。
enum Palette {
    static let canvas = Color(red: 0.969, green: 0.953, blue: 0.925)       // #F7F3EC
    static let canvasDeep = Color(red: 0.925, green: 0.898, blue: 0.851)   // #ECE5D9
    static let surface = Color(red: 1.0, green: 0.999, blue: 0.996)
    static let ink = Color(red: 0.110, green: 0.102, blue: 0.090)          // #1C1A17
    static let inkSecondary = Color(red: 0.420, green: 0.392, blue: 0.349)
    static let inkTertiary = Color(red: 0.620, green: 0.592, blue: 0.549)
    static let accent = Color(red: 0.769, green: 0.333, blue: 0.165)       // #C4552A
    static let accentSoft = Color(red: 0.949, green: 0.886, blue: 0.839)
    static let accentDeep = Color(red: 0.560, green: 0.216, blue: 0.086)
    static let moss = Color(red: 0.247, green: 0.478, blue: 0.369)         // 正向指标
    static let hairline = Color(red: 0.890, green: 0.863, blue: 0.820)
    static let shadow = Color(red: 0.310, green: 0.230, blue: 0.150).opacity(0.13)
}

enum Typeface {
    static func display(_ size: CGFloat, _ weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
    static func body(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight)
    }
    /// 距离、时间、评分等数字用等宽字形，避免跳动
    static func metric(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font {
        .system(size: size, weight: weight, design: .rounded).monospacedDigit()
    }
}

/// 聊天页背景：静态 MeshGradient（iOS 18）+ 一枚暖色光斑。
struct CanvasBackground: View {
    var body: some View {
        ZStack {
            MeshGradient(
                width: 3,
                height: 3,
                points: [
                    [0.0, 0.0], [0.5, 0.0], [1.0, 0.0],
                    [0.0, 0.45], [0.55, 0.5], [1.0, 0.55],
                    [0.0, 1.0], [0.5, 1.0], [1.0, 1.0]
                ],
                colors: [
                    Palette.canvas, Palette.canvas, Palette.canvasDeep,
                    Palette.canvas, Palette.canvas, Palette.canvasDeep,
                    Palette.canvasDeep, Palette.canvasDeep, Palette.canvas
                ]
            )
            RadialGradient(
                colors: [Palette.accent.opacity(0.10), .clear],
                center: .init(x: 0.85, y: 0.08),
                startRadius: 4,
                endRadius: 420
            )
        }
        .ignoresSafeArea()
    }
}

enum Format {
    static func distance(_ meters: Int?) -> String {
        guard let m = meters else { return "距离未知" }
        return m >= 1000 ? String(format: "%.1f km", Double(m) / 1000) : "\(m) m"
    }

    static func duration(_ seconds: Int?) -> String {
        guard let s = seconds, s > 0 else { return "—" }
        if s >= 3600 {
            let h = s / 3600, m = (s % 3600) / 60
            return m > 0 ? "\(h) 小时 \(m) 分" : "\(h) 小时"
        }
        return "\(max(1, s / 60)) 分钟"
    }
}
