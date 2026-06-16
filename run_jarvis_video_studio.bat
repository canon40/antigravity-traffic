@echo off
chcp 65001 >nul
set "JARVIS_ROOT=D:\@code\javis"
set "JARVIS_START_MODE=동영상 스튜디오"
set "JARVIS_VIDEO_PRESET=duracoat_living"
cd /d "%JARVIS_ROOT%"
if not exist "%JARVIS_ROOT%\run_video_studio.bat" (
  echo [ERROR] JARVIS folder missing: %JARVIS_ROOT%
  pause
  exit /b 1
)
call "%JARVIS_ROOT%\run_video_studio.bat"
