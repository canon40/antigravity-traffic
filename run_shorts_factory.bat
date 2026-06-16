@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

rem 사용법:
rem   run_shorts_factory.bat living "kitchen sink, bathroom tile, wiping counter"
rem   run_shorts_factory.bat bike "motorcycle wash, helmet closeup, water beading"
rem   run_shorts_factory.bat auto "car detailing, water beading hood, microfiber wipe"

set "PRODUCT=%~1"
set "KEYWORDS=%~2"
if "%PRODUCT%"=="" set "PRODUCT=living"
if "%KEYWORDS%"=="" set "KEYWORDS=kitchen sink coating spray, bathroom tile coating, dining table coating, home glass coating, faucet chrome coating, easy cleaning kitchen lifestyle"

echo [쇼츠 공장] 제품: %PRODUCT%
echo [쇼츠 공장] 키워드: %KEYWORDS%
echo.

"%PY%" -m shorts_factory.build --product %PRODUCT% --keywords "%KEYWORDS%" --open
pause
