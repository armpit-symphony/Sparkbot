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

# tiktoken 0.8+ discovers encodings via importlib.metadata entry points which are
# unavailable in a frozen PyInstaller bundle, causing "Unknown encoding cl100k_base"
# after the first few LLM calls once the in-process cache expires.
# collect_all bundles the vocab data files AND tiktoken_ext (the openai_public plugin
# that registers cl100k_base / p50k_base / r50k_base / o200k_base).
_tiktoken_datas, _tiktoken_binaries, _tiktoken_hiddenimports = collect_all("tiktoken")
# tiktoken_ext is a namespace inside the tiktoken distribution, not a separate
# PyPI package — collect_all("tiktoken") already picks it up.

block_cipher = None

REPO_ROOT = Path(SPECPATH)          # spec lives at repo root
BACKEND_DIR = REPO_ROOT / "backend"
HOOKS_DIR = str(REPO_ROOT / "pyinstaller-hooks")

a = Analysis(
    [str(BACKEND_DIR / "desktop_launcher.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[] + _litellm_binaries + _certifi_binaries + _tiktoken_binaries,
    datas=[
        # Email templates shipped with the bundle
        (str(BACKEND_DIR / "app" / "email-templates"), "app/email-templates"),
    ] + _litellm_datas + _certifi_datas + _tiktoken_datas,
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
        # tiktoken encoding plugins — must be explicit so frozen importlib.metadata finds them
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
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
        # SQLAlchemy SQLite dialect — needed for local SQLite mode
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.dialects.sqlite.pysqlite",
        # SQLModel (wraps SQLAlchemy + Pydantic)
        "sqlmodel",
        # cryptography — used by Guardian Vault (lazy import, must be explicit)
        "cryptography",
        "cryptography.fernet",
        # alembic — imported at module level in some sqlmodel paths
        "alembic",
        "alembic.runtime.migration",
        "alembic.operations",
    ] + _litellm_hiddenimports + _certifi_hiddenimports + _tiktoken_hiddenimports,
    hookspath=[HOOKS_DIR],
    hooksconfig={},
    runtime_hooks=[str(REPO_ROOT / "pyinstaller-hooks" / "rthook_tiktoken.py")],
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
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
