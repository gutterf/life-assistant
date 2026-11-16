"""硬框架端到端验证：画像学习 -> 注入 -> 主动消息 -> 破甲链路无破坏。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    # 1. 画像初始为空
    s, d = req("GET", "/api/v1/assistant/profile")
    print("1 profile:", s, "last_user_ts=", d["data"]["last_user_ts"], "block=", repr(d["context_block"])[:60])

    # 2. 发一轮聊天（带定位，触发学习）
    s, d = req("POST", "/api/v1/chat", {
        "text": "附近有什么好吃的火锅", "session_id": "frame-1",
        "location": {"latitude": 29.4597, "longitude": 119.9091},
    }, timeout=120)
    print("2 chat:", s, "intent=", d.get("intent"), "reply=", d.get("reply", "")[:50])

    # 3. 画像已学习
    s, d = req("GET", "/api/v1/assistant/profile")
    dd = d["data"]
    print("3 profile:", s, "poi_prefs=", dd["poi_prefs"], "active_hours=", dd["active_hours"],
          "block=", d["context_block"][:80])

    # 4. 主动引擎状态与手动触发
    s, d = req("GET", "/api/v1/assistant/proactive")
    print("4 proactive:", s, "enabled=", d["enabled"])
    s, d = req("POST", "/api/v1/assistant/nudge")
    print("5 nudge:", s, d.get("ok"), (d.get("item") or {}).get("text", "")[:60])

    # 5. 拉取主动消息（未读）
    s, d = req("GET", "/api/v1/assistant/proactive?mark_read=1")
    items = d["items"]
    print("6 pull:", s, "unread=", len(items), "text=", (items[0]["text"][:60] if items else "-"))

    # 6. 开关 toggle
    s, d = req("POST", "/api/v1/assistant/toggle", {"enabled": True})
    print("7 toggle:", s, "enabled=", d["enabled"])

    # 7. 破甲链路未破坏
    s, d = req("GET", "/api/v1/pojia/status", timeout=20)
    print("8 pojia:", s, "nofilter_global=", d.get("nofilter_global"), "seats=", d.get("seats"))


if __name__ == "__main__":
    main()
