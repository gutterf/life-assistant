"""高德 + DeepSeek 的本地假上游，仅用于离线端到端自测（tools/smoke_e2e.py）。

它按真实接口的响应结构返回数据，因此能验证 app/ 里所有解析代码：
高德的 status/info 包装、pois[].biz_ext.rating、route.paths[].steps、transits[].segments，
以及 DeepSeek 的 choices[0].message.content。

单独启动（可选）：
    uvicorn tools.mock_upstream:app --port 18900
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="mock upstream")

# 记录收到的每一次高德请求，供 smoke 脚本断言「传出去的坐标确实是 GCJ-02」
REQUESTS: list[dict[str, Any]] = []
# 打开后所有高德接口都返回失败，用来验证后端的降级路径
FAIL_AMAP = {"on": False}

_CITYCODE = "010"


def _fmt(location: str) -> tuple[float, float]:
    lng, lat = location.split(",")[:2]
    return float(lng), float(lat)


@app.post("/__fail_amap")
async def fail_amap(payload: dict) -> dict:
    FAIL_AMAP["on"] = bool(payload.get("on"))
    return {"ok": True, "on": FAIL_AMAP["on"]}


@app.get("/__requests")
async def dump_requests() -> dict:
    return {"count": len(REQUESTS), "items": REQUESTS}


@app.post("/__reset")
async def reset() -> dict:
    REQUESTS.clear()
    FAIL_AMAP["on"] = False
    return {"ok": True}


# ----------------------------------------------------------------- 高德 v3
@app.get("/v3/geocode/regeo")
async def regeo(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "regeo", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
    lng, lat = _fmt(params.get("location", "116.4,39.9"))
    return {
        "status": "1", "info": "OK", "infocode": "10000",
        "regeocode": {
            "formatted_address": "北京市东城区东华门街道天安门广场",
            "addressComponent": {
                "province": "北京市", "city": "北京市", "district": "东城区",
                "citycode": _CITYCODE, "adcode": "110101",
                "township": [], "streetNumber": {},
            },
        },
    }


@app.get("/v3/geocode/geo")
async def geocode(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "geocode", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
    address = params.get("address", "")
    table = {
        "首都机场": ("116.603128", "40.079296", "北京市顺义区首都机场"),
        "天安门": ("116.397451", "39.908702", "北京市东城区天安门"),
        "西湖": ("120.147000", "30.246000", "浙江省杭州市西湖区西湖"),
    }
    for key, (lng, lat, formatted) in table.items():
        if key in address:
            return {"status": "1", "info": "OK", "infocode": "10000",
                    "geocodes": [{"location": f"{lng},{lat}", "formatted_address": formatted}]}
    return {"status": "1", "info": "OK", "infocode": "10000", "geocodes": []}


@app.get("/v3/place/around")
async def place_around(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "place_around", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}

    keywords = params.get("keywords", "")
    pois = [
        {"name": "老北京炸酱面（前门店）", "type": "餐饮服务;中餐厅;中餐厅",
         "distance": "320", "address": "东城区前门大街1号", "tel": "010-67012345",
         "location": "116.397000,39.899000", "biz_ext": {"rating": "4.6", "cost": "45"}},
        {"name": "川渝火锅（王府井店）", "type": "餐饮服务;中餐厅;火锅店",
         "distance": "1450", "address": "东城区王府井大街255号", "tel": "010-65123456",
         "location": "116.410000,39.915000", "biz_ext": {"rating": "4.9", "cost": "128"}},
        {"name": "巷子口小馆", "type": "餐饮服务;中餐厅;中餐厅",
         "distance": "9800", "address": "朝阳区建国路88号", "tel": [],
         "location": "116.480000,39.910000", "biz_ext": []},
    ]
    return {"status": "1", "info": "OK", "infocode": "10000", "count": str(len(pois)),
            "pois": pois, "keywords": keywords}


@app.get("/v3/direction/walking")
async def walking(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "walking", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
    return {
        "status": "1", "info": "OK", "infocode": "10000",
        "route": {"origin": params.get("origin", ""), "destination": params.get("destination", ""),
                  "paths": [{"distance": "1800", "duration": "1500", "steps": [
                      {"instruction": "沿前门大街向北步行 800 米", "distance": "800", "duration": "650"},
                      {"instruction": "右转进入东长安街步行 1000 米", "distance": "1000", "duration": "850"},
                  ]}]},
    }


@app.get("/v3/direction/driving")
async def driving(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "driving", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
    return {
        "status": "1", "info": "OK", "infocode": "10000",
        "route": {"paths": [{"distance": "28500", "duration": "2700", "tolls": "10",
                             "traffic_lights": "12", "steps": [
                                 {"instruction": "沿东长安街向东行驶 3 公里", "road": "东长安街",
                                  "distance": "3000", "duration": "420"},
                                 {"instruction": "进入机场高速行驶 25 公里", "road": "机场高速",
                                  "distance": "25500", "duration": "2280"},
                             ]}]},
    }


@app.get("/v3/direction/transit/integrated")
async def transit(request: Request) -> dict:
    params = dict(request.query_params)
    REQUESTS.append({"endpoint": "transit", "params": params})
    if FAIL_AMAP["on"]:
        return {"status": "0", "info": "DAILY_QUERY_OVER_LIMIT", "infocode": "10003"}
    # city / cityd 缺失必须按真实高德一样报错，否则测不出后端的城市码兜底逻辑
    if not params.get("city") or not params.get("cityd"):
        return {"status": "0", "info": "INVALID_PARAMS", "infocode": "20000"}

    def plan(distance: str, duration: str, cost: str, walk: str, buses: int) -> dict:
        lines = [{
            "name": f"地铁{i + 1}号线(苹果园--四惠东)",
            "distance": "10500", "duration": "1200", "via_num": "9",
            "departure_stop": {"name": f"第{i + 1}换乘站"},
            "arrival_stop": {"name": f"第{i + 2}换乘站"},
        } for i in range(buses)]
        return {
            "distance": distance, "duration": duration, "cost": cost,
            "walking_distance": walk,
            "segments": [
                {"walking": {"distance": "600", "duration": "480",
                             "steps": [{"instruction": "步行至地铁站 600 米"}]},
                 "bus": {"buslines": lines[:1]}},
                {"walking": {"distance": "400", "duration": "320",
                             "steps": [{"instruction": "步行 400 米到达目的地"}]},
                 "bus": {"buslines": lines[1:]}},
            ],
        }

    return {"status": "1", "info": "OK", "infocode": "10000",
            "route": {"transits": [
                plan("12400", "1200", "6", "1000", 2),
                plan("15000", "1500", "6", "1200", 3),
                plan("17800", "1900", "7", "1500", 3),
            ]}}


# --------------------------------------------------------------- DeepSeek
_INTENT_MARK = "意图判定"
_KNOWLEDGE_MARK = "生活助手"
_IMAGE_MARK = "正在分析用户拍的照片"

_DEST_CANDIDATES = ("首都机场", "天安门", "西湖", "机场")


def _pick_destination(text: str) -> str | None:
    for name in _DEST_CANDIDATES:
        if name in text:
            return name
    m = re.search(r"(?:去|到|往)([\u4e00-\u9fa5A-Za-z0-9]{2,12}?)(?:怎么|要|坐|走|$)", text)
    return m.group(1) if m else None


def _pick_mode(text: str) -> str | None:
    for kw, mode in (("步行", "walking"), ("走路", "walking"), ("走去", "walking"),
                     ("走过去", "walking"), ("地铁", "transit"), ("公交", "transit"),
                     ("打车", "driving"), ("开车", "driving"), ("驾车", "driving")):
        if kw in text:
            return mode
    return None


def _classify(text: str, has_location: bool, has_image: bool) -> dict:
    if has_image:
        return {"intent": "image", "confidence": 0.95}
    if any(k in text for k in ("看看这", "看这张", "分析照片", "识图")):
        return {"intent": "image", "confidence": 0.9}
    if any(k in text for k in ("怎么去", "怎么走", "路线", "导航", "要多久", "坐地铁", "开车去", "走多远")):
        return {"intent": "route", "confidence": 0.93,
                "destination": _pick_destination(text),
                "travel_mode": _pick_mode(text)}
    if any(k in text for k in ("附近", "周边", "公里内", "哪里有", "找个")):
        keyword = "生活服务"
        for kw in ("火锅", "医院", "加油站", "咖啡", "药店"):
            if kw in text:
                keyword = kw
                break
        radius = None
        m = re.search(r"(\d+)\s*公里", text)
        if m:
            radius = int(m.group(1)) * 1000
        return {"intent": "nearby", "confidence": 0.94, "poi_keyword": keyword, "radius_m": radius}
    return {"intent": "knowledge", "confidence": 0.88}


@app.post("/chat/completions")
async def chat_completions(request: Request) -> dict:
    body = await request.json()
    messages = body.get("messages") or []
    system = messages[0].get("content", "") if messages else ""
    user = messages[1].get("content", "") if len(messages) > 1 else ""

    if _INTENT_MARK in system:
        m = re.search(r"用户原话：(.*)", user)
        text = (m.group(1) if m else user).strip()
        decision = _classify(
            text,
            has_location="已提供定位：是" in user,
            has_image="本条消息附带图片：是" in user,
        )
        content = json.dumps(decision, ensure_ascii=False)
    elif _IMAGE_MARK in system:
        ocr_line = ""
        m = re.search(r"图中 OCR 文字：\s*\n?(.*)", user)
        if m:
            ocr_line = m.group(1).split("\n")[0].strip()
        content = (f"1. 图中读到：{ocr_line or '（无明显文字）'}。\n"
                   "2. 结合拍摄地点判断，信息有限，建议以实物标注为准。")
    elif _KNOWLEDGE_MARK in system:
        content = "1. 冷水下锅，水开后煮 8 分钟。\n2. 捞出过一遍凉水，更好剥壳。"
    else:
        content = "（mock 未识别的请求）"

    return {
        "id": "mock-completion", "object": "chat.completion", "model": body.get("model", "deepseek-chat"),
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
    }
