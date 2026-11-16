"""卫星回复开关 + 附近 POI 全量代理。

开关：data/satellite_reply.flag 存在即开启（重启后端不丢）。
开启后 orchestrator 把「卫星规则」注入 system：每次回复第一行输出用户实时坐标
（纬度,经度），第二行用地理反查说明用户站在哪个位置，再开始正文——像卫星视角看用户。
关闭后回复不带头坐标，纯模型正常回答。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("life-assistant.satellite")

_FLAG = Path(__file__).resolve().parents[2] / "data" / "satellite_reply.flag"
_ENABLED = _FLAG.is_file()

SATELLITE_SYSTEM_RULE = (
    "【卫星回复模式】你正在从卫星视角观察用户。每次回复必须严格遵守格式：\n"
    "第一行单独输出用户当前实时坐标，格式为「纬度,经度」（如 29.4597,119.9091），"
    "数字保留 4 位小数，不加任何前缀文字；\n"
    "第二行以「你站在」开头，结合坐标与地理常识说明用户所在位置"
    "（如「你站在浙江金华市浦江县/兰溪市交界附近（29.4597N，119.9091E）。」），"
    "位置说明尽量具体到区县/街道/地标；\n"
    "第三行起再开始正式回答。用户没有提供新坐标时，沿用上一轮坐标。"
)


def is_satellite_reply() -> bool:
    return _ENABLED


def set_satellite_reply(on: bool) -> bool:
    global _ENABLED
    _ENABLED = bool(on)
    try:
        if _ENABLED:
            _FLAG.parent.mkdir(parents=True, exist_ok=True)
            _FLAG.write_text("1", encoding="utf-8")
        elif _FLAG.exists():
            _FLAG.unlink()
    except Exception: # noqa: BLE001
        pass
    return _ENABLED


# 高德 POI 大类码：软件内卫星地图「附近显示都要全」= 全大类一次抓齐
_ALL_TYPES = (
    "050000", # 餐饮
    "060000", # 购物
    "070000", # 生活服务
    "080000", # 医疗保健
    "100000", # 住宿
    "110000", # 风景名胜
    "140000", # 科教文化
    "150000", # 交通设施
    "160000", # 金融保险
    "170000", # 公司企业
    "130000", # 政府机构
    "010000", # 汽车服务
    "020000", # 汽车销售
    "030000", # 汽车维修
    "180000", # 道路附属
    "090000", # 体育休闲
    "120000", # 商务住宅
    "990000", # 地名地址
)

_TYPE_NAMES = {
    "餐饮服务": "餐饮",
    "购物服务": "购物",
    "生活服务": "生活服务",
    "医疗保健服务": "医疗",
    "住宿服务": "住宿",
    "风景名胜": "景点",
    "科教文化服务": "教育文化",
    "交通设施服务": "交通",
    "金融保险服务": "金融",
    "公司企业": "公司",
    "政府机构及社会团体": "政府",
    "汽车服务": "汽车服务",
    "汽车销售": "汽车销售",
    "汽车维修": "汽车维修",
    "摩托车服务": "摩托车",
    "体育休闲服务": "体育休闲",
    "商务住宅": "住宅",
}


async def nearby_pois(client: Any, latitude: float, longitude: float, radius: int = 3000) -> dict[str, Any]:
    """软件内卫星地图数据源：周边全类型 POI，翻 2 页抓满 50 家按距离排序。"""
    radius = max(100, min(radius, 50000))
    items: list[Any] = []
    try:
        for page in (1, 2):
            batch = await client.place_around(
                longitude, latitude,
                keywords="",
                poi_type="|".join(_ALL_TYPES),
                radius_m=radius,
                limit=25,
                page=page,
            )
            items.extend(batch)
            if len(batch) < 25:
                break
    except Exception as e: # noqa: BLE001
        log.warning("nearby pois failed: %s", e)
        return {"center": [longitude, latitude], "total": 0, "groups": {}, "pois": []}
    pois = []
    for p in items:
        if p.lng is None or p.lat is None:
            continue
        typ = (p.category or "其他")
        pois.append(
            {
                "name": p.name,
                "type": typ,
                "type_name": _TYPE_NAMES.get(typ, typ),
                "address": p.address or "",
                "lng": p.lng,
                "lat": p.lat,
                "distance_m": p.distance_m or 0,
                "tel": p.phone or "",
                "rating": p.rating,
            }
        )
    groups: dict[str, list[dict]] = {}
    for p in pois:
        groups.setdefault(p["type_name"], []).append(p)
    return {
        "center": [longitude, latitude],
        "radius_m": radius,
        "total": len(pois),
        "groups": {k: v for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))},
        "pois": pois,
    }
