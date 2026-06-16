@echo off
title Nanumlab SEO Manager (Flet Mobile)
chcp 65001 > nul
cls

echo =============================================================
echo   나눔랩 SEO 매니저 — Flet 모바일 앱 실행
echo =============================================================
echo.

python -m pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo 패키지 설치 실패. Python 설치를 확인하세요.
    pause
    exit /b
)

echo PC에서 앱 창이 열립니다. APK 빌드는 build_apk.bat 을 실행하세요.
echo.
python main.py
pause
