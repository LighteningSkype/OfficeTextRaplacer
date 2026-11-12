"""shadcn/ui 版本的程序入口：QtWebEngine 窗口 + 本地 HTTP 服务。

* 界面：web/dist 里的 React + Tailwind + shadcn/ui 单页应用；
* 能力：app/server/api.py 提供的本地 REST 接口，复用 app/core 的替换引擎；
* 原生能力：文件/文件夹选择框、系统剪贴板、OS 拖放通过信号桥回到 GUI 线程。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
)


def _prepare_webengine_env() -> None:
    """必须在导入 QtWebEngine 之前执行的两个环境设置。

    * ``AA_ShareOpenGLContexts``：Qt 强制要求，不开启会导致 WebEngine 的
      合成器与主窗口不共享 GL 上下文，在部分显卡驱动上表现为整窗持续闪烁。
      这个属性必须在导入 ``QtWebEngineWidgets`` **之前**用
      ``QGuiApplication.setAttribute`` 设定，晚了不生效。
    * 沙箱：部分受管会话里 Chromium 沙箱起不来会白屏，本程序只加载本机
      自身构建的页面，默认关闭；需要保留时设 OTR_WEBENGINE_SANDBOX=1。
    * GL 后端：驱动异常时可用 OTR_WEBENGINE_GL=desktop|software 强制指定。
    """
    QGuiApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    backend = (os.environ.get("OTR_WEBENGINE_GL") or "").strip().lower()
    if backend in ("desktop", "software"):
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --use-gl={backend}".strip()

    if os.environ.get("OTR_WEBENGINE_SANDBOX") != "1":
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")


_prepare_webengine_env()

from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

from .core.config import APP_SUBTITLE, APP_TITLE, Settings
from .server.api import make_server
from .server.bridge import NativeBridge
from .ui.theme import app_icon

# PyInstaller onefile 的静态资源会解压至 _MEIPASS；源码模式仍从项目根目录读取。
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DIST = ROOT / "web" / "dist"

FILE_FILTER = (
    "Office 文件 (*.docx *.xlsx *.pptx);;"
    "Word 文档 (*.docx);;Excel 工作簿 (*.xlsx);;"
    "PowerPoint 演示文稿 (*.pptx);;所有文件 (*.*)"
)

IMAGE_FILTER = (
    "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif);;"
    "JPG 图片 (*.jpg *.jpeg);;PNG 图片 (*.png);;所有文件 (*.*)"
)


def _apply_palette(app: QApplication, theme: str) -> None:
    """只影响原生对话框/菜单，网页本身由 CSS 变量控制。"""
    from PySide6.QtGui import QColor, QPalette

    if theme != "dark":
        return
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#18181b"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#fafafa"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#202024"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#27272a"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#fafafa"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#27272a"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#fafafa"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3b82f6"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


class DropFilter(QObject):
    """在应用级别拦截 OS 拖放，把真实 Windows 路径交给前端。

    QWebEngineView 内部会把 file:// 拖放事件吞掉，且浏览器出于安全不会给出
    完整本地路径；由 Qt 侧捕获后注入才能保证 "拖进来就能用"。
    """

    def __init__(self, bridge: NativeBridge, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            mime = getattr(event, "mimeData", lambda: None)()
            if mime is not None and getattr(mime, "hasUrls", lambda: False)():
                event.acceptProposedAction()
                if kind == QEvent.Type.Drop:
                    paths = [
                        u.toLocalFile()
                        for u in mime.urls()
                        if u.isLocalFile() and u.toLocalFile()
                    ]
                    if paths:
                        self.bridge.dropped_paths(paths)
                return True
        return super().eventFilter(obj, event)


class HostWindow(QMainWindow):
    def __init__(self, url: str, bridge: NativeBridge, devtools: bool = False) -> None:
        super().__init__()
        self.bridge = bridge
        self.setWindowTitle(f"{APP_TITLE} · {APP_SUBTITLE}")
        self.setWindowIcon(app_icon())
        self.resize(1400, 900)
        self.setMinimumSize(1080, 680)

        self.view = QWebEngineView(self)
        # 网页自己实现 shadcn ContextMenu，屏蔽 WebEngine 自带菜单避免叠两层。
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setCentralWidget(self.view)

        self.bridge.filesRequested.connect(self._pick_files)
        self.bridge.folderRequested.connect(self._pick_folder)
        self.bridge.cliRequested.connect(self._pick_cli)
        self.bridge.wallpaperRequested.connect(self._pick_wallpaper)
        self.bridge.clipboardRequested.connect(self._set_clipboard)
        self.bridge.droppedPaths.connect(self._push_paths)

        self.view.load(QUrl(url))
        self.view.loadFinished.connect(self._on_loaded)

    # -- 原生能力槽 ---------------------------------------------------------

    def _pick_files(self, payload) -> None:
        promise, options = payload
        start = str(options.get("start_dir") or "")
        try:
            files, _ = QFileDialog.getOpenFileNames(
                self, "选择 Office 文件", start, FILE_FILTER
            )
            promise.resolve(files)
        except Exception as exc:  # noqa: BLE001
            promise.fail(str(exc))

    def _pick_folder(self, payload) -> None:
        promise, start = payload
        try:
            promise.resolve(QFileDialog.getExistingDirectory(self, "选择文件夹", start or ""))
        except Exception as exc:  # noqa: BLE001
            promise.fail(str(exc))

    def _pick_cli(self, payload) -> None:
        promise, start = payload
        try:
            name = "officecli.exe" if sys.platform == "win32" else "officecli"
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 office-cli 可执行文件", start or "", f"{name} (*);;所有文件 (*.*)"
            )
            promise.resolve(path)
        except Exception as exc:  # noqa: BLE001
            promise.fail(str(exc))

    def _pick_wallpaper(self, payload) -> None:
        promise, start = payload
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择背景壁纸图片", start or "", IMAGE_FILTER
            )
            promise.resolve(path)
        except Exception as exc:  # noqa: BLE001
            promise.fail(str(exc))

    def _set_clipboard(self, payload) -> None:
        promise, text = payload
        try:
            QGuiApplication.clipboard().setText(text)
            promise.resolve(None)
        except Exception as exc:  # noqa: BLE001
            promise.fail(str(exc))

    def _push_paths(self, paths) -> None:
        payload = json.dumps(list(paths), ensure_ascii=False)
        script = (
            "window.dispatchEvent(new CustomEvent('native-paths',"
            f"{{detail: {{paths: {payload}}}}}));"
        )
        self.view.page().runJavaScript(script)

    def _on_loaded(self, ok: bool) -> None:
        if not ok:
            return
        # 把宿主环境告诉前端，便于显示 "桌面模式" 标记与启用拖放提示。
        self.view.page().runJavaScript(
            "window.__OFFICE_REPLACER_NATIVE__ = true;"
        )


def main(devtools: bool = False) -> int:
    if not (DIST / "index.html").is_file():
        print("前端资源未构建：缺少 web/dist/index.html")
        print("请先执行：cd web && npm install && npm run build")
        return 2

    # Qt 要求：使用 QWebEngineView 前必须开启共享 OpenGL 上下文，
    # 否则部分机器上会出现合成器重绘异常（窗口闪烁、局部残影）。
    if devtools:
        os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9223")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("OfficeTextReplacer")
    app.setWindowIcon(app_icon())
    settings = Settings.load()
    _apply_palette(app, settings.theme)

    bridge = NativeBridge()
    httpd = make_server(DIST, bridge)
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    drop_filter = DropFilter(bridge, app)
    app.installEventFilter(drop_filter)

    window = HostWindow(url, bridge, devtools=devtools)
    window.show()
    code = app.exec()
    httpd.shutdown()
    return code
