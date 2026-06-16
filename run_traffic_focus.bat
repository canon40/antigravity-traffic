@echo off
chcp 65001 >nul
title 나눔랩 자동차코팅제 집중 트래픽 엔진

echo.
echo ============================================================
echo   나눔랩 자동차코팅제 집중 순위 상승 엔진
echo   - 집중 키워드: 자동차코팅제 (75%% 집중)
echo   - 세션 간격: 최소 15분
echo   - 봇 감지 시: 45분 자동 쿨다운
echo ============================================================
echo.

echo [준비] 라이브러리 확인 중...
py -3.10 -m pip install requests beautifulsoup4 playwright playwright-stealth pandas -q
echo [OK] 준비 완료

echo.
echo 실행 모드를 선택하세요:
echo   [1] 1회 테스트 실행 (결과 확인 후 종료)
echo   [2] 24시간 연속 엔진 실행 (권장: 하루 3~5회 수동 실행)
echo.
set /p mode="선택 (1 또는 2): "

if "%mode%"=="1" (
    echo.
    echo [테스트] 1회 세션 실행 중...
    py -3.10 traffic_single.py --test
) else if "%mode%"=="2" (
    echo.
    echo [엔진] 24시간 연속 실행 시작 (Ctrl+C로 종료)
    py -3.10 traffic_single.py --engine
) else (
    echo.
    echo [기본] 1회 테스트 실행
    py -3.10 traffic_single.py --test
)

echo.
echo [완료] 작업이 종료되었습니다.
pause
