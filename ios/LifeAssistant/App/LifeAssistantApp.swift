import SwiftUI

@main
struct LifeAssistantApp: App {
    var body: some Scene {
        WindowGroup {
            ChatView()
                // 视觉设计基于暖米色纸张底 + 深墨字，浅色是刻意选择而非默认值
                .preferredColorScheme(.light)
                .tint(Palette.accent)
        }
    }
}
