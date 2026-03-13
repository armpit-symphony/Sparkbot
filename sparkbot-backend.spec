from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(__file__).resolve().parent
backend_root = project_root / "backend"

datas = collect_data_files(
    "app",
    includes=["alembic/**", "email-templates/**"],
)
datas.append((str(backend_root / "alembic.ini"), "."))

hiddenimports = collect_submodules("app")

a = Analysis(
    [str(backend_root / "app" / "desktop_entry.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
