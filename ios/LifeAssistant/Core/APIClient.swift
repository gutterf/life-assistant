import Foundation

/// 后端 REST 客户端。所有密钥都在服务端环境变量里，App 侧不含任何 key。
final class APIClient: @unchecked Sendable {

    static let shared = APIClient()

    /// 每次请求都从 UserDefaults 读，改完地址立即生效，无需重启 App。
    /// 真机必须指向 Mac/PC 的局域网 IP（模拟器才能用 127.0.0.1）。
    private var baseURL: URL { ServerSettings.baseURL }

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 180
        config.waitsForConnectivity = true
        config.httpAdditionalHeaders = ["Accept": "application/json"]
        self.session = URLSession(configuration: config)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    // MARK: - 连通性自检

    /// 用于设置页的「测试连接」，返回人类可读的结果
    func healthCheck() async -> (ok: Bool, message: String) {
        var request = URLRequest(url: baseURL.appending(path: "health"))
        request.httpMethod = "GET"
        request.timeoutInterval = 8
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                return (false, "服务端返回 \(code)")
            }
            if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let missing = (object["missing"] as? [String]) ?? []
                if missing.isEmpty {
                    return (true, "连接正常，密钥已配置")
                }
                return (false, "已连通，但服务端缺少：\(missing.joined(separator: "、"))")
            }
            return (true, "连接正常")
        } catch {
            return (false, "连不上：\(error.localizedDescription)")
        }
    }

    // MARK: - 文字提问

    func chat(_ request: ChatRequest) async throws -> ChatResponse {
        var urlRequest = URLRequest(url: baseURL.appending(path: "api/v1/chat"))
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try encoder.encode(request)

        let response: ChatResponse = try await perform(urlRequest)
        return response
    }

    // MARK: - 图片分析

    func analyzeImage(
        imageData: Data,
        question: String,
        clientOCRText: String?,
        location: GeoPoint?,
        address: String?,
        citycode: String?,
        sessionId: String
    ) async throws -> ImageAnalyzeResponse {
        let boundary = "Boundary-\(UUID().uuidString)"
        var urlRequest = URLRequest(url: baseURL.appending(path: "api/v1/analyze-image"))
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("multipart/form-data; boundary=\(boundary)",
                            forHTTPHeaderField: "Content-Type")

        var fields: [String: String] = [
            "question": question,
            "session_id": sessionId,
        ]
        if let clientOCRText, !clientOCRText.isEmpty { fields["ocr_text"] = clientOCRText }
        if let address, !address.isEmpty { fields["address"] = address }
        if let citycode, !citycode.isEmpty { fields["citycode"] = citycode }
        if let location {
            fields["latitude"] = String(location.latitude)
            fields["longitude"] = String(location.longitude)
            if let acc = location.accuracyM { fields["accuracy_m"] = String(acc) }
        }

        urlRequest.httpBody = Self.multipartBody(
            boundary: boundary,
            fields: fields,
            fileField: "file",
            filename: "photo.jpg",
            mimeType: "image/jpeg",
            fileData: imageData
        )

        let response: ImageAnalyzeResponse = try await perform(urlRequest)
        return response
    }

    // MARK: - 传输

    private func perform<T: Decodable>(_ request: URLRequest, attempt: Int = 0) async throws -> T {
        do {
            let (data, urlResponse) = try await session.data(for: request)
            guard let http = urlResponse as? HTTPURLResponse else {
                throw AssistantError.offline
            }
            guard (200..<300).contains(http.statusCode) else {
                let detail = Self.extractDetail(from: data)
                // 5xx 是临时故障，退避重试一次
                if http.statusCode >= 500, attempt < 1 {
                    try await Task.sleep(for: .milliseconds(700))
                    return try await perform(request, attempt: attempt + 1)
                }
                throw AssistantError.http(http.statusCode, detail)
            }
            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw AssistantError.decoding(String(describing: error))
            }
        } catch let error as AssistantError {
            throw error
        } catch let error as URLError {
            if error.code == .cancelled { throw error }
            if attempt < 1 {
                try await Task.sleep(for: .milliseconds(500))
                return try await perform(request, attempt: attempt + 1)
            }
            throw AssistantError.offline
        }
    }

    private static func extractDetail(from data: Data) -> String {
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = object["detail"] as? String { return detail }
            if let message = object["message"] as? String { return message }
        }
        return String(data: data.prefix(180), encoding: .utf8) ?? "未知错误"
    }

    private static func multipartBody(
        boundary: String,
        fields: [String: String],
        fileField: String,
        filename: String,
        mimeType: String,
        fileData: Data
    ) -> Data {
        var body = Data()
        let crlf = "\r\n"

        for (key, value) in fields.sorted(by: { $0.key < $1.key }) {
            body.append("--\(boundary)\(crlf)")
            body.append("Content-Disposition: form-data; name=\"\(key)\"\(crlf)\(crlf)")
            body.append("\(value)\(crlf)")
        }

        body.append("--\(boundary)\(crlf)")
        body.append("Content-Disposition: form-data; name=\"\(fileField)\"; filename=\"\(filename)\"\(crlf)")
        body.append("Content-Type: \(mimeType)\(crlf)\(crlf)")
        body.append(fileData)
        body.append(crlf)
        body.append("--\(boundary)--\(crlf)")
        return body
    }
}

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) { append(data) }
    }
}
