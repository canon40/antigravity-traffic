@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe
set PW=%~dp0.venv\Scripts\playwright.exe
if not exist "%PY%" set PY=python
if not exist "%PW%" set PW=playwright

echo.
echo   Playwright 브라우저 복구 (글 발행 / 서이추 / 티스토리에 필요)
echo.
"%PY%" -m pip install --force-reinstall playwright
"%PW%" install chromium
"%PY%" -c "from playwright_bootstrap import ensure_playwright_ready; import sys; sys.exit(0 if ensure_playwright_ready() else 1)"
echo.
if errorlevel 1 (
  echo   복구 실패 — 위 오류 메시지를 확인하세요.
) else (
  echo   복구 완료. run_gui.bat 으로 다시 실행하세요.
)
echo.
pause
