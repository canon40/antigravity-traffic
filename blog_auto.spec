# PyInstaller spec for blog auto.exe (배포용)
# 사용: build_blog_auto.bat 실행 전에 config_dist.py가 config.py로 복사된 상태여야 함.

# -*- mode: python ; coding: utf-8 -*-
import sys

block_cipher = None

a = Analysis(
    ['blog_main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'blog_content_gen',
        'blog_gui_tabs',
        'blog_automation_flow',
        'blog_theme',
        'doc_guidelines',
        'naver_module',
        'tistory_module',
        'google_blogger_auto',
        'blogger_browser',
        'config',
        'PIL',
        'PIL._tkinter_finder',
        'google.generativeai',
        'playwright.async_api',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='autoblog',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI만 표시 (콘솔 창 숨김)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
