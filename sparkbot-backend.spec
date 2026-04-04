# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Sparkbot backend sidecar binary.
# Build with:  pyinstaller --distpath src-tauri/binaries sparkbot-backend.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# litellm uses heavy dynamic imports + bundled data files; collect everything
_litellm_datas, _litellm_binaries, _litellm_hiddenimports = collect_all("litellm")

# certifi: bundle the CA certificate store so httpx/requests can verify HTTPS inside the frozen exe
_certifi_datas, _certifi_binaries, _certifi_hiddenimports = collect_all("certifi")

block_cipher = None

BACKEND_DIR = Path(SPECPATH) / "backend"

a = Analysis(
    [str(BACKEND_DIR / "desktop_launcher.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[] + _litellm_binaries + _certifi_binaries,
    datas=[
        # Email templates shipped with the bundle
        (str(BACKEND_DIR / "app" / "email-templates"), "app/email-templates"),
    ] + _litellm_datas + _certifi_datas,
    hiddenimports=[
        # uvicorn internals not auto-discovered
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # FastAPI / Starlette extras
        "fastapi",
        "starlette",
        "email_validator",
        # litellm (collected via collect_all above)
        "litellm",
        # App modules
        "app",
        "app.main",
        "app.core",
        "app.core.config",
        "app.api",
        "app.api.main",
        "app.api.deps",
        "app.api.routes",
        "app.services",
        "app.services.guardian",
        "certifi",
    ] + _litellm_hiddenimports + _certifi_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
        "test",
        "tests",
    ],
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
    name="sparkbot-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir="pyi-runtime",
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
