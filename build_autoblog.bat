@echo off
REM autoblog.exe (키워드 + API 키 포함 / 내 PC용)
pyinstaller --noconfirm blog_auto.spec

REM autoblog2.exe (기본 키워드·API 키 없음 / 다른 PC 배포용)
pyinstaller --noconfirm blog_auto_public.spec

echo.
echo 빌드가 완료되었습니다. dist\autoblog.exe 와 dist\autoblog2.exe 를 확인하세요.
pause

