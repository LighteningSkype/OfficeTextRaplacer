# -*- mode: python ; coding: utf-8 -*-
"""Windows 便携单文件构建：保留 app/web/dist 与 vendor/officecli.exe 的内部布局。

运行：python -m PyInstaller --noconfirm --clean OfficeTextReplacer.spec
软件运行时零安装、零注册表写入；PyInstaller 解压到系统临时目录，配置保存在 EXE 同目录。
"""

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

# 构建机器定位 officecli.exe；路径只在打包时使用，绝不写进 EXE 的运行时配置。
import os

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
cli_binary = next((path for path in candidates if path.is_file() and path.suffix.lower() == ".exe"), None)
if cli_binary is None:
    raise RuntimeError("无法定位 officecli.exe：设置 OFFICECLI_BIN 后重新构建")

# QtWebEngine 由 PyInstaller 内置 PySide6 hook 收集其进程和 Qt 资源。
# 收集 PySide6.QtWebEngineCore 模块，避免纯运行时子模块被漏掉。
datas = [(str(DIST), "web/dist"), (str(cli_binary), "vendor")]
binaries = []
hiddenimports = collect_submodules("PySide6.QtWebEngineCore")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
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
    a.binaries,
    a.datas,
    [],
    name="OfficeTextReplacer",
    icon=str(ROOT / "packaging" / "app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
)
