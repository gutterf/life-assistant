import Foundation
import UIKit
import Vision

/// 图片处理：压缩 + 端上 OCR。
///
/// 端上做 OCR 有两个实打实的好处：省一次服务端推理、识别结果随请求一起上行时
/// 后端不必再跑 OCR 引擎（`ocr_provider=auto` 会优先采用这里的文本）。
enum ImagePipeline {

    /// 长边压到 1600px、JPEG 0.8：肉眼无损，上传体积通常降到 300KB 以内
    static func compressed(_ image: UIImage, maxEdge: CGFloat = 1600, quality: CGFloat = 0.8) -> Data? {
        let longest = max(image.size.width, image.size.height)
        guard longest > 1 else { return nil }

        let target: CGSize
        if longest > maxEdge {
            let scale = maxEdge / longest
            target = CGSize(width: (image.size.width * scale).rounded(),
                            height: (image.size.height * scale).rounded())
        } else {
            target = image.size
        }

        let normalized = image.normalizedOrientation()
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: target, format: format)

        let resized = renderer.image { _ in
            normalized.draw(in: CGRect(origin: .zero, size: target))
        }
        return resized.jpegData(compressionQuality: quality)
    }

    /// 缩略图，用于聊天气泡
    static func thumbnail(_ image: UIImage, edge: CGFloat = 160) -> Data? {
        compressed(image, maxEdge: edge, quality: 0.6)
    }

    /// Vision 文字识别（简体中文 + 英文），失败或无线索时返回空串
    static func recognizeText(in image: UIImage) async -> String {
        guard let cgImage = image.cgImage ?? image.normalizedOrientation().cgImage else { return "" }
        let once = OnceFlag()

        return await withCheckedContinuation { (continuation: CheckedContinuation<String, Never>) in
            let request = VNRecognizeTextRequest { request, _ in
                let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
                let lines = observations.compactMap { $0.topCandidates(1).first?.string }
                once.fire {
                    continuation.resume(returning: lines.joined(separator: "\n"))
                }
            }
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = true

            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try handler.perform([request])
                } catch {
                    once.fire { continuation.resume(returning: "") }
                }
            }
        }
    }
}

/// 保证续体只被恢复一次：Vision 的 completion 与异常分支可能同时到达。
final class OnceFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var fired = false

    func fire(_ block: () -> Void) {
        lock.lock()
        if fired {
            lock.unlock()
            return
        }
        fired = true
        lock.unlock()
        block()
    }
}

extension UIImage {
    /// 相机拍出的横竖屏图片带 orientation 标记，直接缩放会画歪
    func normalizedOrientation() -> UIImage {
        guard imageOrientation != .up else { return self }
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = scale
        format.opaque = false
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: size))
        }
    }
}
