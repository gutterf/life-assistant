@echo off
rem 生活助手桌面版 - 一键启动：语音引擎 VoiceStudio + 后端 API + 本地页面 + 独立窗口
chcp 65001 >nul 2>&1

set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\ipa\Scripts\pythonw.exe"
set "PYC=C:\Users\admin\.workbuddy\binaries\python\envs\ipa\Scripts\python.exe"
set "ROOT=C:\Users\admin\Documents\DSH_Work\life-assistant"

rem 1) VoiceStudio 语音引擎（3900，零样本克隆 TTS + faster-whisper 转写）
netstat -ano | findstr "127.0.0.1:3900" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo [1/3] 启动语音引擎 VoiceStudio...
  start "VoiceStudio" /min cmd /c "cd /d %ROOT%\VoiceStudio\backend && set HF_ENDPOINT=https://hf-mirror.com && %PYC% -m uvicorn main:app --host 127.0.0.1 --port 3900"
  timeout /t 6 /nobreak >nul
) else (
  echo [1/3] 语音引擎已在运行
)

rem 2) 后端 API（8000，聊天/路线/OCR/语音）
rem NO_PROXY 让本机回环不被代理接管；访问外网视频时后端内部会自己清掉它
netstat -ano | findstr "127.0.0.1:8000" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo [2/3] 启动后端 API...
  start "LifeAssistant-Backend" /min cmd /c "cd /d %ROOT%\backend && set NO_PROXY=* && %PYC% -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
  timeout /t 5 /nobreak >nul
) else (
  echo [2/3] 后端 API 已在运行
)

rem 3) 本地页面服务（7891）+ 独立窗口
netstat -ano | findstr "127.0.0.1:7891" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo [3/3] 启动本地页面...
  start /b "" "%PY%" -m http.server 7891 --bind 127.0.0.1 --directory "%ROOT%\desktop"
  timeout /t 1 /nobreak >nul
)
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:7891/ --window-size=1280,860
