@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set CANON_AUTOBLOG_PORT=8790
echo.
echo   canon4040 블로그 스튜디오 — http://127.0.0.1:%CANON_AUTOBLOG_PORT%/
echo.
"%PY%" "%~dp0blog_studio_web.py"
