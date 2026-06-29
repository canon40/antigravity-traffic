@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo [스마트스토어 SEO 반영] 미진입 키워드 상품 우선
python scripts\apply_smartstore_seo.py %*
pause
