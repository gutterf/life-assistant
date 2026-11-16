"""语音模块：视频链接抽人声 -> 保存参考人声 -> VoiceStudio 零样本克隆 TTS 朗读。

依赖三个本地组件：
- yt-dlp：解析视频链接、下载音轨
- demucs：人声/伴奏分离，去掉 BGM
- VoiceStudio（127.0.0.1:3900）：POST /generate 直传 ref_audio 零样本克隆，
  响应体即合成 WAV；服务健康走 /.well-known/voicestudio-speech

数据目录：backend/data/voice/
  refs/<voice_id>.wav    干净参考人声（克隆用）
  clips/<voice_id>/<ts>.mp3  TTS 生成音频
  voices.json            音色清单（可持久）
  jobs.json              提取任务状态
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("life-assistant.voice")

VS_BASE = "http://127.0.0.1:3900"
VS_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=10.0)

# 参考人声统一采样率：VoiceStudio / OmniVoice 的原生率就是 24k，
# 降到 16k 会丢高频、克隆音色发闷。
REF_RATE = 24000

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "voice"
REFS_DIR = DATA_DIR / "refs"
CLIPS_DIR = DATA_DIR / "clips"
JOBS_FILE = DATA_DIR / "jobs.json"

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)


def vs_health() -> tuple[bool, str]:
    try:
        r = httpx.get(f"{VS_BASE}/.well-known/voicestudio-speech", timeout=httpx.Timeout(3.0))
        if r.status_code >= 300:
            return False, f"status={r.status_code}"
        d = r.json()
        return True, f"service={d.get('service')} {d.get('service_version')}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:120]


def _call_vs(method: str, path: str, **kw: Any) -> httpx.Response:
    return httpx.request(method, f"{VS_BASE}{path}", timeout=VS_TIMEOUT, **kw)


def vs_tts(text: str, ref_wav: Path, out_mp3: Path, ref_text: str | None = None) -> float:
    """VoiceStudio 零样本克隆 TTS。

    POST /generate（multipart），ref_audio 直接传参考人声，
    响应体就是合成后的 WAV 二进制。转 mp3 存盘，返回时长秒。
    ref_text：参考音频的文字内容。参考音频没有存 transcript 且 VS 没装
    ASR 模型时会 400 REFERENCE_STT_MISSING；装好 faster-whisper 后
    VS 自动转写，ref_text 可省略。
    """
    data = {
        "text": text,
        "language": "zh",
        "denoise": "true",
        "wav_bits": "16",
        "stream": "false",
    }
    if ref_text:
        data["ref_text"] = ref_text
    with ref_wav.open("rb") as f:
        r = _call_vs(
            "POST",
            "/generate",
            files={"ref_audio": (ref_wav.name, f, "audio/wav")},
            data=data,
        )
    if r.status_code >= 300:
        raise RuntimeError(f"tts failed {r.status_code}: {r.text[:200]}")
    if not r.content or len(r.content) < 44:
        raise RuntimeError("tts returned empty audio")
    tmp_wav = out_mp3.with_suffix(".wav")
    tmp_wav.write_bytes(r.content)
    try:
        _run([_find_ffmpeg() or "ffmpeg", "-y", "-i", str(tmp_wav), "-codec:a", "libmp3lame", "-q:a", "4", str(out_mp3)], out_mp3.parent, 120)
    finally:
        tmp_wav.unlink(missing_ok=True)
    dur = float(r.headers.get("X-Audio-Duration") or 0)
    return dur


# ---------- 人声提取 ----------


def _find_ffmpeg() -> Optional[str]:
    p = shutil.which("ffmpeg")
    if p:
        return p
    for cand in (
        Path(r"C:\Users\admin\Documents\DSH_Work\_tools\bin\ffmpeg.exe"),
        Path.home() / "scoop" / "shims" / "ffmpeg.exe",
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
    ):
        if cand.is_file():
            return str(cand)
    return None


def _net_env() -> dict:
    """外部下载用的环境：清掉 NO_PROXY，保留 HTTP(S)_PROXY。

    后端进程为了本机回环查询（VS 3900）常带 NO_PROXY=*，
    而 yt-dlp 抓视频站必须走代理，否则 HTTPSConnection 直接失败。
    """
    e = dict(os.environ)
    for k in ("NO_PROXY", "no_proxy"):
        e.pop(k, None)
    return e


def _run(cmd: list[str], cwd: Path, timeout_s: int, env: dict | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s,
                       encoding="utf-8", errors="replace", env=env)
    if p.returncode != 0:
        raise RuntimeError(f"cmd failed {' '.join(cmd[:3])}: {p.stderr[-400:]}")
    return p.stdout[-300:]


def download_audio(url: str, workdir: Path) -> Path:
    """yt-dlp 下载视频音轨为 wav（16k 单声道足够克隆）。"""
    out_tpl = workdir / "raw"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x", "--audio-format", "wav",
        "--postprocessor-args", f"ffmpeg:-ar {REF_RATE} -ac 1",
        "-f", "bestaudio/best",
        "-o", f"{out_tpl}.%(ext)s",
        "--no-playlist",
        "--socket-timeout", "30",
        "--retries", "5",
        "--fragment-retries", "5",
        url,
    ]
    _run(cmd, workdir, 600, env=_net_env())
    raw = workdir / "raw.wav"
    if not raw.is_file():
        raise RuntimeError("download ok but no wav output")
    return raw


def separate_vocals(src_wav: Path, workdir: Path) -> Path:
    """demucs 分离，取 vocals 轨，输出 16k 单声道 wav。"""
    _run([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", str(workdir), str(src_wav)], workdir, 900)
    # 输出路径：<workdir>/htdemucs/<stem>/vocals.wav
    vocal = workdir / "htdemucs" / src_wav.stem / "vocals.wav"
    if not vocal.is_file():
        raise RuntimeError("demucs ok but no vocals file")
    out = workdir / "vocals16k.wav"
    # VS 限制：无 transcript 的参考音频超过 20 秒会 400 clone_ref_too_long，
    # 官方建议 3–10 秒。这里掐掉开头静音再取前 8 秒，保证落在合规区间。
    _run([_find_ffmpeg() or "ffmpeg", "-y", "-i", str(vocal),
          "-af", "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-35dB",
          "-t", "8", "-ar", str(REF_RATE), "-ac", "1", str(out)], workdir, 60)
    return out


# ---------- 参考音频转写（faster-whisper 本地模型） ----------

# VS 下载好的 CTranslate2 模型快照，直接复用，backend 不再另下一份。
_WHISPER_MODEL_DIR = Path(
    r"C:\Users\admin\AppData\Local\OmniVoice\hf_cache"
    r"\models--Systran--faster-whisper-large-v3\snapshots"
    r"\edaa852ec7e145841d8ffdb056a99866b5f0a478"
)
_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(str(_WHISPER_MODEL_DIR), device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_ref(ref_wav: Path) -> str:
    """本地转写参考人声（8 秒），返回文本；任何失败返回空串，不阻断流程。

    参数取舍：vad_filter 关闭（避免 silero VAD 模型下载依赖），
    temperature=0 走 greedy 确定性输出，condition_on_previous_text 关闭
    （短参考片段不需要上下文条件），beam_size=5 常规宽度。
    """
    try:
        with _whisper_lock:
            model = _get_whisper()
            segments, _info = model.transcribe(
                str(ref_wav),
                language="zh",
                beam_size=5,
                vad_filter=False,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = "".join(s.text or "" for s in segments).strip()
        return text
    except Exception as e:  # noqa: BLE001
        log.warning("local transcribe failed: %s", e)
        return ""


# ---------- 任务管理 ----------


def _load_jobs() -> None:
    if JOBS_FILE.is_file():
        try:
            _JOBS.update(json.loads(JOBS_FILE.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass


def _save_jobs() -> None:
    with _LOCK:
        JOBS_FILE.write_text(json.dumps(_JOBS, ensure_ascii=False, indent=1), encoding="utf-8")


def new_job(kind: str, url: str | None) -> str:
    jid = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[jid] = {"kind": kind, "url": url, "status": "queued", "progress": "", "voice_id": None, "error": None, "ts": time.time()}
    _save_jobs()
    threading.Thread(target=_run_extract_job, args=(jid,), daemon=True).start()
    return jid


def job_status(jid: str) -> dict | None:
    return _JOBS.get(jid)


def _run_extract_job(jid: str) -> None:
    job = _JOBS[jid]
    url = job["url"]
    try:
        job["status"] = "downloading"
        job["progress"] = "正在下载视频音轨…"
        _save_jobs()
        workdir = DATA_DIR / "tmp" / jid
        workdir.mkdir(parents=True, exist_ok=True)
        raw = download_audio(url, workdir)

        job["status"] = "separating"
        job["progress"] = "正在分离人声、去掉背景音乐…"
        _save_jobs()
        vocal = separate_vocals(raw, workdir)

        job["status"] = "cloning"
        job["progress"] = "正在校验语音服务并保存声音…"
        _save_jobs()
        ok, detail = vs_health()
        if not ok:
            raise RuntimeError(f"VoiceStudio 不可用: {detail}")
        vid = str(uuid.uuid4().hex[:10])
        ref = REFS_DIR / f"{vid}.wav"
        shutil.copyfile(vocal, ref)
        job["voice_id"] = vid
        job["ref_path"] = ref.name

        job["status"] = "transcribing"
        job["progress"] = "正在转写参考人声…"
        _save_jobs()
        transcript = transcribe_ref(ref)
        _set_meta(vid, {"name": "提取的声音", "source": "extract",
                        "transcript": transcript, "ts": time.time()})
        job["status"] = "done"
        job["progress"] = "完成"
        _save_jobs()
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)[:300]
        _save_jobs()
    finally:
        shutil.rmtree(DATA_DIR / "tmp" / jid, ignore_errors=True)


def register_recording(src: Path) -> dict:
    """录制上传：保存为参考人声（TTS 时直传 /generate 零样本克隆）。"""
    _ensure_dirs()
    ok, detail = vs_health()
    if not ok:
        raise RuntimeError(f"VoiceStudio 不可用: {detail}")
    vid = str(uuid.uuid4().hex[:10])
    ref = REFS_DIR / f"{vid}.wav"
    # 统一转 24k 单声道 wav
    ffmpeg = _find_ffmpeg() or "ffmpeg"
    _run([ffmpeg, "-y", "-i", str(src), "-ar", str(REF_RATE), "-ac", "1", str(ref)], DATA_DIR, 120)
    _set_meta(vid, {"name": "我录制的声音", "source": "record", "ts": time.time()})
    return {"voice_id": vid}


def _set_meta(vid: str, item: dict) -> None:
    """写 voices.json 元数据（router 层共用同一路径）。"""
    mf = DATA_DIR / "voices.json"
    meta: dict = {}
    if mf.is_file():
        try:
            meta = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
    meta[vid] = item
    mf.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def synth(text: str, voice_id: str, ref_text: str | None = None) -> Path:
    """用本地 voice_id（ref wav）零样本合成语音，返回 mp3 路径。

    ref_text 为参考音频文字内容；从 voices.json 的 transcript 字段取。
    """
    _ensure_dirs()
    ref = REFS_DIR / f"{voice_id}.wav"
    if not ref.is_file():
        raise FileNotFoundError(f"ref not found: {voice_id}")
    if ref_text is None:
        mf = DATA_DIR / "voices.json"
        if mf.is_file():
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
                ref_text = (meta.get(voice_id) or {}).get("transcript")
            except Exception:  # noqa: BLE001
                ref_text = None
    cdir = CLIPS_DIR / voice_id
    cdir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(f"{voice_id}|{text}".encode("utf-8")).hexdigest()[:16]
    cached = cdir / f"c_{h}.mp3"
    if cached.is_file():
        return cached
    out = cdir / f"{uuid.uuid4().hex[:8]}.mp3"
    vs_tts(text, ref, out, ref_text)
    os.replace(out, cached)
    return cached
