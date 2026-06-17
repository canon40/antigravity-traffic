@echo off
chcp 65001 >nul
cd /d "%~dp0"
set CANON_AUTOBLOG_PORT=8790
set PY=%~dp0.venv\Scripts\python.exe
set PYW=%~dp0.venv\Scripts\pythonw.exe
if not exist "%PY%" set PY=python
if not exist "%PYW%" set PYW=%PY%

"%PY%" "%~dp0blog_single_instance.py" --check
if errorlevel 1 goto launch

echo.
echo   Autoblog is already running. Use the existing window.
echo.
exit /b 0

:launch
set BLOG_API_SPARING=0
set BLOG_TEXT_PROVIDER=gemini
set BLOG_IMAGE_PROVIDER=genai
set BLOG_OLLAMA_MODEL=qwen3:4b
set BLOG_OLLAMA_TIMEOUT=120
if not defined BLOG_LIGHT_GUI set BLOG_LIGHT_GUI=1
if not defined BLOG_LAZY_TABS set BLOG_LAZY_TABS=1
set BLOG_JAVIS_BRIDGE=0
set BLOG_JARVIS_MODEL_ROUTING=0
set BLOG_STANDALONE=1
if not defined BLOG_DEFER_BROWSER set BLOG_DEFER_BROWSER=1
if not defined BLOG_BROWSER_PER_ROUND set BLOG_BROWSER_PER_ROUND=1
if not defined BLOG_UNLOAD_AFTER_JOB set BLOG_UNLOAD_AFTER_JOB=1

echo   Playwright 점검 중...
"%PY%" -c "from playwright_bootstrap import ensure_playwright_ready; raise SystemExit(0 if ensure_playwright_ready() else 1)"
if errorlevel 1 (
  echo   Playwright 복구 실패. run_fix_playwright.bat 을 실행하세요.
  pause
  exit /b 1
)

start "Canon4040 Autoblog" /D "%~dp0" "%PYW%" "%~dp0blog_main.py"
