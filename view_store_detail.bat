@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem SKU 지정: view_store_detail.bat bike_quick
set "SKU=%~1"

if defined SKU (
  start "상세페이지 미리보기" cmd /k "%PY%" "%~dp0docs\store_detail\serve_preview.py" --sku %SKU%
) else (
  start "상세페이지 미리보기" cmd /k "%PY%" "%~dp0docs\store_detail\serve_preview.py"
)

exit /b 0
