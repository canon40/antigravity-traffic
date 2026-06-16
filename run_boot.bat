@echo off
chcp 65001 >nul
cd /d "%~dp0"
set BLOG_API_SPARING=1
set BLOG_TEXT_PROVIDER=ollama
set BLOG_IMAGE_PROVIDER=genai
set BLOG_OLLAMA_MODEL=qwen3:4b
set CANON_AUTOBLOG_PORT=8790

echo.
echo  [0] 프로그램 점검...
call "%~dp0run_programs_check.bat" --minimal
if errorlevel 1 exit /b 1

echo.
echo  [1] 서랍 모듈 목록...
call "%~dp0run_drawer.bat" list

echo.
echo  [2] GUI 시작 (이미 실행 중이면 건너뜀)...
call "%~dp0run_gui.bat"
exit /b 0
