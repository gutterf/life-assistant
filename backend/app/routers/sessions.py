"""会话 API：新建 / 列表 / 详情 / 删除 / 重命名。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import sessions

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class CreateReq(BaseModel):
    title: str = ""


class RenameReq(BaseModel):
    title: str


@router.get("")
def list_sessions() -> dict:
    return {"sessions": sessions.list_sessions()}


@router.post("")
def create_session(req: CreateReq | None = None) -> dict:
    s = sessions.create(title=(req.title if req else "") or "")
    return s


@router.get("/{sid}")
def get_session(sid: str) -> dict:
    s = sessions.get(sid)
    if s is None:
        raise HTTPException(404, "会话不存在")
    return sessions.summarize(sid)


@router.delete("/{sid}")
def delete_session(sid: str) -> dict:
    if not sessions.delete(sid):
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


@router.post("/{sid}/rename")
def rename_session(sid: str, req: RenameReq) -> dict:
    if not sessions.rename(sid, req.title):
        raise HTTPException(404, "会话不存在")
    return {"ok": True, "title": req.title}
