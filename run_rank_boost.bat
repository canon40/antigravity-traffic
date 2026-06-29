@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo [순위 부스트] SEO 반영 후 키워드 동기화 + 순위 추적 + 트래픽
python scripts\launch_rank_boost.py %*
pause
