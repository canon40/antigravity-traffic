@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [MV 가이드] 쇼츠 스튜디오 서버 확인 후 가이드 페이지를 엽니다.
"%PY%" "%~dp0launch_shorts_studio.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8766/guide/mv-flow/"
echo.
echo 가이드: http://127.0.0.1:8766/guide/mv-flow/
pause
