@echo off
chcp 65001 >nul
title 나눔랩 통합 순위 스케줄러

echo.
echo ████████████████████████████████████████████████████████████
echo  나눔랩 순위 자동 모니터 - 상태별 주기 자동 조정
echo  미노출: 15분  /  진입중: 30분  /  노출중: 60분
echo ████████████████████████████████████████████████████████████
echo.

:: ── 작업 디렉토리 설정 ──────────────────────────────────────
cd /d "%~dp0"

:: ── 로그 파일 경로 ──────────────────────────────────────────
set LOG_FILE=monitor_auto.log

echo [%date% %time%] 스케줄러 시작 >> %LOG_FILE%
echo 로그: %LOG_FILE%
echo.

:: ── Python 경로 자동 탐지 ───────────────────────────────────
where python >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python
) else (
    where py >nul 2>&1
    if %errorlevel% == 0 (
        set PYTHON=py
    ) else (
        echo [오류] Python을 찾을 수 없습니다.
        pause
        exit /b 1
    )
)

:: ── 실행 옵션 선택 ──────────────────────────────────────────
echo 실행 모드를 선택하세요:
echo   [1] 자동 조정 (기본 - 상태에 따라 주기 변경)
echo   [2] 집중 모드 (15분 고정)
echo   [3] 표준 모드 (30분 고정)
echo   [4] 절약 모드 (60분 고정)
echo   [5] 1회 즉시 체크
echo.
set /p CHOICE="선택 (기본=1, Enter로 바로 시작): "

if "%CHOICE%"=="" set CHOICE=1
if "%CHOICE%"=="1" goto AUTO
if "%CHOICE%"=="2" goto FAST
if "%CHOICE%"=="3" goto NORMAL
if "%CHOICE%"=="4" goto SLOW
if "%CHOICE%"=="5" goto ONCE
goto AUTO

:AUTO
echo [자동 조정 모드] 상태별 주기 자동 조정...
%PYTHON% rank_scheduler.py --pages 5 2>&1 | tee -a %LOG_FILE%
goto END

:FAST
echo [집중 모드] 15분 고정...
%PYTHON% rank_scheduler.py --fast --pages 5 2>&1 | tee -a %LOG_FILE%
goto END

:NORMAL
echo [표준 모드] 30분 고정...
%PYTHON% rank_scheduler.py --normal --pages 5 2>&1 | tee -a %LOG_FILE%
goto END

:SLOW
echo [절약 모드] 60분 고정...
%PYTHON% rank_scheduler.py --slow --pages 5 2>&1 | tee -a %LOG_FILE%
goto END

:ONCE
echo [1회 체크]...
%PYTHON% rank_scheduler.py --once --pages 5
goto END

:END
echo.
echo [%date% %time%] 스케줄러 종료 >> %LOG_FILE%
echo 프로그램이 종료되었습니다.
pause
