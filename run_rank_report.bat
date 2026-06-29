@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"
echo.
echo   전체 키워드 순위 조회 (NAVER API — 약 10~20분)
echo   .env 에 NAVER_CLIENT_ID/SECRET 필요
echo.
"%PY%" "%~dp0scripts\export_all_ranks.py" %*
echo.
pause
