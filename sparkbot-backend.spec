from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH)  # PyInstaller injects SPECPATH; __file__ is not defined in spec context
backend_root = project_root / "backend"

# ── Data files ────────────────────────────────────────────────────────────────
datas = collect_data_files(
    "app",
    includes=["alembic/**", "email-templates/**"],
)
datas.append((str(backend_root / "alembic.ini"), "."))

# litellm bundles a lot of JSON/YAML provider configs — include them all
datas += collect_data_files("litellm")

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = collect_submodules("app")

# SQLAlchemy dialects needed at runtime
hiddenimports += [
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.ext.asyncio",
]

# litellm uses dynamic imports for every provider; include the common ones
hiddenimports += [
    "litellm.llms.openai",
    "litellm.llms.anthropic",
    "litellm.llms.gemini",
    "litellm.llms.groq",
    "litellm.llms.cohere",
    "litellm.llms.mistral",
    "litellm.llms.ollama",
    "litellm.llms.ollama_chat",
    "litellm.llms.openrouter",
    "litellm.llms.azure",
    "litellm.llms.azure_ai",
    "litellm.main",
    "litellm.utils",
    "litellm.types",
    "litellm.cost_calculator",
    "litellm.router",
]

# tiktoken (used by litellm for token counting)
hiddenimports += [
    "tiktoken",
    "tiktoken.core",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
]

# FastAPI / Starlette internals
hiddenimports += [
    "fastapi.routing",
    "fastapi.middleware",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.routing",
    "starlette.staticfiles",
    "starlette.responses",
    "uvicorn.main",
    "uvicorn.config",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
]

# Pydantic / email validators
hiddenimports += [
    "pydantic.networks",
    "pydantic.v1",
    "email_validator",
]

# JWT / crypto
hiddenimports += [
    "jwt",
    "cryptography.fernet",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "cryptography.hazmat.primitives.ciphers.aead",
]

# Alembic runtime
hiddenimports += [
    "alembic.runtime.migration",
    "alembic.runtime.environment",
    "alembic.script",
]

# httpx + httpcore (used by litellm for all HTTP calls)
hiddenimports += [
    "httpx",
    "httpcore",
    "anyio",
    "anyio.from_thread",
]

# ── Excludes — things that don't belong in a local SQLite build ───────────────
excludes = [
    # PostgreSQL driver — not needed for SQLite
    "psycopg",
    "psycopg2",
    "psycopg_binary",
    # Bridges — not needed in V1 Local mode
    "discord",
    "telegram",
    # Test frameworks
    "pytest",
    "mypy",
    "ruff",
]

a = Analysis(
    [str(backend_root / "app" / "desktop_entry.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sparkbot-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
