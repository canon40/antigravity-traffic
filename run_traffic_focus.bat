@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "NOPAUSE=0"
set "ARGS=%*"
if /I "%~1"=="--no-pause" (
  set "NOPAUSE=1"
  set "ARGS=%ARGS:--no-pause=%"
)

echo.
echo =============================================================
echo   나눔랩 트래픽 1회 (스마트스토어 상품 URL 방문)
echo   ※ 키워드 검색 트래픽(Playwright)은 이 허브에서 제거됨
echo   ※ Cloud 24h와 동일: config 첫 상품 URL HTTP 방문
echo =============================================================
echo.

"%PY%" "%~dp0scripts\traffic_once.py" --mode local %ARGS%
if errorlevel 1 (
  if "%NOPAUSE%"=="0" pause
  exit /b 1
)
if "%NOPAUSE%"=="1" exit /b 0
