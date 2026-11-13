# -*- mode: python ; coding: utf-8 -*-
"""Windows 便携目录版（onedir）：解压即用，不在运行时解压到 %TEMP%。

单文件版（OfficeTextReplacer.spec）在临时目录不可写、磁盘紧张或杀软拦截时
会报 "decompression resulted in return code -3"；目录版没有这个环节。

运行：python -m PyInstaller --noconfirm OfficeTextReplacer-onedir.spec
输出：dist/OfficeTextReplacer-2.0.0-win64/（整个目录可打包分发）
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
DIST = ROOT / "web" / "dist"
if not (DIST / "index.html").is_file():
    raise RuntimeError("web/dist/index.html 缺失：请先在 web 目录运行 npm run build")

candidates = [
    Path.home() / "AppData" / "Roaming" / "npm" / "node_modules"
    / "@officecli" / "officecli" / "vendor" / "officecli.exe",
]
configured = os.environ.get("OFFICECLI_BIN", "")
if configured:
    candidates.insert(0, Path(configured))
try:
    import app.core.cli as office_cli

    detected = office_cli.discover()
    if detected is not None:
        candidates.insert(0, Path(detected.path))
except Exception:
    pass

cli_binary = next(
    (path for path in candidates if path.is_file() and path.suffix.lower() == ".exe"),
    None,
)
if cli_binary is None:
    raise RuntimeError("无法定位 officecli.exe：设置 OFFICECLI_BIN 后重新构建")

datas = [(str(DIST), "web/dist"), (str(cli_binary), "vendor")]
hiddenimports = collect_submodules("PySide6.QtWebEngineCore")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OfficeTextReplacer",
    icon=str(ROOT / "packaging" / "app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="OfficeTextReplacer-2.0.0-win64",
)
