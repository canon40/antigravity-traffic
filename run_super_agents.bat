@echo off
chcp 65001 >nul
cd /d "%~dp0"

set SUPER_AGENT_MODEL=gemma4:e2b
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

if /i "%1"=="init" (
  echo [Super Agent] workflow.json 초기화
  "%PY%" -m super_agents.pipeline init
  exit /b %ERRORLEVEL%
)

if /i "%1"=="status" (
  "%PY%" -m super_agents.pipeline status
  exit /b %ERRORLEVEL%
)

if /i "%1"=="schedule" (
  echo [Super Agent] 매일 09:00 KST Windows 작업 등록
  schtasks /Create /TN "login2_super_agent_daily" /TR "\"%PY%\" \"%~dp0super_agents\pipeline.py\" run" /SC DAILY /ST 09:00 /F
  if errorlevel 1 (
    echo schtasks 등록 실패 — 관리자 권한으로 다시 시도하세요.
    pause
    exit /b 1
  )
  echo 등록 완료. 확인: schtasks /Query /TN login2_super_agent_daily
  exit /b 0
)

if /i "%1"=="guide" (
  call "%~dp0open_super_agents_guide.bat"
  exit /b %ERRORLEVEL%
)

if "%1"=="" (
  echo.
  echo   24/7 Super Agent — Base44 영상 로컬 구현
  echo   https://youtu.be/Ovj5f0ajDww
  echo.
  echo   Usage:
  echo     run_super_agents.bat              - 1회 실행 ^(리서치→스크립트→HTML^)
  echo     run_super_agents.bat init         - workflow.json 생성
  echo     run_super_agents.bat status       - 설정·Ollama·Gmail 상태
  echo     run_super_agents.bat schedule     - 매일 09:00 자동 실행 등록
  echo     run_super_agents.bat guide        - HTML 가이드 열기
  echo     run_super_agents.bat --email      - Gmail 발송 포함
  echo.
  echo   출력: data\super_agents\runs\
  echo.
  "%PY%" -m super_agents.pipeline run
  exit /b %ERRORLEVEL%
)

"%PY%" -m super_agents.pipeline run %*
exit /b %ERRORLEVEL%
