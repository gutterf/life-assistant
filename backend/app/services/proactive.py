"""主动引擎：定时观察画像与作息，主动生成搭话消息（硬框架第 3 层）。

触发规则（全部要求用户最近在场，避免对空房间说话）：
- morning_greet  6:00-10:00 首次在场，当天一次
- meal_nudge     11:30-13:30 / 17:30-19:30 首次在场，结合画像常搜类型与口味
- night_chat     20:00-23:00 首次在场，让 LLM 起一个随机话题
- idle_reconnect 距上次说话超过 8 小时，一条轻搭话

限制：每天最多 max_per_day 条（默认 3），每类型每天一条，失败静默。
设置与队列落盘 backend/data/assistant.json，不碰破甲链路。
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .profile import get_profile

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
_STATE_PATH = _DATA_ROOT / "assistant.json"
_LOCK = threading.Lock()

_TICK_SEC = 60
_ACTIVE_WINDOW_S = 10 * 60  # 10 分钟内说过话才算在场
_IDLE_THRESHOLD_S = 8 * 3600

# 话题池：LLM 失败时的兜底话题
_TOPIC_POOL = (
    "今天有什么新鲜事？",
    "最近在忙什么？",
    "有什么想吃的，我可以帮你找附近的店。",
    "要不要看看明天天气，帮你安排出门？",
    "最近有想去的地方吗，我给你查路线。",
    "有什么烦恼吗，说说看。",
)


def _default_state() -> dict[str, Any]:
    return {
        "enabled": True,
        "max_per_day": 3,
        "sent": {},       # "YYYY-MM-DD" -> {type: 1, ...}
        "queue": [],      # [{id, ts, type, text, read}]
    }


class ProactiveEngine:
    def __init__(self, llm=None) -> None:
        """llm: DeepSeekClient，用于生成闲聊类消息；None 时只用模板。"""
        self._llm = llm
        self._state = _default_state()
        self._load()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------- 状态读写 ----------------
    def _load(self) -> None:
        try:
            if _STATE_PATH.is_file():
                raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    s = _default_state()
                    s.update({k: v for k, v in raw.items() if k in s})
                    self._state = s
        except Exception as exc:  # noqa: BLE001
            log.warning("assistant 状态加载失败: %s", exc)

    def _save(self) -> None:
        with _LOCK:
            try:
                _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                tmp = _STATE_PATH.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, _STATE_PATH)
            except Exception as exc:  # noqa: BLE001
                log.warning("assistant 状态落盘失败: %s", exc)

    def state(self) -> dict[str, Any]:
        return self._state

    def set_enabled(self, on: bool) -> None:
        self._state["enabled"] = bool(on)
        self._save()

    # ---------------- 生命周期 ----------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="proactive-engine", daemon=True)
        self._thread.start()
        log.info("主动引擎已启动（tick=%ds）", _TICK_SEC)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                log.warning("主动引擎 tick 失败: %s", exc)
            self._stop.wait(_TICK_SEC)

    # ---------------- 触发判定 ----------------
    def tick(self) -> None:
        if not self._state["enabled"]:
            return
        profile = get_profile()
        last_ts = profile.data().get("last_user_ts") or 0
        now = time.time()
        if not last_ts or now - last_ts > _ACTIVE_WINDOW_S:
            return  # 用户不在场，不搭话

        lt = time.localtime(now)
        hour, minute = lt.tm_hour, lt.tm_min
        today = time.strftime("%Y-%m-%d", lt)
        sent = self._state["sent"].setdefault(today, {})

        msg: tuple[str, str] | None = None
        if 6 <= hour < 10 and "morning" not in sent:
            msg = ("morning", self._morning_text(profile, lt))
        elif (11 * 60 + 30 <= hour * 60 + minute <= 13 * 60 + 30) and "meal_noon" not in sent:
            msg = ("meal_noon", self._meal_text(profile, "中午"))
        elif (17 * 60 + 30 <= hour * 60 + minute <= 19 * 60 + 30) and "meal_night" not in sent:
            msg = ("meal_night", self._meal_text(profile, "晚上"))
        elif 20 <= hour < 23 and "night" not in sent:
            msg = ("night", self._night_text(profile))
        elif now - last_ts > _IDLE_THRESHOLD_S and "reconnect" not in sent:
            msg = ("reconnect", random.choice(_TOPIC_POOL))

        if msg is None:
            return
        kind, text = msg
        if self._send_count_today(today) >= int(self._state["max_per_day"]):
            return
        sent[kind] = 1
        self._state["queue"].append({
            "id": uuid.uuid4().hex[:10],
            "ts": int(now),
            "type": kind,
            "text": text,
            "read": False,
        })
        self._state["queue"] = self._state["queue"][-30:]
        self._save()
        log.info("主动消息已生成: %s", kind)

    def _send_count_today(self, today: str) -> int:
        return sum(int(v) for v in self._state["sent"].get(today, {}).values())

    # ---------------- 消息文案 ----------------
    def _meal_text(self, profile, label: str) -> str:
        prefs = profile.data().get("poi_prefs") or {}
        tastes = profile.data().get("taste_words") or {}
        kw = max(prefs, key=lambda k: prefs[k]) if prefs else None
        tw = max(tastes, key=lambda k: tastes[k]) if tastes else None
        if kw:
            return f"{label}好，到饭点了。要不要我帮你找找附近的{kw}？" + (f"（记得你偏好{tw}）" if tw else "")
        return f"{label}好，到饭点了。想吃什么？我帮你搜附近的店。"

    def _morning_text(self, profile, lt) -> str:
        prefs = profile.data().get("poi_prefs") or {}
        if prefs:
            kw = max(prefs, key=lambda k: prefs[k])
            return f"早。今天想吃什么的话，附近{kw}随时给你找，出门需要路线就说一声。"
        return "早。今天有什么安排？需要路线、周边或查点什么，随时说。"

    def _night_text(self, profile) -> str:
        if self._llm is not None:
            try:
                block = profile.context_block()
                prompt = ("你是一个生活助手，在晚上主动和用户闲聊。"
                          "用一句不超过 40 字的中文口语搭话，语气自然，不要问候语，"
                          "起一个轻松的话题或问一个有意思的问题。")
                if block:
                    prompt = f"{block}\n{prompt}"
                # 线程里同步跑异步调用
                import asyncio
                text = asyncio.run(self._llm.answer_knowledge(
                    prompt, no_filter=True, model=None, api_key=None))
                text = (text or "").strip()
                if 2 <= len(text) <= 60:
                    return text
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM 生成晚间话题失败，用兜底: %s", exc)
        return random.choice(_TOPIC_POOL)

    # ---------------- 队列接口 ----------------
    def pull(self, mark_read: bool = False) -> dict[str, Any]:
        items = [it for it in self._state["queue"] if not it["read"]]
        if mark_read:
            for it in items:
                it["read"] = True
            self._save()
        return {
            "enabled": bool(self._state["enabled"]),
            "max_per_day": int(self._state["max_per_day"]),
            "items": items,
        }

    def nudge_now(self) -> dict[str, Any]:
        """手动触发一条（绕过时段限制，仍受每日上限约束）。"""
        profile = get_profile()
        lt = time.localtime()
        today = time.strftime("%Y-%m-%d", lt)
        if self._send_count_today(today) >= int(self._state["max_per_day"]):
            return {"ok": False, "reason": "今日已达上限"}
        kinds = [self._night_text(profile), self._morning_text(profile, lt), random.choice(_TOPIC_POOL)]
        text = random.choice(kinds) if random.random() < 0.5 else self._night_text(profile)
        sent = self._state["sent"].setdefault(today, {})
        sent["manual"] = int(sent.get("manual", 0)) + 1
        item = {"id": uuid.uuid4().hex[:10], "ts": int(time.time()), "type": "manual", "text": text, "read": False}
        self._state["queue"].append(item)
        self._state["queue"] = self._state["queue"][-30:]
        self._save()
        return {"ok": True, "item": item}


_engine: ProactiveEngine | None = None


def get_engine(llm=None) -> ProactiveEngine:
    global _engine
    if _engine is None:
        _engine = ProactiveEngine(llm)
    return _engine
