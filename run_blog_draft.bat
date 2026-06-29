@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
echo   블로그 초안 + 스마트스토어 링크 (반자동 발행용)
echo   예: run_blog_draft.bat "퍼마코트 자동차"
echo.
if "%~1"=="" (
  set /p KW="키워드: "
  if "!KW!"=="" (
    echo 키워드가 비어 있습니다.
    pause
    exit /b 1
  )
  "%PY%" "%~dp0scripts\generate_blog_draft.py" "!KW!"
) else (
  "%PY%" "%~dp0scripts\generate_blog_draft.py" %*
)
echo.
pause
