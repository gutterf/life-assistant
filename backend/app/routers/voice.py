"""语音 API：提取/录制 -> 克隆 -> 试听 -> TTS 朗读。"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import httpx

from ..services import voice
from ..services.voice import DATA_DIR, REFS_DIR, _JOBS

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

_META_FILE = DATA_DIR / "voices.json"


def _load_meta() -> dict:
    if _META_FILE.is_file():
        try:
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_meta(meta: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


class ExtractReq(BaseModel):
    url: str
    name: str | None = None


class TTSReq(BaseModel):
    text: str
    voice_id: str


@router.get("/health")
def voice_health() -> dict:
    ok, detail = voice.vs_health()
    return {"vs_ready": ok, "detail": detail, "data_dir": str(DATA_DIR)}


@router.post("/extract")
def extract(req: ExtractReq) -> dict:
    """视频链接 -> 后台任务：下载音轨 -> demucs 去 BGM -> 克隆。"""
    url = (req.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "链接格式不对，粘贴完整视频链接")
    jid = voice.new_job("extract", url)
    return {"job_id": jid, "status": "queued"}


@router.get("/job/{jid}")
def job(jid: str) -> dict:
    j = voice.job_status(jid)
    if j is None:
        raise HTTPException(404, "任务不存在")
    return {k: j.get(k) for k in ("kind", "url", "status", "progress", "voice_id", "error")}


@router.post("/record")
async def record(file: UploadFile = File(...), transcript: str | None = Form(None)) -> dict:
    """录制 10 秒声音上传，直接克隆。transcript 可选：参考音频的文字内容。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / f"rec_{uuid.uuid4().hex[:8]}{Path(file.filename or 'r.m4a').suffix or '.m4a'}"
    tmp.write_bytes(await file.read())
    try:
        res = voice.register_recording(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    meta = _load_meta()
    item = {"name": "我录制的声音", "source": "record", "ts": __import__("time").time()}
    if transcript and transcript.strip():
        item["transcript"] = transcript.strip()
    meta[res["voice_id"]] = item
    _save_meta(meta)
    return {"voice_id": res["voice_id"], "name": "我录制的声音"}


@router.post("/tts")
def tts(req: TTSReq):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "要朗读的文本为空")
    ref = REFS_DIR / f"{req.voice_id}.wav"
    if not ref.is_file():
        raise HTTPException(404, "这个声音不存在，先提取或录制")
    try:
        out = voice.synth(text, req.voice_id)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"语音引擎连不上: {e}") from e
    except RuntimeError as e:
        raise HTTPException(502, f"语音服务异常: {e}") from e
    return JSONResponse(
        {
            "url": f"/api/v1/voice/audio/{req.voice_id}/{out.name}",
            "bytes": out.stat().st_size,
        }
    )


@router.get("/audio/{voice_id}/{fname}")
def audio(voice_id: str, fname: str):
    p = (DATA_DIR / "clips" / voice_id / fname).resolve()
    if not str(p).startswith(str(DATA_DIR.resolve())) or not p.is_file():
        raise HTTPException(404, "音频不存在")
    return FileResponse(p, media_type="audio/mpeg")


@router.get("/preview/{voice_id}")
def preview(voice_id: str):
    p = (REFS_DIR / f"{voice_id}.wav").resolve()
    if not p.is_file():
        raise HTTPException(404, "参考音频不存在")
    return FileResponse(p, media_type="audio/wav")


@router.get("/list")
def voice_list() -> dict:
    """本机所有音色（提取+录制），含试听链接。"""
    meta = _load_meta()
    items = []
    if REFS_DIR.is_dir():
        for p in sorted(REFS_DIR.glob("*.wav")):
            vid = p.stem
            items.append(
                {
                    "voice_id": vid,
                    "name": meta.get(vid, {}).get("name", vid),
                    "source": meta.get(vid, {}).get("source", "extract"),
                    "preview_url": f"/api/v1/voice/preview/{vid}",
                }
            )
    return {"voices": items}
