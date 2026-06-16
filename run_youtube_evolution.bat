@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo   YouTube 학습 - 동영상 제작 플레이북 진화
echo.
"%PY%" "%~dp0learn_youtube_evolution.py" --seed
if errorlevel 1 pause
