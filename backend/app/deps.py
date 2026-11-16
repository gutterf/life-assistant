"""依赖注入：Orchestrator 及其下游客户端随应用生命周期创建一次。"""

from __future__ import annotations

from fastapi import Request

from .config import Settings, get_settings
from .schemas import API_KEY_HEADER, MODEL_HEADER, NOFILTER_HEADER, ClientOverride, normalize_model
from .services.amap import AMapClient
from .services.deepseek import DeepSeekClient
from .services.ocr import OCRService
from .services.orchestrator import Orchestrator
from .services import filters


def get_client_override(request: Request) -> ClientOverride:
 raw_model = (request.headers.get(MODEL_HEADER) or "").strip()
 model = normalize_model(raw_model) if raw_model else None
 key = (request.headers.get(API_KEY_HEADER) or "").strip() or None
 no_filter = (request.headers.get(NOFILTER_HEADER) or "").strip() == "1" or filters.is_global_nofilter()
 return ClientOverride(model=model, api_key=key, no_filter=no_filter)


def get_settings_dep(request: Request) -> Settings:
    """优先取 lifespan 装填的实例，保证全应用只有一份生效配置。"""
    return getattr(request.app.state, "settings", None) or get_settings()


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_amap(request: Request) -> AMapClient:
    return request.app.state.amap


def get_llm(request: Request) -> DeepSeekClient:
    return request.app.state.llm


def get_ocr(request: Request) -> OCRService:
    return request.app.state.ocr
