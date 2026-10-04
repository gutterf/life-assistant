"""图片文字识别。可插拔 provider，按可用性自动选择。

优先级：
  1. client_hint  —— iOS 端 Vision（VNRecognizeTextRequest）已识别出的文本，免费、离线、中文准
  2. rapidocr     —— 服务端本地 ONNX 推理，无需联网与密钥
  3. baidu        —— 百度云 OCR（需要 key，按量计费）
  4. none         —— 全部不可用，返回空文本（DeepSeek 仍会基于位置给出有限回答）
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from ..config import Settings

log = logging.getLogger(__name__)

_rapid_engine: Any = None
_rapid_unavailable = False


class OCRError(RuntimeError):
    pass


class OCRService:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def extract(self, image_bytes: bytes, client_hint: str | None = None) -> tuple[str, str]:
        """返回 (识别文本, 实际使用的 provider)。"""
        hint = (client_hint or "").strip()
        provider = (self._s.ocr_provider or "auto").lower()

        if provider in ("auto", "ios") and hint:
            return hint, "ios_vision"
        if provider == "ios":
            return "", "ios_vision"

        if provider in ("auto", "rapidocr"):
            text = await self._rapidocr(image_bytes)
            if text:
                return text, "rapidocr"
            if provider == "rapidocr":
                return "", "rapidocr"

        if provider == "baidu" or (provider == "auto" and self._s.baidu_ocr_api_key):
            text = await self._baidu(image_bytes)
            if text:
                return text, "baidu"

        return hint, "none" if not hint else "ios_vision"

    # ------------------------------------------------------------ rapidocr
    async def _rapidocr(self, image_bytes: bytes) -> str:
        global _rapid_engine, _rapid_unavailable
        if _rapid_unavailable:
            return ""
        try:
            if _rapid_engine is None:
                from rapidocr_onnxruntime import RapidOCR  # 延迟导入：未安装时不影响服务启动
                _rapid_engine = RapidOCR()
        except Exception as exc:  # noqa: BLE001 - 导入失败原因较多，统一降级
            _rapid_unavailable = True
            log.info("rapidocr 不可用，跳过服务端 OCR: %s", exc)
            return ""

        def _run() -> str:
            import numpy as np
            from PIL import Image
            import io

            img = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
            result, _ = _rapid_engine(img)
            if not result:
                return ""
            return "\n".join(str(line[1]).strip() for line in result if len(line) > 1 and str(line[1]).strip())

        try:
            # RapidOCR 是同步 CPU 密集调用，放线程池避免阻塞事件循环
            return await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as exc:  # noqa: BLE001
            log.warning("rapidocr 识别失败: %s", exc)
            return ""

    # --------------------------------------------------------------- baidu
    async def _token(self) -> str:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(
                "https://aip.baidubce.com/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self._s.baidu_ocr_api_key,
                    "client_secret": self._s.baidu_ocr_secret_key,
                },
            )
            r.raise_for_status()
            return r.json().get("access_token", "")

    async def _baidu(self, image_bytes: bytes) -> str:
        if not (self._s.baidu_ocr_api_key and self._s.baidu_ocr_secret_key):
            return ""
        try:
            token = await self._token()
            if not token:
                return ""
            async with httpx.AsyncClient(timeout=20.0) as cli:
                r = await cli.post(
                    "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic",
                    params={"access_token": token},
                    data={"image": base64.b64encode(image_bytes).decode(),
                          "language_type": "CHN_ENG",
                          "detect_direction": "true"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                r.raise_for_status()
                body = r.json()
                if "error_code" in body:
                    log.warning("baidu ocr 失败: %s", body)
                    return ""
                return "\n".join(w.get("words", "") for w in body.get("words_result", []))
        except httpx.HTTPError as exc:
            log.warning("baidu ocr 请求异常: %s", exc)
            return ""
