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

if not exist ".venv\Scripts\python.exe" (
  echo  [설치] 가상환경이 없습니다. run_install.bat 을 실행합니다...
  call "%~dp0run_install.bat"
  if errorlevel 1 exit /b 1
)

set "PY=.venv\Scripts\python.exe"

echo [1] 의존성 확인...
"%PY%" -m pip install -r requirements.txt -q
echo.

echo [2] 프로그램 카탈로그 동기화...
if defined CLOUDTYPE (
  "%PY%" "%~dp0scripts\sync_javis_catalog.py" --bundled-only
) else (
  "%PY%" "%~dp0scripts\sync_javis_catalog.py"
)
echo.

echo [3] 서버 시작 (http://127.0.0.1:5000)
echo     로컬 실행 탭의 bat 은 이 주소에서만 PC에 실행됩니다.
echo     permacoat.shop 은 클라우드 대체 동작만 합니다.
echo.
set PORT=5000
start "" "http://127.0.0.1:5000"
"%PY%" app.py
pause
