@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"

echo === SEO 허브 파이프라인 검증 (로컬) ===
"%PY%" "%~dp0scripts\verify_seo_hub.py" %*
set "EC=%ERRORLEVEL%"
if not "%~1"=="" exit /b %EC%
pause
exit /b %EC%
