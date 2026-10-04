import Foundation

// MARK: - 与后端 app/schemas.py 严格对应的数据契约
// 解码器统一使用 .convertFromSnakeCase，因此这里只写 camelCase 属性名。

enum IntentKind: String, Codable {
    case route, nearby, image, knowledge, unknown
}

enum TravelMode: String, Codable, CaseIterable {
    case transit, walking, driving

    var label: String {
        switch self {
        case .transit: "公交"
        case .walking: "步行"
        case .driving: "驾车"
        }
    }

    var symbol: String {
        switch self {
        case .transit: "bus.fill"
        case .walking: "figure.walk"
        case .driving: "car.fill"
        }
    }
}

enum CardType: String, Codable {
    case placeList = "place_list"
    case route
    case imageAnalysis = "image_analysis"
    case text
}

struct GeoPoint: Codable, Equatable {
    let latitude: Double
    let longitude: Double
    var accuracyM: Double?
}

struct PlaceItem: Codable, Identifiable, Hashable {
    let name: String
    let rating: Double?
    let distanceM: Int?
    let address: String?
    let phone: String?
    let category: String?

    var id: String { "\(name)-\(distanceM ?? -1)-\(address ?? "")" }
}

struct RouteLeg: Codable, Hashable, Identifiable {
    let mode: String
    let instruction: String
    let distanceM: Int?
    let durationS: Int?
    let lineName: String?

    var id: String { "\(mode)-\(instruction)-\(distanceM ?? 0)" }
}

struct RoutePlan: Codable, Hashable {
    let mode: TravelMode
    let totalDistanceM: Int
    let totalDurationS: Int
    let costYuan: Double?
    let transferCount: Int?
    let legs: [RouteLeg]
    let summary: String
}

struct ImageAnalysis: Codable, Hashable {
    let ocrText: String
    let analysis: String
    let tags: [String]
    let confidence: Double?
}

struct ResultCard: Codable, Identifiable, Hashable {
    let type: CardType
    let title: String
    let subtitle: String?
    let speech: String?
    let places: [PlaceItem]
    let routes: [RoutePlan]
    let image: ImageAnalysis?
    let text: String?

    var id: String { "\(type.rawValue)-\(title)-\(subtitle ?? "")" }
}

struct ChatResponse: Codable {
    let sessionId: String
    let intent: IntentKind
    let reply: String
    let cards: [ResultCard]
    let speech: String?
    let meta: [String: AnyCodable]
}

struct ImageAnalyzeResponse: Codable {
    let sessionId: String
    let analysis: ImageAnalysis
    let reply: String
    let cards: [ResultCard]
    let speech: String?
    let meta: [String: AnyCodable]
}

// MARK: - 请求体

struct ChatRequest: Codable {
    let text: String
    let location: GeoPoint?
    let address: String?
    let citycode: String?
    let sessionId: String
    let contextHint: String?
}

// MARK: - 本地模型

struct ChatMessage: Identifiable, Equatable {
    enum Role: Equatable {
        case user
        case assistant
        /// 服务端返回的结构化卡片，气泡里只显示摘要，实体在中间弹窗呈现
        case cards([ResultCard])
    }

    let id = UUID()
    var role: Role
    var text: String
    var timestamp: Date = .now
    /// 用户消息附带的位置标签
    var locationLabel: String?
    /// 用户消息附带的缩略图
    var thumbnail: Data?
    var isStreamingPlaceholder: Bool = false
}

// MARK: - 宽松 JSON（meta 字段结构不固定）

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self) { value = v }
        else if let v = try? container.decode(Int.self) { value = v }
        else if let v = try? container.decode(Double.self) { value = v }
        else if let v = try? container.decode(String.self) { value = v }
        else if let v = try? container.decode([String: AnyCodable].self) { value = v }
        else if let v = try? container.decode([AnyCodable].self) { value = v }
        else { value = NSNull() }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let v as Bool: try container.encode(v)
        case let v as Int: try container.encode(v)
        case let v as Double: try container.encode(v)
        case let v as String: try container.encode(v)
        case let v as [String: AnyCodable]: try container.encode(v)
        case let v as [AnyCodable]: try container.encode(v)
        default: try container.encodeNil()
        }
    }
}

// MARK: - 错误

enum AssistantError: LocalizedError {
    case badURL
    case http(Int, String)
    case decoding(String)
    case offline

    var errorDescription: String? {
        switch self {
        case .badURL: "后端地址配置有误"
        case .http(let code, let detail): "服务端返回 \(code)：\(detail)"
        case .decoding(let detail): "响应解析失败：\(detail)"
        case .offline: "网络连接失败，检查后端是否在运行"
        }
    }
}
