@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] config.py 백업...
if exist config.py copy /Y config.py config.py.bak

echo [2/4] 배포용 설정 적용 (config_dist.py -> config.py)...
copy /Y config_dist.py config.py

echo [3/4] PyInstaller로 blog auto.exe 빌드...
if not exist .venv\Scripts\activate.bat (
    echo .venv 없음. pip install pyinstaller 후 다시 실행하세요.
    goto restore
)
call .venv\Scripts\activate.bat
pyinstaller --clean --noconfirm blog_auto.spec
if errorlevel 1 (
    echo 빌드 실패.
    goto restore
)

echo [4/4] config.py 복원...
:restore
if exist config.py.bak (
    copy /Y config.py.bak config.py
    del config.py.bak
    echo config.py 복원 완료.
)

echo.
echo 완료. dist\blog auto.exe 를 다른 PC에 복사해 사용하세요.
echo (첫 실행 전 해당 PC에서 "playwright install" 또는 playwright 브라우저 설치 필요할 수 있음.)
pause
