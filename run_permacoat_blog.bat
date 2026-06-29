@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
echo   퍼마코트 SEO 블로그 초안 (Gemini + 스마트스토어 링크)
echo   예: run_permacoat_blog.bat 12577296206
echo   목록: run_permacoat_blog.bat --list
echo.
if "%~1"=="" (
  echo   자동차 예: 12577296206 ^(디테일링^)  12578368490 ^(퀵 티탄^)
  echo   바이크 예: 12655391634 ^(헬멧^)      12751444412 ^(퀵^)
  set /p PID="상품 ID: "
  if "!PID!"=="" (
    pause
    exit /b 1
  )
  "%PY%" "%~dp0scripts\permacoat_blog_seo.py" "!PID!"
) else (
  "%PY%" "%~dp0scripts\permacoat_blog_seo.py" %*
)
echo.
pause
