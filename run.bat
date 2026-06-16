@echo off
title Permacoat SEO Monitor
chcp 65001 > nul
cls

echo =============================================================
echo   나눔랩 SEO 매니저 (웹 PWA + 순위/키워드/콘텐츠)
echo   모바일 앱: run_mobile.bat  /  APK: build_apk.bat
echo =============================================================
echo.

echo [1단계] 라이브러리 설치 중...
python -m pip install --upgrade pip > nul 2>&1
python -m pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo 파이썬 또는 pip 설치를 확인해 주세요.
    pause
    exit /b
)
echo.

echo [2단계] 로컬 IP 확인 중...
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1 -ExpandProperty IPAddress"`) do (
    set LOCAL_IP=%%i
)

echo =============================================================
echo   휴대폰 접속 방법:
echo.
echo   1. PC와 휴대폰이 같은 Wi-Fi에 연결되어 있어야 합니다.
echo   2. 휴대폰 브라우저에서 아래 주소를 입력하세요:
echo.
echo      http://%LOCAL_IP%:5000
echo.
echo   3. "홈 화면에 추가" 또는 "앱 설치"로 PWA 앱처럼 사용하세요.
echo =============================================================
echo.

echo [3단계] 서버 실행 중...
python app.py
pause
