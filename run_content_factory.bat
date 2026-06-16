@echo off
chcp 65001 >nul
cd /d "%~dp0"

set CONTENT_FACTORY_PORT=8792
set CONTENT_FACTORY_MODEL=gemma4:e2b
set CONTENT_FACTORY_DIR=%~dp0blog_content

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

if "%1"=="" (
  echo Usage:
  echo   run_content_factory.bat api          - FastAPI 서버 시작 ^(n8n 연동^)
  echo   run_content_factory.bat run "주제"   - 파이프라인 1회 실행
  exit /b 1
)

if /i "%1"=="api" (
  echo Content Factory API http://127.0.0.1:%CONTENT_FACTORY_PORT%
  python -m content_factory.api
  exit /b %ERRORLEVEL%
)

if /i "%1"=="run" (
  shift
  python -m content_factory.pipeline %*
  exit /b %ERRORLEVEL%
)

echo Unknown command: %1
exit /b 1
