import Foundation

/// 后端地址存在 UserDefaults 里，可随时在 App 内修改。
///
/// 这样装到手机之后换 Wi-Fi、换路由器、改端口都不需要重新编译，
/// 也就不用重跑一次云端构建。
enum ServerSettings {

    static let storageKey = "lifeassistant.server.baseURL"
    static let fallback = "http://127.0.0.1:8000"

    /// 当前生效的地址；未配置或配置非法时回落到默认值
    static var baseURL: URL {
        guard let raw = UserDefaults.standard.string(forKey: storageKey),
              let url = normalize(raw) else {
            return URL(string: fallback)!
        }
        return url
    }

    static var rawValue: String {
        UserDefaults.standard.string(forKey: storageKey) ?? fallback
    }

    static var isCustomized: Bool {
        (UserDefaults.standard.string(forKey: storageKey) ?? fallback) != fallback
    }

    @discardableResult
    static func save(_ raw: String) -> URL? {
        guard let url = normalize(raw) else { return nil }
        UserDefaults.standard.set(url.absoluteString, forKey: storageKey)
        return url
    }

    static func reset() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }

    /// 宽容解析：允许用户只填 `192.168.1.20:8000` 这类省略 scheme 的写法
    static func normalize(_ raw: String) -> URL? {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        if !text.contains("://") { text = "http://" + text }
        while text.hasSuffix("/") { text.removeLast() }
        guard let url = URL(string: text),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = url.host(), !host.isEmpty else { return nil }
        return url
    }
}
