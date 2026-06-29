@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
echo   키워드 순위 진행 현황 (몇 위까지 진입했는지)
echo.
"%PY%" "%~dp0scripts\rank_progress.py"
echo.
pause
