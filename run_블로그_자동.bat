@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   블로그 자동 GUI (login2 단독 — JARVIS 연동 선택)
echo.
call "%~dp0run_gui.bat"
exit /b %ERRORLEVEL%
