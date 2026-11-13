"""生成 packaging/app.ico（多尺寸，内嵌 PNG），供 exe 与安装器复用。

运行：python packaging/make_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "app.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def build() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    sys.path.insert(0, str(ROOT))

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841
    from app.ui.theme import app_icon

    icon = app_icon()
    entries: list[tuple[int, bytes]] = []
    for size in SIZES:
        tmp = HERE / f"_tmp_{size}.png"
        if not icon.pixmap(size, size).save(str(tmp), "PNG"):
            raise RuntimeError(f"无法生成 {size}px 图标")
        entries.append((size, tmp.read_bytes()))
        tmp.unlink()

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    images = b""
    for size, png in entries:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        images += png
        offset += len(png)
    OUT.write_bytes(header + directory + images)
    print(f"ICO {OUT} ({OUT.stat().st_size} bytes, {len(entries)} sizes)")


if __name__ == "__main__":
    build()
