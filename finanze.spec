# -*- mode: python ; coding: utf-8 -*-
import platform


a = Analysis(
    ['finanze/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['speech_recognition', 'pydub', 'aiohttp', 'selenium', 'seleniumwire', 'playwright'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if (platform_name := platform.system().lower()) == 'darwin':
    platform_name = f"macos-{'arm64' if platform.machine() == 'arm64' else 'x64'}"

exec_name = 'finanze-server-{}'.format(platform_name)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exec_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
