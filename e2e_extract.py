# -*- coding: utf-8 -*-
"""视频链接 -> 提取人声 -> 克隆 -> TTS 全链路。"""
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.bilibili.com/video/BV1GJ411x7h7"

c = httpx.Client(base_url=BASE, trust_env=False,
                 timeout=httpx.Timeout(420.0, connect=5.0, write=120.0))

r = c.post("/api/v1/voice/extract", json={"url": URL})
print("EXTRACT", r.status_code, r.text[:200])
if r.status_code != 200:
    sys.exit(1)
jid = r.json()["job_id"]

vid = None
t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(4)
    j = c.get(f"/api/v1/voice/job/{jid}").json()
    print("%5.0fs %-12s %s %s" % (time.time() - t0, j.get("status"), j.get("progress"), (j.get("error") or "")[:120]))
    if j.get("status") in ("done", "failed"):
        vid = j.get("voice_id")
        break
if not vid:
    print("NO_VOICE"); sys.exit(2)

r = c.post("/api/v1/voice/tts", json={"text": "这是从视频里提取出来的声音，现在用它说一句话。", "voice_id": vid})
print("TTS", r.status_code, r.text[:200])
if r.status_code == 200:
    u = r.json()["url"]
    a = c.get(u)
    out = r"C:\Users\admin\Documents\DSH_Work\life-assistant\extract_out.mp3"
    open(out, "wb").write(a.content)
    print("AUDIO", a.status_code, len(a.content), "->", out)
