@echo off
rem Double-click this to start the FastAPI backend on all network interfaces.
rem Keep this file ASCII only: cmd reads .bat in the OEM codepage and Chinese garbles.
rem All Chinese output lives in scripts\start-backend.ps1.
chcp 65001 >nul
title LifeAssistant - backend
cd /d "%~dp0"

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-backend.ps1"
