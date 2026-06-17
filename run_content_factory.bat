@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo   콘텐츠 팩토리 — SEO 블로그·상품 초안 생성
echo.
"%PY%" -c "from javis_serverless import run_serverless_program; import json; r=run_serverless_program('traffic_content_factory', {'id':'traffic_content_factory','name':'콘텐츠 팩토리','category':'blog','workspace':'traffic'}, print); print(json.dumps(r, ensure_ascii=False, indent=2))"
echo.
pause
