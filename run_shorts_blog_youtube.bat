@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
echo   숏폼 -^> YouTube -^> 블로그(영상첨부) -^> 트래픽
echo   예: run_shorts_blog_youtube.bat "퍼마코트 자동차"
echo.
if "%~1"=="" (
  set /p KW="키워드: "
  if "!KW!"=="" (
    echo 키워드 필요
    pause
    exit /b 1
  )
  "%PY%" "%~dp0scripts\run_shorts_blog_youtube.py" "!KW!"
) else (
  "%PY%" "%~dp0scripts\run_shorts_blog_youtube.py" %*
)
echo.
pause
