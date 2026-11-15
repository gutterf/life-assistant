import Foundation

/// 后端地址存在 UserDefaults 里，可随时在 App 内修改。
///
/// 这样装到手机之后换 Wi-Fi、换路由器、改端口都不需要重新编译，
/// 也就不用重跑一次云端构建。
/// 可选模型预设。App 内改完立即生效，无需重装。
enum ModelPreset: String, CaseIterable, Identifiable {
 case chat = "deepseek-chat"
 case reasoner = "deepseek-reasoner"
 case custom

 var id: String { rawValue }

 var label: String {
 switch self {
 case .chat: return "DeepSeek Chat（日常问答，快）"
 case .reasoner: return "DeepSeek Reasoner（多步推理，慢）"
 case .custom: return "自定义模型"
 }
 }
}

enum ServerSettings {

 static let storageKey = "lifeassistant.server.baseURL"
 static let fallback = "http://127.0.0.1:8000"

 // ---- 模型与密钥（可选覆盖）----
 static let modelPresetKey = "lifeassistant.model.preset"
 static let customModelKey = "lifeassistant.model.custom"
 static let apiKeyKey = "lifeassistant.apiKey"

 /// 请求头名：后端据此按次覆盖 .env 里的模型与 key
 static let modelHeader = "X-LifeAssistant-Model"
 static let apiKeyHeader = "X-LifeAssistant-Api-Key"

 /// 当前选择的模型预设
 static var modelPreset: ModelPreset {
 get {
 guard let raw = UserDefaults.standard.string(forKey: modelPresetKey),
 let preset = ModelPreset(rawValue: raw) else {
 return .chat
 }
 return preset
 }
 set { UserDefaults.standard.set(newValue.rawValue, forKey: modelPresetKey) }
 }

 /// 自定义模型名（preset 为 custom 时生效）
 static var customModelName: String {
 get { UserDefaults.standard.string(forKey: customModelKey) ?? "" }
 set { UserDefaults.standard.set(newValue, forKey: customModelKey) }
 }

 /// App 内填的 API Key；留空表示用服务器端 .env 里的 key
 static var apiKey: String {
 get { UserDefaults.standard.string(forKey: apiKeyKey) ?? "" }
 set { UserDefaults.standard.set(newValue, forKey: apiKeyKey) }
 }

 /// 最终生效的模型名：自定义预设用填的名字，否则用预设本身
 static var effectiveModel: String {
 switch modelPreset {
 case .chat, .reasoner: return modelPreset.rawValue
 case .custom:
 let name = customModelName.trimmingCharacters(in: .whitespacesAndNewlines)
 return name.isEmpty ? "deepseek-chat" : name
 }
 }

 /// 最终生效的 API Key：空白视为未配置（nil = 交给服务器）
 static var effectiveApiKey: String? {
 let key = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
 return key.isEmpty ? nil : key
 }

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
