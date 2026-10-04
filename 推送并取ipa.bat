@echo off
rem One-click: commit -> push -> wait for GitHub Actions -> drop ipa on Desktop
rem Keep this file ASCII only (cmd reads .bat in the OEM codepage; Chinese garbles).
rem All Chinese output lives in scripts\poll-build.ps1.
chcp 65001 >nul
title LifeAssistant - push and fetch ipa
cd /d "%~dp0"

set "GIT=C:\Program Files\Git\cmd\git.exe"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo.
echo   [1/3] commit
"%GIT%" add -A
"%GIT%" -c user.name=gutterf -c user.email=gutterf@users.noreply.github.com commit -m "update" 2>nul

echo   [2/3] push
rem Push straight to github.com. Your global git config rewrites
rem https://github.com/ to the ghproxy mirror, which is read-only and
rem has a mismatched certificate, so the rewrite is disabled for this one
rem command via an empty config file (your global config is left untouched).
set "EMPTYCFG=%TEMP%\gitconfig-empty"
if not exist "%EMPTYCFG%" type nul > "%EMPTYCFG%"
set "GIT_CONFIG_GLOBAL=%EMPTYCFG%"
set "GIT_CONFIG_NOSYSTEM=1"
set "GIT_TERMINAL_PROMPT=0"
"%GIT%" push "https://github.com/gutterf/life-assistant.git" HEAD:main
if errorlevel 1 (
  echo.
  echo   push failed. Check network / credentials.
  echo.
  pause
  exit /b 1
)

echo   [3/3] wait for build and download ipa
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\poll-build.ps1"

echo.
pause
