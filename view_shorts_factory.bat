@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "data/shorts_factory/stock_api_keys.json" (
  echo(
  echo [안내] data/shorts_factory/stock_api_keys.json 이 없습니다.
  echo        data/shorts_factory/stock_api_keys.example.json 을 복사한 뒤 API 키를 넣으세요.
  echo        Pexels: https://www.pexels.com/api/
  echo        Pixabay: https://pixabay.com/api/docs/
  echo(
)
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0launch_shorts_studio.py"
if errorlevel 1 pause
