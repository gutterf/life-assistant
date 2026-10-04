"""高德地图 Web 服务封装：逆地理编码、周边搜索、三种出行方式的路线规划。

注意：入参坐标必须是 **GCJ-02**（用 coord.wgs84_to_gcj02 转好再传）。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import Settings
from ..schemas import PlaceItem, RouteLeg, RoutePlan, TravelMode
from .coord import format_amap_location, haversine_m

log = logging.getLogger(__name__)

# 高德 POI 分类码：餐饮 050000 / 购物 060000 / 生活服务 070000 等
TYPE_ALIASES: dict[str, str] = {
    "饭店": "050000", "餐厅": "050000", "吃饭": "050000", "美食": "050000",
    "中餐": "050100", "快餐": "050300", "火锅": "050117", "咖啡": "050500",
    "奶茶": "050500", "甜品": "050400", "超市": "060400", "商场": "060100",
    "便利店": "060200", "药店": "090601", "医院": "090100", "银行": "160100",
    "加油站": "010100", "停车场": "010200", "酒店": "100000", "宾馆": "100000",
    "电影院": "080601", "公园": "110101", "ktv": "080302", "酒吧": "080304",
}

_DRIVING_STRATEGY = {
    "fastest": 32,        # 默认：高德推荐（躲避拥堵优先）
    "avoid_congestion": 34,
    "no_highway": 33,
}


class AMapError(RuntimeError):
    def __init__(self, endpoint: str, info: str, infocode: str = "") -> None:
        super().__init__(f"amap {endpoint} failed: {info} ({infocode})")
        self.endpoint = endpoint
        self.info = info
        self.infocode = infocode


class AMapClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._s.amap_base_url,
                timeout=self._s.amap_timeout_s,
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._s.amap_key:
            raise AMapError(path, "AMAP_KEY 未配置")
        query = {"key": self._s.amap_key, "output": "json", **params}
        resp = await (await self._http()).get(path, params=query)
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("status")) != "1":
            raise AMapError(path, str(data.get("info")), str(data.get("infocode", "")))
        return data

    # ------------------------------------------------------------------ 逆地理
    async def regeo(self, lng: float, lat: float) -> dict[str, str]:
        """返回 {formatted_address, city, citycode, adcode, province, district}。"""
        data = await self._get(
            "/v3/geocode/regeo",
            {"location": format_amap_location(lng, lat), "extensions": "base", "radius": 1000},
        )
        rc = data.get("regeocode") or {}
        comp = rc.get("addressComponent") or {}

        def _s(v: Any) -> str:
            # 高德在字段缺失时返回空 list，不是空字符串
            return v if isinstance(v, str) else ""

        return {
            "formatted_address": _s(rc.get("formatted_address")),
            "province": _s(comp.get("province")),
            "city": _s(comp.get("city")) or _s(comp.get("province")),
            "district": _s(comp.get("district")),
            "citycode": _s(comp.get("citycode")),
            "adcode": _s(comp.get("adcode")),
        }

    # -------------------------------------------------------------- 地理编码
    async def geocode(self, address: str, city: str = "") -> tuple[float, float, str]:
        """地名 -> GCJ-02 坐标。返回 (lng, lat, 规范化地名)。"""
        params: dict[str, Any] = {"address": address, "extensions": "base"}
        if city:
            params["city"] = city
        data = await self._get("/v3/geocode/geo", params)
        geocodes = data.get("geocodes") or []
        if not geocodes:
            raise AMapError("/v3/geocode/geo", f"无法解析地点「{address}」")
        g = geocodes[0]
        loc = str(g.get("location") or "")
        try:
            lng_s, lat_s = loc.split(",")[:2]
            return float(lng_s), float(lat_s), str(g.get("formatted_address") or address)
        except ValueError as exc:
            raise AMapError("/v3/geocode/geo", f"坐标格式异常: {loc}") from exc

    # ------------------------------------------------------------- 周边搜索
    async def place_around(
        self,
        lng: float,
        lat: float,
        keywords: str = "",
        radius_m: int | None = None,
        poi_type: str | None = None,
        limit: int = 20,
    ) -> list[PlaceItem]:
        """半径内周边搜索，结果按距离升序。keywords 与 types 至少给一个。"""
        radius = max(1, min(radius_m or self._s.default_radius_m, self._s.max_radius_m))
        types = TYPE_ALIASES.get((poi_type or "").strip().lower()) or _normalize_types(poi_type)

        params: dict[str, Any] = {
            "location": format_amap_location(lng, lat),
            "radius": radius,
            "offset": min(max(limit, 1), 25),
            "page": 1,
            "sortrule": "distance",
            "extensions": "all",
        }
        # 高德对 keywords 与 types 是 AND 关系，同时给会大幅收窄结果，这里强制二选一
        if keywords:
            params["keywords"] = keywords
        elif types:
            params["types"] = types
        else:
            params["keywords"] = "生活服务"

        data = await self._get("/v3/place/around", params)
        items: list[PlaceItem] = []
        for poi in data.get("pois") or []:
            items.append(_to_place(poi, lng, lat))
        items.sort(key=lambda p: p.distance_m if p.distance_m is not None else 1 << 30)
        return items[:limit]

    # ------------------------------------------------------------- 路线规划
    async def route(
        self,
        mode: TravelMode,
        origin_lng: float,
        origin_lat: float,
        dest_lng: float,
        dest_lat: float,
        citycode: str = "",
        dest_citycode: str = "",
    ) -> RoutePlan:
        origin = format_amap_location(origin_lng, origin_lat)
        dest = format_amap_location(dest_lng, dest_lat)
        if mode is TravelMode.WALKING:
            return await self._walking(origin, dest)
        if mode is TravelMode.DRIVING:
            return await self._driving(origin, dest)
        return await self._transit(origin, dest, citycode, dest_citycode, origin_lng, origin_lat, dest_lng, dest_lat)

    async def _walking(self, origin: str, dest: str) -> RoutePlan:
        data = await self._get("/v3/direction/walking", {"origin": origin, "destination": dest})
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            raise AMapError("/v3/direction/walking", "无可用步行路径")
        p = paths[0]
        legs = [
            RouteLeg(
                mode="walking",
                instruction=str(s.get("instruction") or ""),
                distance_m=_int(s.get("distance")),
                duration_s=_int(s.get("duration")),
            )
            for s in (p.get("steps") or [])[:24]
        ]
        dist = _int(p.get("distance")) or 0
        dur = _int(p.get("duration")) or 0
        return RoutePlan(
            mode=TravelMode.WALKING,
            total_distance_m=dist,
            total_duration_s=dur,
            legs=legs,
            summary=f"步行 {_km(dist)}，约 {_min(dur)}",
        )

    async def _driving(self, origin: str, dest: str) -> RoutePlan:
        data = await self._get(
            "/v3/direction/driving",
            {"origin": origin, "destination": dest, "extensions": "all",
             "strategy": _DRIVING_STRATEGY["fastest"]},
        )
        paths = (data.get("route") or {}).get("paths") or []
        if not paths:
            raise AMapError("/v3/direction/driving", "无可用驾车路径")
        p = paths[0]
        legs = [
            RouteLeg(
                mode="driving",
                instruction=str(s.get("instruction") or ""),
                distance_m=_int(s.get("distance")),
                duration_s=_int(s.get("duration")),
                line_name=(s.get("road") or None),
            )
            for s in (p.get("steps") or [])[:24]
        ]
        dist = _int(p.get("distance")) or 0
        dur = _int(p.get("duration")) or 0
        tolls = p.get("tolls")
        toll = float(tolls) if isinstance(tolls, (int, float, str)) and str(tolls).replace(".", "", 1).isdigit() else None
        lights = _int(p.get("traffic_lights")) or 0
        return RoutePlan(
            mode=TravelMode.DRIVING,
            total_distance_m=dist,
            total_duration_s=dur,
            cost_yuan=toll,
            legs=legs,
            summary=f"驾车 {_km(dist)}，约 {_min(dur)}" + (f"，红绿灯 {lights} 个" if lights else ""),
        )

    async def _transit(
        self,
        origin: str,
        dest: str,
        citycode: str,
        dest_citycode: str,
        o_lng: float, o_lat: float, d_lng: float, d_lat: float,
    ) -> RoutePlan:
        params: dict[str, Any] = {
            "origin": origin, "destination": dest,
            "strategy": 0, "extensions": "all", "nightflag": 0,
        }
        # city / cityd 是公交接口的必填项：缺失会导致 INVALID_PARAMS
        if citycode:
            params["city"] = citycode
            params["cityd"] = dest_citycode or citycode
        else:
            # 没拿到城市码时用坐标反查，保证接口可用
            resolved = await self._resolve_citycode(o_lng, o_lat, d_lng, d_lat)
            params["city"] = resolved
            params["cityd"] = dest_citycode or resolved

        data = await self._get("/v3/direction/transit/integrated", params)
        route = data.get("route") or {}
        transits = route.get("transits") or []
        if not transits:
            raise AMapError("/v3/direction/transit/integrated", "无可用公交方案")

        # 高德会返回多个候选方案，只展开第一个（即最优方案）。
        # 早先的写法把三个方案的 segments 全灌进同一个 legs 列表，总距离会虚高约三倍。
        best = transits[0]
        legs: list[RouteLeg] = []
        transfers = 0
        for seg in best.get("segments") or []:
            walking = seg.get("walking") or {}
            wdist, wdur = _int(walking.get("distance")), _int(walking.get("duration"))
            wsteps = walking.get("steps") or []
            hint = wsteps[0].get("instruction") if wsteps else "步行"
            if wdur:
                legs.append(RouteLeg(mode="walking", instruction=str(hint),
                                     distance_m=wdist, duration_s=wdur))
            bus = seg.get("bus") or {}
            for line in bus.get("buslines") or []:
                transfers += 1
                legs.append(RouteLeg(
                    mode="transit",
                    instruction=_bus_instruction(line),
                    distance_m=_int(line.get("distance")),
                    duration_s=_int(line.get("duration")),
                    line_name=str(line.get("name") or ""),
                ))

        # 高德公交方案字段的语义（见官方 AMapTransit 定义，容易望文生义搞错）：
        #   cost              -> 此方案票价，单位「元」
        #   duration          -> 此方案预期耗时，单位「秒」
        #   distance          -> 方案总距离，单位「米」
        #   walking_distance  -> 方案总步行距离，单位「米」
        # 早先的实现把 cost 当成了秒数，并把票价读成不存在的 cost_yuan，
        # 结果每张公交卡片都显示「约 1 分钟」且没有票价。
        duration_s = _int(best.get("duration")) or 0
        fare_yuan = _float(best.get("cost"))
        walk_m = _int(best.get("walking_distance")) or 0
        # 优先用高德给的方案总里程；它缺失时才退化成把分段加起来
        dist = _int(best.get("distance")) or sum(leg.distance_m or 0 for leg in legs) or 0
        transfer_count = max(transfers - 1, 0)
        return RoutePlan(
            mode=TravelMode.TRANSIT,
            total_distance_m=dist,
            total_duration_s=duration_s,
            cost_yuan=fare_yuan,
            transfer_count=transfer_count,
            legs=legs[:30],
            summary=(f"公交约 {_min(duration_s)}" if duration_s else "公交方案")
            + (f"，票价 {fare_yuan:g} 元" if fare_yuan else "")
            + (f"，换乘 {transfer_count} 次" if transfer_count else "，无需换乘")
            + (f"，步行 {walk_m} 米" if walk_m else ""),
        )

    async def _resolve_citycode(self, o_lng: float, o_lat: float, d_lng: float, d_lat: float) -> str:
        try:
            origin_info = await self.regeo(o_lng, o_lat)
            if origin_info.get("citycode"):
                return origin_info["citycode"]
            dest_info = await self.regeo(d_lng, d_lat)
            return dest_info.get("citycode") or "010"
        except (AMapError, httpx.HTTPError):
            log.warning("公交 citycode 解析失败，回落到 010")
            return "010"


# ------------------------------------------------------------------ helpers
def _normalize_types(poi_type: str | None) -> str:
    """如果调用方直接给了 6 位分类码就透传，否则为空（改用 keywords 检索）。"""
    t = (poi_type or "").strip()
    return t if t.isdigit() and len(t) == 6 else ""


def _bus_instruction(line: dict[str, Any]) -> str:
    name = str(line.get("name") or "").split("(")[0]
    dep = ((line.get("departure_stop") or {}).get("name")) or ""
    arr = ((line.get("arrival_stop") or {}).get("name")) or ""
    via = _int(line.get("via_num")) or 0
    parts = [f"乘坐 {name}"]
    if dep:
        parts.append(f"从 {dep} 上车")
    if via:
        parts.append(f"经 {via} 站")
    if arr:
        parts.append(f"到 {arr} 下车")
    return "，".join(parts)


def _to_place(poi: dict[str, Any], lng: float, lat: float) -> PlaceItem:
    biz = poi.get("biz_ext") or {}
    rating = _float(biz.get("rating"))
    dist = _int(poi.get("distance"))
    if dist is None and isinstance(poi.get("location"), str) and "," in poi["location"]:
        try:
            plng, plat = (float(x) for x in poi["location"].split(",")[:2])
            dist = int(haversine_m(lng, lat, plng, plat))
        except ValueError:
            dist = None
    phone = poi.get("tel")
    return PlaceItem(
        name=str(poi.get("name") or "未命名地点"),
        rating=rating,
        distance_m=dist,
        address=poi.get("address") if isinstance(poi.get("address"), str) else None,
        phone=phone if isinstance(phone, str) and phone else None,
        category=str(poi.get("type") or "").split(";")[-1] or None,
    )


def _int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _km(m: int) -> str:
    return f"{m / 1000:.1f} 公里" if m >= 1000 else f"{m} 米"


def _min(s: int) -> str:
    if s >= 3600:
        h, rest = divmod(s, 3600)
        return f"{h} 小时 {rest // 60} 分钟"
    return f"{max(1, s // 60)} 分钟"
