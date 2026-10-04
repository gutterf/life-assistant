"""编排层：把「意图判定 -> 高德查数据 -> 生成卡片与话术」这条链收敛在一处。

设计取舍：自然语言回复用确定性模板拼装，不额外调一次大模型。
卡片字段（距离、时间、评分）必须与高德返回严格一致，交给模型复述反而会引入错数。
大模型只用在不可替代的三处：意图判定、常识回答、图片分析。
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Settings
from ..schemas import (Card, CardType, ChatRequest, ChatResponse, GeoPoint, ImageAnalyzeResponse,
                       ImageAnalysis, Intent, PlaceItem, RoutePlan, TravelMode)
from .amap import AMapClient, AMapError
from .coord import format_amap_location, haversine_m, wgs84_to_gcj02
from .deepseek import DeepSeekClient, DeepSeekError, IntentDecision
from .ocr import OCRService

log = logging.getLogger(__name__)

_MODE_LABEL = {
    TravelMode.TRANSIT: "公共交通",
    TravelMode.WALKING: "步行",
    TravelMode.DRIVING: "驾车",
}


class ResolvedLocation:
    __slots__ = ("lng", "lat", "address", "city", "citycode", "source")

    def __init__(self, lng: float, lat: float, address: str = "", city: str = "",
                 citycode: str = "", source: str = "device") -> None:
        self.lng, self.lat = lng, lat
        self.address, self.city, self.citycode, self.source = address, city, citycode, source

    @property
    def label(self) -> str:
        return self.address or self.city or f"{self.lat:.4f}, {self.lng:.4f}"

    @property
    def amap_location(self) -> str:
        return format_amap_location(self.lng, self.lat)


class Orchestrator:
    def __init__(self, settings: Settings, amap: AMapClient, llm: DeepSeekClient, ocr: OCRService) -> None:
        self._s = settings
        self._amap = amap
        self._llm = llm
        self._ocr = ocr

    # ------------------------------------------------------------ 位置解析
    async def resolve_location(self, point: GeoPoint | None, address: str | None,
                               citycode: str | None) -> ResolvedLocation | None:
        """把 iOS 传来的 WGS-84 转成 GCJ-02，并按需补齐结构化地址与城市码。"""
        if point is None:
            return None
        lng, lat = wgs84_to_gcj02(point.longitude, point.latitude)
        info: dict[str, str] = {}
        if not address or not citycode:
            try:
                info = await self._amap.regeo(lng, lat)
            except Exception as exc:  # noqa: BLE001 - 逆地理失败不应阻断主流程
                log.warning("regeo 失败，使用客户端地址兜底: %s", exc)
        return ResolvedLocation(
            lng=lng, lat=lat,
            address=address or info.get("formatted_address", ""),
            city=info.get("city", ""),
            citycode=citycode or info.get("citycode", ""),
        )

    # ------------------------------------------------------------ 主入口
    async def handle_chat(self, req: ChatRequest) -> ChatResponse:
        session_id = req.session_id or "local"
        meta: dict[str, Any] = {}

        location = await self.resolve_location(req.location, req.address, req.citycode)
        if location:
            meta["location"] = {
                "label": location.label,
                "city": location.city,
                "gcj02": [round(location.lng, 6), round(location.lat, 6)],
            }

        decision = await self._llm.classify(
            req.text,
            has_location=location is not None,
            context_hint=req.context_hint,
        )
        meta["intent"] = decision.as_meta()

        handler = {
            Intent.ROUTE: self._handle_route,
            Intent.NEARBY: self._handle_nearby,
            Intent.KNOWLEDGE: self._handle_knowledge,
            Intent.IMAGE: self._handle_image_without_photo,
        }.get(decision.intent)

        if handler is None:
            return await self._handle_knowledge(req, decision, location, session_id, meta)

        try:
            return await handler(req, decision, location, session_id, meta)
        except (AMapError, DeepSeekError) as exc:
            log.warning("意图 %s 处理失败: %s", decision.intent.value, exc)
            return await self._fallback(req, decision, location, session_id, meta, str(exc))

    # ------------------------------------------------------------ 路线规划
    async def _handle_route(self, req: ChatRequest, decision: IntentDecision,
                            location: ResolvedLocation | None, session_id: str,
                            meta: dict[str, Any]) -> ChatResponse:
        if location is None:
            return self._need_location(session_id, meta,
                                       "规划路线需要先知道你在哪，点一下定位按钮就好。")

        destination_name = decision.destination or decision.search_query
        if not destination_name:
            return await self._handle_knowledge(req, decision, location, session_id, meta)

        d_lng, d_lat, d_label = await self._amap.geocode(destination_name, decision.destination_city or location.city or "")
        dest_citycode = ""
        try:
            dest_info = await self._amap.regeo(d_lng, d_lat)
            dest_citycode = dest_info.get("citycode", "")
            if not decision.destination_city:
                d_label = dest_info.get("formatted_address") or d_label
        except Exception as exc:  # noqa: BLE001
            log.info("目的地 regeo 失败，忽略: %s", exc)

        mode = decision.travel_mode or TravelMode.TRANSIT
        plan = await self._amap.route(
            mode, location.lng, location.lat, d_lng, d_lat,
            citycode=location.citycode, dest_citycode=dest_citycode,
        )
        straight = int(haversine_m(location.lng, location.lat, d_lng, d_lat))
        meta["destination"] = {"name": d_label, "gcj02": [round(d_lng, 6), round(d_lat, 6)]}
        meta["straight_line_m"] = straight

        card = Card(
            type=CardType.ROUTE,
            title=f"到 {d_label}",
            subtitle=f"{_MODE_LABEL[mode]} · 直线 {straight} 米",
            speech=f"从{location.label}到{d_label}，{plan.summary}。",
            routes=[plan],
        )
        reply = (f"从**{location.label}**到**{d_label}**，{plan.summary}。\n"
                 f"直线距离 {straight} 米，实际路线 {plan.total_distance_m} 米。")
        if mode is TravelMode.TRANSIT and plan.transfer_count:
            reply += f"\n需要换乘 {plan.transfer_count} 次。"
        return ChatResponse(session_id=session_id, intent=Intent.ROUTE, reply=reply,
                            cards=[card], speech=card.speech, meta=meta)

    # ------------------------------------------------------------ 周边搜索
    async def _handle_nearby(self, req: ChatRequest, decision: IntentDecision,
                             location: ResolvedLocation | None, session_id: str,
                             meta: dict[str, Any]) -> ChatResponse:
        if location is None:
            return self._need_location(session_id, meta,
                                       "周边搜索需要定位，打开定位后我就能帮你找。")

        radius = decision.radius_m or self._s.default_radius_m
        radius = max(200, min(radius, self._s.max_radius_m))
        keyword = decision.poi_keyword or decision.search_query or "生活服务"
        # 6 位纯数字视为高德分类码，否则当自然语言关键词用
        is_type_code = keyword.isdigit() and len(keyword) == 6

        places = await self._amap.place_around(
            location.lng, location.lat,
            keywords="" if is_type_code else keyword,
            radius_m=radius,
            poi_type=keyword if is_type_code else None,
            limit=20,
        )
        meta["radius_m"] = radius
        meta["keyword"] = keyword
        meta["result_count"] = len(places)

        if not places:
            return ChatResponse(
                session_id=session_id, intent=Intent.NEARBY,
                reply=f"{radius // 1000} 公里内没有找到与「{keyword}」匹配的地点，换个关键词试试。",
                meta=meta,
            )

        card = Card(
            type=CardType.PLACE_LIST,
            title=f"{keyword} · 附近结果",
            subtitle=f"半径 {radius // 1000} 公里 · 共 {len(places)} 家",
            speech=_places_speech(places, radius),
            places=places,
        )
        top = places[0]
        best_rated = max((p for p in places if p.rating), key=lambda p: p.rating or 0, default=None)
        reply = f"以**{location.label}**为中心，{radius // 1000} 公里内找到 {len(places)} 家{keyword}。\n"
        reply += f"最近的是 {top.name}" + (f"，{top.distance_m} 米" if top.distance_m is not None else "") + "。"
        if best_rated and best_rated is not top and best_rated.rating:
            reply += f"\n评分最高的是 {best_rated.name}，{best_rated.rating} 分。"
        return ChatResponse(session_id=session_id, intent=Intent.NEARBY, reply=reply,
                            cards=[card], speech=card.speech, meta=meta)

    # ------------------------------------------------------------ 常识问答
    async def _handle_knowledge(self, req: ChatRequest, decision: IntentDecision,
                                location: ResolvedLocation | None, session_id: str,
                                meta: dict[str, Any]) -> ChatResponse:
        try:
            answer = await self._llm.answer_knowledge(
                req.text, location_label=location.label if location else None)
        except DeepSeekError as exc:
            log.warning("常识问答失败: %s", exc)
            answer = "我这边暂时连不上知识服务，稍后再问一次试试。"
        card = Card(type=CardType.TEXT, title="回答", text=answer, speech=answer)
        return ChatResponse(session_id=session_id, intent=Intent.KNOWLEDGE, reply=answer,
                            cards=[card], speech=answer, meta=meta)

    # ------------------------------------------------------------ 图片分析
    async def _handle_image_without_photo(self, req: ChatRequest, decision: IntentDecision,
                                          location: ResolvedLocation | None, session_id: str,
                                          meta: dict[str, Any]) -> ChatResponse:
        """文字里说要看图、但这一轮没带图片。

        直接当成常识问题回答是错的：用户明显在等一个「看图」的结果，
        这里明确告诉他图片要从哪进来，并把当前定位状态一并告诉他。
        """
        text = ("要分析图片的话，点输入栏左边的相机图标，拍照或从相册选一张，"
                "再补一句想问什么（比如「这个还能吃吗」）就行。")
        if location is None:
            text += "\n顺便说一句，现在还没定位，打开定位后我能结合拍摄地点一起判断。"
        return ChatResponse(
            session_id=session_id, intent=Intent.IMAGE, reply=text,
            cards=[Card(type=CardType.TEXT, title="怎么发图片", text=text, speech=text)],
            speech=text, meta=meta,
        )

    async def handle_image(self, *, image_bytes: bytes, question: str, client_ocr_text: str | None,
                           point: GeoPoint | None, address: str | None, citycode: str | None,
                           session_id: str) -> ImageAnalyzeResponse:
        meta: dict[str, Any] = {}
        location = await self.resolve_location(point, address, citycode)
        ocr_text, provider = await self._ocr.extract(image_bytes, client_ocr_text)
        meta["ocr_provider"] = provider
        meta["image_bytes"] = len(image_bytes)
        if location:
            meta["location"] = {"label": location.label, "city": location.city}

        try:
            analysis = await self._llm.analyze_image(
                ocr_text=ocr_text, question=question,
                location_label=location.label if location else None,
                coordinates=(point.latitude, point.longitude) if point else None,
            )
        except DeepSeekError as exc:
            log.warning("图片分析失败: %s", exc)
            analysis = ImageAnalysis(
                ocr_text=ocr_text,
                analysis="已提取图片文字，但分析服务暂时不可用。识别到的文字见下方。",
                tags=[],
                confidence=0.2,
            )

        card = Card(
            type=CardType.IMAGE_ANALYSIS,
            title="图片分析",
            subtitle=f"识别 {len(ocr_text)} 字 · {provider}",
            speech=analysis.analysis,
            image=analysis,
        )
        return ImageAnalyzeResponse(session_id=session_id, analysis=analysis,
                                    reply=analysis.analysis, cards=[card],
                                    speech=analysis.analysis, meta=meta)

    # ------------------------------------------------------------ 兜底
    def _need_location(self, session_id: str, meta: dict[str, Any], text: str) -> ChatResponse:
        return ChatResponse(session_id=session_id, intent=Intent.UNKNOWN, reply=text,
                            cards=[Card(type=CardType.TEXT, title="需要定位", text=text, speech=text)],
                            speech=text, meta=meta)

    async def _fallback(self, req: ChatRequest, decision: IntentDecision,
                        location: ResolvedLocation | None, session_id: str,
                        meta: dict[str, Any], reason: str) -> ChatResponse:
        """地图服务不可用时，退回让大模型基于自身知识尽量回答，而不是直接报错。"""
        meta["degraded"] = True
        meta["reason"] = reason[:200]
        try:
            answer = await self._llm.answer_knowledge(
                f"用户问：{req.text}\n（地图检索服务暂时不可用，请基于常识回答，"
                f"不要编造具体的店名、距离或路线数据。）",
                location_label=location.label if location else None,
            )
        except DeepSeekError:
            answer = "地图服务暂时不可用，稍后再试一次。"
        return ChatResponse(session_id=session_id, intent=decision.intent, reply=answer,
                            cards=[Card(type=CardType.TEXT, title="降级回答", text=answer, speech=answer)],
                            speech=answer, meta=meta)


def _places_speech(places: list[PlaceItem], radius_m: int) -> str:
    top = places[:3]
    head = f"{radius_m // 1000} 公里内找到 {len(places)} 家。"
    parts = []
    for i, p in enumerate(top, 1):
        seg = f"第{i}家，{p.name}"
        if p.distance_m is not None:
            seg += f"，距离 {p.distance_m} 米"
        if p.rating:
            seg += f"，评分 {p.rating} 分"
        parts.append(seg)
    return head + "。".join(parts) + "。"
