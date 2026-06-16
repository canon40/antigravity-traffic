@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo   나눔랩 순위 일일 추적 (전체 키워드)
echo.
"%PY%" "%~dp0scripts\rank_daily.py" %*
pause
