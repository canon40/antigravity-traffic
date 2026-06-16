@echo off
chcp 65001 > nul
echo.
echo ╔══════════════════════════════════════════════╗
echo ║   나눔랩 SEO 전략 파이프라인 실행           ║
echo ║   목표: 10위권 진입                          ║
echo ╚══════════════════════════════════════════════╝
echo.

echo [1/3] 틈새 키워드 발굴 중...
python keyword_opportunity_finder.py --apply
echo.

echo [2/3] 상품별 블로그 초안 생성 중...
python seo_blog_campaign.py --from-report --count 3
echo.

echo [3/3] SEO 전략 보고서 생성 중...
python seo_strategy_report.py
echo.

echo ✅ 파이프라인 완료!
echo 📂 블로그 초안: blog_drafts\
echo 📊 전략 보고서: seo_strategy_report.html
echo.
pause
