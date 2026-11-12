"""Qt GUI 线程 ↔ 本地 HTTP 工作线程之间的桥。

Qt 的对话框、剪贴板必须在主线程创建。HTTP 线程通过信号发出请求并阻塞在
``Promise`` 上，主线程的槽执行完后 set()，工作线程再读结果返回给前端。
信号是 AutoConnection，跨线程会自动排队，因此不会破坏 Qt 的线程亲和性。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal


@dataclass
class Promise:
    event: threading.Event = field(default_factory=threading.Event)
    value: Any = None
    error: str = ""

    def resolve(self, value: Any) -> None:
        self.value = value
        self.event.set()

    def fail(self, message: str) -> None:
        self.error = message
        self.event.set()

    def wait(self, timeout: float = 300.0) -> Any:
        if not self.event.wait(timeout):
            raise TimeoutError("原生对话框超时")
        if self.error:
            raise RuntimeError(self.error)
        return self.value


class NativeBridge(QObject):
    """发往主线程的原生能力请求。"""

    filesRequested = Signal(object)      # (Promise, options dict)
    folderRequested = Signal(object)     # (Promise, start_dir)
    cliRequested = Signal(object)        # (Promise, start_dir)
    wallpaperRequested = Signal(object)  # (Promise, start_dir)
    clipboardRequested = Signal(object)  # (Promise, text)
    droppedPaths = Signal(object)        # list[str]

    def pick_files(self, options: dict) -> list[str]:
        promise = Promise()
        self.filesRequested.emit((promise, options))
        return list(promise.wait() or [])

    def pick_folder(self, start_dir: str = "") -> str:
        promise = Promise()
        self.folderRequested.emit((promise, start_dir))
        return str(promise.wait() or "")

    def pick_cli(self, start_dir: str = "") -> str:
        promise = Promise()
        self.cliRequested.emit((promise, start_dir))
        return str(promise.wait() or "")

    def pick_wallpaper(self, start_dir: str = "") -> str:
        promise = Promise()
        self.wallpaperRequested.emit((promise, start_dir))
        return str(promise.wait() or "")

    def set_clipboard(self, text: str) -> None:
        promise = Promise()
        self.clipboardRequested.emit((promise, text))
        promise.wait()

    def dropped_paths(self, paths: list[str]) -> None:
        """Qt 窗口收到系统拖放时，把真实路径推给前端。"""
        self.droppedPaths.emit(paths)
