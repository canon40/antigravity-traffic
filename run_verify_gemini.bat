@echo off

chcp 65001 >nul

cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"

if not exist "%PY%" set "PY=python"

set "PYTHONIOENCODING=utf-8"

echo.

echo   Gemini API 연동 확인

echo.

"%PY%" "%~dp0scripts\verify_gemini.py"

echo.

pause


