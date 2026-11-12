"""本地 HTTP API：把 app/core 的替换能力暴露给 shadcn/ui 前端。

只监听 127.0.0.1 的随机端口，不对外暴露；Qt 宿主窗口拿到端口后加载页面。
所有耗时任务（扫描 / 替换）都在后台线程里跑，前端按游标轮询增量结果。
"""

from __future__ import annotations

import base64
import json
import mimetypes
import struct
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ..core import engine
from ..core.cli import CliInfo, OfficeCli, discover
from ..core.config import (
    APP_SUBTITLE,
    APP_TITLE,
    IMAGE_EXT,
    Settings,
    normalize_wallpaper,
    prune_wallpapers,
    wallpaper_available,
    wallpaper_dir,
)
from ..core.engine import FileResult, FileScan, Scope, STATUS_LABEL
from ..core.extract import KIND_LABEL, SUPPORTED_EXT, detect_kind
from ..core.rules import CompiledRule, ReplaceRule, RuleError
from . import reveal

MAX_HITS_UI = 80
MAX_WALLPAPER_BYTES = 16 * 1024 * 1024

# 只做“是不是图片”的轻量判断，不引入额外依赖。
_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)


def image_size(raw: bytes) -> tuple[int, int] | None:
    """返回图片像素尺寸；识别失败说明不是有效图片。"""
    head = raw[:32]
    for magic, _kind in _IMAGE_MAGIC:
        if head.startswith(magic):
            break
    else:
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return (1, 1)  # WebP 只需确认容器头，Chromium 自己会解码
        if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
            return (1, 1)
        return None

    try:
        if head[:2] == b"\xff\xd8":
            index = 2
            while index < len(raw) - 9:
                if raw[index] != 0xFF:
                    index += 1
                    continue
                marker = raw[index + 1]
                if marker in (0xD8, 0xD9):
                    index += 2
                    continue
                length = struct.unpack(">H", raw[index + 2 : index + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", raw[index + 5 : index + 9])
                    return (w, h)
                index += 2 + length
            return None
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", raw[16:24])
            return (w, h)
        if head[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", raw[6:10])
            return (w, h)
        if head[:2] == b"BM":
            w, h = struct.unpack("<ii", raw[18:26])
            return (abs(w), abs(h))
    except (struct.error, IndexError, ValueError):
        return None
    return None


# --------------------------------------------------------------------------- 任务


@dataclass
class Job:
    id: str
    mode: str
    total: int = 0
    status: str = "running"  # running | done | cancelled | error
    done: int = 0
    current: str = ""
    scans: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, level: str, text: str) -> None:
        with self.lock:
            self.logs.append({"level": level, "text": text, "ts": round(time.time() * 1000)})

    def add_scan(self, item: dict) -> None:
        with self.lock:
            self.scans.append(item)

    def add_result(self, item: dict) -> None:
        with self.lock:
            self.results.append(item)

    def snapshot(self, since_scan: int, since_result: int, since_log: int) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "mode": self.mode,
                "status": self.status,
                "total": self.total,
                "done": self.done,
                "current": self.current,
                "error": self.error,
                "summary": self.summary,
                "scans": self.scans[since_scan:],
                "results": self.results[since_result:],
                "logs": self.logs[since_log:],
                "counts": {
                    "scans": len(self.scans),
                    "results": len(self.results),
                    "logs": len(self.logs),
                },
            }


class ApiState:
    def __init__(self, dist: Path, bridge) -> None:
        self.dist = dist
        self.bridge = bridge
        self.settings = Settings.load()
        self.settings_lock = threading.Lock()
        self.cli_info: CliInfo | None = None
        self.jobs: dict[str, Job] = {}
        self.jobs_lock = threading.Lock()

    def cli(self) -> OfficeCli:
        info = self.cli_info or discover(self.settings.cli_path or None)
        if not info:
            raise LookupError("未找到 office-cli，请先在设置里指定可执行文件")
        return OfficeCli(info)

    def probe(self) -> None:
        self.cli_info = discover(self.settings.cli_path or None)


# --------------------------------------------------------------------------- 序列化


def scan_to_dict(scan: FileScan) -> dict:
    path = scan.path
    return {
        "path": path,
        "name": Path(path).name,
        "folder": str(Path(path).parent),
        "kind": scan.kind,
        "kind_label": KIND_LABEL.get(scan.kind, scan.kind.upper() or "未知"),
        "ok": scan.ok,
        "error": scan.error,
        "error_code": scan.error_code,
        "hit_count": scan.hit_count,
        "element_count": scan.element_count,
        "excluded_hits": scan.excluded_hits,
        "truncated": scan.truncated,
        "duration": round(scan.duration, 3),
        "hits": [
            {
                "location": h.location,
                "region": h.region,
                "before": h.before,
                "matched": h.matched,
                "after": h.after,
                "replacement": h.replacement,
            }
            for h in scan.hits[:MAX_HITS_UI]
        ],
        "hits_shown": min(len(scan.hits), MAX_HITS_UI),
        "excluded": [
            {"location": loc, "reason": reason, "count": count}
            for loc, reason, count in scan.excluded
        ],
    }


def result_to_dict(result: FileResult) -> dict:
    return {
        "path": result.path,
        "name": Path(result.path).name,
        "folder": str(Path(result.path).parent),
        "kind": result.kind,
        "kind_label": KIND_LABEL.get(result.kind, result.kind.upper()),
        "status": result.status,
        "status_label": STATUS_LABEL.get(result.status, result.status),
        "hits": result.hits,
        "elements": result.elements,
        "skipped": result.skipped,
        "message": result.message,
        "notes": result.notes,
        "backup": result.backup,
        "duration": round(result.duration, 3),
    }


def _custom_exists(settings: Settings) -> bool:
    """非自定义壁纸一律视为可用；自定义壁纸判断图片是否仍能读到。"""
    if settings.wallpaper_source != "custom":
        return True
    return wallpaper_available(settings.wallpaper_path)


def file_entry(path: str) -> dict:
    p = Path(path)
    kind = detect_kind(path) or ""
    return {
        "path": str(p),
        "name": p.name,
        "folder": str(p.parent),
        "kind": kind,
        "kind_label": KIND_LABEL.get(kind, kind.upper() or "?"),
        "exists": p.is_file(),
    }


# --------------------------------------------------------------------------- 业务


def build_rule(data: dict) -> CompiledRule:
    return ReplaceRule(
        find=str(data.get("find") or ""),
        replace=str(data.get("replace") or ""),
        regex=bool(data.get("regex")),
        case_sensitive=bool(data.get("case_sensitive", True)),
        whole_word=bool(data.get("whole_word")),
    ).compile()


def build_scope(data: dict) -> Scope:
    sheets = data.get("sheets") or []
    return Scope(
        body=bool(data.get("body", True)),
        table=bool(data.get("table", True)),
        header_footer=bool(data.get("header_footer", True)),
        notes=bool(data.get("notes", False)),
        sheets=[str(s) for s in sheets] if sheets else None,
    )


def expand_paths(paths: list[str], recursive: bool, max_files: int) -> tuple[list[str], list[str]]:
    """把用户给的路径展开成受支持文件列表；返回 (文件, 提示)。"""
    found: list[str] = []
    seen: set[str] = set()
    notes: list[str] = []
    for raw in paths:
        text = str(raw or "").strip().strip('"').strip("'")
        if not text:
            continue
        p = Path(text)
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            candidates = [q for q in it if q.is_file()]
        else:
            notes.append(f"路径不存在：{text}")
            continue
        for item in candidates:
            if item.name.startswith("~$"):
                continue
            if item.suffix.lower() not in SUPPORTED_EXT:
                continue
            key = str(item).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(str(item))
    if len(found) > max_files:
        notes.append(f"文件数超过上限 {max_files}，已只保留前 {max_files} 个")
        found = found[:max_files]
    return [os.path.normpath(x) for x in found], notes


def run_preview(state: ApiState, job: Job, paths: list[str], rule: CompiledRule, scope: Scope) -> None:
    try:
        cli = state.cli()
    except LookupError as exc:
        job.status = "error"
        job.error = str(exc)
        job.log("error", str(exc))
        return
    job.log("info", f"开始预览 {len(paths)} 个文件")
    for index, path in enumerate(paths):
        if job.cancel.is_set():
            break
        job.current = Path(path).name
        scan = engine.scan_file(cli, path, rule, scope)
        job.add_scan(scan_to_dict(scan))
        if scan.error:
            job.log("error", f"{Path(path).name}：{scan.error}")
        else:
            job.log("info", f"{Path(path).name}：命中 {scan.hit_count} 处")
        with job.lock:
            job.done = index + 1
    _finish_preview(job)


def _finish_preview(job: Job) -> None:
    hits = sum(s["hit_count"] for s in job.scans)
    matched_files = sum(1 for s in job.scans if s["hit_count"] > 0)
    errors = sum(1 for s in job.scans if not s["ok"])
    job.summary = {
        "files": len(job.scans),
        "hits": hits,
        "matched_files": matched_files,
        "errors": errors,
        "skipped": sum(s["excluded_hits"] for s in job.scans),
    }
    job.status = "cancelled" if job.cancel.is_set() else "done"
    job.current = ""
    job.log("info", "预览完成" if job.status == "done" else "预览已取消")


def run_apply(state: ApiState, job: Job, paths: list[str], rule: CompiledRule, scope: Scope) -> None:
    try:
        cli = state.cli()
    except LookupError as exc:
        job.status = "error"
        job.error = str(exc)
        job.log("error", str(exc))
        return

    with state.settings_lock:
        settings = Settings.load()
    run_dir = None
    if settings.keep_backup:
        try:
            run_dir = engine.make_run_dir(settings.backup_root)
        except OSError:
            run_dir = None

    job.log("info", f"开始替换 {len(paths)} 个文件（先复制副本，校验通过后才写回）")
    summary = {
        "files": len(paths),
        "success": 0,
        "no_match": 0,
        "skipped": 0,
        "error": 0,
        "cancelled": 0,
        "hits": 0,
        "seconds": 0.0,
        "run_dir": str(run_dir) if run_dir else "",
    }
    started = time.perf_counter()
    for index, path in enumerate(paths):
        if job.cancel.is_set():
            job.add_result(
                result_to_dict(
                    FileResult(
                        path=path,
                        kind=detect_kind(path) or "",
                        status="cancelled",
                        message="已取消，未处理（原文件未改动）",
                    )
                )
            )
            summary["cancelled"] += 1
            continue
        job.current = Path(path).name
        # 每次都重新扫描：不能信任前端传来的旧预览（文件可能已被外部改动）。
        scan = engine.scan_file(cli, path, rule, scope)
        if scan.error:
            result = FileResult(
                path=path, kind=scan.kind, status="error", message=scan.error
            )
        else:
            result = engine.apply_file(
                cli,
                scan,
                rule,
                scope,
                run_dir=run_dir,
                keep_backup=settings.keep_backup and run_dir is not None,
                verify_after=settings.verify_after,
                cancel_check=job.cancel.is_set,
            )
        job.add_result(result_to_dict(result))
        summary[result.status] = summary.get(result.status, 0) + 1
        summary["hits"] += result.hits
        level = {"success": "info", "error": "error", "skipped": "warn"}.get(result.status, "info")
        job.log(level, f"{Path(path).name}：{result.message}")
        with job.lock:
            job.done = index + 1
    summary["seconds"] = round(time.perf_counter() - started, 2)
    if run_dir is not None:
        engine.prune_runs(settings.backup_root)
    job.summary = summary
    job.status = "cancelled" if job.cancel.is_set() else "done"
    job.current = ""
    job.log("info", "替换完成" if job.status == "done" else "替换已取消")


# --------------------------------------------------------------------------- HTTP


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "OfficeReplacer/2.0"
    state: ApiState  # 由 make_server 注入到类上

    def log_message(self, fmt: str, *args) -> None:  # 静音访问日志
        return

    # -- 基础响应 -----------------------------------------------------------

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _static(self, rel: str) -> None:
        target = (self.state.dist / rel.lstrip("/")).resolve()
        root = self.state.dist.resolve()
        if root not in target.parents and target != root:
            self._json({"ok": False, "message": "非法路径"}, 403)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self.send_error(404, "Not Found")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, target: Path) -> None:
        """只读地把一张本地图片回给前端（自定义壁纸 / 收款码）。"""
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(404, "Not Found")
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/wallpaper":
            target = self._wallpaper_target()
            if target is None:
                self.send_error(404, "Not Found")
                return
            self._file(target)
            return
        if path.startswith("/api/"):
            try:
                self._api_get(path, parse_qs(parsed.query))
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "message": f"服务端异常：{exc}"}, 500)
            return
        self._static("index.html" if path in ("", "/") else path)

    def _wallpaper_target(self) -> Path | None:
        """只回吐配置里记录的那张图片，不暴露任意文件读取。"""
        saved = self.state.settings.wallpaper_path
        return Path(saved) if wallpaper_available(saved) else None

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/"):
            self.send_error(404)
            return
        try:
            self._api_post(path, self._body())
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "message": f"服务端异常：{exc}"}, 500)

    # -- API ---------------------------------------------------------------

    def _api_get(self, path: str, query: dict) -> None:
        state = self.state
        if path == "/api/health":
            self._json({"ok": True, "platform": sys.platform})
            return
        if path == "/api/bootstrap":
            with state.settings_lock:
                settings = state.settings
                info = {
                    "cli_path": settings.cli_path,
                    "keep_backup": settings.keep_backup,
                    "verify_after": settings.verify_after,
                    "backup_root": settings.backup_root,
                    "last_dir": settings.last_dir,
                    "recursive_scan": settings.recursive_scan,
                    "max_files": settings.max_files,
                    "theme": settings.theme,
                    "accent": settings.accent,
                    "wallpaper_source": settings.wallpaper_source,
                    "wallpaper_id": settings.wallpaper_id,
                    "wallpaper_path": settings.wallpaper_path,
                    "wallpaper_blur": settings.wallpaper_blur,
                    "wallpaper_panel_opacity": settings.wallpaper_panel_opacity,
                }
            state.probe()
            cli = state.cli_info
            self._json(
                {
                    "ok": True,
                    "app": {
                        "title": APP_TITLE,
                        "subtitle": APP_SUBTITLE,
                        "version": "2.0.0",
                    },
                    "cli": {
                        "found": cli is not None,
                        "version": cli.version if cli else "",
                        "origin": cli.origin if cli else "",
                        "path": cli.path if cli else "",
                    },
                    "settings": info,
                    "platform": sys.platform,
                    "wallpaper_exists": _custom_exists(settings),
                }
            )
            return
        if path == "/api/job":
            job_id = (query.get("id") or [""])[0]
            with state.jobs_lock:
                job = state.jobs.get(job_id)
            if not job:
                self._json({"ok": False, "message": "任务不存在"}, 404)
                return
            num = lambda key: int((query.get(key) or ["0"])[0] or 0)  # noqa: E731
            self._json(
                {
                    "ok": True,
                    **job.snapshot(num("since_scan"), num("since_result"), num("since_log")),
                }
            )
            return
        self._json({"ok": False, "message": "未知接口"}, 404)

    def _api_post(self, path: str, data: dict) -> None:
        state = self.state

        if path == "/api/settings":
            allowed = {
                "cli_path",
                "keep_backup",
                "verify_after",
                "backup_root",
                "recursive_scan",
                "max_files",
                "theme",
                "accent",
                "last_dir",
                "wallpaper_source",
                "wallpaper_id",
                "wallpaper_path",
                "wallpaper_blur",
                "wallpaper_panel_opacity",
            }
            with state.settings_lock:
                for key, value in data.items():
                    if key in allowed and hasattr(state.settings, key):
                        if key in ("wallpaper_blur", "wallpaper_panel_opacity"):
                            try:
                                value = int(value)
                            except (TypeError, ValueError):
                                continue
                        if isinstance(value, type(getattr(state.settings, key))):
                            setattr(state.settings, key, value)
                (
                    state.settings.wallpaper_source,
                    state.settings.wallpaper_id,
                    state.settings.wallpaper_path,
                    state.settings.wallpaper_blur,
                    state.settings.wallpaper_panel_opacity,
                ) = normalize_wallpaper(
                    state.settings.wallpaper_source,
                    state.settings.wallpaper_id,
                    state.settings.wallpaper_path,
                    state.settings.wallpaper_blur,
                    state.settings.wallpaper_panel_opacity,
                )
                state.settings.save()
                from dataclasses import asdict

                payload = asdict(state.settings)
            payload["wallpaper_exists"] = _custom_exists(state.settings)
            self._json({"ok": True, "settings": payload})
            return

        if path == "/api/probe":
            state.probe()
            cli = state.cli_info
            self._json(
                {
                    "ok": True,
                    "cli": {
                        "found": cli is not None,
                        "version": cli.version if cli else "",
                        "origin": cli.origin if cli else "",
                        "path": cli.path if cli else "",
                    },
                }
            )
            return

        if path == "/api/validate-rule":
            try:
                build_rule(data)
                self._json({"ok": True, "error": ""})
            except RuleError as exc:
                self._json({"ok": False, "error": str(exc)})
            return

        if path == "/api/dialog/files":
            with state.settings_lock:
                start = data.get("start_dir") or state.settings.last_dir
            files = state.bridge.pick_files({"start_dir": start})
            if files:
                with state.settings_lock:
                    state.settings.last_dir = str(Path(files[0]).parent)
                    state.settings.save()
            self._json({"ok": True, "files": files})
            return

        if path == "/api/dialog/folder":
            folder = state.bridge.pick_folder(str(data.get("start_dir") or ""))
            self._json({"ok": True, "folder": folder})
            return

        if path == "/api/dialog/cli":
            exe = state.bridge.pick_cli(str(data.get("start_dir") or ""))
            self._json({"ok": True, "path": exe})
            return

        if path == "/api/dialog/wallpaper":
            try:
                chosen = state.bridge.pick_wallpaper(str(data.get("start_dir") or ""))
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "message": f"无法打开系统文件选择框：{exc}"})
                return
            self._json({"ok": True, "path": chosen})
            return

        if path == "/api/wallpaper/upload":
            # 浏览器环境拿不到真实路径时的兜底：把用户选的图片复制进应用数据目录。
            name = Path(str(data.get("name") or "wallpaper")).name
            suffix = Path(name).suffix.lower()
            if suffix not in IMAGE_EXT:
                self._json({"ok": False, "message": "请选择 JPG / PNG / WebP 等图片文件"})
                return
            try:
                raw = base64.b64decode(str(data.get("data") or ""), validate=True)
            except (ValueError, TypeError, base64.binascii.Error):
                self._json({"ok": False, "message": "图片数据无法解析"})
                return
            if not raw or len(raw) > MAX_WALLPAPER_BYTES:
                self._json(
                    {"ok": False, "message": f"图片为空或超过 {MAX_WALLPAPER_BYTES // (1024 * 1024)} MB"}
                )
                return
            if image_size(raw) is None:
                self._json({"ok": False, "message": "文件内容不是可识别的图片"})
                return
            target = wallpaper_dir() / f"custom-{uuid.uuid4().hex[:10]}{suffix}"
            try:
                target.write_bytes(raw)
            except OSError as exc:
                self._json({"ok": False, "message": f"保存图片失败：{exc}"})
                return
            prune_wallpapers(keep=str(target))
            self._json({"ok": True, "path": str(target), "name": name})
            return

        if path == "/api/add-paths":
            with state.settings_lock:
                recursive = state.settings.recursive_scan
                max_files = state.settings.max_files
            paths, notes = expand_paths(
                list(data.get("paths") or []), recursive, max_files
            )
            self._json({"ok": True, "files": [file_entry(p) for p in paths], "notes": notes})
            return

        if path == "/api/sheets":
            target = str(data.get("path") or "")
            if detect_kind(target) != "xlsx":
                self._json({"ok": True, "sheets": []})
                return
            try:
                self._json({"ok": True, "sheets": state.cli().list_sheets(target)})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "message": str(exc)})
            return

        if path in ("/api/preview", "/api/apply"):
            paths = [str(p) for p in (data.get("paths") or [])]
            if not paths:
                self._json({"ok": False, "message": "请先添加文件"})
                return
            if not state.cli_info and not discover(state.settings.cli_path or None):
                self._json({"ok": False, "message": "未找到 office-cli，请先在设置中配置"})
                return
            try:
                rule = build_rule(data.get("rule") or {})
            except RuleError as exc:
                self._json({"ok": False, "message": str(exc)})
                return
            scope = build_scope(data.get("scope") or {})
            mode = "preview" if path == "/api/preview" else "apply"
            job = Job(id=uuid.uuid4().hex[:12], mode=mode, total=len(paths))
            with state.jobs_lock:
                # 只保留最近 20 个任务，避免长时间运行累积内存
                if len(state.jobs) > 20:
                    for old in list(state.jobs)[: len(state.jobs) - 19]:
                        state.jobs.pop(old, None)
                state.jobs[job.id] = job
            target_fn = run_preview if mode == "preview" else run_apply
            threading.Thread(
                target=target_fn,
                args=(state, job, paths, rule, scope),
                daemon=True,
            ).start()
            self._json({"ok": True, "job_id": job.id})
            return

        if path == "/api/cancel":
            with state.jobs_lock:
                job = state.jobs.get(str(data.get("id") or ""))
            if job:
                job.cancel.set()
                job.log("warn", "收到取消请求，正在停止…")
            self._json({"ok": True})
            return

        if path == "/api/undo":
            with state.settings_lock:
                root = state.settings.backup_root
            run_dir = engine.latest_run(root)
            if not run_dir:
                self._json({"ok": False, "message": "没有可撤销的备份"})
                return
            rows = engine.restore_run(run_dir)
            restored = sum(1 for _p, ok, _m in rows if ok)
            failed = [f"{Path(p).name}：{m}" for p, ok, m in rows if not ok]
            self._json(
                {
                    "ok": True,
                    "restored": restored,
                    "failed": failed,
                    "message": f"已还原 {restored} 个文件" + (f"，{len(failed)} 个失败" if failed else ""),
                }
            )
            return

        if path in ("/api/reveal", "/api/open-folder", "/api/open-file"):
            target = str(data.get("path") or "")
            try:
                if path == "/api/reveal":
                    message = reveal.reveal(target)
                elif path == "/api/open-folder":
                    message = reveal.open_folder(target)
                else:
                    message = reveal.open_file(target)
                self._json({"ok": True, "message": message})
            except (reveal.RevealError, OSError) as exc:
                self._json({"ok": False, "message": str(exc)})
            return

        if path == "/api/clipboard":
            state.bridge.set_clipboard(str(data.get("text") or ""))
            self._json({"ok": True})
            return

        self._json({"ok": False, "message": "未知接口"}, 404)


def make_server(dist: Path, bridge) -> ThreadingHTTPServer:
    """在 127.0.0.1 的随机端口启动服务，返回已就绪的 server 对象。"""
    state = ApiState(dist, bridge)

    class BoundHandler(ApiHandler):
        pass

    BoundHandler.state = state
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), BoundHandler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
