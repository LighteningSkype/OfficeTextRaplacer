"""预览与执行引擎：所有写盘动作都在"副本"上完成。

安全模型
--------
1. 先把原文件复制成同目录下的临时副本；
2. 只在副本上执行 office-cli 的批量替换；
3. 用 OpenXML 校验器验证副本仍然合法；
4. 把原文件复制进备份目录（可关闭）；
5. ``os.replace`` 原子地把副本换到原路径。

任何一步失败，临时副本都会被删除，原文件一个字节都不会被改动。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .cli import CliError, OfficeCli
from .extract import Excluded, Extraction, TextElement, detect_kind, extract
from .rules import CompiledRule, RuleError, snippet

MAX_HITS_PER_FILE = 800
MAX_HITS_PER_ELEMENT = 60
MAX_EXCLUDED_ROWS = 12
_NUMERIC_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


@dataclass
class Scope:
    body: bool = True
    table: bool = True
    header_footer: bool = True
    notes: bool = False
    sheets: list[str] | None = None  # None = 全部工作表

    def allows(self, element: TextElement) -> bool:
        region = element.region
        if region in ("body", "textbox", "slide"):
            return self.body
        if region == "table":
            return self.table
        if region in ("header", "footer"):
            return self.header_footer
        if region == "notes":
            return self.notes
        if region == "cell":
            if self.sheets is None:
                return True
            return str(element.meta.get("sheet") or "") in self.sheets
        return False


@dataclass
class MatchHit:
    location: str
    path: str
    region: str
    before: str
    matched: str
    after: str
    replacement: str
    index: int = 0


@dataclass
class FileScan:
    path: str
    kind: str
    hits: list[MatchHit] = field(default_factory=list)
    elements: dict[str, TextElement] = field(default_factory=dict)
    hit_count: int = 0
    element_count: int = 0
    excluded: list[tuple[str, str, int]] = field(default_factory=list)
    excluded_hits: int = 0
    truncated: bool = False
    error: str = ""
    error_code: str = ""
    duration: float = 0.0
    fingerprint: tuple[float, int] | None = None

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def matched(self) -> bool:
        return self.hit_count > 0


@dataclass
class FileResult:
    path: str
    kind: str
    status: str  # success | no_match | skipped | error | cancelled
    hits: int = 0
    elements: int = 0
    skipped: int = 0
    message: str = ""
    notes: list[str] = field(default_factory=list)
    backup: str = ""
    duration: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "success"


STATUS_LABEL = {
    "success": "已替换",
    "no_match": "无匹配",
    "skipped": "已跳过",
    "error": "失败",
    "cancelled": "已取消",
}


def fingerprint(path: str) -> tuple[float, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_mtime, stat.st_size)


def scan_file(cli: OfficeCli, path: str, rule: CompiledRule, scope: Scope) -> FileScan:
    started = time.perf_counter()
    kind = detect_kind(path) or ""
    scan = FileScan(path=path, kind=kind, fingerprint=fingerprint(path))
    if not kind:
        scan.error = "仅支持 .docx / .xlsx / .pptx（旧版 .doc/.xls/.ppt 请先另存为新格式）"
        scan.error_code = "unsupported_format"
        scan.duration = time.perf_counter() - started
        return scan
    try:
        data = extract(cli, path, kind)
    except CliError as exc:
        scan.error = exc.friendly()
        scan.error_code = exc.code
        scan.duration = time.perf_counter() - started
        return scan
    except OSError as exc:
        scan.error = f"无法读取文件：{exc.strerror or exc}"
        scan.error_code = "io_error"
        scan.duration = time.perf_counter() - started
        return scan

    _collect_hits(scan, data, rule, scope)
    scan.duration = time.perf_counter() - started
    return scan


def _collect_hits(scan: FileScan, data: Extraction, rule: CompiledRule, scope: Scope) -> None:
    total = 0
    shown = 0
    paths_with_hits: set[str] = set()
    for element in data.elements:
        if not scope.allows(element):
            continue
        matches = list(rule.iter_matches(element.text))
        if not matches:
            continue
        total += len(matches)
        paths_with_hits.add(element.path)
        scan.elements[element.path] = element
        for index, match in enumerate(matches):
            if shown >= MAX_HITS_PER_FILE or index >= MAX_HITS_PER_ELEMENT:
                scan.truncated = True
                break
            before, matched, after = snippet(element.text, match.start(), match.end())
            scan.hits.append(
                MatchHit(
                    location=element.location,
                    path=element.path,
                    region=element.region,
                    before=before,
                    matched=matched,
                    after=after,
                    replacement=rule.replacement_for(match),
                    index=index,
                )
            )
            shown += 1
    scan.hit_count = total
    scan.element_count = len(paths_with_hits)

    excluded_total = 0
    for item in data.excluded:
        count = rule.count(item.text)
        if not count:
            continue
        excluded_total += count
        if len(scan.excluded) < MAX_EXCLUDED_ROWS:
            scan.excluded.append((item.location, item.reason, count))
    scan.excluded_hits = excluded_total


# --------------------------------------------------------------------------- 执行


class ApplyError(RuntimeError):
    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def apply_file(
    cli: OfficeCli,
    scan: FileScan,
    rule: CompiledRule,
    scope: Scope,
    *,
    run_dir: Path | None = None,
    keep_backup: bool = True,
    verify_after: bool = True,
    cancel_check=None,
) -> FileResult:
    started = time.perf_counter()
    path = scan.path
    result = FileResult(path=path, kind=scan.kind, status="error")

    try:
        _preflight(path, scan.kind)
    except ApplyError as exc:
        result.status = "skipped"
        result.message = exc.message
        result.duration = time.perf_counter() - started
        return result

    if cancel_check and cancel_check():
        result.status = "cancelled"
        result.message = "已取消"
        return result

    fresh = scan
    if scan.fingerprint != fingerprint(path) or scan.error:
        fresh = scan_file(cli, path, rule, scope)
        if fresh.error:
            result.message = fresh.error
            result.duration = time.perf_counter() - started
            return result

    if not fresh.matched:
        result.status = "no_match"
        result.skipped = fresh.excluded_hits
        result.message = "未找到匹配项"
        if fresh.excluded_hits:
            result.notes.append(_skipped_note(fresh))
        result.duration = time.perf_counter() - started
        return result

    temp_path = _temp_sibling(path)
    type_conversions = 0
    try:
        shutil.copy2(path, temp_path)
        items, expected_paths, cell_counts, type_conversions = _build_items(fresh, rule)
        if not items:
            result.status = "no_match"
            result.message = "未找到匹配项"
            result.duration = time.perf_counter() - started
            return result

        batch = cli.batch(temp_path, items)
        failures = [item for item in batch if not item.success]
        if failures:
            first = failures[0]
            raise ApplyError(
                f"第 {first.index + 1} 个元素的替换被拒绝：{first.error or '未知原因'}"
            )
        hits = 0
        changed = 0
        for item in batch:
            expected_path = expected_paths[item.index] if 0 <= item.index < len(expected_paths) else ""
            count = cell_counts.get(expected_path, item.matched)
            hits += count
            if count:
                changed += 1
        if hits == 0:
            result.status = "no_match"
            result.message = "未找到匹配项"
            result.duration = time.perf_counter() - started
            return result

        if verify_after:
            ok, text = cli.validate(temp_path)
            if not ok:
                raise ApplyError(f"替换后的文件未通过结构校验，已放弃写入（原文件未改动）：{text}")

        if cancel_check and cancel_check():
            result.status = "cancelled"
            result.message = "已取消（原文件未改动）"
            return result

        backup_path = ""
        if keep_backup and run_dir is not None:
            backup_path = _make_backup(path, run_dir)

        try:
            os.replace(temp_path, path)
        except OSError as exc:
            raise ApplyError(
                f"无法写入原文件（可能正被 Office 打开）：{exc.strerror or exc}"
            ) from exc

        result.status = "success"
        result.hits = hits
        result.elements = changed
        result.skipped = fresh.excluded_hits
        result.backup = backup_path
        result.message = f"已替换 {hits} 处，涉及 {changed} 个位置"
        if fresh.excluded_hits:
            result.notes.append(_skipped_note(fresh))
        if type_conversions:
            result.notes.append(f"{type_conversions} 个数值单元格因替换结果非数字，已转为文本")
        if fresh.truncated:
            result.notes.append("预览仅展示前若干条命中，实际替换数量以上方统计为准")
        result.duration = time.perf_counter() - started
        return result
    except ApplyError as exc:
        result.status = "error"
        result.message = exc.message
        result.duration = time.perf_counter() - started
        return result
    except CliError as exc:
        result.status = "error"
        result.message = exc.friendly()
        result.duration = time.perf_counter() - started
        return result
    except OSError as exc:
        result.status = "error"
        result.message = f"文件操作失败：{exc.strerror or exc}"
        result.duration = time.perf_counter() - started
        return result
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def _skipped_note(scan: FileScan) -> str:
    reasons: list[str] = []
    for _location, reason, _count in scan.excluded:
        short = reason.split("（")[0]
        if short not in reasons:
            reasons.append(short)
    suffix = f"：{'、'.join(reasons[:3])}" if reasons else ""
    return f"{scan.excluded_hits} 处未处理{suffix}"


def _preflight(path: str, kind: str) -> None:
    target = Path(path)
    if not kind:
        raise ApplyError("仅支持 .docx / .xlsx / .pptx")
    if not target.is_file():
        raise ApplyError("文件不存在或已被移动")
    if target.stat().st_size == 0:
        raise ApplyError("文件为空（0 字节）")
    lock_file = target.with_name("~$" + target.name)
    if lock_file.exists():
        raise ApplyError("文件正在被 Office 打开，请先关闭后重试")
    if not os.access(path, os.W_OK):
        raise ApplyError("没有写入权限（文件为只读，或所在目录受限）")
    try:
        with open(path, "r+b"):
            pass
    except PermissionError as exc:
        raise ApplyError(f"没有写入权限：{exc.strerror or exc}") from exc
    except OSError as exc:
        raise ApplyError(f"无法打开文件：{exc.strerror or exc}") from exc


def _temp_sibling(path: str) -> Path:
    target = Path(path)
    token = uuid.uuid4().hex[:8]
    return target.with_name(f"{target.stem}.otr-{token}{target.suffix}")


def _build_items(
    scan: FileScan, rule: CompiledRule
) -> tuple[list[dict], list[str], dict[str, int], int]:
    """构造 office-cli 批量命令。

    Word / PowerPoint 交给 office-cli 原生 find/replace（可保留 run 级格式）；
    Excel 单元格没有 find/replace 接口，改为本地算出新值再 ``set value``。
    """
    items: list[dict] = []
    paths: list[str] = []
    cell_counts: dict[str, int] = {}
    conversions = 0
    for element_path, element in scan.elements.items():
        if element.region == "cell":
            old_text = element.text
            new_text = rule.replace(old_text)
            if new_text == old_text:
                continue
            cell_type = str(element.meta.get("type") or "String")
            props: dict[str, str] = {"value": new_text}
            if cell_type == "Number":
                if _NUMERIC_RE.match(new_text.strip()):
                    props["value"] = new_text.strip()
                else:
                    props["type"] = "string"
                    conversions += 1
            elif cell_type == "String":
                props["type"] = "string"
            items.append({"command": "set", "path": element_path, "props": props})
            paths.append(element_path)
            cell_counts[element_path] = rule.count(old_text)
        else:
            items.append({"command": "set", "path": element_path, "props": rule.cli_props()})
            paths.append(element_path)
    return items, paths, cell_counts, conversions


# --------------------------------------------------------------------------- 备份


def make_run_dir(backup_root: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(backup_root) / f"{stamp}-{uuid.uuid4().hex[:4]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"created": datetime.now().isoformat(timespec="seconds"), "items": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir


def _make_backup(path: str, run_dir: Path) -> str:
    source = Path(path)
    target = run_dir / f"{source.stem}{source.suffix}"
    index = 1
    while target.exists():
        target = run_dir / f"{source.stem}-{index}{source.suffix}"
        index += 1
    shutil.copy2(source, target)

    manifest_path = run_dir / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"created": datetime.now().isoformat(timespec="seconds"), "items": []}
    data.setdefault("items", []).append({"original": str(source), "backup": str(target)})
    try:
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return str(target)


def run_manifest(run_dir: str) -> list[dict]:
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data.get("items", []) if isinstance(item, dict)]


def restore_run(run_dir: str) -> list[tuple[str, bool, str]]:
    """把某次运行备份的文件恢复回原位。"""
    results: list[tuple[str, bool, str]] = []
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.is_file():
        return results
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return results
    for item in data.get("items", []):
        original = str(item.get("original") or "")
        backup = str(item.get("backup") or "")
        if not original or not Path(backup).is_file():
            results.append((original, False, "备份文件缺失"))
            continue
        try:
            lock = Path(original).with_name("~$" + Path(original).name)
            if lock.exists():
                results.append((original, False, "文件正被 Office 打开"))
                continue
            shutil.copy2(backup, original)
            results.append((original, True, "已还原"))
        except OSError as exc:
            results.append((original, False, str(exc.strerror or exc)))
    return results


def latest_run(backup_root: str) -> str | None:
    root = Path(backup_root)
    if not root.is_dir():
        return None
    runs = sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)
    return str(runs[0]) if runs else None


def prune_runs(backup_root: str, keep: int = 12) -> None:
    root = Path(backup_root)
    if not root.is_dir():
        return
    runs = sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)
    for old in runs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


__all__ = [
    "ApplyError",
    "Excluded",
    "FileResult",
    "FileScan",
    "MatchHit",
    "RuleError",
    "Scope",
    "apply_file",
    "fingerprint",
    "latest_run",
    "make_run_dir",
    "prune_runs",
    "restore_run",
    "scan_file",
    "STATUS_LABEL",
]
