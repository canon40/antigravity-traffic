@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
if /I "%~1"=="--api-only" (
  echo   전체 키워드 순위 — NAVER API 최대 1000위만 ^(빠른 조회^)
  "%PY%" "%~dp0scripts\sync_catalog_ranks.py" --api-only %*
) else (
  echo   전체 키워드 순위 — API 1000위 + 미노출 자동 Playwright 딥스캔 ^(10000위^)
  echo   .env NAVER API + playwright install chromium 필요
  echo   API만: run_rank_report.bat --api-only
  "%PY%" "%~dp0scripts\sync_catalog_ranks.py" --auto-deep %*
)
echo.
pause
