"""视觉主题：深色、低饱和、单一强调色。

Qt 样式表不支持阴影/过渡，因此层次全部靠"表面色阶 + 1px 描边"表达。
少量图标（勾选、箭头）在首次运行时写成 SVG，避免仓库里塞二进制资源。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from ..core.config import app_data_dir

# ------------------------------------------------------------------ 颜色令牌

BG = "#0E1116"
SURFACE = "#151A22"
SURFACE_2 = "#1A2029"
SURFACE_3 = "#212836"
BORDER = "#242B37"
BORDER_SOFT = "#1C222C"
TEXT = "#E8EDF6"
TEXT_DIM = "#98A5B9"
TEXT_MUTED = "#68748A"

ACCENT = "#4C8DFF"
ACCENT_HOVER = "#6AA2FF"
ACCENT_PRESSED = "#3B7AE6"
SUCCESS = "#3ED598"
WARNING = "#F0B357"
DANGER = "#FF6B6B"
INFO = "#7FB2FF"

WORD_COLOR = "#3B7BD4"
EXCEL_COLOR = "#2E9E6B"
PPT_COLOR = "#D96B3F"

TONE_COLORS = {
    "muted": TEXT_MUTED,
    "text": TEXT,
    "dim": TEXT_DIM,
    "accent": ACCENT,
    "success": SUCCESS,
    "warning": WARNING,
    "danger": DANGER,
}

FONT_STACK = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif'
MONO_STACK = '"Cascadia Mono", "Consolas", "JetBrains Mono", monospace'


# ------------------------------------------------------------------ 资源生成


def _assets_dir() -> Path:
    path = app_data_dir() / "ui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(name: str, content: str) -> str:
    target = _assets_dir() / name
    if not target.is_file() or target.read_text(encoding="utf-8") != content:
        target.write_text(content, encoding="utf-8")
    return str(target).replace("\\", "/")


def _svg(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        f'viewBox="0 0 16 16">{body}</svg>'
    )


def asset(check: str = "#FFFFFF") -> dict[str, str]:
    return {
        "check": _write(
            "check.svg",
            _svg(
                f'<path d="M3.4 8.4 L6.3 11.2 L12.6 4.8" fill="none" stroke="{check}" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
        ),
        "dash": _write(
            "dash.svg",
            _svg(
                f'<rect x="3.5" y="7.2" width="9" height="1.8" rx="0.9" fill="{check}"/>'
            ),
        ),
        "arrow_down": _write(
            "arrow_down.svg",
            _svg(
                '<path d="M4 6 L8 10 L12 6" fill="none" stroke="#8FA0B8" stroke-width="1.6" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
            ),
        ),
        "arrow_right": _write(
            "arrow_right.svg",
            _svg(
                '<path d="M6 4 L10 8 L6 12" fill="none" stroke="#8FA0B8" stroke-width="1.6" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
            ),
        ),
    }


# ------------------------------------------------------------------ 应用图标


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, size - 1, size - 1)
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0.0, QColor("#5B8DFF"))
        gradient.setColorAt(1.0, QColor("#7B5BFF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        radius = size * 0.26
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QPen(QColor("#FFFFFF")))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(int(size * 0.5))
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "文")
        painter.end()
        icon.addPixmap(pixmap)
    return icon


# ------------------------------------------------------------------ 样式表


def stylesheet() -> str:
    svg = asset()
    return f"""
* {{
    outline: 0;
}}

QWidget {{
    color: {TEXT};
    font-family: {FONT_STACK};
    font-size: 13px;
}}

QWidget#root {{
    background: {BG};
}}

QFrame#header {{
    background: {BG};
    border-bottom: 1px solid {BORDER_SOFT};
}}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}

QFrame#subcard {{
    background: {SURFACE_2};
    border: 1px solid {BORDER_SOFT};
    border-radius: 11px;
}}

QFrame#divider {{
    background: {BORDER_SOFT};
    max-height: 1px;
    border: none;
}}

QLabel {{
    background: transparent;
}}

QLabel#appTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}

QLabel#appSubtitle {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}

QLabel#sectionTitle {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_DIM};
    letter-spacing: 0.4px;
}}

QLabel#fieldLabel {{
    font-size: 12px;
    color: {TEXT_DIM};
}}

QLabel#muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QLabel#hint {{
    color: {TEXT_MUTED};
    font-size: 11.5px;
}}

QLabel#errorText {{
    color: {DANGER};
    font-size: 11.5px;
}}

QLabel#statValue {{
    font-size: 22px;
    font-weight: 600;
}}

QLabel#statLabel {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}

QLabel#emptyTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_DIM};
}}

QLabel#emptyBody {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

QLabel#fileTitle {{
    font-size: 12.5px;
    font-weight: 600;
    color: {TEXT};
}}

QLabel#filePath {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}

/* ---------------------------------------------------------------- 输入框 */

QLineEdit {{
    background: #10151C;
    border: 1px solid #2A3241;
    border-radius: 9px;
    padding: 9px 12px;
    color: {TEXT};
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #0A0F18;
}}

QLineEdit:hover {{
    border-color: #333D4E;
}}

QLineEdit:focus {{
    border-color: {ACCENT};
    background: #111823;
}}

QLineEdit[invalid="true"] {{
    border-color: {DANGER};
}}

QLineEdit:disabled {{
    color: {TEXT_MUTED};
    background: #131822;
}}

QLineEdit#search {{
    padding: 7px 11px;
}}

/* ---------------------------------------------------------------- 按钮 */

QPushButton {{
    border-radius: 9px;
    padding: 8px 14px;
    font-size: 12.5px;
    color: {TEXT_DIM};
    background: transparent;
    border: 1px solid transparent;
}}

QPushButton:hover {{
    background: {SURFACE_3};
    color: {TEXT};
}}

QPushButton:pressed {{
    background: #1A2130;
}}

QPushButton:disabled {{
    color: #4B5568;
    background: transparent;
}}

QPushButton[kind="primary"] {{
    background: {ACCENT};
    color: #08111F;
    font-weight: 600;
    padding: 10px 22px;
    border: none;
}}

QPushButton[kind="primary"]:hover {{
    background: {ACCENT_HOVER};
}}

QPushButton[kind="primary"]:pressed {{
    background: {ACCENT_PRESSED};
}}

QPushButton[kind="primary"]:disabled {{
    background: #24303F;
    color: #5A6879;
}}

QPushButton[kind="ghost"] {{
    border: 1px solid #2A3241;
    color: {TEXT_DIM};
    background: #141A23;
    padding: 8px 14px;
}}

QPushButton[kind="ghost"]:hover {{
    border-color: #3A4557;
    color: {TEXT};
    background: #18202B;
}}

QPushButton[kind="ghost"]:disabled {{
    border-color: {BORDER_SOFT};
    color: #4B5568;
    background: transparent;
}}

QPushButton[kind="danger"] {{
    background: rgba(255, 107, 107, 0.12);
    color: {DANGER};
    border: 1px solid rgba(255, 107, 107, 0.28);
}}

QPushButton[kind="danger"]:hover {{
    background: rgba(255, 107, 107, 0.18);
}}

QPushButton[kind="danger"]:disabled {{
    background: transparent;
    color: #4B5568;
    border-color: {BORDER_SOFT};
}}

QPushButton[kind="tab"] {{
    border-radius: 8px;
    padding: 7px 14px;
    color: {TEXT_MUTED};
    font-weight: 500;
}}

QPushButton[kind="tab"]:checked {{
    background: {SURFACE_3};
    color: {TEXT};
}}

QPushButton[kind="tab"]:hover {{
    color: {TEXT};
}}

QPushButton[kind="chip"] {{
    border: 1px solid #2A3241;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    color: {TEXT_MUTED};
    background: #131923;
}}

QPushButton[kind="chip"]:checked {{
    border-color: rgba(76, 141, 255, 0.55);
    background: rgba(76, 141, 255, 0.14);
    color: {INFO};
}}

QMessageBox QPushButton {{
    background: #1B222D;
    border: 1px solid #2A3241;
    border-radius: 8px;
    padding: 7px 18px;
    min-width: 76px;
    color: {TEXT_DIM};
}}

QMessageBox QPushButton:hover {{
    background: #222B38;
    color: {TEXT};
}}

QMessageBox QPushButton#primaryButton {{
    background: {ACCENT};
    color: #08111F;
    border: none;
    font-weight: 600;
}}

QMessageBox QPushButton#primaryButton:hover {{
    background: {ACCENT_HOVER};
}}

QMessageBox QPushButton#dangerButton {{
    background: rgba(255, 107, 107, 0.14);
    color: {DANGER};
    border: 1px solid rgba(255, 107, 107, 0.32);
}}

QMessageBox QPushButton#dangerButton:hover {{
    background: rgba(255, 107, 107, 0.2);
}}

QPushButton[kind="chip"]:disabled {{
    color: #414B5C;
    border-color: {BORDER_SOFT};
    background: transparent;
}}

/* ---------------------------------------------------------------- 复选 / 下拉 */

QCheckBox {{
    color: {TEXT_DIM};
    font-size: 12.5px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #333D4E;
    background: #10151C;
}}

QCheckBox::indicator:hover {{
    border-color: #445067;
}}

QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url("{svg['check']}");
}}

QCheckBox::indicator:disabled {{
    border-color: {BORDER_SOFT};
    background: transparent;
}}

QComboBox {{
    background: #10151C;
    border: 1px solid #2A3241;
    border-radius: 8px;
    padding: 6px 30px 6px 11px;
    color: {TEXT_DIM};
    font-size: 12px;
    min-width: 96px;
}}

QComboBox:hover {{
    border-color: #3A4557;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}

QComboBox::down-arrow {{
    image: url("{svg['arrow_down']}");
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {TEXT};
    selection-background-color: rgba(76, 141, 255, 0.18);
    outline: 0;
}}

/* ---------------------------------------------------------------- 列表 */

QListWidget {{
    background: transparent;
    border: none;
    padding: 0;
}}

QListWidget::item {{
    border-radius: 10px;
    margin: 2px 0;
    border: 1px solid transparent;
}}

QListWidget::item:hover {{
    background: {SURFACE_2};
}}

QListWidget::item:selected {{
    background: rgba(76, 141, 255, 0.10);
    border: 1px solid rgba(76, 141, 255, 0.28);
}}

/* ---------------------------------------------------------------- 树 / 表 */

QTreeWidget, QTableWidget {{
    background: transparent;
    border: none;
    color: {TEXT};
    font-size: 12.5px;
    selection-background-color: rgba(76, 141, 255, 0.10);
}}

QTreeWidget::item {{
    height: 32px;
    border-bottom: 1px solid {BORDER_SOFT};
}}

QTreeWidget::item:selected {{
    background: rgba(76, 141, 255, 0.08);
    color: {TEXT};
}}

QTreeView::branch {{
    background: transparent;
}}

QTreeView::branch:closed:has-children {{
    image: url("{svg['arrow_right']}");
}}

QTreeView::branch:open:has-children {{
    image: url("{svg['arrow_down']}");
}}

QHeaderView {{
    background: {SURFACE};
    border: none;
}}

QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 10px;
    font-size: 11.5px;
    font-weight: 600;
}}

QTableCornerButton::section {{
    background: {SURFACE};
    border: none;
}}

QTableWidget {{
    gridline-color: {BORDER_SOFT};
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {BORDER_SOFT};
}}

QTableWidget::item:hover {{
    background: rgba(255, 255, 255, 0.03);
}}

/* ---------------------------------------------------------------- 文本区 */

QTextEdit, QPlainTextEdit {{
    background: #10151C;
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
    color: {TEXT_DIM};
    font-family: {MONO_STACK};
    font-size: 11.5px;
    padding: 10px;
    selection-background-color: {ACCENT};
}}

/* ---------------------------------------------------------------- 进度 / 滚动条 */

QProgressBar {{
    background: #1B2230;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #2B3444;
    border-radius: 4px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3A4559;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: #2B3444;
    border-radius: 4px;
    min-width: 28px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ---------------------------------------------------------------- 其它 */

QToolTip {{
    background: #1E2531;
    color: {TEXT};
    border: 1px solid #2E3847;
    padding: 6px 9px;
    border-radius: 6px;
    font-size: 11.5px;
}}

QSplitter::handle {{
    background: transparent;
    width: 1px;
}}

QMenu {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px;
    color: {TEXT};
}}

QMenu::item {{
    padding: 7px 18px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background: rgba(76, 141, 255, 0.16);
}}

QDialog {{
    background: {BG};
}}
"""


def apply_theme(app: QApplication) -> None:
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(13)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
