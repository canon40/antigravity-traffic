@echo off
chcp 65001 >nul
set PY=C:\Users\hymin\AppData\Local\Programs\Python\python310\python.exe
echo.
echo ====================================================
echo   나눔랩 미노출 상품 순위 진입 엔진
echo ====================================================
echo.
echo [1] 현재 순위 체크만 (빠름)
echo [2] 1회 테스트 세션 (창 표시)
echo [3] 연속 엔진 가동 - 백그라운드 (권장)
echo [4] 연속 엔진 가동 - 창 표시 모드
echo.
set /p choice="선택 (1/2/3/4): "

if "%choice%"=="1" (
    echo.
    echo 순위 체크 중...
    %PY% rank_booster.py --check
)
if "%choice%"=="2" (
    echo.
    echo 1회 테스트 실행 (브라우저 창 표시)...
    %PY% rank_booster.py --once --show
)
if "%choice%"=="3" (
    echo.
    echo 연속 엔진 가동 (백그라운드 헤드리스 모드)...
    echo    (Ctrl+C 로 중지)
    %PY% rank_booster.py --headless
)
if "%choice%"=="4" (
    echo.
    echo 연속 엔진 가동 (브라우저 창 표시 모드)...
    echo    (Ctrl+C 로 중지)
    %PY% rank_booster.py --show
)

pause
