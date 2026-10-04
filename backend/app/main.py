"""FastAPI 应用入口。

本地启动：
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import chat, upload
from .services.amap import AMapClient, AMapError
from .services.deepseek import DeepSeekClient, DeepSeekError
from .services.ocr import OCRService
from .services.orchestrator import Orchestrator


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _configure_logging(settings.log_level)
    log = logging.getLogger("life-assistant")

    missing = settings.missing_required()
    if missing:
        log.warning("以下环境变量未配置，相关功能会降级: %s", ", ".join(missing))
    else:
        log.info("配置校验通过")

    app.state.settings = settings
    app.state.amap = AMapClient(settings)
    app.state.llm = DeepSeekClient(settings)
    app.state.ocr = OCRService(settings)
    app.state.orchestrator = Orchestrator(settings, app.state.amap, app.state.llm, app.state.ocr)
    log.info("生活助手后端已就绪")
    try:
        yield
    finally:
        await app.state.amap.aclose()
        await app.state.llm.aclose()
        log.info("已释放下游连接")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="生活助手后端",
        version="1.0.0",
        description="CoreLocation 定位 + DeepSeek 意图判定 + 高德地图路线/周边检索 + 图片 OCR 分析",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat.router)
    app.include_router(upload.router)

    @app.exception_handler(AMapError)
    async def _amap_error(_: Request, exc: AMapError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": "amap_error", "endpoint": exc.endpoint, "message": exc.info},
        )

    @app.exception_handler(DeepSeekError)
    async def _llm_error(_: Request, exc: DeepSeekError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": "deepseek_error", "message": str(exc)})

    @app.get("/health", tags=["ops"], summary="健康检查")
    async def health() -> dict:
        return {
            "status": "ok",
            "configured": not settings.missing_required(),
            "missing": settings.missing_required(),
            "ocr_provider": settings.ocr_provider,
            "default_radius_m": settings.default_radius_m,
        }

    return app


app = create_app()
