# -*- coding: utf-8 -*-
"""pojia 链路部署：编译检查 + 同步 deploy + 重启 8000 后端。"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = r"C:\Users\admin\Documents\DSH_Work\life-assistant"
PY = r"C:\Users\admin\.workbuddy\binaries\python\envs\ipa\Scripts\python.exe"
CHANGED = [
 r"backend\app\services\pojia.py",
 r"backend\app\services\filters.py",
 r"backend\app\deps.py",
 r"backend\app\routers\pojia.py",
 r"backend\app\main.py",
]


def run(args, **kw):
 return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def main():
 os.chdir(ROOT)
 print("== 1. 语法检查 ==")
 for rel in CHANGED:
  p = os.path.join(ROOT, rel)
  r = run([PY, "-m", "py_compile", p])
  print(("OK " if r.returncode == 0 else "FAIL") + " " + rel + ("" if r.returncode == 0 else " " + r.stderr.strip()[:300]))

 print("\n== 2. 同步 deploy ==")
 for d in ("backend", "desktop"):
  src = os.path.join(ROOT, d)
  dst = os.path.join(ROOT, "deploy", d)
  for root, _dirs, files in os.walk(src):
   if "__pycache__" in root or ".git" in root or "node_modules" in root:
    continue
   relroot = os.path.relpath(root, src)
   target = os.path.join(dst, relroot)
   os.makedirs(target, exist_ok=True)
   for f in files:
    s, t = os.path.join(root, f), os.path.join(target, f)
    if not os.path.exists(t) or os.path.getmtime(s) > os.path.getmtime(t):
     shutil.copy2(s, t)
 print("synced backend + desktop")

 print("\n== 3. 重启后端 ==")
 kill = run(["cmd", "/c", "for /f \"tokens=5\" %a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %a"], timeout=30)
 print("kill out:", (kill.stdout or kill.stderr).strip()[:200] or "(none)")
 time.sleep(1)
 logf = os.path.join(ROOT, "la_backend.log")
 with open(logf, "w", encoding="utf-8") as f:
  pass
 env = dict(os.environ)
 env["HTTP_PROXY"] = env["HTTPS_PROXY"] = ""
 env["NO_PROXY"] = "*"
 proc = subprocess.Popen(
  [PY, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
  cwd=os.path.join(ROOT, "backend"), env=env,
  stdout=open(logf, "a", encoding="utf-8"), stderr=subprocess.STDOUT,
  creationflags=subprocess.CREATE_NO_WINDOW,
 )
 print("backend pid:", proc.pid)
 ok = False
 for _ in range(30):
  time.sleep(1)
  try:
   with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as resp:
    if resp.status == 200:
     ok = True
     break
  except Exception:
   pass
 if not ok:
  print("后端启动失败，日志尾部:")
  print(open(logf, encoding="utf-8", errors="replace").read()[-1200:])
  return 1
 print("health OK")
 return 0


if __name__ == "__main__":
 sys.exit(main())
