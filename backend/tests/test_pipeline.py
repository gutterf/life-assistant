"""端到端管线测试：打桩掉 DeepSeek 与高德，验证编排、坐标转换与卡片契约。

运行：
    cd backend && python -m pytest tests -q
不需要 pytest-asyncio：异步用例在同步测试函数里用 asyncio.run 驱动。
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas import ImageAnalysis, Intent, PlaceItem, RouteLeg, RoutePlan, TravelMode
from app.services.amap import AMapClient
from app.services.coord import gcj02_to_wgs84, haversine_m, wgs84_to_gcj02
from app.services.deepseek import DeepSeekClient, IntentDecision
from app.services.ocr import OCRService
from app.services.orchestrator import Orchestrator

# 天安门广场附近（GCJ-02 与 WGS-84 在此处相差约 500m，用于验证转换确实生效）
WGS_LNG, WGS_LAT = 116.397128, 39.916527


@pytest.fixture()
def settings() -> Settings:
    return Settings(deepseek_api_key="test-key", amap_key="test-amap", ocr_provider="none")


def _app_with_stubs(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    """构造 app 并手动装填 state。

    httpx.ASGITransport 不执行 lifespan，因此不走 create_app 的启动钩子，
    这里显式组装依赖，等价于运行时状态。
    """
    app = create_app()
    amap = AMapClient(settings)
    llm = DeepSeekClient(settings)
    ocr = OCRService(settings)
    app.state.settings = settings
    app.state.amap = amap
    app.state.llm = llm
    app.state.ocr = ocr
    app.state.orchestrator = Orchestrator(settings, amap, llm, ocr)

    monkeypatch.setattr(amap, "regeo", AsyncMock(return_value={
        "formatted_address": "北京市东城区东华门街道天安门广场",
        "city": "北京市", "citycode": "010", "province": "北京市",
        "district": "东城区", "adcode": "110101",
    }))
    return app, amap, llm, ocr


async def _client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ------------------------------------------------------------------ 坐标系
def test_coord_roundtrip_and_offset():
    glng, glat = wgs84_to_gcj02(WGS_LNG, WGS_LAT)
    offset = haversine_m(WGS_LNG, WGS_LAT, glng, glat)
    assert 300 < offset < 800, f"北京地区偏移应约 500m，实测 {offset:.0f}m"

    back_lng, back_lat = gcj02_to_wgs84(glng, glat)
    assert abs(back_lng - WGS_LNG) < 1e-6
    assert abs(back_lat - WGS_LAT) < 1e-6


def test_coord_outside_china_untouched():
    lng, lat = wgs84_to_gcj02(-122.4194, 37.7749)
    assert (lng, lat) == (-122.4194, 37.7749)


# ------------------------------------------------------------------ 常识
def test_knowledge_path(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision(
        {"intent": "knowledge", "confidence": 0.9})))
    monkeypatch.setattr(llm, "answer_knowledge", AsyncMock(return_value="1. 冷水下锅。2. 煮 8 分钟。"))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={"text": "煮鸡蛋要几分钟", "session_id": "s1"})
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "knowledge"
    assert body["cards"][0]["type"] == "text"
    assert body["speech"], "必须有语音播报文本"


# ------------------------------------------------------------------ 周边
def test_nearby_path_uses_gcj02_and_radius(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    captured: dict = {}

    async def fake_around(lng, lat, keywords="", radius_m=None, poi_type=None, limit=20):
        captured.update(lng=lng, lat=lat, keywords=keywords, radius=radius_m, poi_type=poi_type)
        return [
            PlaceItem(name="老北京炸酱面", rating=4.6, distance_m=320, address="东城区前门大街1号"),
            PlaceItem(name="川渝火锅", rating=4.9, distance_m=1450, address="东城区王府井大街"),
            PlaceItem(name="粤菜馆", rating=None, distance_m=9800, address="朝阳区建国路"),
        ]

    monkeypatch.setattr(amap, "place_around", fake_around)
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision({
        "intent": "nearby", "confidence": 0.95, "poi_keyword": "火锅", "radius_m": 15000})))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={
                "text": "附近15公里有什么火锅店",
                "location": {"latitude": WGS_LAT, "longitude": WGS_LNG},
                "session_id": "s2",
            })
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()

    # 传给高德的必须是 GCJ-02，不是原始 WGS-84
    assert abs(captured["lng"] - WGS_LNG) > 0.001, "未做 WGS84 -> GCJ02 转换"
    assert captured["radius"] == 15000
    assert captured["keywords"] == "火锅"

    places = body["cards"][0]["places"]
    assert len(places) == 3
    assert places[0]["distance_m"] <= places[-1]["distance_m"], "结果应按距离升序"
    assert places[0]["rating"] == 4.6
    assert "评分最高" in body["reply"] and "川渝火锅" in body["reply"]
    assert body["meta"]["radius_m"] == 15000


# ------------------------------------------------------------------ 路线
def test_route_path_walking(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    geo_called: dict = {}

    async def fake_geocode(address, city=""):
        geo_called.update(address=address, city=city)
        return 116.410000, 39.990000, "北京市西城区西长安街"

    async def fake_route(mode, olng, olat, dlng, dlat, citycode="", dest_citycode=""):
        assert mode is TravelMode.WALKING
        return RoutePlan(
            mode=TravelMode.WALKING, total_distance_m=1800, total_duration_s=1500,
            legs=[RouteLeg(mode="walking", instruction="沿前门大街向北步行 800 米", distance_m=800, duration_s=650)],
            summary="步行 1.8 公里，约 25 分钟",
        )

    monkeypatch.setattr(amap, "geocode", fake_geocode)
    monkeypatch.setattr(amap, "route", fake_route)
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision({
        "intent": "route", "confidence": 0.92, "destination": "天安门", "travel_mode": "walking"})))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={
                "text": "走去天安门要多久",
                "location": {"latitude": WGS_LAT, "longitude": WGS_LNG},
                "session_id": "s3",
            })
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()
    assert geo_called["address"] == "天安门"
    card = body["cards"][0]
    assert card["type"] == "route"
    assert card["routes"][0]["total_distance_m"] == 1800
    assert "1.8 公里" in card["routes"][0]["summary"]
    assert "1.8 公里" in card["speech"]
    assert body["meta"]["straight_line_m"] > 0


# ------------------------------------------------------------------ 公交字段语义
def test_transit_field_semantics(settings, monkeypatch):
    """回归：高德公交方案里 cost 是「票价（元）」，duration 才是「耗时（秒）」。

    曾经的写法把 cost 当秒数（卡片显示「公交约 1 分钟」），票价又去读一个
    根本不存在的 cost_yuan 字段，于是票价永远是空。这里把两个字段钉死。
    """
    amap = AMapClient(settings)
    payload = {
        "status": "1", "info": "OK",
        "route": {"transits": [
            {"distance": "12400", "duration": "1200", "cost": "6", "walking_distance": "1000",
             "segments": [
                 {"walking": {"distance": "600", "duration": "480",
                              "steps": [{"instruction": "步行至地铁站"}]},
                  "bus": {"buslines": [{"name": "地铁1号线(苹果园--四惠东)", "distance": "10500",
                                        "duration": "1200", "via_num": "9",
                                        "departure_stop": {"name": "国贸"},
                                        "arrival_stop": {"name": "东直门"}}]}},
                 {"walking": {"distance": "400", "duration": "320",
                              "steps": [{"instruction": "步行到达"}]},
                  "bus": {"buslines": [{"name": "地铁2号线", "distance": "1200", "duration": "300",
                                        "via_num": "2",
                                        "departure_stop": {"name": "东直门"},
                                        "arrival_stop": {"name": "T2航站楼"}}]}},
             ]},
            # 另外两个候选方案：里程/耗时都不同，用来验证不会被混进第一个方案里
            {"distance": "15000", "duration": "1500", "cost": "6", "walking_distance": "1200",
             "segments": [{"walking": {"distance": "500", "duration": "400",
                                       "steps": [{"instruction": "备选方案步行"}]},
                           "bus": {"buslines": [{"name": "备选1号线", "distance": "9000",
                                                 "duration": "900", "via_num": "6"}]}}]},
            {"distance": "17800", "duration": "1900", "cost": "7", "walking_distance": "1500",
             "segments": [{"walking": {"distance": "700", "duration": "560",
                                       "steps": [{"instruction": "备选方案二步行"}]},
                           "bus": {"buslines": [{"name": "备选2号线", "distance": "9800",
                                                 "duration": "1100", "via_num": "8"}]}}]},
        ]},
    }

    async def fake_get(path, params):
        assert path == "/v3/direction/transit/integrated"
        # 公交接口缺 city/cityd 会 INVALID_PARAMS，这里确认调用方补齐了
        assert params["city"] == "010" and params["cityd"] == "010"
        return payload

    monkeypatch.setattr(amap, "_get", fake_get)

    async def run():
        return await amap.route(TravelMode.TRANSIT, 116.397, 39.908, 116.603, 40.079,
                                citycode="010", dest_citycode="010")

    plan = asyncio.run(run())
    assert plan.total_duration_s == 1200, "耗时必须取 duration（秒），不是 cost（元）"
    assert plan.cost_yuan == 6.0, "票价必须取 cost（元）"
    assert plan.total_distance_m == 12400, "总里程取方案自身的 distance"
    assert plan.transfer_count == 1, "两条线路 -> 换乘 1 次"
    assert "票价 6 元" in plan.summary and "换乘 1 次" in plan.summary
    # 只展开最优方案：2 段步行 + 2 条线路 = 4 段。
    # 旧实现在这里会返回 14 段，并把三个方案的里程叠加成约三倍。
    assert len(plan.legs) == 4, f"只应展开最优方案的 4 段，实际 {len(plan.legs)} 段"
    assert all("备选" not in leg.line_name for leg in plan.legs if leg.line_name)
    assert sum(leg.distance_m or 0 for leg in plan.legs) < plan.total_distance_m * 2


def test_extract_tags_survives_regex_groups():
    """回归：_TAG_RE 里的货币分支若写成捕获组，findall 只会返回组内容，
    其他分支的匹配全变成空串，标签列表永远是空的。"""
    from app.services.deepseek import _extract_tags

    tags = _extract_tags("保质期 2026-03-01 净含量 250g 售价 ￥19.9 电话 010-12345678")
    for expected in ("保质期", "2026-03-01", "净含量", "￥19.9", "电话"):
        assert expected in tags, f"漏了 {expected}：{tags}"
    assert _extract_tags("") == []


# ------------------------------------------------------------------ 图片意图
def test_image_intent_without_photo_guides_user(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision(
        {"intent": "image", "confidence": 0.9})))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={"text": "帮我看看这张照片", "session_id": "s6"})
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "image"
    assert "相机" in body["reply"], "应引导用户从相机/相册发图，而不是硬答"
    assert body["speech"]


# ------------------------------------------------------------------ 降级
def test_route_without_location_asks_for_it(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision({
        "intent": "route", "confidence": 0.9, "destination": "机场"})))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={"text": "怎么去机场"})
        return r

    r = asyncio.run(run())
    body = r.json()
    assert r.status_code == 200
    assert "定位" in body["reply"]


def test_amap_failure_degrades_to_llm(settings, monkeypatch):
    from app.services.amap import AMapError

    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(amap, "place_around", AsyncMock(side_effect=AMapError("/v3/place/around", "DAILY_QUERY_OVER_LIMIT")))
    monkeypatch.setattr(llm, "classify", AsyncMock(return_value=IntentDecision({
        "intent": "nearby", "confidence": 0.9, "poi_keyword": "医院"})))
    monkeypatch.setattr(llm, "answer_knowledge", AsyncMock(return_value="附近医院信息暂时查不到，建议拨打 120。"))

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/chat", json={
                "text": "附近有医院吗",
                "location": {"latitude": WGS_LAT, "longitude": WGS_LNG},
            })
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["degraded"] is True
    assert "120" in body["reply"]


# ------------------------------------------------------------------ 图片
def test_image_upload_uses_client_ocr_hint(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(llm, "analyze_image", AsyncMock(return_value=ImageAnalysis(
        ocr_text="保质期 2026-03-01", analysis="1. 该食品保质期到 2026 年 3 月 1 日。",
        tags=["保质期", "2026-03-01"], confidence=0.8)))

    async def run():
        app.state.llm = llm
        app.state.orchestrator._llm = llm
        # OCR provider=none，但客户端传了 Vision 结果，应直接采用
        async with await _client(app) as c:
            r = await c.post("/api/v1/analyze-image",
                             files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")},
                             data={"question": "这个还能吃吗", "ocr_text": "保质期 2026-03-01",
                                   "latitude": str(WGS_LAT), "longitude": str(WGS_LNG)})
        return r

    r = asyncio.run(run())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["ocr_provider"] == "ios_vision"
    assert body["analysis"]["ocr_text"] == "保质期 2026-03-01"
    assert body["cards"][0]["type"] == "image_analysis"
    assert body["speech"]


def test_image_rejects_oversize(settings, monkeypatch):
    app, amap, llm, _ = _app_with_stubs(settings, monkeypatch)
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    async def run():
        async with await _client(app) as c:
            r = await c.post("/api/v1/analyze-image",
                             files={"file": ("big.jpg", b"x" * (1024 * 1024 + 10), "image/jpeg")},
                             data={"question": "?"})
        return r

    r = asyncio.run(run())
    assert r.status_code == 413


# ------------------------------------------------------------------ 契约
def test_health_and_openapi(settings):
    app = create_app()

    async def run():
        async with await _client(app) as c:
            h = await c.get("/health")
            o = await c.get("/openapi.json")
        return h, o

    h, o = asyncio.run(run())
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    paths = o.json()["paths"]
    assert "/api/v1/chat" in paths
    assert "/api/v1/analyze-image" in paths
    # 响应契约必须可在 OpenAPI 中看到，供 iOS 端核对
    assert "ChatResponse" in json.dumps(o.json())
