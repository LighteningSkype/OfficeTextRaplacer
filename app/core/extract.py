"""按文件类型抽取"可见文本元素"。

office-cli 的 DOM 已经提供了稳定的路径与文本，这里只做三件事：

1. 选对选择器（docx: ``p, txbxContent``；xlsx: ``cell``；pptx: ``paragraph, tc, notes``）；
2. 把路径翻译成人能读懂的位置（"正文 · 第 3 段"、"Sheet1 · B4"）；
3. 标出**不参与替换**的元素（公式单元格、日期单元格等），供界面解释"跳过"。

所有路径都会原样交给 office-cli 执行替换，因此位置标签与实际落点天然一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .cli import CliError, OfficeCli

SUPPORTED_EXT = {".docx", ".xlsx", ".pptx"}

KIND_LABEL = {"word": "Word 文档", "excel": "Excel 工作簿", "powerpoint": "PowerPoint 演示文稿"}
KIND_BADGE = {"word": "W", "excel": "X", "powerpoint": "P"}


def detect_kind(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    return {".docx": "word", ".xlsx": "excel", ".pptx": "powerpoint"}.get(ext)


@dataclass
class TextElement:
    path: str
    text: str
    region: str
    location: str
    kind: str
    meta: dict = field(default_factory=dict)


@dataclass
class Excluded:
    location: str
    reason: str
    text: str


@dataclass
class Extraction:
    elements: list[TextElement]
    excluded: list[Excluded]
    sheets: list[str] = field(default_factory=list)


_SLIDE_RE = re.compile(r"/slide\[(\d+)\]")
_TBL_RE = re.compile(r"/tbl\[(\d+)\]")
_TR_RE = re.compile(r"/tr\[(\d+)\]")
_TC_RE = re.compile(r"/tc\[(\d+)\]")
_HEADER_RE = re.compile(r"/header\[(\d+)\]")
_FOOTER_RE = re.compile(r"/footer\[(\d+)\]")
_DATE_TOKENS = re.compile(r"(?<!\\)[ymdhs]", re.IGNORECASE)


def extract(cli: OfficeCli, path: str, kind: str) -> Extraction:
    if kind == "word":
        return _extract_docx(cli, path)
    if kind == "excel":
        return _extract_xlsx(cli, path)
    if kind == "powerpoint":
        return _extract_pptx(cli, path)
    raise CliError(f"不支持的文件类型：{Path(path).suffix}", code="unsupported_format")


# --------------------------------------------------------------------------- Word


def _extract_docx(cli: OfficeCli, path: str) -> Extraction:
    rows = cli.query(path, "p, txbxContent")
    elements: list[TextElement] = []
    body_index = 0
    textbox_index = 0
    for row in rows:
        text = str(row.get("text") or "")
        node_path = str(row.get("path") or "")
        if not node_path or not text.strip():
            continue
        if _HEADER_RE.search(node_path):
            num = _HEADER_RE.search(node_path).group(1)  # type: ignore[union-attr]
            elements.append(
                TextElement(node_path, text, "header", f"页眉 {num}", "paragraph")
            )
            continue
        if _FOOTER_RE.search(node_path):
            num = _FOOTER_RE.search(node_path).group(1)  # type: ignore[union-attr]
            elements.append(
                TextElement(node_path, text, "footer", f"页脚 {num}", "paragraph")
            )
            continue
        if "txbxContent" in node_path:
            textbox_index += 1
            elements.append(
                TextElement(node_path, text, "textbox", f"文本框 {textbox_index}", "textbox")
            )
            continue
        if "/tbl[" in node_path:
            tbl = _TBL_RE.search(node_path)
            tr = _TR_RE.search(node_path)
            tc = _TC_RE.search(node_path)
            label = "表格"
            if tbl:
                label += f" {tbl.group(1)}"
            if tr and tc:
                label += f" · {tr.group(1)} 行 {tc.group(1)} 列"
            elements.append(TextElement(node_path, text, "table", label, "cell-paragraph"))
            continue
        body_index += 1
        elements.append(
            TextElement(node_path, text, "body", f"正文 · 第 {body_index} 段", "paragraph")
        )
    return Extraction(elements=elements, excluded=[])


# -------------------------------------------------------------------------- Excel


def _extract_xlsx(cli: OfficeCli, path: str) -> Extraction:
    rows = cli.query(path, "cell")
    elements: list[TextElement] = []
    excluded: list[Excluded] = []
    sheets: list[str] = []
    for row in rows:
        node_path = str(row.get("path") or "")
        if "/" not in node_path.strip("/"):
            continue
        sheet, ref = node_path.strip("/").rsplit("/", 1)
        if sheet not in sheets:
            sheets.append(sheet)
        text = str(row.get("text") or "")
        if not text:
            continue
        fmt = row.get("format") if isinstance(row.get("format"), dict) else {}
        cell_type = str(fmt.get("type") or "String")
        formula = str(fmt.get("formula") or "")
        number_format = str(fmt.get("numberformat") or "")
        location = f"{sheet} · {ref}"

        reason = ""
        if formula:
            reason = "公式单元格（结果由公式计算，替换会破坏公式）"
        elif cell_type in ("Boolean", "Error"):
            reason = "布尔值或错误值单元格"
        elif cell_type == "Number" and _looks_like_date(number_format):
            reason = "日期/时间格式单元格（替换数字会破坏日期语义）"

        if reason:
            excluded.append(Excluded(location=location, reason=reason, text=text))
            continue
        elements.append(
            TextElement(
                node_path,
                text,
                "cell",
                location,
                "cell",
                {"sheet": sheet, "ref": ref, "type": cell_type, "numberformat": number_format},
            )
        )
    if not sheets:
        sheets = cli.list_sheets(path)
    return Extraction(elements=elements, excluded=excluded, sheets=sheets)


def _looks_like_date(number_format: str) -> bool:
    if not number_format:
        return False
    # 去掉引号包裹的字面量与颜色/条件段，避免把 "年" 之类误判
    cleaned = re.sub(r'"[^"]*"', "", number_format)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    return bool(_DATE_TOKENS.search(cleaned))


# ---------------------------------------------------------------- PowerPoint


def _extract_pptx(cli: OfficeCli, path: str) -> Extraction:
    rows = cli.query(path, "paragraph, tc, notes")
    elements: list[TextElement] = []
    per_slide: dict[int, int] = {}
    for row in rows:
        node_path = str(row.get("path") or "")
        text = str(row.get("text") or "")
        if not node_path or not text.strip():
            continue
        slide_match = _SLIDE_RE.search(node_path)
        slide_no = int(slide_match.group(1)) if slide_match else 0

        if node_path.rstrip("/").endswith("/notes"):
            elements.append(
                TextElement(node_path, text, "notes", f"第 {slide_no} 页 · 备注", "notes")
            )
            continue
        if "/tc[" in node_path:
            tbl = _TBL_RE.search(node_path)
            tr = _TR_RE.search(node_path)
            tc = _TC_RE.search(node_path)
            label = f"第 {slide_no} 页 · 表格"
            if tbl:
                label += f" {tbl.group(1)}"
            if tr and tc:
                label += f" · {tr.group(1)} 行 {tc.group(1)} 列"
            elements.append(TextElement(node_path, text, "table", label, "cell"))
            continue
        per_slide[slide_no] = per_slide.get(slide_no, 0) + 1
        label = f"第 {slide_no} 页 · 第 {per_slide[slide_no]} 段文本"
        elements.append(TextElement(node_path, text, "slide", label, "paragraph"))
    return Extraction(elements=elements, excluded=[])
