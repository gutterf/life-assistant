"""前后端共享的接口契约。iOS 端的 Codable 模型与此一一对应。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    ROUTE = "route"        # 路线规划
    NEARBY = "nearby"      # 周边搜索
    IMAGE = "image"        # 拍照 / 选图分析
    KNOWLEDGE = "knowledge"  # 生活常识
    UNKNOWN = "unknown"


class TravelMode(str, Enum):
    TRANSIT = "transit"
    WALKING = "walking"
    DRIVING = "driving"


class CardType(str, Enum):
    PLACE_LIST = "place_list"
    ROUTE = "route"
    IMAGE_ANALYSIS = "image_analysis"
    TEXT = "text"


class GeoPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_m: float | None = None


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    location: GeoPoint | None = None
    # 客户端 CoreLocation 逆地理结果，可省一次后端调用
    address: str | None = None
    citycode: str | None = None
    session_id: str | None = None
    # 上一次会话里出现过的地点，供「去那儿」这类指代消解
    context_hint: str | None = None


class PlaceItem(BaseModel):
    name: str
    rating: float | None = None
    distance_m: int | None = None
    address: str | None = None
    phone: str | None = None
    category: str | None = None


class RouteLeg(BaseModel):
    mode: str
    instruction: str
    distance_m: int | None = None
    duration_s: int | None = None
    line_name: str | None = None


class RoutePlan(BaseModel):
    mode: TravelMode
    total_distance_m: int
    total_duration_s: int
    cost_yuan: float | None = None
    transfer_count: int | None = None
    legs: list[RouteLeg] = Field(default_factory=list)
    summary: str


class ImageAnalysis(BaseModel):
    ocr_text: str = ""
    analysis: str
    tags: list[str] = Field(default_factory=list)
    confidence: float | None = None


class Card(BaseModel):
    type: CardType
    title: str
    subtitle: str | None = None
    # 该卡片被展示时用于语音播报的文本
    speech: str | None = None
    places: list[PlaceItem] = Field(default_factory=list)
    routes: list[RoutePlan] = Field(default_factory=list)
    image: ImageAnalysis | None = None
    text: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    intent: Intent
    reply: str
    cards: list[Card] = Field(default_factory=list)
    speech: str | None = None
    meta: dict = Field(default_factory=dict)


class ImageAnalyzeResponse(BaseModel):
    session_id: str
    analysis: ImageAnalysis
    reply: str
    cards: list[Card] = Field(default_factory=list)
    speech: str | None = None
    meta: dict = Field(default_factory=dict)
