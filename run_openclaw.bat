@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "OPENCLAW_WORKSPACE=%~dp0.openclaw\workspace"
set "JARVIS_ROOT=D:\@code\javis"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

where openclaw >nul 2>&1
if errorlevel 1 (
  echo [ERROR] openclaw CLI not found. Run: npm install -g openclaw@latest
  pause
  exit /b 1
)

if /i "%~1"=="onboard" (
  echo === OpenClaw 온보딩 (Ollama + 게이트웨이 데몬) ===
  openclaw onboard --non-interactive --accept-risk --mode local --auth-choice ollama --skip-channels --flow quickstart --install-daemon --skip-health --workspace "%OPENCLAW_WORKSPACE%"
  goto status
)

if /i "%~1"=="start" (
  openclaw gateway start
  goto status
)

if /i "%~1"=="stop" (
  openclaw gateway stop
  goto end
)

if /i "%~1"=="restart" (
  openclaw gateway restart
  goto status
)

if /i "%~1"=="dashboard" (
  start "" http://127.0.0.1:18789/
  goto end
)

if /i "%~1"=="checklist" (
  if exist "%JARVIS_ROOT%\run_openclaw_ai_employee.py" (
    if exist "%JARVIS_ROOT%\.venv\Scripts\python.exe" (
      "%JARVIS_ROOT%\.venv\Scripts\python.exe" "%JARVIS_ROOT%\run_openclaw_ai_employee.py" --action checklist
    ) else (
      python "%JARVIS_ROOT%\run_openclaw_ai_employee.py" --action checklist
    )
  ) else (
    echo JARVIS OpenClaw playbook not found.
  )
  goto end
)

:status
echo.
echo === OpenClaw 게이트웨이 ===
openclaw gateway status
echo.
echo === login2 연동 확인 ===
"%PY%" "%~dp0verify_fable_openclaw.py" --openclaw-only
goto end

:end
if "%~1"=="" (
  echo.
  echo Usage: run_openclaw.bat [onboard^|start^|stop^|restart^|dashboard^|checklist]
  echo   기본: gateway status + 연동 점검
  echo   dashboard: http://127.0.0.1:18789/
  pause
)
exit /b 0
