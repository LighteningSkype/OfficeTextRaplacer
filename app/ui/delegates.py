"""自绘委托：文件行、命中片段高亮。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from . import theme

KIND_COLORS = {
    "word": theme.WORD_COLOR,
    "excel": theme.EXCEL_COLOR,
    "powerpoint": theme.PPT_COLOR,
}
KIND_LETTER = {"word": "W", "excel": "X", "powerpoint": "P"}

ROLE_ENTRY = Qt.ItemDataRole.UserRole
ROLE_SEGMENT = Qt.ItemDataRole.UserRole + 1
ROLE_TONE = Qt.ItemDataRole.UserRole + 2


class FileRowDelegate(QStyledItemDelegate):
    """左侧文件行：类型徽标 + 文件名 + 路径 + 右侧状态。"""

    ROW_HEIGHT = 58

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        entry = index.data(ROLE_ENTRY)
        if not entry:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(1, 1, -1, -1)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(QPen(QColor(76, 141, 255, 90), 1))
            painter.setBrush(QColor(76, 141, 255, 26))
            painter.drawRoundedRect(rect, 10, 10)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(26, 32, 41))
            painter.drawRoundedRect(rect, 10, 10)

        # 类型徽标
        badge = QRect(rect.left() + 10, rect.top() + (rect.height() - 32) // 2, 32, 32)
        color = QColor(KIND_COLORS.get(entry.get("kind", ""), theme.TEXT_MUTED))
        fill = QColor(color)
        fill.setAlpha(38)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(badge, 9, 9)

        letter_font = QFont(option.font)
        letter_font.setPixelSize(13)
        letter_font.setWeight(QFont.Weight.Bold)
        painter.setFont(letter_font)
        painter.setPen(color)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, KIND_LETTER.get(entry.get("kind", ""), "?"))

        # 右侧状态
        status_text = str(entry.get("status_text") or "")
        tone = QColor(theme.TONE_COLORS.get(entry.get("tone", "muted"), theme.TEXT_MUTED))
        small = QFont(option.font)
        small.setPixelSize(11)
        painter.setFont(small)
        status_width = painter.fontMetrics().horizontalAdvance(status_text) + 6
        status_rect = QRect(
            rect.right() - status_width - 12,
            rect.top(),
            status_width,
            rect.height(),
        )
        painter.setPen(tone)
        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            status_text,
        )

        # 文件名 / 路径
        text_left = badge.right() + 11
        text_width = max(20, status_rect.left() - text_left - 8)
        name_font = QFont(option.font)
        name_font.setPixelSize(12)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(theme.TEXT if not selected else "#FFFFFF"))
        name = painter.fontMetrics().elidedText(
            str(entry.get("name") or ""), Qt.TextElideMode.ElideMiddle, text_width
        )
        painter.drawText(
            QRect(text_left, rect.top() + 9, text_width, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

        path_font = QFont(option.font)
        path_font.setPixelSize(10)
        painter.setFont(path_font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        path = painter.fontMetrics().elidedText(
            str(entry.get("folder") or ""), Qt.TextElideMode.ElideMiddle, text_width
        )
        painter.drawText(
            QRect(text_left, rect.top() + 29, text_width, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            path,
        )
        painter.restore()


class SnippetDelegate(QStyledItemDelegate):
    """命中片段：命中词带底色高亮，超宽时从两侧收缩。"""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        segment = index.data(ROLE_SEGMENT)
        if not segment:
            super().paint(painter, option, index)
            return

        before, matched, after = segment
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(76, 141, 255, 22))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(255, 255, 255, 6))

        rect = option.rect.adjusted(10, 0, -10, 0)
        metrics = QFontMetrics(option.font)
        base_y = rect.center().y() + (metrics.ascent() - metrics.descent()) // 2

        chip_pad = 4
        matched_width = metrics.horizontalAdvance(matched) + chip_pad * 2
        available = max(10, rect.width() - matched_width)

        before_text = before
        before_width = metrics.horizontalAdvance(before_text)
        if before_width > available * 0.45:
            keep = max(0, int(available * 0.45))
            before_text = "…" + metrics.elidedText(before_text, Qt.TextElideMode.ElideLeft, keep)
            before_width = metrics.horizontalAdvance(before_text)

        after_avail = max(0, available - before_width)
        after_text = metrics.elidedText(after, Qt.TextElideMode.ElideRight, after_avail)

        x = rect.left()
        painter.setFont(option.font)
        painter.setPen(QColor(theme.TEXT_DIM))
        if before_text:
            painter.drawText(x, base_y, before_text)
            x += before_width

        chip = QRect(x, rect.center().y() - 10, matched_width, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(76, 141, 255, 46))
        painter.drawRoundedRect(chip, 4, 4)
        painter.setPen(QColor("#CFE0FF"))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, matched)
        x += matched_width

        painter.setPen(QColor(theme.TEXT_MUTED))
        if after_text:
            painter.drawText(x, base_y, after_text)
        painter.restore()
