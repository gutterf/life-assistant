"""生活框架路由：主动消息队列 + 画像查看 + 开关。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..services.proactive import get_engine
from ..services.profile import get_profile

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/proactive")
async def proactive(request: Request, mark_read: int = 0) -> dict:
    eng = get_engine(getattr(request.app.state, "llm", None))
    return eng.pull(mark_read=bool(mark_read))


@router.get("/profile")
async def profile_view() -> dict:
    p = get_profile()
    return {"data": p.data(), "context_block": p.context_block()}


@router.post("/toggle")
async def toggle(body: ToggleBody, request: Request) -> dict:
    eng = get_engine(getattr(request.app.state, "llm", None))
    eng.set_enabled(body.enabled)
    return {"enabled": eng.state()["enabled"]}


@router.post("/nudge")
async def nudge(request: Request) -> dict:
    eng = get_engine(getattr(request.app.state, "llm", None))
    return eng.nudge_now()
