"""会话管理：多会话持久化（backend/data/sessions/<id>.json）。

每个会话一个 JSON：{id, title, created, updated, messages:[{role,text,ts}]}
chat 请求带 session_id 时自动归档消息；不带的会话标题取第一句前 20 字。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

SESS_DIR = Path(__file__).resolve().parents[2] / "data" / "sessions"
_LOCK = threading.Lock()


def _ensure() -> None:
    SESS_DIR.mkdir(parents=True, exist_ok=True)


def _path(sid: str) -> Path:
    return SESS_DIR / f"{sid}.json"


def _load(sid: str) -> Optional[dict]:
    p = _path(sid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save(s: dict) -> None:
    _ensure()
    _path(s["id"]).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def create(title: str = "") -> dict:
    with _LOCK:
        s = {
            "id": uuid.uuid4().hex[:12],
            "title": (title or "新会话").strip()[:40] or "新会话",
            "created": time.time(),
            "updated": time.time(),
            "messages": [],
        }
        _save(s)
        return s


def get(sid: str) -> Optional[dict]:
    return _load(sid)


def list_sessions(limit: int = 100) -> list[dict]:
    _ensure()
    out = []
    for p in sorted(SESS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        s = _load(p.stem)
        if s:
            out.append(
                {
                    "id": s["id"],
                    "title": s["title"],
                    "created": s.get("created", 0),
                    "updated": s.get("updated", 0),
                    "count": len(s.get("messages", [])),
                }
            )
        if len(out) >= limit:
            break
    return out


def delete(sid: str) -> bool:
    with _LOCK:
        p = _path(sid)
        if p.is_file():
            p.unlink()
            return True
        return False


def rename(sid: str, title: str) -> bool:
    with _LOCK:
        s = _load(sid)
        if not s:
            return False
        s["title"] = (title or "新会话").strip()[:40] or "新会话"
        s["updated"] = time.time()
        _save(s)
        return True


def append_message(sid: str, role: str, text: str, auto_title: bool = True) -> None:
    """追加一条消息；不存在的会话自动创建（title 取第一句）。"""
    with _LOCK:
        s = _load(sid)
        if s is None:
            s = {
                "id": sid,
                "title": (text or "").strip()[:20] or "新会话",
                "created": time.time(),
                "updated": time.time(),
                "messages": [],
            }
        if auto_title and s["title"] in ("新会话", "") and role == "user" and text:
            s["title"] = text.strip()[:20]
        s["messages"].append({"role": role, "text": text, "ts": time.time()})
        s["updated"] = time.time()
        _save(s)


def messages(sid: str) -> list[dict]:
    s = _load(sid)
    return s.get("messages", []) if s else []


def summarize(sid: str) -> dict[str, Any]:
    s = _load(sid)
    if not s:
        return {"id": sid, "title": "新会话", "count": 0, "messages": []}
    return {
        "id": s["id"],
        "title": s["title"],
        "created": s.get("created", 0),
        "updated": s.get("updated", 0),
        "messages": s.get("messages", []),
    }
