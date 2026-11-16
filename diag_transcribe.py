# -*- coding: utf-8 -*-
"""诊断：3592223e82.wav 转写为什么为空。"""
import time
from faster_whisper import WhisperModel

M = r"C:\Users\admin\AppData\Local\OmniVoice\hf_cache\models--Systran--faster-whisper-large-v3\snapshots\edaa852ec7e145841d8ffdb056a99866b5f0a478"
W = r"C:\Users\admin\Documents\DSH_Work\life-assistant\backend\data\voice\refs\3592223e82.wav"

t = time.time()
m = WhisperModel(M, device="cpu", compute_type="int8")
print("load %.1fs" % (time.time() - t), flush=True)

t = time.time()
segs, info = m.transcribe(W, beam_size=1, vad_filter=True)
print("transcribe %.1fs lang=%s langprob=%.2f dur=%.1fs" % (time.time() - t, info.language, info.language_probability, info.duration), flush=True)
segs = list(segs)
print("segments:", len(segs), flush=True)
for s in segs:
    print("  [%.2f-%.2f] %r" % (s.start, s.end, s.text), flush=True)
