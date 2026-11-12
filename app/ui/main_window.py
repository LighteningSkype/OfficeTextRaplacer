"""主窗口：文件选择 → 规则配置 → 预览 → 执行 → 结果反馈。"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import engine
from ..core.cli import CliInfo, OfficeCli, discover
from ..core.config import APP_SUBTITLE, APP_TITLE, Settings
from ..core.engine import FileResult, FileScan, Scope, STATUS_LABEL, latest_run, prune_runs, restore_run
from ..core.extract import KIND_LABEL, SUPPORTED_EXT, detect_kind
from ..core.rules import CompiledRule, ReplaceRule, RuleError
from ..server import reveal
from . import theme
from .delegates import FileRowDelegate, ROLE_ENTRY, ROLE_SEGMENT, SnippetDelegate
from .widgets import (
    Card,
    ConfirmDialog,
    Divider,
    ElidedLabel,
    EmptyState,
    SectionTitle,
    StatCard,
    StatusPill,
    Toast,
)

ROLE_PATH = Qt.ItemDataRole.UserRole + 10
ROLE_BACKUP = Qt.ItemDataRole.UserRole + 11


# --------------------------------------------------------------------------- 数据


@dataclass
class FileEntry:
    path: str
    kind: str
    status: str = "pending"
    scan: FileScan | None = None
    result: FileResult | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def folder(self) -> str:
        return str(Path(self.path).parent)


STATUS_STYLE = {
    "pending": ("待预览", "muted"),
    "scanning": ("预览中…", "accent"),
    "ready": ("_hits", "accent"),
    "no_match": ("无匹配", "muted"),
    "error": ("失败", "danger"),
    "replacing": ("替换中…", "warning"),
    "success": ("_ok", "success"),
    "skipped": ("已跳过", "warning"),
    "cancelled": ("已取消", "muted"),
}


# --------------------------------------------------------------------------- 线程


class CliProbe(QThread):
    done = Signal(object)

    def __init__(self, configured: str) -> None:
        super().__init__()
        self.configured = configured

    def run(self) -> None:
        info = discover(self.configured or None)
        self.done.emit(info)


class ScanWorker(QThread):
    progressed = Signal(int, int, str)
    scanned = Signal(object)
    done = Signal()

    def __init__(self, cli: OfficeCli, paths: list[str], rule: CompiledRule, scope: Scope) -> None:
        super().__init__()
        self.cli = cli
        self.paths = paths
        self.rule = rule
        self.scope = scope
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        total = len(self.paths)
        for index, path in enumerate(self.paths):
            if self._cancel:
                for rest in self.paths[index:]:
                    scan = engine.FileScan(
                        path=rest,
                        kind=detect_kind(rest) or "",
                        error="已取消，未处理",
                        error_code="cancelled",
                    )
                    self.scanned.emit(scan)
                break
            scan = engine.scan_file(self.cli, path, self.rule, self.scope)
            self.scanned.emit(scan)
            self.progressed.emit(index + 1, total, Path(path).name)
        self.done.emit()


class ApplyWorker(QThread):
    progressed = Signal(int, int, str)
    applied = Signal(object)
    done = Signal(dict)

    def __init__(
        self,
        cli: OfficeCli,
        scans: list[FileScan],
        rule: CompiledRule,
        scope: Scope,
        settings: Settings,
    ) -> None:
        super().__init__()
        self.cli = cli
        self.scans = scans
        self.rule = rule
        self.scope = scope
        self.settings = settings
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        run_dir = None
        if self.settings.keep_backup:
            try:
                run_dir = engine.make_run_dir(self.settings.backup_root)
            except OSError:
                run_dir = None
        total = len(self.scans)
        summary = {
            "run_dir": str(run_dir) if run_dir else "",
            "total": total,
            "success": 0,
            "no_match": 0,
            "skipped": 0,
            "error": 0,
            "cancelled": 0,
            "hits": 0,
            "seconds": 0.0,
        }
        started = time.perf_counter()
        for index, scan in enumerate(self.scans):
            if self._cancel:
                for rest in self.scans[index:]:
                    self.applied.emit(
                        FileResult(
                            path=rest.path,
                            kind=rest.kind,
                            status="cancelled",
                            message="已取消，未处理（原文件未改动）",
                        )
                    )
                break
            result = engine.apply_file(
                self.cli,
                scan,
                self.rule,
                self.scope,
                run_dir=run_dir,
                keep_backup=self.settings.keep_backup and run_dir is not None,
                verify_after=self.settings.verify_after,
                cancel_check=lambda: self._cancel,
            )
            summary[result.status] = summary.get(result.status, 0) + 1
            summary["hits"] += result.hits
            self.applied.emit(result)
            self.progressed.emit(index + 1, total, Path(scan.path).name)
        summary["seconds"] = time.perf_counter() - started
        if run_dir is not None:
            prune_runs(self.settings.backup_root)
        self.done.emit(summary)


# --------------------------------------------------------------------------- 对话框


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, info: CliInfo | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("设置")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        hint = QLabel(
            "office-cli 是替换引擎，本工具通过它读写 Word / Excel / PowerPoint 文件。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(Divider())

        row = QHBoxLayout()
        row.setSpacing(8)
        self.cli_edit = QLineEdit(settings.cli_path)
        self.cli_edit.setPlaceholderText("留空则自动搜索 PATH / npm 全局目录")
        browse = QPushButton("浏览…")
        browse.setProperty("kind", "ghost")
        browse.clicked.connect(self._browse_cli)
        row.addWidget(self.cli_edit, 1)
        row.addWidget(browse)
        layout.addWidget(self._field("office-cli 可执行文件", row))

        status_text = (
            f"当前检测：{info.version} · {info.origin} · {info.path}"
            if info
            else "当前未检测到 office-cli，可留空让程序自动搜索，或手动指定可执行文件。"
        )
        status = ElidedLabel(status_text)
        status.setObjectName("hint")
        layout.addWidget(status)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.backup_edit = QLineEdit(settings.backup_root)
        browse2 = QPushButton("浏览…")
        browse2.setProperty("kind", "ghost")
        browse2.clicked.connect(self._browse_backup)
        row2.addWidget(self.backup_edit, 1)
        row2.addWidget(browse2)
        layout.addWidget(self._field("备份目录", row2))

        self.keep_backup = QCheckBox("替换前自动备份原文件（可在「撤销」中还原）")
        self.keep_backup.setChecked(settings.keep_backup)
        self.verify = QCheckBox("替换后校验文件结构，校验失败则放弃写入")
        self.verify.setChecked(settings.verify_after)
        self.recursive = QCheckBox("添加文件夹时包含子文件夹")
        self.recursive.setChecked(settings.recursive_scan)
        layout.addWidget(self.keep_backup)
        layout.addWidget(self.verify)
        layout.addWidget(self.recursive)

        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setProperty("kind", "ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setProperty("kind", "primary")
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    @staticmethod
    def _field(label: str, widget_layout: QHBoxLayout) -> QWidget:
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        box.addWidget(caption)
        box.addLayout(widget_layout)
        return holder

    def _browse_cli(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 office-cli 可执行文件", "", "可执行文件 (*.exe);;所有文件 (*)")
        if path:
            self.cli_edit.setText(path)

    def _browse_backup(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择备份目录", self.backup_edit.text())
        if path:
            self.backup_edit.setText(path)

    def result_settings(self) -> Settings:
        self.settings.cli_path = self.cli_edit.text().strip()
        self.settings.backup_root = self.backup_edit.text().strip() or self.settings.backup_root
        self.settings.keep_backup = self.keep_backup.isChecked()
        self.settings.verify_after = self.verify.isChecked()
        self.settings.recursive_scan = self.recursive.isChecked()
        return self.settings


# --------------------------------------------------------------------------- 主窗口


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("root")
        self.setAcceptDrops(True)
        self.setWindowTitle(f"{APP_TITLE} · {APP_SUBTITLE}")
        self.resize(1240, 820)
        self.setMinimumSize(1080, 700)

        self.settings = Settings.load()
        self.entries: list[FileEntry] = []
        self.scans: dict[str, FileScan] = {}
        self.cli: OfficeCli | None = None
        self.cli_info: CliInfo | None = None
        self._worker: QThread | None = None
        self._preview_signature: tuple | None = None
        self._busy = False
        self._last_run_dir = ""
        self._log_lines = 0
        self._stat_hits = 0

        self._build_ui()
        self._wire_shortcuts()
        self._set_actions_enabled(False)
        self._validate_rule_now()
        self._refresh_counts()
        self._start_probe()

    # ------------------------------------------------------------------ 构建

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_status_strip())

        self.toast = Toast(self)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(66)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 18, 0)
        layout.setSpacing(12)

        mark = QLabel()
        mark.setPixmap(theme.app_icon().pixmap(34, 34))
        mark.setFixedSize(34, 34)
        layout.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        subtitle = QLabel(APP_SUBTITLE)
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.cli_pill = StatusPill()
        layout.addWidget(self.cli_pill)

        self.btn_backup_dir = QPushButton("备份目录")
        self.btn_backup_dir.setProperty("kind", "ghost")
        self.btn_backup_dir.setToolTip("打开备份文件夹")
        self.btn_backup_dir.clicked.connect(self._open_backup_dir)
        layout.addWidget(self.btn_backup_dir)

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setProperty("kind", "ghost")
        self.btn_settings.clicked.connect(self._open_settings)
        layout.addWidget(self.btn_settings)

        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 10)
        layout.setSpacing(16)
        layout.addWidget(self._build_file_panel())
        layout.addLayout(self._build_right_panel(), 1)
        return body

    def _build_file_panel(self) -> QWidget:
        card = Card(padding=16, spacing=10)
        card.setFixedWidth(338)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(SectionTitle("文件"))
        self.file_count = QLabel("0")
        self.file_count.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; background: {theme.SURFACE_2};"
            f"border: 1px solid {theme.BORDER}; border-radius: 8px;"
            "padding: 1px 7px; font-size: 10.5px;"
        )
        head.addWidget(self.file_count)
        head.addStretch(1)
        card.body.addLayout(head)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.btn_add_files = QPushButton("+ 添加文件")
        self.btn_add_files.setProperty("kind", "ghost")
        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder = QPushButton("+ 文件夹")
        self.btn_add_folder.setProperty("kind", "ghost")
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setProperty("kind", "ghost")
        self.btn_clear.clicked.connect(self._clear_files)
        for button in (self.btn_add_files, self.btn_add_folder, self.btn_clear):
            buttons.addWidget(button)
        card.body.addLayout(buttons)

        self.file_list = DropListWidget()
        self.file_list.setItemDelegate(FileRowDelegate(self.file_list))
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_list.setMouseTracking(True)
        self.file_list.setUniformItemSizes(True)
        self.file_list.setSpacing(2)
        self.file_list.itemDoubleClicked.connect(self._open_file)
        self.file_list.filesDropped.connect(self._add_paths)

        self.file_stack = QStackedWidget()
        self.list_empty = EmptyState(
            "把文件拖到这里",
            "支持 .docx / .xlsx / .pptx\n也可以拖入文件夹批量添加",
        )
        self.file_stack.addWidget(self.list_empty)
        self.file_stack.addWidget(self.file_list)
        card.body.addWidget(self.file_stack, 1)

        hint = QLabel("把文件或文件夹拖进来 · 仅支持 .docx / .xlsx / .pptx")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        card.body.addWidget(hint)

        return card

    def _build_right_panel(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(14)
        column.addWidget(self._build_rule_card())
        column.addWidget(self._build_content_card(), 1)
        column.addLayout(self._build_action_bar())
        return column

    def _build_rule_card(self) -> QWidget:
        card = Card(padding=18, spacing=12)
        head = QHBoxLayout()
        head.addWidget(SectionTitle("替换规则"))
        head.addStretch(1)
        self.btn_preview = QPushButton("预览匹配")
        self.btn_preview.setProperty("kind", "ghost")
        self.btn_preview.setToolTip("Ctrl+Enter")
        self.btn_preview.clicked.connect(self._start_preview)
        head.addWidget(self.btn_preview)
        card.body.addLayout(head)

        fields = QHBoxLayout()
        fields.setSpacing(12)

        find_box = QVBoxLayout()
        find_box.setSpacing(6)
        find_label = QLabel("查找内容")
        find_label.setObjectName("fieldLabel")
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("要查找的文字，例如：Draft 或 保密")
        self.find_edit.textChanged.connect(self._on_find_changed)
        find_box.addWidget(find_label)
        find_box.addWidget(self.find_edit)

        replace_box = QVBoxLayout()
        replace_box.setSpacing(6)
        replace_label = QLabel("替换为")
        replace_label.setObjectName("fieldLabel")
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("留空表示删除匹配内容")
        self.replace_edit.textChanged.connect(self._mark_stale)
        replace_box.addWidget(replace_label)
        replace_box.addWidget(self.replace_edit)

        fields.addLayout(find_box, 1)
        fields.addLayout(replace_box, 1)
        card.body.addLayout(fields)

        options = QHBoxLayout()
        options.setSpacing(10)
        self.mode_plain = QPushButton("普通文本")
        self.mode_regex = QPushButton("正则表达式")
        for button in (self.mode_plain, self.mode_regex):
            button.setCheckable(True)
            button.setProperty("kind", "chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.mode_plain)
        self.mode_group.addButton(self.mode_regex)
        self.mode_plain.setChecked(True)
        self.mode_plain.clicked.connect(self._on_mode_changed)
        self.mode_regex.clicked.connect(self._on_mode_changed)
        options.addWidget(self.mode_plain)
        options.addWidget(self.mode_regex)

        options.addSpacing(6)
        self.check_case = QCheckBox("区分大小写")
        self.check_case.setChecked(True)
        self.check_case.clicked.connect(self._mark_stale)
        self.check_word = QCheckBox("全词匹配")
        self.check_word.setToolTip("只匹配完整单词；对中文按“不与英文/数字相邻”处理")
        self.check_word.clicked.connect(self._mark_stale)
        options.addWidget(self.check_case)
        options.addWidget(self.check_word)
        options.addStretch(1)
        card.body.addLayout(options)

        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)
        scope_label = QLabel("范围")
        scope_label.setObjectName("fieldLabel")
        scope_row.addWidget(scope_label)
        self.scope_body = QPushButton("正文")
        self.scope_table = QPushButton("表格")
        self.scope_header = QPushButton("页眉页脚")
        self.scope_notes = QPushButton("备注")
        self.scope_body.setToolTip("Word 正文 / PowerPoint 幻灯片文本 / Excel 单元格文本")
        self.scope_table.setToolTip("Word 表格与 PowerPoint 表格中的文字")
        self.scope_header.setToolTip("仅 Word：页眉与页脚")
        self.scope_notes.setToolTip("仅 PowerPoint：演讲者备注（默认不替换）")
        for button, checked in (
            (self.scope_body, True),
            (self.scope_table, True),
            (self.scope_header, True),
            (self.scope_notes, False),
        ):
            button.setCheckable(True)
            button.setChecked(checked)
            button.setProperty("kind", "chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(self._mark_stale)
            scope_row.addWidget(button)
        scope_row.addStretch(1)
        self.scope_hint = QLabel("Excel 自动跳过公式与日期单元格")
        self.scope_hint.setObjectName("hint")
        scope_row.addWidget(self.scope_hint)
        card.body.addLayout(scope_row)

        self.rule_message = QLabel("")
        self.rule_message.setObjectName("hint")
        self.rule_message.setWordWrap(True)
        card.body.addWidget(self.rule_message)
        return card

    def _build_content_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(50)
        head = QHBoxLayout(header)
        head.setContentsMargins(16, 0, 16, 0)
        head.setSpacing(6)
        self.tab_preview = QPushButton("预览")
        self.tab_results = QPushButton("结果")
        self.tab_log = QPushButton("日志")
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        for index, button in enumerate((self.tab_preview, self.tab_results, self.tab_log)):
            button.setCheckable(True)
            button.setProperty("kind", "tab")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._switch_tab(i))
            self.tab_group.addButton(button, index)
            head.addWidget(button)
        self.tab_preview.setChecked(True)
        head.addStretch(1)
        self.content_status = QLabel("")
        self.content_status.setObjectName("hint")
        head.addWidget(self.content_status)
        outer.addWidget(header)
        outer.addWidget(Divider())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_preview_page())
        self.stack.addWidget(self._build_results_page())
        self.stack.addWidget(self._build_log_page())
        outer.addWidget(self.stack, 1)
        return card

    def _build_preview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.preview_stack = QStackedWidget()
        self.preview_empty = EmptyState(
            "还没有预览结果",
            "配置规则后点击「预览匹配」，这里会按文件列出每一处命中的上下文。",
        )
        self.preview_stack.addWidget(self.preview_empty)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setColumnCount(3)
        self.preview_tree.setHeaderLabels(["位置", "匹配上下文", "替换为"])
        self.preview_tree.setRootIsDecorated(True)
        self.preview_tree.setUniformRowHeights(True)
        self.preview_tree.setAlternatingRowColors(False)
        self.preview_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview_tree.setItemDelegateForColumn(1, SnippetDelegate(self.preview_tree))
        self.preview_tree.setIndentation(14)
        header = self.preview_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.preview_tree.setColumnWidth(0, 200)
        self.preview_tree.setColumnWidth(2, 220)
        self.preview_stack.addWidget(self.preview_tree)

        layout.setContentsMargins(0, 0, 0, 10)
        layout.addWidget(self.preview_stack)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.stat_files = StatCard("处理文件", "text")
        self.stat_hits = StatCard("命中数量", "accent")
        self.stat_skipped = StatCard("未替换", "warning")
        self.stat_failed = StatCard("失败", "danger")
        for stat in (self.stat_files, self.stat_hits, self.stat_skipped, self.stat_failed):
            stats.addWidget(stat)
        layout.addLayout(stats)

        self.result_stack = QStackedWidget()
        self.result_empty = EmptyState(
            "还没有执行替换",
            "预览确认无误后点击「开始替换」。原文件会先备份，再以原子替换方式写回，任何一步失败都不会改动原文件。",
        )
        self.result_stack.addWidget(self.result_empty)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(["状态", "文件", "命中", "跳过项", "说明"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setShowGrid(False)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setAlternatingRowColors(False)
        self.result_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_table.customContextMenuRequested.connect(self._show_result_menu)
        header = self.result_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.result_table.setColumnWidth(0, 86)
        self.result_table.setColumnWidth(2, 64)
        self.result_table.setColumnWidth(3, 74)
        self.result_table.verticalHeader().setDefaultSectionSize(38)
        self.result_stack.addWidget(self.result_table)

        layout.addWidget(self.result_stack, 1)
        return page

    def _build_log_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_view)
        return page

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.action_hint = QLabel("先添加文件，再填写查找内容")
        self.action_hint.setObjectName("muted")
        bar.addWidget(self.action_hint)
        bar.addStretch(1)

        self.btn_undo = QPushButton("撤销本次")
        self.btn_undo.setProperty("kind", "ghost")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self._undo_last)
        bar.addWidget(self.btn_undo)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setProperty("kind", "danger")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        bar.addWidget(self.btn_stop)

        self.btn_apply = QPushButton("开始替换")
        self.btn_apply.setProperty("kind", "primary")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._start_apply)
        bar.addWidget(self.btn_apply)
        return bar

    def _build_status_strip(self) -> QWidget:
        strip = QFrame()
        strip.setFixedHeight(34)
        strip.setStyleSheet(f"background: {theme.BG}; border-top: 1px solid {theme.BORDER_SOFT};")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)
        self.status_text = QLabel("就绪")
        self.status_text.setObjectName("hint")
        layout.addWidget(self.status_text)
        layout.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(150)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("hint")
        self.progress_label.setMinimumWidth(56)
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.progress_label)
        return strip

    # ------------------------------------------------------------------ 交互

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, self._pick_files)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._start_preview)
        QShortcut(QKeySequence("Ctrl+Shift+Return"), self, self._start_apply)
        QShortcut(QKeySequence("F5"), self, self._start_preview)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.file_list, self._remove_selected)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._add_paths(paths)
            event.acceptProposedAction()

    # -- 文件管理 -----------------------------------------------------------

    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 Office 文件",
            self.settings.last_dir,
            "Office 文档 (*.docx *.xlsx *.pptx);;Word 文档 (*.docx);;Excel 工作簿 (*.xlsx);;PowerPoint (*.pptx)",
        )
        if paths:
            self.settings.last_dir = str(Path(paths[0]).parent)
            self.settings.save()
            self._add_paths(paths)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", self.settings.last_dir)
        if not folder:
            return
        self.settings.last_dir = folder
        self.settings.save()
        self._add_paths([folder])

    def _add_paths(self, paths: list[str]) -> None:
        if self._busy:
            self._toast("正在处理中，请稍候", "warning")
            return
        collected: list[str] = []
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                pattern = "**/*" if self.settings.recursive_scan else "*"
                for child in sorted(path.glob(pattern)):
                    if not child.is_file() or child.suffix.lower() not in SUPPORTED_EXT:
                        continue
                    if ".otr-" in child.name:  # 上次异常退出遗留的临时副本
                        continue
                    collected.append(str(child))
            elif path.is_file():
                collected.append(str(path))

        existing = {os.path.normcase(os.path.abspath(entry.path)) for entry in self.entries}
        added = 0
        ignored = 0
        for path in collected:
            suffix = Path(path).suffix.lower()
            if suffix not in SUPPORTED_EXT:
                ignored += 1
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in existing:
                continue
            if len(self.entries) >= self.settings.max_files:
                self._toast(f"最多支持 {self.settings.max_files} 个文件", "warning")
                break
            kind = detect_kind(path) or ""
            entry = FileEntry(path=os.path.abspath(path), kind=kind)
            self.entries.append(entry)
            existing.add(key)
            self._append_item(entry)
            added += 1

        self._refresh_counts()
        if added:
            self._log(f"添加 {added} 个文件", "info")
            self._mark_stale()
            self.toast.show_message(f"已添加 {added} 个文件", "success")
        elif ignored:
            self._toast("仅支持 .docx / .xlsx / .pptx，已忽略其他文件", "warning")
        elif collected:
            self._toast("文件已在列表中", "default")

    def _append_item(self, entry: FileEntry) -> None:
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, FileRowDelegate.ROW_HEIGHT))
        item.setData(ROLE_ENTRY, self._entry_payload(entry))
        item.setData(ROLE_PATH, entry.path)
        item.setToolTip(f"{entry.path}\n{entry.kind and KIND_LABEL.get(entry.kind, '')}")
        self.file_list.addItem(item)
        entry._item = item  # type: ignore[attr-defined]

    @staticmethod
    def _entry_payload(entry: FileEntry) -> dict:
        text, tone = STATUS_STYLE.get(entry.status, ("待预览", "muted"))
        if text == "_hits":
            count = entry.scan.hit_count if entry.scan else 0
            text = f"{count} 处" if count else "无匹配"
            tone = "accent" if count else "muted"
        elif text == "_ok":
            count = entry.result.hits if entry.result else 0
            text = f"{count} 处"
            tone = "success"
        return {
            "name": entry.name,
            "folder": entry.folder,
            "kind": entry.kind,
            "status_text": text,
            "tone": tone,
        }

    def _refresh_entry(self, entry: FileEntry) -> None:
        item = getattr(entry, "_item", None)
        if item is not None:
            item.setData(ROLE_ENTRY, self._entry_payload(entry))
            self.file_list.viewport().update()

    def _refresh_counts(self) -> None:
        self.file_count.setText(str(len(self.entries)))
        if hasattr(self, "file_stack"):
            self.file_stack.setCurrentIndex(1 if self.entries else 0)
        if not self.entries:
            self.action_hint.setText("先添加文件，再填写查找内容")
        elif not self.find_edit.text().strip():
            self.action_hint.setText("请输入要查找的内容")
        elif self._preview_signature is None:
            self.action_hint.setText("规则已就绪 · 点击「预览匹配」查看命中")
        else:
            total = sum(scan.hit_count for scan in self.scans.values())
            self.action_hint.setText(f"预览完成 · 共 {total} 处命中")

    def _remove_selected(self) -> None:
        if self._busy:
            return
        rows = sorted({self.file_list.row(item) for item in self.file_list.selectedItems()})
        if not rows:
            return
        for row in reversed(rows):
            item = self.file_list.takeItem(row)
            entry = self.entries.pop(row)
            self.scans.pop(entry.path, None)
            del item
        self._refresh_counts()
        self._mark_stale()

    def _clear_files(self) -> None:
        if self._busy or not self.entries:
            return
        self.file_list.clear()
        self.entries.clear()
        self.scans.clear()
        self._refresh_counts()
        self._mark_stale()
        self._log("已清空文件列表", "muted")

    def _open_file(self, item: QListWidgetItem) -> None:
        path = item.data(ROLE_PATH)
        if not path or not Path(path).exists():
            self._toast("文件不存在", "danger")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            self._toast(f"无法打开文件：{exc}", "danger")

    # -- 规则 ---------------------------------------------------------------

    def _on_mode_changed(self) -> None:
        is_regex = self.mode_regex.isChecked()
        self.find_edit.setPlaceholderText(
            r"正则表达式，例如：Draft\s*\d+ 或 (?i)error" if is_regex else "要查找的文字，例如：Draft 或 保密"
        )
        self._validate_rule()
        self._mark_stale()

    def _on_find_changed(self) -> None:
        self._validate_rule(debounce=True)

    def _validate_rule(self, debounce: bool = False) -> None:
        if debounce:
            QTimer.singleShot(220, self._validate_rule_now)
        else:
            self._validate_rule_now()

    def _validate_rule_now(self) -> None:
        find = self.find_edit.text()
        if not find:
            self.find_edit.setProperty("invalid", "false")
            self._restyle(self.find_edit)
            self.rule_message.setObjectName("hint")
            self.rule_message.setText(
                "正则模式支持 (?i) 忽略大小写、分组 $1 反向引用；匹配不跨段落。"
                if self.mode_regex.isChecked()
                else "普通文本模式按字面匹配，中文、英文与数字均安全。"
            )
            self._restyle(self.rule_message)
            self._update_action_state()
            return
        try:
            self._compile_rule()
        except RuleError as exc:
            self.find_edit.setProperty("invalid", "true")
            self._restyle(self.find_edit)
            self.rule_message.setObjectName("errorText")
            self.rule_message.setText(str(exc))
            self._restyle(self.rule_message)
        else:
            self.find_edit.setProperty("invalid", "false")
            self._restyle(self.find_edit)
            self.rule_message.setObjectName("hint")
            self.rule_message.setText(
                "匹配不跨段落；$1 / ${name} 为分组引用，$$ 表示字面 $。"
                if self.mode_regex.isChecked()
                else "普通文本模式按字面匹配，中文、英文与数字均安全。"
            )
            self._restyle(self.rule_message)
        self._update_action_state()

    @staticmethod
    def _restyle(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def current_rule(self) -> ReplaceRule:
        return ReplaceRule(
            find=self.find_edit.text(),
            replace=self.replace_edit.text(),
            regex=self.mode_regex.isChecked(),
            case_sensitive=self.check_case.isChecked(),
            whole_word=self.check_word.isChecked(),
        )

    def current_scope(self) -> Scope:
        return Scope(
            body=self.scope_body.isChecked(),
            table=self.scope_table.isChecked(),
            header_footer=self.scope_header.isChecked(),
            notes=self.scope_notes.isChecked(),
        )

    def _compile_rule(self) -> CompiledRule:
        return self.current_rule().compile()

    def _signature(self) -> tuple:
        rule = self.current_rule()
        scope = self.current_scope()
        return (
            rule.find,
            rule.replace,
            rule.regex,
            rule.case_sensitive,
            rule.whole_word,
            scope.body,
            scope.table,
            scope.header_footer,
            scope.notes,
            tuple(sorted(os.path.normcase(entry.path) for entry in self.entries)),
        )

    def _mark_stale(self) -> None:
        if self._busy:
            return
        self._preview_signature = None
        self.content_status.setText("规则已修改 · 需重新预览")
        self.content_status.setStyleSheet(f"color: {theme.WARNING}; font-size: 11.5px;")
        self._update_action_state()

    # -- 预览 ---------------------------------------------------------------

    def _start_preview(self) -> None:
        if self._busy:
            return
        if not self._ensure_ready():
            return
        try:
            rule = self._compile_rule()
        except RuleError as exc:
            self._toast(str(exc), "danger")
            self.find_edit.setFocus()
            return
        paths = [entry.path for entry in self.entries]
        if not paths:
            self._toast("请先添加要处理的文件", "warning")
            return

        self._set_busy(True, "正在预览匹配…")
        for entry in self.entries:
            entry.status = "scanning"
            entry.scan = None
            entry.result = None
            self._refresh_entry(entry)
        self.scans.clear()
        self.preview_tree.clear()
        self._switch_tab(0)

        scope = self.current_scope()
        self._pending_signature = self._signature()
        worker = ScanWorker(self.cli, paths, rule, scope)  # type: ignore[arg-type]
        worker.scanned.connect(self._on_scanned)
        worker.progressed.connect(self._on_progress)
        worker.done.connect(self._on_scan_done)
        self._worker = worker
        worker.start()
        self._log(f"开始预览：{len(paths)} 个文件", "info")

    def _on_scanned(self, scan: FileScan) -> None:
        self.scans[scan.path] = scan
        entry = self._find_entry(scan.path)
        if entry is None:
            return
        entry.scan = scan
        if scan.error_code == "cancelled":
            entry.status = "cancelled"
            self._log(f"· {entry.name}：已取消", "muted")
            self._refresh_entry(entry)
            return
        if scan.error:
            entry.status = "error"
            self._log(f"✗ {entry.name}：{scan.error}", "danger")
        elif scan.matched:
            entry.status = "ready"
            self._log(
                f"· {entry.name}：{scan.hit_count} 处命中 / {scan.element_count} 个位置",
                "text",
            )
        else:
            entry.status = "no_match"
            self._log(f"· {entry.name}：无匹配", "muted")
        self._refresh_entry(entry)
        self._append_preview(entry, scan)

    def _append_preview(self, entry: FileEntry, scan: FileScan) -> None:
        if scan.error:
            return
        if not scan.matched:
            return
        parent = QTreeWidgetItem(self.preview_tree)
        summary = f"{scan.hit_count} 处命中 · {scan.element_count} 个位置"
        if scan.excluded_hits:
            summary += f" · {scan.excluded_hits} 处自动跳过"
        parent.setText(0, entry.name)
        parent.setText(1, summary)
        parent.setText(2, "")
        if scan.excluded:
            tips = "\n".join(
                f"{location}：{reason}（{count} 处）" for location, reason, count in scan.excluded
            )
            parent.setToolTip(1, "以下内容不参与替换：\n" + tips)
        parent.setFirstColumnSpanned(False)
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        parent.setFont(0, font)
        parent.setForeground(0, QBrush(QColor(theme.TEXT)))
        parent.setForeground(1, QBrush(QColor(theme.TEXT_MUTED)))
        parent.setData(0, ROLE_PATH, entry.path)

        limit = 150
        for hit in scan.hits[:limit]:
            child = QTreeWidgetItem(parent)
            child.setText(0, hit.location)
            child.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
            child.setData(1, ROLE_SEGMENT, (hit.before, hit.matched, hit.after))
            child.setText(2, hit.replacement if hit.replacement else "（删除）")
            child.setForeground(2, QBrush(QColor(theme.INFO if hit.replacement else theme.WARNING)))
        if len(scan.hits) > limit:
            more = QTreeWidgetItem(parent)
            more.setText(0, f"… 另有 {scan.hit_count - limit} 处命中未展开")
            more.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
        parent.setExpanded(True)

    def _on_scan_done(self) -> None:
        total_hits = sum(scan.hit_count for scan in self.scans.values())
        failed = [
            scan
            for scan in self.scans.values()
            if scan.error and scan.error_code != "cancelled"
        ]
        cancelled = bool(getattr(self._worker, "_cancel", False))
        self._worker = None
        self._set_busy(False)
        if cancelled:
            self._preview_signature = None
            self.content_status.setText("预览已取消")
            self.content_status.setStyleSheet(f"color: {theme.WARNING}; font-size: 11.5px;")
            self._log("预览已取消", "warning")
            self._toast("预览已取消", "warning")
            self._refresh_counts()
            self._update_action_state()
            return
        self._preview_signature = getattr(self, "_pending_signature", None)
        if total_hits:
            self.preview_stack.setCurrentWidget(self.preview_tree)
            self.content_status.setText(f"命中 {total_hits} 处")
            self.content_status.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11.5px;")
            self._toast(f"预览完成：{total_hits} 处命中", "success")
        else:
            self.preview_empty.set_text(
                "未找到匹配项",
                "请检查查找内容、大小写与全词匹配设置，或确认替换范围是否把目标区域排除在外。",
            )
            self.preview_stack.setCurrentWidget(self.preview_empty)
            self.content_status.setText("无匹配")
            self.content_status.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11.5px;")
            self._toast("未找到匹配项", "warning")
        if failed:
            self._toast(f"{len(failed)} 个文件无法读取，详见日志", "danger")
        self.status_text.setText("就绪")
        self.progress_label.setText("")
        self._log(
            f"预览结束：命中 {total_hits} 处，失败 {len(failed)} 个文件",
            "danger" if failed else "success",
        )
        self._refresh_counts()
        self._update_action_state()

    # -- 执行 ---------------------------------------------------------------

    def _start_apply(self) -> None:
        if self._busy:
            return
        if not self._ensure_ready():
            return
        if self._preview_signature != self._signature():
            self._toast("请先预览当前规则", "warning")
            return
        scans = [self.scans[entry.path] for entry in self.entries if entry.path in self.scans and self.scans[entry.path].matched]
        if not scans:
            self._toast("没有可替换的命中项", "warning")
            return

        total_hits = sum(scan.hit_count for scan in scans)
        rows = [f"{Path(scan.path).name} · 命中 {scan.hit_count} 处" for scan in scans]
        warning = (
            ""
            if self.settings.keep_backup
            else "当前未开启备份，替换后无法撤销。建议先到「设置」中开启备份。"
        )
        ok, _ = ConfirmDialog.confirm(
            self,
            "开始替换",
            f"即将修改 {len(scans)} 个文件，共 {total_hits} 处命中。\n"
            "替换在临时副本上完成并校验通过后，才会写回原文件；任何一步失败都不会改动原文件。",
            rows=rows,
            warning=warning,
            action_text="开始替换",
        )
        if not ok:
            return

        try:
            rule = self._compile_rule()
        except RuleError as exc:
            self._toast(str(exc), "danger")
            return

        self._begin_apply(scans, rule)

    def _begin_apply(self, scans: list[FileScan], rule: CompiledRule) -> None:
        self._set_busy(True, "正在替换…")
        self._switch_tab(1)
        self.result_table.setRowCount(0)
        self.result_stack.setCurrentWidget(self.result_empty)
        self._reset_stats()
        self._last_run_dir = ""
        queued = {scan.path for scan in scans}
        for entry in self.entries:
            entry.status = "replacing" if entry.path in queued else "pending"
            self._refresh_entry(entry)

        worker = ApplyWorker(self.cli, scans, rule, self.current_scope(), self.settings)  # type: ignore[arg-type]
        worker.applied.connect(self._on_applied)
        worker.progressed.connect(self._on_progress)
        worker.done.connect(self._on_apply_done)
        self._worker = worker
        worker.start()

    def _on_applied(self, result: FileResult) -> None:
        entry = self._find_entry(result.path)
        if entry is not None:
            entry.result = result
            entry.status = result.status
            self._refresh_entry(entry)
        self._append_result_row(result)
        self.result_stack.setCurrentWidget(self.result_table)

        hits = self._stat_hits + result.hits
        self._stat_hits = hits
        self.stat_hits.set_value(hits)
        if result.status != "cancelled":
            self.stat_files.set_value(int(self.stat_files.value.text() or 0) + 1)
        if result.status == "error":
            self.stat_failed.set_value(int(self.stat_failed.value.text() or 0) + 1)
        elif result.status in ("no_match", "skipped", "cancelled"):
            self.stat_skipped.set_value(int(self.stat_skipped.value.text() or 0) + 1)

        tone = {
            "success": "success",
            "no_match": "muted",
            "skipped": "warning",
            "error": "danger",
            "cancelled": "muted",
        }.get(result.status, "text")
        self._log(
            f"{'✓' if result.status == 'success' else '×'} {Path(result.path).name}："
            f"{STATUS_LABEL.get(result.status, result.status)} — {result.message}",
            tone,
        )

    def _append_result_row(self, result: FileResult) -> None:
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        tone = {
            "success": theme.SUCCESS,
            "no_match": theme.TEXT_MUTED,
            "skipped": theme.WARNING,
            "error": theme.DANGER,
            "cancelled": theme.TEXT_MUTED,
        }.get(result.status, theme.TEXT)
        status_item = QTableWidgetItem(STATUS_LABEL.get(result.status, result.status))
        status_item.setForeground(QBrush(QColor(tone)))
        name_item = QTableWidgetItem(Path(result.path).name)
        name_item.setToolTip(
            f"{result.path}\n位置 {result.elements} 个 · 耗时 {result.duration:.1f}s"
        )
        name_item.setData(ROLE_PATH, result.path)
        name_item.setData(ROLE_BACKUP, result.backup)
        hits_item = QTableWidgetItem(str(result.hits))
        skipped_item = QTableWidgetItem(str(result.skipped) if result.skipped else "—")
        if result.skipped:
            skipped_item.setForeground(QBrush(QColor(theme.WARNING)))
            skipped_item.setToolTip("公式单元格、日期单元格等受保护内容，未参与替换")
        note = result.message
        if result.notes:
            note += "；" + "；".join(result.notes)
        note_item = QTableWidgetItem(note)
        note_item.setToolTip(note)
        note_item.setForeground(QBrush(QColor(theme.TEXT_MUTED)))
        for column, item in enumerate(
            (status_item, name_item, hits_item, skipped_item, note_item)
        ):
            if column in (1, 4):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                )
            self.result_table.setItem(row, column, item)

    def _show_result_menu(self, pos) -> None:
        """结果表右键：定位到文件管理器、打开备份、复制路径。"""
        hit = self.result_table.itemAt(pos)
        if hit is None:
            return
        name_item = self.result_table.item(hit.row(), 1)
        if name_item is None:
            return
        path = str(name_item.data(ROLE_PATH) or "")
        backup = str(name_item.data(ROLE_BACKUP) or "")
        if not path:
            return

        menu = QMenu(self.result_table)
        menu.setToolTipsVisible(True)

        def add(label: str, fn, target: str, tip: str = "") -> None:
            action = menu.addAction(label)
            action.setToolTip(tip or target)
            action.triggered.connect(
                lambda _checked=False, f=fn, t=target: self._run_menu_action(f, t)
            )

        add("在文件管理器中显示", reveal.reveal, path, "打开资源管理器并选中该文件")
        add("打开所在文件夹", reveal.open_folder, path)
        add("用默认程序打开文件", reveal.open_file, path)
        if backup:
            menu.addSeparator()
            add("在文件管理器中显示备份", reveal.reveal, backup)
            add("打开备份目录", reveal.open_folder, backup)
        menu.addSeparator()
        add("复制完整路径", self._copy_text, path)
        add("复制所在文件夹", self._copy_text, str(Path(path).parent))
        note_item = self.result_table.item(hit.row(), 4)
        if note_item and note_item.text():
            add("复制状态说明", self._copy_text, note_item.text())
        menu.exec(self.result_table.viewport().mapToGlobal(pos))

    def _run_menu_action(self, fn, target: str) -> None:
        try:
            message = fn(target)
            if message:
                self._toast(str(message))
        except (reveal.RevealError, OSError) as exc:
            self._toast(str(exc), "danger")
            self._log(f"右键操作失败：{exc}", "danger")

    @staticmethod
    def _copy_text(text: str) -> str:
        QApplication.clipboard().setText(text)
        return "已复制到剪贴板"

    def _on_apply_done(self, summary: dict) -> None:
        self._worker = None
        self._set_busy(False)
        self._preview_signature = None
        self._last_run_dir = str(summary.get("run_dir") or "")
        self.btn_undo.setEnabled(bool(self._last_run_dir) and summary.get("success", 0) > 0)
        total = int(summary.get("total", 0))
        hits = int(summary.get("hits", 0))
        success = int(summary.get("success", 0))
        failed = int(summary.get("error", 0))
        seconds = float(summary.get("seconds", 0.0))
        cancelled = int(summary.get("cancelled", 0))
        if cancelled and not success:
            message = "已取消：未完成任何文件，原文件均未改动"
        else:
            message = f"完成 {success}/{total} 个文件，命中 {hits} 处，用时 {seconds:.1f}s"
        tone = "success" if not failed and not cancelled else "warning"
        self._log(message, tone)
        self._toast(message, tone, 2600)
        self.content_status.setText(message)
        self.content_status.setStyleSheet(
            f"color: {theme.SUCCESS if tone == 'success' else theme.WARNING}; font-size: 11.5px;"
        )
        self.status_text.setText("就绪")
        self._refresh_counts()
        self.action_hint.setText(
            f"已取消 · 完成 {success} 个文件 · 命中 {hits} 处"
            if cancelled
            else f"上次替换：{success} 个文件 · {hits} 处命中"
        )
        self._update_action_state()

    # -- 工具 ---------------------------------------------------------------

    def _reset_stats(self) -> None:
        self._stat_hits = 0
        for stat in (self.stat_files, self.stat_hits, self.stat_skipped, self.stat_failed):
            stat.set_value(0)

    def _find_entry(self, path: str) -> FileEntry | None:
        key = os.path.normcase(os.path.abspath(path))
        for entry in self.entries:
            if os.path.normcase(os.path.abspath(entry.path)) == key:
                return entry
        return None

    def _ensure_ready(self) -> bool:
        if self.cli is None:
            self._toast("未检测到 office-cli，请先在设置中指定路径", "danger")
            return False
        if not self.entries:
            self._toast("请先添加要处理的文件", "warning")
            return False
        if not self.find_edit.text():
            self._toast("请输入查找内容", "warning")
            self.find_edit.setFocus()
            return False
        return True

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.btn_add_files.setEnabled(not busy)
        self.btn_add_folder.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        self.btn_settings.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)
        self.progress.setRange(0, 100 if busy else 1)
        if busy:
            self.progress.setValue(0)
            self.progress_label.setText("0 / 0")
            self.status_text.setText(message or "处理中…")
        else:
            self.progress.setValue(0)
            self.progress_label.setText("")
        self._update_action_state()

    def _update_action_state(self) -> None:
        cli_ok = self.cli is not None
        invalid = str(self.find_edit.property("invalid")) == "true"
        if self._busy:
            self.btn_apply.setEnabled(False)
            self.btn_preview.setEnabled(False)
            return
        self.btn_preview.setEnabled(cli_ok and not invalid)
        ready = (
            cli_ok
            and not invalid
            and bool(self.entries)
            and bool(self.find_edit.text())
            and self._preview_signature is not None
            and self._preview_signature == self._signature()
            and any(scan.matched for scan in self.scans.values())
        )
        self.btn_apply.setEnabled(ready)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.btn_preview.setEnabled(enabled)
        if not enabled:
            self.btn_apply.setEnabled(False)

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.progress_label.setText(f"{done} / {total}")
        if name:
            self.status_text.setText(f"正在处理：{name}")

    def _stop(self) -> None:
        if isinstance(self._worker, (ScanWorker, ApplyWorker)):
            self._worker.cancel()
            self.btn_stop.setEnabled(False)
            self.status_text.setText("正在停止…")

    def _switch_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        button = (self.tab_preview, self.tab_results, self.tab_log)[index]
        if not button.isChecked():
            button.setChecked(True)

    def _open_backup_dir(self) -> None:
        target = self._last_run_dir or self.settings.backup_root
        path = Path(target)
        if not path.exists():
            path = Path(self.settings.backup_root)
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            self._toast(f"无法打开目录：{exc}", "danger")

    def _undo_last(self) -> None:
        if self._busy:
            return
        run_dir = self._last_run_dir or latest_run(self.settings.backup_root) or ""
        if not run_dir:
            self._toast("没有可撤销的替换", "warning")
            return
        manifest = engine.run_manifest(run_dir)
        rows = [f"{Path(item.get('original', '')).name} · 备份于 {Path(run_dir).name}" for item in manifest]
        ok, _ = ConfirmDialog.confirm(
            self,
            "撤销本次替换",
            "将用备份覆盖回原文件。本次替换之后对这些文件做过的修改会丢失。",
            rows=rows,
            action_text="还原",
            action_kind="danger",
        )
        if not ok:
            return
        results = restore_run(run_dir)
        ok_count = sum(1 for _, success, _ in results if success)
        fail = [item for item in results if not item[1]]
        self._log(f"撤销完成：还原 {ok_count} 个文件，失败 {len(fail)} 个", "warning" if fail else "success")
        self._toast(f"已还原 {ok_count} 个文件", "success" if not fail else "warning")
        for path, success, message in fail:
            self._log(f"  × {Path(path).name}：{message}", "danger")
        for entry in self.entries:
            entry.status = "pending"
            entry.scan = None
            entry.result = None
            self._refresh_entry(entry)
        self.btn_undo.setEnabled(False)
        self._mark_stale()

    def _open_settings(self) -> None:
        if self._busy:
            return
        dialog = SettingsDialog(self.settings, self.cli_info, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.result_settings()
            self.settings.save()
            self._start_probe()
            self._toast("设置已保存", "success")

    def _start_probe(self) -> None:
        self.cli_pill.set_state("检测 office-cli…", "muted")
        self._probe = CliProbe(self.settings.cli_path)
        self._probe.done.connect(self._on_probe_done)
        self._probe.start()

    def _on_probe_done(self, info: CliInfo | None) -> None:
        self.cli_info = info
        if info:
            self.cli = OfficeCli(info)
            version = info.version or "office-cli"
            self.cli_pill.set_state(f"{version} · 就绪", "success")
            self._log(f"office-cli {version}（{info.origin}）：{info.path}", "success")
        else:
            self.cli = None
            self.cli_pill.set_state("未找到 office-cli", "danger")
            self._toast("未找到 office-cli，请在设置中指定路径", "danger", 4000)
            self._log("未找到 office-cli，请安装：npm install -g @officecli/officecli", "danger")
        self._set_actions_enabled(self.cli is not None)
        self._update_action_state()

    def _log(self, text: str, tone: str = "text") -> None:
        if not hasattr(self, "log_view"):
            return
        color = {
            "text": theme.TEXT_DIM,
            "muted": theme.TEXT_MUTED,
            "info": theme.INFO,
            "success": theme.SUCCESS,
            "warning": theme.WARNING,
            "danger": theme.DANGER,
        }.get(tone, theme.TEXT_DIM)
        stamp = time.strftime("%H:%M:%S")
        html = (
            f'<span style="color:{theme.TEXT_MUTED}">{stamp}</span> '
            f'<span style="color:{color}">{_escape(text)}</span>'
        )
        self.log_view.append(html)
        self._log_lines += 1
        if self._log_lines > 1200:
            self.log_view.clear()
            self._log_lines = 1
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _toast(self, text: str, tone: str = "default", duration: int = 2200) -> None:
        if hasattr(self, "toast"):
            self.toast.show_message(text, tone, duration)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy and isinstance(self._worker, ApplyWorker):
            ok, _ = ConfirmDialog.confirm(
                self,
                "正在替换",
                "替换尚未完成，确定要退出吗？正在写入的文件会被放弃，原文件不会被破坏。",
                action_text="退出",
                action_kind="danger",
            )
            if not ok:
                event.ignore()
                return
            self._worker.cancel()
        self.settings.save()
        event.accept()


class DropListWidget(QListWidget):
    filesDropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
    )
