@echo off
chcp 65001 >nul
cd /d "%~dp0"
set BLOG_LIGHT_GUI=0
set BLOG_LAZY_TABS=0
set BLOG_JAVIS_BRIDGE=1
set BLOG_DEFER_BROWSER=0
set BLOG_BROWSER_PER_ROUND=0
call "%~dp0run_gui.bat"
