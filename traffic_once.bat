@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "NOPAUSE=0"
set "ARGS=%*"
if /I "%~1"=="--no-pause" (
  set "NOPAUSE=1"
  set "ARGS=%ARGS:--no-pause=%"
)
"%PY%" "%~dp0scripts\traffic_once.py" --mode local %ARGS%
if errorlevel 1 (
  if "%NOPAUSE%"=="0" pause
  exit /b 1
)
if "%NOPAUSE%"=="1" exit /b 0
