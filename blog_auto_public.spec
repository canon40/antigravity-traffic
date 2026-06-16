# -*- mode: python ; coding: utf-8 -*-


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
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='autoblog2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
