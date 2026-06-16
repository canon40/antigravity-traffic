@echo off
chcp 65001 >nul
echo Supabase SQL Editor 를 엽니다.
echo.
echo   sql\keywords_schema.sql      - 스마트스토어 keywords 테이블
echo   sql\blog_tasks_schedule.sql  - BlogTasks 컬럼/스케줄 시드
echo.
echo 필요한 파일 내용을 복사해 Run 하세요.
start "" "https://supabase.com/dashboard/project/qkporqtajfikppwsishz/sql/new"
pause
