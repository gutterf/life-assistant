@echo off
rem 生活助手桌面版 - 一键启动：语音引擎 VoiceStudio + 后端 API（单端口全栈）+ 独立窗口
chcp 65001 >nul 2>&1

set "PYC=C:\Users\admin\.workbuddy\binaries\python\envs\ipa\Scripts\python.exe"
set "ROOT=C:\Users\admin\Documents\DSH_Work\life-assistant"

rem 1) VoiceStudio 语音引擎（3900，零样本克隆 TTS + faster-whisper 转写）
netstat -ano | findstr "127.0.0.1:3900" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
 echo [1/2] 启动语音引擎 VoiceStudio...
 start "VoiceStudio" /min cmd /c "cd /d %ROOT%\VoiceStudio\backend && set HF_ENDPOINT=https://hf-mirror.com && set NO_PROXY=127.0.0.1,localhost && %PYC% -m uvicorn main:app --host 127.0.0.1 --port 3900"
 timeout /t 6 /nobreak >nul
) else (
 echo [1/2] 语音引擎已在运行
)

rem 2) 后端 API（8000：聊天/路线/OCR/语音/会话/卫星地图，静态页同源挂载）
netstat -ano | findstr "127.0.0.1:8000" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
 echo [2/2] 启动后端 API...
 start "LifeAssistant-Backend" /min cmd /c "cd /d %ROOT%\backend && set NO_PROXY=* && %PYC% -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
 timeout /t 5 /nobreak >nul
) else (
 echo [2/2] 后端 API 已在运行
)

start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:8000/ --window-size=1280,860
