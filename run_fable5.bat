@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "JARVIS_ROOT=D:\@code\javis"
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%JARVIS_ROOT%\run_claude_fable.py" (
  echo [ERROR] JARVIS not found: %JARVIS_ROOT%
  pause
  exit /b 1
)

if /i "%~1"=="apply" (
  echo === Claude Fable 5 전역 적용 ===
  if exist "%JARVIS_ROOT%\.venv\Scripts\python.exe" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" "%JARVIS_ROOT%\run_claude_fable.py" --apply
  ) else (
    python "%JARVIS_ROOT%\run_claude_fable.py" --apply
  )
  goto verify
)

if /i "%~1"=="loop" (
  if exist "%JARVIS_ROOT%\.venv\Scripts\python.exe" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" "%JARVIS_ROOT%\run_claude_fable.py" --loop
  ) else (
    python "%JARVIS_ROOT%\run_claude_fable.py" --loop
  )
  goto verify
)

if /i "%~1"=="guide" (
  if exist "%JARVIS_ROOT%\.venv\Scripts\python.exe" (
    "%JARVIS_ROOT%\.venv\Scripts\python.exe" "%JARVIS_ROOT%\run_claude_fable.py" --guide
  ) else (
    python "%JARVIS_ROOT%\run_claude_fable.py" --guide
  )
  goto end
)

:verify
echo.
echo === login2 연동 확인 ===
"%PY%" "%~dp0verify_fable_openclaw.py" --fable-only
goto end

:end
if "%~1"=="" pause
exit /b 0
