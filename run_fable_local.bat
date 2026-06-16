@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [루프릴] Fable5 로컬 루프 — Ollama 무료 모드
echo.

where ollama >nul 2>&1
if errorlevel 1 (
  echo [안내] Ollama가 PATH에 없습니다.
  echo        https://ollama.com 에서 설치 후 다시 실행하세요.
  echo        Fable 루프 없이 Gemini/1회 생성만 가능합니다.
  echo.
) else (
  echo Ollama 확인 중...
  ollama list 2>nul
  if errorlevel 1 (
    echo [안내] ollama serve 가 실행 중인지 확인하세요.
  ) else (
    echo.
    echo 권장 모델 (빠름): set BLOG_OLLAMA_MODEL=gemma2:2b
    echo 또는: ollama pull qwen3:4b
    echo.
  )
)

set SHORTS_FABLE_LOOP=1
set BLOG_OLLAMA_MODEL=gemma2:2b
"%PY%" "%~dp0launch_shorts_studio.py"
if errorlevel 1 pause
