@echo off
chcp 65001 >nul
set "JARVIS_ROOT=D:\@code\javis"
set "JARVIS_START_MODE=상세페이지 스튜디오"
set "LOGIN2_ROOT=%~dp0"
cd /d "%LOGIN2_ROOT%"
set "PY=%LOGIN2_ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1] LoopReel 상세페이지 스튜디오 서버 확인...
"%PY%" "%LOGIN2_ROOT%launch_detail_page.py"
if errorlevel 1 (
  echo 서버 시작 대기 중...
  timeout /t 2 /nobreak >nul
)

echo [2] JARVIS Streamlit — 상세페이지 스튜디오 모드...
if not exist "%JARVIS_ROOT%\run_detail_page_studio.bat" (
  echo [WARN] JARVIS run_detail_page_studio.bat 없음 — 브라우저만 열림
  pause
  exit /b 0
)
cd /d "%JARVIS_ROOT%"
call "%JARVIS_ROOT%\run_detail_page_studio.bat"
