@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo.
echo   [평일 통합 일과] 월~금
echo   - 퍼마코트 자동차 / 바이크 / 리빙코트 블로그
echo   - 서로이웃, 답글, 티스토리, 이웃 새글 댓글
echo   - 인스타 DM 오늘 팩 + 업무 대시보드
echo   로그: data\weekly_ops.log
echo   클릭 대시보드: view_daily_ops.bat  (http://127.0.0.1:8770/)
echo.

"%PY%" "%~dp0blog_weekly_ops.py" %*
exit /b %ERRORLEVEL%
