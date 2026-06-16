@echo off
title Build APK - Nanumlab SEO Manager
chcp 65001 > nul
cls

echo =============================================================
echo   Flet APK 빌드 (Android)
echo =============================================================
echo.
echo 사전 요구사항:
echo   - Python 3.10+
echo   - Android SDK / JDK (Flet 빌드 시 자동 안내)
echo   - 인터넷 연결
echo.

python -m pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo pip 설치 실패
    pause
    exit /b
)

echo APK 빌드 시작... (수 분~30분 소요될 수 있습니다)
echo Windows: 설정 - 개발자용 - 개발자 모드 ON 권장 (심볼릭 링크)
echo.

set FLET_CLI_NO_RICH_OUTPUT=1
flet build apk --project nanumlab-seo-manager --module-name main --product "Nanumlab SEO" --org com.nanumlab --android-permissions android.permission.INTERNET=true --no-rich-output --yes

if %ERRORLEVEL% neq 0 (
    echo.
    echo flet 빌드 단계 실패. Flutter로 직접 빌드 시도...
    set SERIOUS_PYTHON_SITE_PACKAGES=%CD%\build\site-packages
    cd build\flutter
    flutter build apk --release
    cd ..\..
)

if not exist build\apk mkdir build\apk
if exist build\flutter\build\app\outputs\flutter-apk\app-release.apk (
    copy /Y build\flutter\build\app\outputs\flutter-apk\app-release.apk build\apk\nanumlab-seo-manager.apk >nul
    echo.
    echo 빌드 완료: build\apk\nanumlab-seo-manager.apk
) else if exist build\apk\app-release.apk (
    echo.
    echo 빌드 완료: build\apk\app-release.apk
) else (
    echo.
    echo 빌드 실패. flet doctor 로 환경을 점검하세요.
    echo   flet doctor
)

pause
