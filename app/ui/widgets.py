"""通用小部件：卡片、空状态、统计卡、浮动提示。"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, padding: int = 18, spacing: int = 14) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("divider")
        self.setFixedHeight(1)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionTitle")


def _empty_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(10.5, 6.5, size - 21, size - 13)
    painter.setPen(QPen(QColor(theme.BORDER), 1.6))
    painter.setBrush(QColor(26, 32, 41))
    painter.drawRoundedRect(rect, 9, 9)
    painter.setPen(QPen(QColor(theme.TEXT_MUTED), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i, width in enumerate((16, 22, 12)):
        y = rect.top() + 15 + i * 10
        painter.drawLine(int(rect.left() + 9), int(y), int(rect.left() + 9 + width), int(y))
    painter.end()
    return pixmap


class EmptyState(QWidget):
    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addStretch(1)

        icon = QLabel()
        icon.setPixmap(_empty_pixmap())
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        self.title = QLabel(title)
        self.title.setObjectName("emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.body = QLabel(body)
        self.body.setObjectName("emptyBody")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setWordWrap(True)
        self.body.setMaximumWidth(420)
        body_row = QHBoxLayout()
        body_row.addStretch(1)
        body_row.addWidget(self.body)
        body_row.addStretch(1)
        layout.addLayout(body_row)
        layout.addStretch(1)

    def set_text(self, title: str, body: str) -> None:
        self.title.setText(title)
        self.body.setText(body)


class StatCard(QFrame):
    def __init__(self, label: str, tone: str = "text", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subcard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 12)
        layout.setSpacing(3)
        self._tone = tone
        self.value = QLabel("0")
        self.value.setObjectName("statValue")
        self.value.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.caption = QLabel(label)
        self.caption.setObjectName("statLabel")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)

    def set_value(self, value: int | str) -> None:
        self.value.setText(str(value))
        zero = str(value).strip() in ("0", "")
        color = theme.TEXT_MUTED if zero else theme.TONE_COLORS.get(self._tone, theme.TEXT)
        self.value.setStyleSheet(f"color: {color};")


class StatusPill(QFrame):
    """左上角的 office-cli 状态药丸。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subcard")
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(7)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 8px;")
        self.text = QLabel("检测 office-cli…")
        self.text.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11.5px;")
        layout.addWidget(self.dot)
        layout.addWidget(self.text)

    def set_state(self, text: str, tone: str = "muted") -> None:
        color = theme.TONE_COLORS.get(tone, theme.TEXT_MUTED)
        self.dot.setStyleSheet(f"color: {color}; font-size: 8px;")
        self.text.setText(text)
        self.text.setStyleSheet(f"color: {color}; font-size: 11.5px;")
        self.text.setToolTip(text)


class Toast(QLabel):
    """窗口底部的轻提示，1.9 秒后淡出。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: {theme.SURFACE_3}; color: {theme.TEXT};"
            f"border: 1px solid {theme.BORDER}; border-radius: 10px;"
            "padding: 9px 16px; font-size: 12px;"
        )
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, tone: str = "default", duration: int = 1900) -> None:
        color = {
            "default": theme.TEXT,
            "success": theme.SUCCESS,
            "warning": theme.WARNING,
            "danger": theme.DANGER,
        }.get(tone, theme.TEXT)
        self.setStyleSheet(
            f"background: {theme.SURFACE_3}; color: {color};"
            f"border: 1px solid {theme.BORDER}; border-radius: 10px;"
            "padding: 9px 16px; font-size: 12px;"
        )
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.animation.stop()
        self.animation.setStartValue(self.effect.opacity())
        self.animation.setEndValue(1.0)
        self.animation.start()
        self._timer.start(duration)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 132
        self.move(QPoint(max(12, x), max(12, y)))

    def _fade_out(self) -> None:
        self.animation.stop()
        self.animation.setStartValue(self.effect.opacity())
        self.animation.setEndValue(0.0)
        self.animation.start()
        QTimer.singleShot(220, self.hide)


class ElidedLabel(QLabel):
    """长文本自动省略，保留完整 tooltip。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self.setToolTip(text)
        super().setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        metrics = self.fontMetrics()
        super().setText(metrics.elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))



class ConfirmDialog(QDialog):
    """自定义确认框：深色主题下比 QMessageBox 更可控，也能列出文件清单。"""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        message: str,
        *,
        rows: list[str] | None = None,
        warning: str = "",
        action_text: str = "确定",
        action_kind: str = "primary",
        checkbox_text: str = "",
        checkbox_checked: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMaximumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("appTitle")
        layout.addWidget(heading)

        body = QLabel(message)
        body.setObjectName("muted")
        body.setWordWrap(True)
        layout.addWidget(body)

        if warning:
            warn = QLabel(warning)
            warn.setStyleSheet(f"color: {theme.WARNING}; font-size: 12px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        if rows:
            frame = QFrame()
            frame.setObjectName("subcard")
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 10, 12, 10)
            box.setSpacing(6)
            visible = rows[:7]
            for row in visible:
                label = QLabel(row)
                label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 12px;")
                box.addWidget(label)
            if len(rows) > len(visible):
                more = QLabel(f"… 另有 {len(rows) - len(visible)} 个文件")
                more.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11.5px;")
                box.addWidget(more)
            layout.addWidget(frame)

        self.checkbox: QCheckBox | None = None
        if checkbox_text:
            self.checkbox = QCheckBox(checkbox_text)
            self.checkbox.setChecked(checkbox_checked)
            layout.addWidget(self.checkbox)

        layout.addSpacing(2)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setProperty("kind", "ghost")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(action_text)
        confirm.setProperty("kind", action_kind)
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        confirm.setFocus()

    @classmethod
    def confirm(
        cls,
        parent: QWidget | None,
        title: str,
        message: str,
        **kwargs,
    ) -> tuple[bool, bool]:
        dialog = cls(parent, title, message, **kwargs)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        checked = dialog.checkbox.isChecked() if dialog.checkbox else False
        return accepted, checked
