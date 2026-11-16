# -*- coding: utf-8 -*-
"""卫星回复开关 + 会话归档 端到端验证。"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=180) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def chat(text, sid):
    body = {
        "text": text,
        "session_id": sid,
        "location": {"latitude": 29.4597, "longitude": 119.9091},
    }
    return req("POST", "/api/v1/chat", body)


ok = 0
fail = 0


def check(name, cond, detail=""):
    global ok, fail
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(detail)[:120]) if detail else ""))
    if cond:
        ok += 1
    else:
        fail += 1


# 1. 开关开
_, s = req("POST", "/api/v1/satellite/toggle", {"enabled": True})
check("卫星开关开启", s.get("enabled") is True, s)

# 2. 聊天应带坐标抬头
st, r = chat("附近有什么好吃的？", "sat-test-1")
reply = r.get("reply", "")
check("聊天200", st == 200, st)
check("回复带坐标抬头", reply.split("\n")[0].strip().count(",") == 1
      and "你站在" in reply, reply[:120])

# 3. 关掉后正常
_, s = req("POST", "/api/v1/satellite/toggle", {"enabled": False})
st, r = chat("1加1等于几", "sat-test-2")
reply = r.get("reply", "")
first = reply.split("\n")[0].strip()
check("关闭后不带坐标抬头", "你站在" not in reply and "," not in first, reply[:120])

# 4. 会话归档
_, created = req("POST", "/api/v1/sessions", {"title": ""})
sid = created.get("id")
check("创建会话", bool(sid), created)
st, _ = chat("你好，测试会话", sid)
time.sleep(0.5)
_, lst = req("GET", "/api/v1/sessions")
found = [x for x in lst.get("sessions", []) if x["id"] == sid]
check("会话出现在列表", len(found) == 1, found)
check("会话有消息", found[0]["count"] >= 2 if found else False, found[0] if found else None)
_, detail = req("GET", "/api/v1/sessions/" + sid)
check("会话详情含消息", len(detail.get("messages", [])) >= 2, len(detail.get("messages", [])))
_, d = req("DELETE", "/api/v1/sessions/" + sid)
check("删除会话", d.get("ok") is True, d)
_, lst2 = req("GET", "/api/v1/sessions")
check("删除后列表无此会话", not any(x["id"] == sid for x in lst2.get("sessions", [])))

# 5. 破甲链路不受影响
_, st_pojia = req("GET", "/api/v1/pojia/status")
check("破甲状态接口200", st_pojia == 200, st_pojia)

print("\n%d/%d 通过" % (ok, ok + fail))
sys.exit(0 if fail == 0 else 1)
