@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PYTHONIOENCODING=utf-8"

if /i "%~1"=="probes" (
  "%PY%" "%~dp0drawer\cli.py" dev-plan --probes-only
  goto end
)

if /i "%~1"=="blog" (
  "%PY%" "%~dp0drawer\cli.py" pipeline --mode blog
  goto end
)

if /i "%~1"=="check" (
  echo === [0] programs_check ===
  call "%~dp0run_programs_check.bat" --minimal
  echo.
  echo === Fable / OpenClaw ===
  "%PY%" "%~dp0verify_fable_openclaw.py"
  goto end
)

echo === 프로그램 개발 — 에이전트 사용 순서 ===
echo.
"%PY%" "%~dp0drawer\cli.py" dev-plan --task "%*"
echo.
echo --- 빠른 명령 ---
echo   run_dev_pipeline.bat probes     설치된 에이전트 JSON
echo   run_dev_pipeline.bat check      환경+연동 점검
echo   run_dev_pipeline.bat blog       블로그 콘텐츠 파이프라인 순서
echo   run_drawer.bat dev-plan --json  전체 계획 JSON
echo.

:end
if "%~1"=="" pause
exit /b 0
