@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0programs_check.py" %*
if errorlevel 1 (
  echo.
  echo   필수 점검 실패. AGENT_PIPELINE.md 의 [0단계] 를 먼저 완료하세요.
  echo.
  pause
  exit /b 1
)
if "%~1"=="" pause
exit /b 0
