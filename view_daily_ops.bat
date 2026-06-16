@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
start "업무 대시보드" cmd /k "%PY%" "%~dp0ops_dashboard_server.py"
exit /b 0
