@echo off
title Permacoat SEO Hub
chcp 65001 > nul
cd /d "%~dp0"
cls

echo =============================================================
echo   나눔랩 SEO 허브 — 순위 / SEO / 블로그 초안
echo   웹: https://permacoat.shop
echo =============================================================
echo.

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [1] 의존성 확인...
"%PY%" -m pip install -r requirements.txt -q
echo.

echo [2] 서버 시작 (http://127.0.0.1:5000)
echo     휴대폰: 같은 Wi-Fi에서 PC IP:5000
echo     permacoat.shop 과 별도 — 로컬은 아래 주소 사용
echo.
set PORT=5000
start "" "http://127.0.0.1:5000"
"%PY%" app.py
pause
