@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [1/2] 가상환경 생성...
  python -m venv "%~dp0.venv"
  set "PY=%~dp0.venv\Scripts\python.exe"
)

if not exist "%PY%" (
  echo Python을 찾을 수 없습니다. run_install.bat 을 먼저 실행하세요.
  pause
  exit /b 1
)

echo [2/2] Flask 확인...
"%PY%" -m pip install flask -q

set CANON_AUTOBLOG_PORT=8790
echo.
echo   canon4040 블로그 스튜디오
echo   http://127.0.0.1:%CANON_AUTOBLOG_PORT%/
echo.
start "" "http://127.0.0.1:%CANON_AUTOBLOG_PORT%/"
"%PY%" "%~dp0blog_studio_web.py"
