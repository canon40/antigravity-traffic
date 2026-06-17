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

echo  [4/6] 프로그램 카탈로그 갱신 ...
if defined CLOUDTYPE (
  "%PY%" "%~dp0scripts\sync_javis_catalog.py" --bundled-only
) else (
  "%PY%" "%~dp0scripts\sync_javis_catalog.py"
)

echo  [5/6] JARVIS 서브모듈 (선택) ...
git submodule update --init --recursive javis 2>nul

echo  [6/6] Playwright Chromium (블로그 발행/서이추) ...
"%PY%" -m playwright install chromium
if errorlevel 1 (
  echo  Playwright Chromium 설치 실패
  pause
  exit /b 1
)
"%PY%" -c "from playwright_bootstrap import ensure_playwright_ready; import sys; sys.exit(0 if ensure_playwright_ready() else 1)"

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
