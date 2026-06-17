@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
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
pause
