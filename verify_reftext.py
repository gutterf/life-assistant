# -*- coding: utf-8 -*-
"""验证：本地转写参考人声 → 带 ref_text 调 VS TTS → mp3。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\admin\Documents\DSH_Work\life-assistant\backend")
from app.services import voice  # noqa: E402

VID = sys.argv[1] if len(sys.argv) > 1 else "3592223e82"
ref = voice.REFS_DIR / f"{VID}.wav"
print("ref exists:", ref.is_file(), flush=True)

t0 = time.time()
text = voice.transcribe_ref(ref)
print("TRANSCRIBE %.1fs -> %r" % (time.time() - t0, text), flush=True)

out = voice.CLIPS_DIR / VID / "verify_reftext.mp3"
out.parent.mkdir(parents=True, exist_ok=True)
t0 = time.time()
voice.vs_tts("这是从视频里提取的声音，现在用它读一段话。", ref, out, ref_text=text or None)
print("TTS %.1fs -> %s (%d bytes)" % (time.time() - t0, out, out.stat().st_size), flush=True)
