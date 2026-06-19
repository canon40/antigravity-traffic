@echo off

chcp 65001 >nul

cd /d "%~dp0"

set CANON_AUTOBLOG_PORT=8790

set PY=%~dp0.venv\Scripts\python.exe

if not exist "%PY%" set PY=C:\Users\hymin\AppData\Local\Python\bin\python.exe

if not exist "%PY%" set PY=python

set JARVIS_ROOT=D:\@code\javis

set BLOG_STANDALONE=0

set BLOG_JAVIS_BRIDGE=1

start "Canon4040 Blog Web" /D "%~dp0" "%PY%" "%~dp0blog_studio_web.py"

