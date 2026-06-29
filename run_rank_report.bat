@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
if /I "%~1"=="--deep" (
  echo   전체 키워드 순위 — API 1000위 + Playwright 딥스캔 10000위 ^(로컬 PC, 수 시간^)
  echo   .env NAVER API + playwright install chromium 필요
  "%PY%" "%~dp0scripts\sync_catalog_ranks.py" --deep %*
) else (
  echo   전체 키워드 순위 — NAVER API 최대 1000위 ^(약 15~25분^)
  echo   1000위 밖: run_rank_report.bat --deep
  echo   .env 에 NAVER_CLIENT_ID/SECRET 필요
  "%PY%" "%~dp0scripts\sync_catalog_ranks.py" %*
)
echo.
pause
