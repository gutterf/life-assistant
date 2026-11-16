"""前后端共享的接口契约。iOS 端的 Codable 模型与此一一对应。"""

from __future__ import annotations

from dataclasses import dataclass
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
 # GCJ-02 坐标，供客户端「点选 → 定位 → 导航」
 lng: float | None = None
 lat: float | None = None


class NavigateRequest(BaseModel):
 origin: GeoPoint
 dest: GeoPoint
 dest_name: str = ""
 mode: TravelMode = TravelMode.DRIVING
 citycode: str | None = None
 session_id: str | None = None


class NavigateResponse(BaseModel):
 session_id: str
 reply: str
 cards: list[Card] = Field(default_factory=list)
 speech: str | None = None
 # 高德网页版导航链接（无需 key，可直接打开跳转导航）
 amap_web_url: str | None = None


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


# ---- App 端模型 / 密钥覆盖 ----

# 请求头名：后端据此按次覆盖 .env 里的模型与 key
MODEL_HEADER = "X-LifeAssistant-Model"
API_KEY_HEADER = "X-LifeAssistant-Api-Key"
NOFILTER_HEADER = "X-LifeAssistant-NoFilter"

# DeepSeek 开放平台当前有效模型名（2026-11 实测）
_VALID_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner", "deepseek-flash"}


def normalize_model(name: str | None, default: str = "deepseek-v4-flash") -> str:
    """把客户端传来的任意模型名变体归一化到 DeepSeek 开放平台有效名。

    覆盖：deepseek-v4.1-flash-1017 / v4.1 系列 / v3 / r1 / chat / reasoner 等变体。
    非法或未知名字一律回落到 deepseek-v4-flash。
    """
    if not name:
        return default
    n = str(name).strip().lower()
    if "v4.1" in n or "1017" in n:
        n = "deepseek-v4-flash"
    elif "pro" in n:
        n = "deepseek-v4-pro"
    elif "reason" in n or n.endswith("r1"):
        n = "deepseek-reasoner"
    elif any(k in n for k in ("chat", "flash", "v4", "v3")):
        n = "deepseek-v4-flash"
    if n not in _VALID_MODELS:
        n = default
    return n


@dataclass(frozen=True)
class ClientOverride:
    """单次请求的模型 / 密钥覆盖。字段为 None 表示沿用服务器配置。"""

    model: str | None = None
    api_key: str | None = None
    no_filter: bool = False

    @property
    def enabled(self) -> bool:
        return self.model is not None or self.api_key is not None
