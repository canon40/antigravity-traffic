@echo off
chcp 65001 >nul
title 나눔랩 AI 블로그 자동 포스팅

echo.
echo ============================================================
echo   나눔랩 AI 블로그 자동 포스팅 엔진
echo   - 자동차코팅제 SEO 최적화 글 자동 생성
echo   - 초안: blog_drafts 폴더에 HTML 파일로 저장
echo   - 티스토리 API 설정 시 자동 발행
echo ============================================================
echo.

echo [준비] 라이브러리 확인 중...
py -3.10 -m pip install requests beautifulsoup4 -q
echo [OK] 준비 완료

echo 실행 모드를 선택하세요:
echo   [1] 글 1개 즉시 생성 (테스트)
echo   [2] 무한 자동 발행 엔진 (하루 최대 5개)
echo   [3] 키워드 트렌드 분석 먼저 실행
echo.
set /p mode="선택 (1/2/3, 엔터=1개 생성): "

if "%mode%"=="2" (
    echo.
    echo [엔진] 무한 자동 발행 시작... (Ctrl+C로 종료)
    py -3.10 blog_autoposter.py --engine
) else if "%mode%"=="3" (
    echo.
    echo [분석] 키워드 트렌드 분석 실행...
    py -3.10 keyword_trend_analyzer.py
    echo.
    echo 분석 완료. 블로그 글도 생성하시겠습니까? (Y/N)
    set /p ans="선택: "
    if /i "%ans%"=="Y" (
        py -3.10 blog_autoposter.py --once
    )
) else (
    echo.
    echo [생성] 블로그 글 1개 즉시 생성 중...
    py -3.10 blog_autoposter.py --once
)

echo.
echo 생성된 초안은 'blog_drafts' 폴더에서 확인하세요.
echo 네이버 블로그에 붙여넣기 하시면 됩니다.
pause
