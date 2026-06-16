@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo   [평일 일과] 월~금: 글쓰기 + 서로이웃 + 답글 + 티스토리
echo   로그: data\daily_weekday.log
echo.

"%PY%" "%~dp0blog_daily_weekday.py" %*
exit /b %ERRORLEVEL%
