"""DeepSeek 调用层：意图判定、生活常识问答、图片（OCR 文本 + 位置）分析。

DeepSeek 官方 API 没有视觉模型，因此图片路径的正确做法是：
客户端/服务端先 OCR 出文字，再把 OCR 文本 + 位置 + 用户问题一起交给 deepseek-chat 分析。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from ..config import Settings
from ..schemas import ImageAnalysis, Intent, TravelMode

log = logging.getLogger(__name__)

_CONF_MIN = 0.35

INTENT_SYSTEM = """你是一个中文生活助手的意图判定模块。用户会用口语提问，你只做分类和参数抽取。

必须只输出一个 json 对象，不要任何解释文字、不要 markdown 代码块。json 结构固定为：
{
  "intent": "route | nearby | image | knowledge | unknown",
  "confidence": 0.0 到 1.0 之间的小数,
  "destination": "目的地名称，没有则 null",
  "destination_city": "目的地的城市名，没有则 null",
  "travel_mode": "transit | walking | driving | null",
  "poi_keyword": "要搜索的周边场所关键词（如 火锅、加油站），没有则 null",
  "radius_m": 搜索半径米数（整数）或 null,
  "search_query": "用于地图检索的规范化短语，没有则 null"
}

分类规则：
- route：要去某个地方、问怎么走、要路线、要多久能到。例："怎么去西湖"、"从天安门到机场坐地铁怎么走"
- nearby：在当前地点附近找某类场所。例："附近有什么好吃的"、"15公里内找个加油站"
- image：用户要求看图片、分析照片、识别图中内容。
- knowledge：生活常识、做法、注意事项、概念解释。例："煮鸡蛋要几分钟"、"感冒能喝咖啡吗"
- unknown：完全无法归类。

出行方式只为 route 填写，用户没说时填 null。
目的地要抽干净，去掉"怎么去""路线"这类词，只留地名。"""

KNOWLEDGE_SYSTEM = """你是一个贴心、可靠的中文生活助手。回答要短、要具体、可执行。

硬性要求：
1. 直接给结论，不要"这个问题很好"之类的开场。
2. 分点用「1. 2. 3.」，每点不超过 35 字。
3. 涉及安全、健康、用药、法律时，给出明确提醒，但不要说教。
4. 总长度控制在 180 字以内，除非用户明确要求详细展开。
5. 不要输出 markdown 标题和代码块。"""

IMAGE_SYSTEM = """你是一个中文生活助手，正在分析用户拍的照片。

你会拿到：图片中 OCR 出来的文字、拍摄地点的地址与坐标、用户的提问。
你看不到图片本身，因此只能依据 OCR 文字和位置来推断。

要求：
1. 先说明从图中读到了什么关键信息，再给出结论或建议。
2. 如果 OCR 文字稀少或像是照片里没有文字，就说清楚这一点，再从场景（依据地址、用户描述）给出有限的判断，不要编造图中不存在的细节。
3. 如果文字中包含价格、日期、有效期、配料、地址、电话等，优先提取出来。
4. 分点用「1. 2. 3.」，总长度 200 字以内。
5. 不要输出 markdown 标题和代码块。"""


class DeepSeekError(RuntimeError):
    pass


class IntentDecision:
    __slots__ = ("intent", "confidence", "destination", "destination_city",
                 "travel_mode", "poi_keyword", "radius_m", "search_query")

    def __init__(self, data: dict[str, Any]) -> None:
        raw = str(data.get("intent") or "unknown").strip().lower()
        self.intent = Intent(raw) if raw in {i.value for i in Intent} else Intent.UNKNOWN
        try:
            self.confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            self.confidence = 0.0
        self.destination = _clean(data.get("destination"))
        self.destination_city = _clean(data.get("destination_city"))
        mode = _clean(data.get("travel_mode"))
        self.travel_mode = TravelMode(mode) if mode in {m.value for m in TravelMode} else None
        self.poi_keyword = _clean(data.get("poi_keyword"))
        try:
            self.radius_m = int(float(data["radius_m"])) if data.get("radius_m") else None
        except (TypeError, ValueError):
            self.radius_m = None
        self.search_query = _clean(data.get("search_query"))

    def as_meta(self) -> dict[str, Any]:
        return {
            "confidence": round(self.confidence, 3),
            "destination": self.destination,
            "travel_mode": self.travel_mode.value if self.travel_mode else None,
            "poi_keyword": self.poi_keyword,
            "radius_m": self.radius_m,
        }


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._s.deepseek_base_url,
                timeout=httpx.Timeout(self._s.deepseek_timeout_s, connect=8.0),
                headers={
                    "Authorization": f"Bearer {self._s.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _chat(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        if not self._s.deepseek_api_key:
            raise DeepSeekError("DEEPSEEK_API_KEY 未配置")

        payload: dict[str, Any] = {
            "model": model or self._s.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            # DeepSeek 的 json_object 模式要求提示词里出现 "json" 字样，否则报 400
            payload["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(self._s.deepseek_max_retries + 1):
            try:
                resp = await (await self._http()).post("/chat/completions", json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise DeepSeekError(f"upstream {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:
                    raise DeepSeekError(f"http {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                return (data["choices"][0]["message"]["content"] or "").strip()
            except (httpx.HTTPError, DeepSeekError, KeyError, IndexError) as exc:
                last_err = exc
                if attempt < self._s.deepseek_max_retries:
                    await asyncio.sleep(0.6 * (2 ** attempt))
                    log.warning("deepseek 重试 %s/%s: %s", attempt + 1, self._s.deepseek_max_retries, exc)
        raise DeepSeekError(f"deepseek 调用失败: {last_err}")

    # ---------------------------------------------------------- 意图判定
    async def classify(self, text: str, *, has_location: bool, has_image: bool = False,
                       context_hint: str | None = None) -> IntentDecision:
        parts = [f"用户原话：{text}"]
        parts.append(f"用户是否已提供定位：{'是' if has_location else '否'}")
        if has_image:
            parts.append("本条消息附带图片：是")
        if context_hint:
            parts.append(f"上一轮对话上下文（用于指代消解，如「去那儿」指向的地点）：{context_hint}")
        try:
            raw = await self._chat(INTENT_SYSTEM, "\n".join(parts),
                                   json_mode=True, temperature=0.0, max_tokens=256)
            data = _parse_json(raw)
            decision = IntentDecision(data)
        except (DeepSeekError, ValueError, json.JSONDecodeError) as exc:
            log.warning("意图判定失败，回落关键词规则: %s", exc)
            return _rule_based_intent(text, has_image)

        if decision.confidence < _CONF_MIN and decision.intent is not Intent.UNKNOWN:
            fallback = _rule_based_intent(text, has_image)
            if fallback.confidence > decision.confidence:
                return fallback
        return decision

    # ---------------------------------------------------------- 常识问答
    async def answer_knowledge(self, text: str, *, location_label: str | None = None) -> str:
        user = text if not location_label else f"（我在{location_label}）{text}"
        return await self._chat(KNOWLEDGE_SYSTEM, user, temperature=0.5, max_tokens=700)

    # ---------------------------------------------------------- 图片分析
    async def analyze_image(
        self,
        *,
        ocr_text: str,
        question: str,
        location_label: str | None = None,
        coordinates: tuple[float, float] | None = None,
    ) -> ImageAnalysis:
        lines = []
        lines.append(f"图中 OCR 文字：\n{ocr_text.strip() if ocr_text.strip() else '（未识别到文字）'}")
        lines.append(f"用户提问：{question.strip() or '这是什么？有什么需要注意的？'}")
        if location_label:
            lines.append(f"拍摄地点：{location_label}")
        if coordinates:
            lines.append(f"坐标（WGS-84）：{coordinates[0]:.6f}, {coordinates[1]:.6f}")

        raw = await self._chat(IMAGE_SYSTEM, "\n\n".join(lines), temperature=0.4, max_tokens=900)
        tags = _extract_tags(ocr_text)
        return ImageAnalysis(
            ocr_text=ocr_text.strip(),
            analysis=raw or "未能从这张图片中提取到有效信息。",
            tags=tags,
            confidence=0.8 if ocr_text.strip() else 0.35,
        )


# ------------------------------------------------------------------ helpers
def _clean(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s or s.lower() in {"null", "none", "无", "未知", "未提供", "n/a"}:
        return None
    return s


def _parse_json(raw: str) -> dict[str, Any]:
    """模型偶尔会套上 ```json 围栏，这里做兜底剥离。"""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            raise
        parsed = json.loads(m.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("意图判定返回的不是 json 对象")
    return parsed


_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.ROUTE, ("怎么去", "怎么走", "路线", "导航", "多远", "要多久", "坐地铁", "坐公交", "打车去", "开车去")),
    (Intent.NEARBY, ("附近", "周边", "旁边", "最近", "有没有", "找个", "哪里有", "公里内", "范围")),
    (Intent.IMAGE, ("这是什么", "拍一下", "看看这", "识别", "图片", "照片")),
    (Intent.KNOWLEDGE, ("怎么做", "为什么", "能不能", "可以吗", "多少", "是什么", "怎么办", "如何")),
]


def _rule_based_intent(text: str, has_image: bool) -> IntentDecision:
    """DeepSeek 不可用或低置信度时的兜底规则，保证 App 永远有响应。"""
    t = text.strip()
    best = Intent.UNKNOWN
    score = 0.0
    for intent, words in _KEYWORD_RULES:
        hits = sum(1 for w in words if w in t)
        if hits:
            s = min(0.5 + 0.15 * hits, 0.85)
            if s > score:
                best, score = intent, s
    if has_image and best in (Intent.UNKNOWN, Intent.IMAGE):
        best, score = Intent.IMAGE, max(score, 0.7)
    if best is Intent.UNKNOWN:
        best, score = Intent.KNOWLEDGE, 0.4

    mode = None
    for kw, m in (("步行", TravelMode.WALKING), ("走路", TravelMode.WALKING),
                  ("骑车", TravelMode.WALKING), ("公交", TravelMode.TRANSIT),
                  ("地铁", TravelMode.TRANSIT), ("打车", TravelMode.DRIVING),
                  ("开车", TravelMode.DRIVING), ("驾车", TravelMode.DRIVING)):
        if kw in t:
            mode = m
            break
    return IntentDecision({
        "intent": best.value,
        "confidence": score,
        "travel_mode": mode.value if mode else None,
        "search_query": t[:40],
    })


# 注意：货币那一段必须用非捕获组。
# re.findall 只要模式里存在捕获组，就只返回组内容；写成 (￥|¥|\$) 时
# 其余分支的匹配都会返回空串，被下面的过滤丢掉，标签永远是空列表。
_TAG_RE = re.compile(r"(?:￥|¥|\$)\s?\d+(?:\.\d+)?|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}|\d{1,2}:\d{2}|"
                     r"保质期|有效期|生产日期|净含量|配料|地址|电话|客服|警告|注意")


def _extract_tags(ocr_text: str) -> list[str]:
    """从 OCR 文本里挑出对生活场景有用的结构化线索。"""
    if not ocr_text.strip():
        return []
    found = _TAG_RE.findall(ocr_text)
    seen: list[str] = []
    for f in found:
        token = f.strip()
        if token and token not in seen:
            seen.append(token)
    return seen[:8]
