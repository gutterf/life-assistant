import CoreLocation
import Foundation
// @Observable 宏与 ObservationRegistrar 都在 Observation 模块里。
// 本文件不 import SwiftUI，必须显式引入，否则 @Observable 无法展开。
import Observation

/// 定位 + 逆地理编码。
///
/// 注意坐标系：CoreLocation 产出的是 **WGS-84**，直接发给高德会有数百米偏差。
/// 转换统一放在后端完成（`backend/app/services/coord.py`），这里保持原始值不动。
@MainActor
@Observable
final class LocationService: NSObject {

    enum Status: Equatable {
        case idle
        case locating
        case ready
        case denied
        case failed(String)
    }

    private(set) var status: Status = .idle
    private(set) var coordinate: CLLocationCoordinate2D?
    private(set) var accuracyM: Double?
    /// 逆地理得到的可读地址，用于气泡与卡片标题
    private(set) var label: String = ""

    private let manager = CLLocationManager()
    private let geocoder = CLGeocoder()
    private var geocodeInFlight = false

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 20
    }

    var hasFix: Bool { coordinate != nil }

    var authorizationDescription: String {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse: "已授权"
        case .denied, .restricted: "已拒绝"
        case .notDetermined: "未决定"
        @unknown default: "未知"
        }
    }

    func requestPermission() {
        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse:
            start()
        case .denied, .restricted:
            status = .denied
        @unknown default:
            break
        }
    }

    func start() {
        guard CLLocationManager.locationServicesEnabled() else {
            status = .failed("系统定位服务已关闭")
            return
        }
        switch manager.authorizationStatus {
        case .notDetermined:
            requestPermission()
            return
        case .denied, .restricted:
            status = .denied
            return
        default:
            break
        }
        status = .locating
        manager.startUpdatingLocation()
        // 允许复用几分钟内的缓存定位，省电且够用
        if let cached = manager.location, cached.age < 120, coordinate == nil {
            apply(latitude: cached.coordinate.latitude,
                  longitude: cached.coordinate.longitude,
                  accuracy: cached.horizontalAccuracy)
        }
    }

    func stop() {
        manager.stopUpdatingLocation()
    }

    /// 提交一个由外部提供的坐标（例如用户在地图上手动选点）
    func setManual(latitude: Double, longitude: Double, label: String) {
        coordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        accuracyM = nil
        self.label = label
        status = .ready
    }

    // MARK: - 内部

    fileprivate func apply(latitude: Double, longitude: Double, accuracy: Double) {
        coordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        accuracyM = accuracy > 0 ? accuracy : nil
        status = .ready
        reverseGeocode(latitude: latitude, longitude: longitude)
    }

    private func reverseGeocode(latitude: Double, longitude: Double) {
        guard !geocodeInFlight else { return }
        geocodeInFlight = true
        let location = CLLocation(latitude: latitude, longitude: longitude)
        geocoder.reverseGeocodeLocation(location, preferredLocale: Locale(identifier: "zh_CN")) { [weak self] placemarks, _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.geocodeInFlight = false
                guard let p = placemarks?.first else { return }
                self.label = Self.compose(from: p)
            }
        }
    }

    /// 拼一个「城市 + 区 + 街道/POI」的短标签，避免直接把长地址塞进气泡
    private static func compose(from p: CLPlacemark) -> String {
        var parts: [String] = []
        for candidate in [p.locality, p.subLocality, p.name] {
            guard let value = candidate, !value.isEmpty, !parts.contains(value) else { continue }
            parts.append(value)
        }
        if parts.isEmpty, let thoroughfare = p.thoroughfare {
            parts.append(thoroughfare)
        }
        return parts.prefix(3).joined(separator: " · ")
    }
}

// MARK: - CLLocationManagerDelegate

extension LocationService: CLLocationManagerDelegate {

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor [weak self] in
            guard let self else { return }
            switch status {
            case .authorizedAlways, .authorizedWhenInUse:
                self.start()
            case .denied, .restricted:
                self.status = .denied
            default:
                break
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let last = locations.last, last.horizontalAccuracy > 0 else { return }
        // 只传递值类型，避免把 CLLocation 跨隔离域传出去
        let lat = last.coordinate.latitude
        let lng = last.coordinate.longitude
        let acc = last.horizontalAccuracy
        Task { @MainActor [weak self] in
            self?.apply(latitude: lat, longitude: lng, accuracy: acc)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let message = error.localizedDescription
        Task { @MainActor [weak self] in
            guard let self else { return }
            // 定位暂时失败时不要清空已有的可用坐标
            if self.coordinate == nil {
                self.status = .failed(message)
            }
        }
    }
}
