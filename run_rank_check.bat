@echo off
chcp 65001 >nul
title 나눔랩 실시간 순위 체크

echo.
echo ============================================================
echo   나눔랩 네이버 쇼핑 순위 실시간 체크
echo   - 자동차코팅제 / 바이크코팅제 비교
echo   - 퍼마코트 / 유리막코팅제 등 5개 키워드
echo ============================================================
echo.

echo [준비] 라이브러리 확인 중...
py -3.10 -m pip install requests beautifulsoup4 -q
echo [OK] 준비 완료

echo 체크 모드를 선택하세요:
echo   [1] 1회 즉시 체크 (빠름)
echo   [2] 자동 반복 체크 (60분마다)
echo   [3] 자동 반복 체크 (30분마다)
echo.
set /p mode="선택 (1/2/3, 엔터=1회): "

if "%mode%"=="2" (
    echo.
    echo [반복] 60분마다 순위 체크 시작... (Ctrl+C로 종료)
    py -3.10 rank_monitor_live.py --watch --interval 60
) else if "%mode%"=="3" (
    echo.
    echo [반복] 30분마다 순위 체크 시작... (Ctrl+C로 종료)
    py -3.10 rank_monitor_live.py --watch --interval 30
) else (
    echo.
    echo [1회] 순위 즉시 체크 중...
    py -3.10 rank_monitor_live.py
)

echo.
echo 결과는 rank_live_log.csv 에도 저장됩니다.
pause
