@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/2] 콘티 기반 상세페이지 생성 (키워드+이미지 12장)...
"%PY%" docs\store_detail\build_preview.py
if errorlevel 1 exit /b 1

echo [2/2] 로컬 서버 + 브라우저 미리보기 (종료: 서버 창에서 Ctrl+C)...
start "상세페이지 미리보기" cmd /k "%PY%" docs\store_detail\serve_preview.py --no-build

echo.
echo 브라우저: http://127.0.0.1:8765/index.html
echo 콘티:     http://127.0.0.1:8765/plan.html
echo 빠른 실행: view_store_detail.bat
echo 편집: docs\store_detail\bike_detail_conti.json
echo 스마트스토어용: docs\store_detail\store_detail_bike_*.html
