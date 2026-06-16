@echo off
cd /d "%~dp0"
python scripts\traffic_once.py --mode local %*
if errorlevel 1 pause
