"""聊天主接口：/api/v1/chat"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import ClientOverride, get_client_override, get_orchestrator
from ..schemas import ChatRequest, ChatResponse, NavigateRequest, NavigateResponse
from ..services.deepseek import DeepSeekError
from ..services.orchestrator import Orchestrator

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="文字提问（可带经纬度）")
async def chat(
 payload: ChatRequest,
 orchestrator: Orchestrator = Depends(get_orchestrator),
 override: ClientOverride = Depends(get_client_override),
) -> ChatResponse:
    if not payload.location and not any(
        kw in payload.text for kw in ("是什么", "为什么", "怎么做", "请问", "介绍")
    ):
        log.info("无定位请求，意图可能受限: %s", payload.text[:40])
    try:
        resp = await orchestrator.handle_chat(payload, override)
    except DeepSeekError as exc:
        # 大模型完全不可用时才返回 503，前端据此展示重试
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"模型服务不可用: {exc}") from exc
    # 会话归档：消息持久化到 data/sessions/<session_id>.json（失败不影响回复）
    try:
        from ..services import sessions
        sid = payload.session_id or "local"
        sessions.append_message(sid, "user", payload.text)
        sessions.append_message(sid, "assistant", resp.reply)
    except Exception: # noqa: BLE001
        pass
    return resp


@router.post("/navigate", response_model=NavigateResponse, summary="点选地点后开启导航")
async def navigate(
 payload: NavigateRequest,
 orchestrator: Orchestrator = Depends(get_orchestrator),
) -> NavigateResponse:
    return await orchestrator.handle_navigate(payload, payload.session_id or "local")
