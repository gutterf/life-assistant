"""图片上传分析接口：/api/v1/analyze-image

multipart/form-data 字段：
  file          必填，图片二进制（客户端已压缩到长边 1600px 以内）
  question      选填，用户对这一拍的提问
  ocr_text      选填，iOS Vision 预先识别出的文字，命中时省掉服务端 OCR
  latitude/longitude/accuracy_m  选填，WGS-84 原始坐标
  address/citycode/session_id    选填
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from ..config import Settings
from ..deps import get_orchestrator, get_settings_dep
from ..schemas import GeoPoint, ImageAnalyzeResponse
from ..services.deepseek import DeepSeekError
from ..services.orchestrator import Orchestrator

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["image"])

_ACCEPTED = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}


@router.post("/analyze-image", response_model=ImageAnalyzeResponse, summary="拍照 / 选图分析")
async def analyze_image(
    file: UploadFile = File(..., description="图片文件"),
    question: str = Form(""),
    ocr_text: str | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    accuracy_m: float | None = Form(None),
    address: str | None = Form(None),
    citycode: str | None = Form(None),
    session_id: str | None = Form(None),
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings_dep),
) -> ImageAnalyzeResponse:
    if file.content_type and file.content_type not in _ACCEPTED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"不支持的图片类型: {file.content_type}")

    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="空文件")
    if len(data) > limit:
        # 413：新旧 Starlette 对该常量的命名不同，直接用字面量避免版本耦合
        raise HTTPException(413, detail=f"图片超过 {settings.max_upload_mb} MB")

    point = None
    if latitude is not None and longitude is not None:
        try:
            point = GeoPoint(latitude=latitude, longitude=longitude, accuracy_m=accuracy_m)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="坐标越界") from exc

    try:
        return await orchestrator.handle_image(
            image_bytes=data,
            question=question or "",
            client_ocr_text=ocr_text,
            point=point,
            address=address,
            citycode=citycode,
            session_id=session_id or "local",
        )
    except DeepSeekError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"模型服务不可用: {exc}") from exc
