@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "JARVIS_ROOT=D:\@code\javis"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/2] JARVIS .env Supabase 동기화...
"%PY%" "%~dp0sync_jarvis_env.py"
echo.
echo [2/2] 연동 점검...
"%PY%" "%~dp0javis_connect_check.py"
echo.
pause
