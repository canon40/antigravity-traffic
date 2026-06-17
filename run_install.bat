@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo.
echo  ========================================
echo   Permacoat SEO 허브 — 설치
echo  ========================================
echo.

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo  [1/4] 가상환경 .venv 생성 ...
  python -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo  Python 3.10+ 필요
    pause
    exit /b 1
  )
)

echo  [2/4] pip 업그레이드 ...
"%PY%" -m pip install --upgrade pip wheel -q

echo  [3/4] requirements.txt 설치 ...
"%PY%" -m pip install -r "%~dp0requirements.txt" -q

echo  [4/4] 프로그램 카탈로그 갱신 ...
"%PY%" "%~dp0scripts\sync_javis_catalog.py"

echo.
echo  SEO 허브 검증 ...
"%PY%" "%~dp0scripts\verify_seo_hub.py"
echo.
echo  트래픽 모듈 검증 ...
"%PY%" "%~dp0scripts\verify_vercel_traffic.py"
echo.
call "%~dp0run_programs_check.bat" --minimal

echo.
echo  완료. 실행: run.bat  /  검증: run_seo_hub_verify.bat
echo.
pause
exit /b 0
