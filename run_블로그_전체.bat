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
echo   블로그 전체 발행 (login2 단독 — JARVIS 없이도 실행)
echo   티스토리 + 네이버 — accounts.json 설정 사용
echo.
if "%~1"=="" (
  echo   사용: run_블로그_전체.bat "키워드"
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
