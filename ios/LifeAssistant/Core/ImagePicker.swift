import PhotosUI
import SwiftUI
import UIKit

enum ImageSource: String, Identifiable {
    case camera
    case library

    var id: String { rawValue }

    var label: String {
        switch self {
        case .camera: "拍照"
        case .library: "从相册选择"
        }
    }

    var symbol: String {
        switch self {
        case .camera: "camera.fill"
        case .library: "photo.on.rectangle.angled"
        }
    }
}

/// 相机（UIImagePickerController 是唯一可靠的自定义相机入口）
struct CameraPicker: UIViewControllerRepresentable {
    let onPicked: (UIImage) -> Void

    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
        picker.cameraCaptureMode = .photo
        picker.allowsEditing = false
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onPicked: onPicked, dismiss: { dismiss() }) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        private let onPicked: (UIImage) -> Void
        private let dismiss: () -> Void

        init(onPicked: @escaping (UIImage) -> Void, dismiss: @escaping () -> Void) {
            self.onPicked = onPicked
            self.dismiss = dismiss
        }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                onPicked(image)
            }
            dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            dismiss()
        }
    }
}

/// 相册（PHPicker 由系统进程承载，App 不接触用户全量图库）
struct LibraryPicker: UIViewControllerRepresentable {
    let onPicked: (UIImage) -> Void

    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(photoLibrary: .shared())
        config.filter = .images
        config.selectionLimit = 1
        config.preferredAssetRepresentationMode = .current
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onPicked: onPicked, dismiss: { dismiss() }) }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        private let onPicked: (UIImage) -> Void
        private let dismiss: () -> Void

        init(onPicked: @escaping (UIImage) -> Void, dismiss: @escaping () -> Void) {
            self.onPicked = onPicked
            self.dismiss = dismiss
        }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            dismiss()
            guard let provider = results.first?.itemProvider,
                  provider.canLoadObject(ofClass: UIImage.self) else { return }
            provider.loadObject(ofClass: UIImage.self) { object, _ in
                guard let image = object as? UIImage else { return }
                Task { @MainActor in onPicked(image) }
            }
        }
    }
}
