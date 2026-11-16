"""生活画像：位置模型（家/公司/常去）、偏好模型（口味/出行/话题）、作息模型。

硬框架第 1 层。所有数据落盘 backend/data/profile.json，
每次聊天结束后 observe 异步学习；context_block() 生成注入用的画像摘要。

原则：只学习，不打扰 —— observe 失败静默，画像注入纯文本拼接，不碰破甲链路。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
_PROFILE_PATH = _DATA_ROOT / "profile.json"
_WRITE_LOCK = threading.Lock()

# 时段分界：早上/下午/晚上/深夜
_MORNING, _AFTERNOON, _EVENING, _NIGHT = 5, 12, 18, 23


def _default() -> dict[str, Any]:
    return {
        "version": 1,
        "home": None,        # {lat,lng,label,city,n}
        "office": None,
        "places": [],        # [{name,lat,lng,city,n,last_at}]
        "poi_prefs": {},     # keyword -> count
        "taste_words": {},   # 口味词 -> count
        "route_modes": {},   # driving/transit/walking -> count
        "topics": {},        # intent -> count
        "interest_words": {},  # 知识问答里的高频主题词 -> count
        "active_hours": {},  # hour -> count
        "last_user_ts": 0,
        "greeted_days": [],  # 已发过早安消息的日期 YYYY-MM-DD
    }


class Profile:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _PROFILE_PATH
        self._data: dict[str, Any] = _default()
        self._dirty = False
        self._load()

    # ---------------- 读写 ----------------
    def _load(self) -> None:
        try:
            if not self.path.is_file():
                return
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = _default()
                self._data.update({k: v for k, v in raw.items() if k in self._data})
        except Exception as exc:  # noqa: BLE001
            log.warning("profile 加载失败，用空画像: %s", exc)

    def save(self) -> None:
        with _WRITE_LOCK:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            except Exception as exc:  # noqa: BLE001
                log.warning("profile 落盘失败: %s", exc)

    def data(self) -> dict[str, Any]:
        return self._data

    # ---------------- 学习入口 ----------------
    def observe_chat(self, *, text: str, intent: str, location: dict[str, Any] | None,
                     poi_keyword: str | None = None,
                     route_mode: str | None = None,
                     destination: str | None = None) -> None:
        """聊天一轮结束后调用。全部字段可选，逐项增量学习。"""
        now = time.time()
        hour = time.localtime(now).tm_hour
        self._bump(self._data["active_hours"], str(hour))
        self._bump(self._data["topics"], intent or "unknown")
        self._data["last_user_ts"] = int(now)

        if location and all(k in location for k in ("lat", "lng")):
            self._learn_place(now, float(location["lng"]), float(location["lat"]),
                              str(location.get("label") or ""),
                              str(location.get("city") or ""))
        if poi_keyword:
            kw = poi_keyword.strip()
            if kw and not kw.isdigit():
                self._bump(self._data["poi_prefs"], kw)
        for w in _TASTE_WORDS:
            if w in text:
                self._bump(self._data["taste_words"], w)
        if route_mode:
            self._bump(self._data["route_modes"], route_mode)

    def observe_navigate(self, *, dest_name: str, dest: dict[str, Any], mode: str | None) -> None:
        now = time.time()
        if mode:
            self._bump(self._data["route_modes"], mode)
        if not dest_name or "lat" not in dest or "lng" not in dest:
            return
        for p in self._data["places"]:
            if p["name"] == dest_name:
                p["n"] += 1
                p["last_at"] = int(now)
                self._data["places"].sort(key=lambda x: x["n"], reverse=True)
                return
        self._data["places"].append({
            "name": dest_name, "lat": float(dest["lat"]), "lng": float(dest["lng"]),
            "city": "", "n": 1, "last_at": int(now),
        })
        self._data["places"] = self._data["places"][:30]

    def observe_knowledge(self, text: str) -> None:
        for w in _INTEREST_WORDS:
            if w in text:
                self._bump(self._data["interest_words"], w)

    def _bump(self, counter: dict, key: str, n: int = 1) -> None:
        counter[key] = int(counter.get(key, 0)) + n

    def _learn_place(self, now: float, lng: float, lat: float, label: str, city: str) -> None:
        hour = time.localtime(now).tm_hour
        # 活跃时段把定位当成观察到的地点
        if _MORNING <= hour < _AFTERNOON:
            self._cluster_into("office", now, lng, lat, label, city)
        elif _EVENING <= hour < _NIGHT or hour < _MORNING:
            self._cluster_into("home", now, lng, lat, label, city)
        # 午/晚之间不判定，避免逛街位置被误当固定点

    def _cluster_into(self, key: str, now: float, lng: float, lat: float,
                      label: str, city: str) -> None:
        cur = self._data.get(key)
        if not cur:
            self._data[key] = {"lat": lat, "lng": lng, "label": label,
                               "city": city, "n": 1, "last_at": int(now)}
            return
        # 距现聚类点 > 3km 视为新观察：慢速漂移（权重 1/n），避免一次出差把家搬走
        from .coord import haversine_m  # 局部导入，避免循环
        try:
            d = haversine_m(cur["lng"], cur["lat"], lng, lat)
        except Exception:  # noqa: BLE001
            d = 1e9
        n = int(cur.get("n", 1))
        if d > 3000:
            if n >= 5:
                return  # 已稳定，不漂移
            w = 1 / (n + 1)
        else:
            w = 0.4  # 同点观察快速收敛
        cur["lat"] = cur["lat"] * (1 - w) + lat * w
        cur["lng"] = cur["lng"] * (1 - w) + lng * w
        cur["n"] = n + 1
        cur["last_at"] = int(now)
        if label:
            cur["label"] = label
        if city:
            cur["city"] = city

    def mark_greeted(self, day: str) -> bool:
        days = self._data["greeted_days"]
        if day in days:
            return False
        days.append(day)
        self._data["greeted_days"] = days[-14:]
        return True

    # ---------------- 注入导出 ----------------
    def context_block(self, max_len: int = 600) -> str:
        """生成注入给模型的画像摘要。无数据时返回空串。"""
        parts: list[str] = []
        d = self._data
        if d.get("home"):
            h = d["home"]
            parts.append(f"家：{h.get('label') or '已定位'}（约 {h['lat']:.4f}, {h['lng']:.4f}）")
        if d.get("office"):
            o = d["office"]
            parts.append(f"公司/常驻点：{o.get('label') or '已定位'}（约 {o['lat']:.4f}, {o['lng']:.4f}）")
        if d.get("places"):
            top = [p["name"] for p in d["places"][:5]]
            parts.append("常去地点：" + "、".join(top))
        if d.get("poi_prefs"):
            top = [k for k, _ in Counter(d["poi_prefs"]).most_common(5)]
            parts.append("常搜的周边类型：" + "、".join(top))
        if d.get("taste_words"):
            tw = [k for k, _ in Counter(d["taste_words"]).most_common(4)]
            parts.append("口味偏好关键词：" + "、".join(tw))
        if d.get("route_modes"):
            mode = Counter(d["route_modes"]).most_common(1)[0][0]
            parts.append(f"常用出行方式：{mode}")
        if d.get("interest_words"):
            top = [k for k, _ in Counter(d["interest_words"]).most_common(6)]
            parts.append("常聊话题：" + "、".join(top))
        if d.get("active_hours"):
            ah = Counter({k: v for k, v in d["active_hours"].items() if k.isdigit()})
            if ah:
                top_h = int(ah.most_common(1)[0][0])
                parts.append(f"最常活跃时段：{top_h} 点左右")
        block = "【用户生活画像】" + "；".join(parts) + "。"
        return block[:max_len] if parts else ""

    def top_poi_keyword(self, fallback: str) -> str:
        prefs = Counter(self._data.get("poi_prefs") or {})
        return prefs.most_common(1)[0][0] if prefs else fallback

    def home_anchor(self) -> dict[str, Any] | None:
        return self._data.get("home")


_TASTE_WORDS = ("辣", "麻辣", "清淡", "便宜", "贵", "环境好", "安静", "热闹", "甜",
                "酸", "快餐", "小吃", "火锅", "烧烤", "面", "咖啡", "奶茶", "酒吧", "健身")
_INTEREST_WORDS = ("游戏", "电影", "电视剧", "音乐", "小说", "动漫", "旅行", "健身",
                   "跑步", "做饭", "摄影", "汽车", "数码", "股票", "基金", "宠物",
                   "猫", "狗", "足球", "篮球", "编程", "英语", "考试", "养生", "减肥")

_profile_singleton: Profile | None = None


def get_profile() -> Profile:
    global _profile_singleton
    if _profile_singleton is None:
        _profile_singleton = Profile()
    return _profile_singleton
