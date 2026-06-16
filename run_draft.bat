@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set BLOG_API_SPARING=1
set BLOG_TEXT_PROVIDER=ollama
set BLOG_IMAGE_PROVIDER=genai
set BLOG_OLLAMA_MODEL=qwen3:4b
set BLOG_OLLAMA_TIMEOUT=480

if "%~1"=="" (
  echo.
  echo   사용법: run_draft.bat "키워드"
  echo   예:     run_draft.bat "자동차 유리막 코팅"
  echo.
  exit /b 1
)

"%PY%" "%~dp0draft_blog.py" --keyword %*
exit /b %ERRORLEVEL%
