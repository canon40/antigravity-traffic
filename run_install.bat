@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo.
echo  ========================================
echo   Canon4040 Autoblog - CMD 설치
echo  ========================================
echo.

set "PY=%~dp0.venv\Scripts\python.exe"
set "PIP=%~dp0.venv\Scripts\pip.exe"

if not exist "%PY%" (
  echo  [1/5] 가상환경 생성 .venv ...
  python -m venv "%~dp0.venv"
  if errorlevel 1 (
    echo  Python 3.10+ 가 필요합니다. https://python.org
    pause
    exit /b 1
  )
)

if not exist "%PIP%" set "PIP=python -m pip"

echo  [2/5] pip 업그레이드 ...
"%PY%" -m pip install --upgrade pip wheel -q

if not exist "%~dp0requirements.txt" (
  echo  requirements.txt 없음 - httpx만 설치합니다.
  "%PY%" -m pip install "httpx>=0.28.1" -q
) else (
  echo  [3/5] requirements.txt 설치 (시간이 걸릴 수 있음) ...
  "%PY%" -m pip install -r "%~dp0requirements.txt" -q
  if errorlevel 1 (
    echo  pip install 실패. 네트워크 또는 requirements.txt 확인.
    pause
    exit /b 1
  )
)

echo  [4/5] Playwright Chromium (블로그 발행용, 선택) ...
"%PY%" -m playwright install chromium 2>nul
if errorlevel 1 (
  echo        Playwright 브라우저 설치 생략 또는 실패 - 발행 전 다시 실행하세요.
)

echo  [5/6] SEO 허브 API 검증 ...
"%PY%" "%~dp0scripts\verify_seo_hub.py"
set "SH=%ERRORLEVEL%"

echo  [6/6] Vercel 트래픽 연동 검증 ...
"%PY%" "%~dp0scripts\verify_vercel_traffic.py"
set "VC=%ERRORLEVEL%"

echo.
echo  프로그램 점검 (필수만) ...
call "%~dp0run_programs_check.bat" --minimal

echo.
if "%VC%"=="0" if "%SH%"=="0" (
  echo  설치 완료. GUI: run_gui.bat  /  허브 검증: run_seo_hub_verify.bat
) else if "%SH%"=="0" (
  echo  설치 완료 (Vercel 트래픽 검증 일부 실패). 허브: run_seo_hub_verify.bat
) else (
  echo  설치 완료 (SEO 허브 검증 실패 — scripts\verify_seo_hub.py 확인)
)
echo.
pause
exit /b 0
