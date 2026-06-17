@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
set "NOPAUSE=0"
if /I "%~1"=="--no-pause" (
  set "NOPAUSE=1"
  shift
)
echo.
echo   blog post — 키워드 1회 발행 (traffic 로컬)
echo.
if "%~1"=="" (
  echo   사용: run_blog_post.bat "키워드"
  "%PY%" "%~dp0_run_blog_session.py"
  goto :done
)
set "BLOG_OVERRIDE_KEYWORD=%~1"
"%PY%" "%~dp0_run_blog_session.py"
:done
if "%NOPAUSE%"=="1" (
  exit /b 0
) else (
  pause
)
