"""坐标系转换。

iOS CoreLocation 输出 WGS-84，中国大陆的高德地图使用 GCJ-02。
不做转换直接查高德，偏差可达数百米——这是国内定位类 App 最常见的坑。
"""

from __future__ import annotations

import math

_A = 6378245.0            # 克拉索夫斯基椭球长半轴
_EE = 0.00669342162296594323  # 第一偏心率平方


def out_of_china(lng: float, lat: float) -> bool:
    """粗略判断是否在中国境外；境外不做偏移。"""
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(lng: float, lat: float) -> float:
    ret = (
        -100.0
        + 2.0 * lng
        + 3.0 * lat
        + 0.2 * lat * lat
        + 0.1 * lng * lat
        + 0.2 * math.sqrt(abs(lng))
    )
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = (
        300.0
        + lng
        + 2.0 * lat
        + 0.1 * lng * lng
        + 0.1 * lng * lat
        + 0.1 * math.sqrt(abs(lng))
    )
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """WGS-84 -> GCJ-02（火星坐标）。"""
    if out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    dlng = (dlng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 -> WGS-84，数值反解（迭代逼近，精度 < 0.5m）。"""
    if out_of_china(lng, lat):
        return lng, lat
    wlng, wlat = lng, lat
    for _ in range(6):
        tlng, tlat = wgs84_to_gcj02(wlng, wlat)
        wlng += lng - tlng
        wlat += lat - tlat
    return wlng, wlat


def haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """两坐标点球面距离（米），用于后端兜底计算。"""
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def format_amap_location(lng: float, lat: float) -> str:
    """高德要求的 location 参数格式：经度在前，6 位小数。"""
    return f"{lng:.6f},{lat:.6f}"
