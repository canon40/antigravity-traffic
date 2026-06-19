@echo off
chcp 65001 >nul
cd /d "%~dp0"
set CANON_AUTOBLOG_PORT=8790
set PY=%~dp0.venv\Scripts\python.exe
set PYW=%~dp0.venv\Scripts\pythonw.exe
if not exist "%PY%" set PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe
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
set JARVIS_ROOT=D:\@code\javis
set BLOG_STANDALONE=0
set BLOG_JAVIS_BRIDGE=1
if not defined BLOG_DEFER_BROWSER set BLOG_DEFER_BROWSER=1
if not defined BLOG_BROWSER_PER_ROUND set BLOG_BROWSER_PER_ROUND=1
if not defined BLOG_UNLOAD_AFTER_JOB set BLOG_UNLOAD_AFTER_JOB=1

echo   Playwright 점검 중...
"%PY%" -m pip install -r "%~dp0requirements-blog.txt" -q
"%PY%" -c "from playwright_bootstrap import ensure_playwright_ready; raise SystemExit(0 if ensure_playwright_ready() else 1)"
if errorlevel 1 (
  echo   Playwright 점검 실패 — GUI는 계속 실행합니다.
  echo   (발행 자동화가 필요하면 run_fix_playwright.bat 으로 복구하세요.)
)

start "Canon4040 Autoblog" /D "%~dp0" "%PYW%" "%~dp0blog_main.py"
