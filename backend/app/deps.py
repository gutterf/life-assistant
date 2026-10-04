"""依赖注入：Orchestrator 及其下游客户端随应用生命周期创建一次。"""

from __future__ import annotations

from fastapi import Request

from .config import Settings, get_settings
from .services.amap import AMapClient
from .services.deepseek import DeepSeekClient
from .services.ocr import OCRService
from .services.orchestrator import Orchestrator


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
