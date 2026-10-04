"""离线端到端自测：真 uvicorn + 真 HTTP + 假的高德/DeepSeek 上游。

与 tests/test_pipeline.py 的区别：
    test_pipeline.py 把 AMapClient / DeepSeekClient 整个打桩，测的是「编排逻辑」。
    本脚本不碰任何客户端内部，只把两个 base_url 指向 tools/mock_upstream，
    因此真实地跑过 httpx 请求、高德响应解析、DeepSeek JSON 解析和 FastAPI 序列化。

用法（在 backend 目录下）：
    python tools/smoke_e2e.py
不需要任何真实 API Key，也不联网。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Windows 控制台默认 GBK，中文报表会变乱码
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from app.config import Settings  # noqa: E402
from app.services.coord import wgs84_to_gcj02  # noqa: E402

WGS_LNG, WGS_LAT = 116.397128, 39.916527

# ------------------------------------------------------------------ 测试框架
ROWS: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    ROWS.append((bool(ok), name, detail))
    return bool(ok)


def eq(name: str, actual, expected) -> bool:
    return check(name, actual == expected, f"实际={actual!r} 期望={expected!r}")


def contains(name: str, haystack: str, needle: str) -> bool:
    return check(name, needle in (haystack or ""), f"「{needle}」不在响应里：{(haystack or '')[:120]!r}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ------------------------------------------------------------------ 进程管理
class Server:
    def __init__(self, spec: str, port: int, env: dict[str, str]) -> None:
        self.port, self.spec = port, spec
        slug = spec.split(":")[0].split(".")[-1]
        self.log = BACKEND / "tools" / f"_smoke_{slug}.log"
        self.handle = self.log.open("w", encoding="utf-8", errors="replace")
        full_env = {**os.environ, **env, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", spec, "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning"],
            cwd=str(BACKEND), env=full_env, stdout=self.handle, stderr=subprocess.STDOUT,
        )

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def wait_ready(self, path: str, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                if httpx.get(self.base + path, timeout=1.5).status_code < 500:
                    return True
            except httpx.HTTPError:
                time.sleep(0.25)
        return False

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.handle.close()

    def tail(self, lines: int = 25) -> str:
        try:
            text = self.log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(text[-lines:])


# ------------------------------------------------------------------ 主流程
def main() -> int:
    mock_port, app_port = free_port(), free_port()
    mock = Server("tools.mock_upstream:app", mock_port, {})
    app = Server("app.main:app", app_port, {
        "DEEPSEEK_API_KEY": "smoke-deepseek-key",
        "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{mock_port}",
        "AMAP_KEY": "smoke-amap-key",
        "AMAP_BASE_URL": f"http://127.0.0.1:{mock_port}",
        "OCR_PROVIDER": "auto",
        "LOG_LEVEL": "WARNING",
    })

    try:
        if not mock.wait_ready("/docs"):
            print("假上游启动失败:\n" + mock.tail())
            return 2
        if not app.wait_ready("/health"):
            print("后端启动失败:\n" + app.tail())
            return 2

        chat = app.base + "/api/v1/chat"
        image = app.base + "/api/v1/analyze-image"
        client = httpx.Client(timeout=30.0)

        def ask(text: str, with_location: bool = True, session: str = "smoke") -> dict:
            payload: dict = {"text": text, "session_id": session}
            if with_location:
                payload["location"] = {"latitude": WGS_LAT, "longitude": WGS_LNG}
            r = client.post(chat, json=payload)
            check(f"HTTP 200 · {text}", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
            return r.json() if r.status_code == 200 else {}

        # ---------------------------------------------------------- 0 基础
        h = client.get(app.base + "/health").json()
        eq("health.status", h.get("status"), "ok")
        eq("health.configured", h.get("configured"), True)
        eq("health.missing", h.get("missing"), [])
        eq("health.default_radius_m", h.get("default_radius_m"), 15000)

        paths = client.get(app.base + "/openapi.json").json()["paths"]
        check("openapi 暴露两个业务接口",
              "/api/v1/chat" in paths and "/api/v1/analyze-image" in paths, str(sorted(paths)))

        missing = Settings(deepseek_api_key="", amap_key="").missing_required()
        eq("缺密钥时 /health 会自报缺失", missing, ["DEEPSEEK_API_KEY", "AMAP_KEY"])

        # ---------------------------------------------------------- 1 周边搜索
        client.post(mock.base + "/__reset")
        body = ask("附近15公里有什么火锅店")
        eq("S1 intent", body.get("intent"), "nearby")
        card = (body.get("cards") or [{}])[0]
        eq("S1 卡片类型", card.get("type"), "place_list")
        places = card.get("places") or []
        eq("S1 结果条数", len(places), 3)
        dists = [p.get("distance_m") for p in places]
        check("S1 按距离升序", dists == sorted(dists), str(dists))
        eq("S1 名称", places[0].get("name"), "老北京炸酱面（前门店）")
        eq("S1 评分", places[0].get("rating"), 4.6)
        eq("S1 距离", places[0].get("distance_m"), 320)
        eq("S1 分类", places[0].get("category"), "中餐厅")
        eq("S1 无评分时留空", places[2].get("rating"), None)
        eq("S1 半径元数据", (body.get("meta") or {}).get("radius_m"), 15000)
        contains("S1 话术点出评分最高", body.get("reply", ""), "评分最高")
        contains("S1 话术点名最近一家", body.get("reply", ""), "老北京炸酱面")
        contains("S1 播报文本含距离", card.get("speech", ""), "320 米")

        sent = [i for i in client.get(mock.base + "/__requests").json()["items"]
                if i["endpoint"] == "place_around"][-1]["params"]
        eq("S1 关键词优先于分类码", sent.get("keywords"), "火锅")
        eq("S1 半径传到高德", sent.get("radius"), "15000")
        eq("S1 按距离排序参数", sent.get("sortrule"), "distance")
        eq("S1 extensions=all 才会带评分", sent.get("extensions"), "all")
        glng, glat = wgs84_to_gcj02(WGS_LNG, WGS_LAT)
        out_lng, out_lat = (float(x) for x in sent["location"].split(","))
        check("S1 传给高德的是 GCJ-02 而非 WGS-84",
              abs(out_lng - glng) < 1e-6 and abs(out_lat - glat) < 1e-6,
              f"发出去={out_lng:.6f},{out_lat:.6f} 期望={glng:.6f},{glat:.6f}")
        check("S1 纠偏量符合北京地区预期",
              300 < (abs(out_lng - WGS_LNG) * 85000) < 800,
              f"约 {abs(out_lng - WGS_LNG) * 85000:.0f} 米")

        # ---------------------------------------------------------- 2 公交路线
        body = ask("从天安门到首都机场坐地铁怎么走")
        eq("S2 intent", body.get("intent"), "route")
        plan = ((body.get("cards") or [{}])[0].get("routes") or [{}])[0]
        eq("S2 出行方式", plan.get("mode"), "transit")
        eq("S2 总里程取高德方案值", plan.get("total_distance_m"), 12400)
        eq("S2 总耗时取 duration（秒）而非 cost（元）", plan.get("total_duration_s"), 1200)
        eq("S2 换乘次数", plan.get("transfer_count"), 1)
        eq("S2 票价取 cost（元）", plan.get("cost_yuan"), 6.0)
        contains("S2 summary 含票价", plan.get("summary", ""), "票价 6 元")
        line_names = [leg.get("line_name") for leg in plan.get("legs", []) if leg.get("line_name")]
        eq("S2 公交段线路名", (line_names or [""])[0], "地铁1号线(苹果园--四惠东)")
        contains("S2 话术含换乘", body.get("reply", ""), "换乘 1 次")
        sent = [i for i in client.get(mock.base + "/__requests").json()["items"]
                if i["endpoint"] == "transit"][-1]["params"]
        eq("S2 公交接口必填 city", sent.get("city"), "010")
        eq("S2 公交接口必填 cityd", sent.get("cityd"), "010")

        # ---------------------------------------------------------- 3 步行
        body = ask("走去天安门要多久")
        plan = ((body.get("cards") or [{}])[0].get("routes") or [{}])[0]
        eq("S3 出行方式", plan.get("mode"), "walking")
        eq("S3 里程", plan.get("total_distance_m"), 1800)
        eq("S3 耗时", plan.get("total_duration_s"), 1500)
        contains("S3 summary 可读", plan.get("summary", ""), "1.8 公里")
        contains("S3 播报含路线", body.get("speech", ""), "步行")
        check("S3 直线距离已计算", (body.get("meta") or {}).get("straight_line_m", 0) > 0,
              str((body.get("meta") or {}).get("straight_line_m")))

        # ---------------------------------------------------------- 4 驾车
        body = ask("开车去首都机场")
        plan = ((body.get("cards") or [{}])[0].get("routes") or [{}])[0]
        eq("S4 出行方式", plan.get("mode"), "driving")
        eq("S4 里程", plan.get("total_distance_m"), 28500)
        eq("S4 过路费", plan.get("cost_yuan"), 10.0)
        contains("S4 summary 含红绿灯", plan.get("summary", ""), "红绿灯 12 个")

        # ---------------------------------------------------------- 5 常识问答
        body = ask("煮鸡蛋要几分钟", with_location=False)
        eq("S5 intent", body.get("intent"), "knowledge")
        eq("S5 卡片类型", (body.get("cards") or [{}])[0].get("type"), "text")
        contains("S5 回答内容", body.get("reply", ""), "8 分钟")
        check("S5 播报文本存在", bool(body.get("speech")), "")

        # ---------------------------------------------------------- 6 想看图但没带图
        body = ask("帮我看看这张照片")
        eq("S6 intent", body.get("intent"), "image")
        contains("S6 引导用户去拍照", body.get("reply", ""), "相机")

        # ---------------------------------------------------------- 7 图片：带端上 OCR
        with open(BACKEND / "tools" / "_smoke.jpg", "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0" + b"smoke-jpeg" * 40)
        with open(BACKEND / "tools" / "_smoke.jpg", "rb") as fh:
            r = client.post(image, files={"file": ("photo.jpg", fh, "image/jpeg")},
                            data={"question": "这个还能吃吗", "ocr_text": "保质期 2026-03-01 净含量 250g",
                                  "latitude": str(WGS_LAT), "longitude": str(WGS_LNG),
                                  "address": "北京市东城区天安门广场", "session_id": "smoke"})
        check("S7 HTTP 200", r.status_code == 200, r.text[:200])
        body = r.json() if r.status_code == 200 else {}
        eq("S7 OCR 供应商", (body.get("meta") or {}).get("ocr_provider"), "ios_vision")
        eq("S7 卡片类型", (body.get("cards") or [{}])[0].get("type"), "image_analysis")
        eq("S7 OCR 原文回填", (body.get("analysis") or {}).get("ocr_text"), "保质期 2026-03-01 净含量 250g")
        tags = (body.get("analysis") or {}).get("tags") or []
        check("S7 结构化线索抽取", "保质期" in tags, str(tags))
        contains("S7 分析结论", (body.get("analysis") or {}).get("analysis", ""), "保质期")
        check("S7 播报文本存在", bool(body.get("speech")), "")
        eq("S7 图片字节数已记录", (body.get("meta") or {}).get("image_bytes"), 4 + 400)

        # ---------------------------------------------------------- 8 图片：无端上 OCR
        with open(BACKEND / "tools" / "_smoke.jpg", "rb") as fh:
            r = client.post(image, files={"file": ("photo.jpg", fh, "image/jpeg")},
                            data={"question": "这是什么", "session_id": "smoke"})
        check("S8 无 OCR 线索也不报错", r.status_code == 200, r.text[:200])
        provider = (r.json().get("meta") or {}).get("ocr_provider") if r.status_code == 200 else None
        check("S8 供应商回落合理", provider in {"none", "rapidocr"}, str(provider))

        r = client.post(image, files={"file": ("note.gif", b"GIF89a", "image/gif")}, data={"question": "?"})
        eq("S8 拒绝非图片类型", r.status_code, 415)

        # ---------------------------------------------------------- 9 缺定位的路线
        body = ask("怎么去机场", with_location=False)
        eq("S9 要求先定位", body.get("intent"), "unknown")
        contains("S9 提示语气", body.get("reply", ""), "定位")

        # ---------------------------------------------------------- 10 高德故障降级
        client.post(mock.base + "/__fail_amap", json={"on": True})
        body = ask("附近有医院吗")
        meta = body.get("meta") or {}
        eq("S10 标记为降级", meta.get("degraded"), True)
        check("S10 仍给出回答", len(body.get("reply", "")) > 5, body.get("reply", "")[:80])
        check("S10 记下降级原因", "DAILY_QUERY_OVER_LIMIT" in str(meta.get("reason")), str(meta.get("reason")))
        client.post(mock.base + "/__fail_amap", json={"on": False})

        # ---------------------------------------------------------- 11 坐标越界
        r = client.post(chat, json={"text": "附近有火锅吗",
                                    "location": {"latitude": 999, "longitude": 116.4}})
        eq("S11 越界坐标被拒", r.status_code, 422)

    finally:
        app.stop()
        mock.stop()
        for stale in (BACKEND / "tools" / "_smoke.jpg",
                      BACKEND / "tools" / "_smoke_main.log",
                      BACKEND / "tools" / "_smoke_mock_upstream.log"):
            stale.unlink(missing_ok=True)

    # ------------------------------------------------------------------ 报表
    passed = sum(1 for ok, _, _ in ROWS if ok)
    failed = [(n, d) for ok, n, d in ROWS if not ok]

    print("=" * 78)
    print(f"离线端到端自测：{passed}/{len(ROWS)} 项通过")
    print("=" * 78)
    for ok, name, detail in ROWS:
        print(f"  {'✓' if ok else '✗'} {name}")
        if not ok:
            print(f"      {detail}")

    print("-" * 78)
    if failed:
        print(f"失败 {len(failed)} 项：")
        for n, d in failed:
            print(f"  - {n}\n      {d}")
        print("\n后端日志尾部：\n" + app.tail())
        return 1
    print("全部通过：意图判定 → 高德路线/周边 → OCR → DeepSeek → 卡片契约 全链路可用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
