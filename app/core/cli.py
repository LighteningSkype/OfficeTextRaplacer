"""office-cli 的薄封装：进程调用、JSON 解析、错误归一化。

设计要点
--------
* 永远通过参数数组调用（不经过 shell），中文路径与含空格路径都安全。
* 每个子进程都带超时，避免大文件或损坏文件把界面卡死。
* office-cli 会往 stdout 混入警告文字（例如残留会话提示），因此解析 JSON 前
  先裁掉首个 ``{`` 之前的内容。
* 批量命令一律走 ``--input <file>``：Windows 命令行长度上限约 32K，
  直接把 JSON 塞进 ``--commands`` 会在文档较大时触发 WinError 206。
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DEFAULT_TIMEOUT = 240
BATCH_TIMEOUT = 900


class CliError(RuntimeError):
    """office-cli 返回的业务错误。"""

    def __init__(self, message: str, code: str | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code or ""
        self.detail = detail

    def friendly(self) -> str:
        return friendly_message(self.code, self.message)


class CliNotFound(RuntimeError):
    pass


@dataclass
class CliInfo:
    path: str
    version: str
    origin: str


@dataclass
class BatchItemResult:
    index: int
    success: bool
    output: str = ""
    error: str = ""
    matched: int = 0


@dataclass
class CliResponse:
    data: object = None
    message: str = ""
    raw: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- 定位


def _vendor_from_launcher(launcher: str) -> str | None:
    """npm 生成的 officecli / officecli.cmd 只是转发脚本，优先找到真正的二进制。"""
    base = Path(launcher).resolve().parent
    for rel in (
        ("node_modules", "@officecli", "officecli", "vendor", "officecli.exe"),
        ("node_modules", "@officecli", "officecli", "vendor", "officecli"),
    ):
        candidate = base.joinpath(*rel)
        if candidate.is_file():
            return str(candidate)
    # 有些安装把 vendor 目录放在包根目录的同级
    sibling = base / "vendor" / "officecli.exe"
    if sibling.is_file():
        return str(sibling)
    return None


def _candidate_paths(configured: str | None) -> list[tuple[str, str]]:
    """返回 (路径, 来源说明) 候选列表。"""
    out: list[tuple[str, str]] = []

    def add(path: str | None, origin: str) -> None:
        if path and path not in [p for p, _ in out]:
            out.append((path, origin))

    # 单文件 EXE 自带 office-cli；优先于旧配置和系统 PATH，保证移动目录后仍完整可用。
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", "")) / "vendor" / "officecli.exe"
        if bundled.is_file():
            add(str(bundled), "内置便携引擎")

    if configured:
        cfg = Path(configured)
        if cfg.is_dir():
            for name in ("officecli.exe", "officecli"):
                if (cfg / name).is_file():
                    add(str(cfg / name), "设置")
                    break
        else:
            add(str(cfg), "设置")

    for env_name in ("OFFICECLI_BIN", "OFFICECLI_PATH"):
        value = os.environ.get(env_name)
        if value:
            add(value, env_name)

    for which_name in ("officecli.exe", "officecli"):
        found = shutil.which(which_name)
        if found:
            vendor = _vendor_from_launcher(found)
            if vendor:
                add(vendor, "PATH")
            else:
                add(found, "PATH")

    home = Path.home()
    roaming = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
    local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
    globs = [
        (str(Path(roaming) / "npm" / "node_modules" / "@officecli" / "officecli" / "vendor" / "officecli.exe"), "npm 全局"),
        (str(Path(local) / "npm" / "node_modules" / "@officecli" / "officecli" / "vendor" / "officecli.exe"), "npm 全局"),
        (str(Path("C:/Program Files/nodejs/node_modules/@officecli/officecli/vendor/officecli.exe")), "npm 全局"),
        (str(home / "scoop" / "apps" / "officecli" / "current" / "officecli.exe"), "scoop"),
    ]
    for path, origin in globs:
        if Path(path).is_file():
            add(path, origin)

    # WorkBuddy / 便携 Node 发行版：<root>/node_modules/@officecli/officecli/vendor/officecli.exe
    for root in (
        home / ".workbuddy" / "binaries" / "node" / "versions",
        Path(local) / "Programs",
    ):
        pattern = str(root / "*" / "node_modules" / "@officecli" / "officecli" / "vendor" / "officecli.exe")
        for path in sorted(glob.glob(pattern), reverse=True):
            add(path, "便携 Node")

    return out


def discover(configured: str | None = None, probe: bool = True) -> CliInfo | None:
    """搜寻可用的 office-cli，返回版本信息；找不到返回 None。"""
    for path, origin in _candidate_paths(configured):
        if not Path(path).is_file():
            continue
        if not probe:
            return CliInfo(path=path, version="", origin=origin)
        version = probe_version(path)
        if version:
            return CliInfo(path=path, version=version, origin=origin)
    return None


def probe_version(exe: str, timeout: float = 20) -> str | None:
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or proc.stderr or "").strip().splitlines()
    if proc.returncode == 0 and text:
        return text[0].strip()
    return None


# --------------------------------------------------------------------------- 调用


class OfficeCli:
    def __init__(self, info: CliInfo) -> None:
        self.info = info
        self.path = info.path
        # office-cli 默认会把文档留在后台驻留进程里，这会一直握着文件句柄，
        # 导致我们最后的 os.replace 原子替换失败（"另一个程序正在使用此文件"）。
        # 关掉自动驻留后，进程读完即释放句柄，替换才能原子完成。
        self._env = os.environ.copy()
        self._env["OFFICECLI_NO_AUTO_RESIDENT"] = "1"
        self._env.setdefault("DOTNET_CLI_UI_LANGUAGE", "en")

    # -- 低层 ---------------------------------------------------------------

    def _exec(self, args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.path, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_CREATE_NO_WINDOW,
                env=self._env,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliError(
                f"office-cli 响应超时（超过 {int(timeout)} 秒）。文件可能过大，或正被其他程序占用。",
                code="timeout",
            ) from exc
        except FileNotFoundError as exc:
            raise CliError(
                "找不到 office-cli 可执行文件，请到「设置」中重新指定路径。", code="cli_missing"
            ) from exc
        except OSError as exc:
            raise CliError(f"无法启动 office-cli：{exc}", code="cli_start_failed") from exc

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def run(self, args: list[str], timeout: float = DEFAULT_TIMEOUT) -> CliResponse:
        payload = self._call(args, timeout)
        if payload.get("success") is False:
            raise CliError(*_payload_error(payload))
        return CliResponse(
            data=payload.get("data"),
            message=str(payload.get("message") or ""),
            raw=payload,
        )

    def _call(self, args: list[str], timeout: float) -> dict:
        proc = self._exec(args, timeout)
        payload = self._extract_json(proc.stdout or "")
        if payload is None:
            payload = self._extract_json(proc.stderr or "")
        if payload is None:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise CliError(
                detail.splitlines()[0] if detail else f"office-cli 执行失败（退出码 {proc.returncode}）",
                code="no_output",
                detail=detail,
            )
        return payload

    # -- 高层 ---------------------------------------------------------------

    def query(self, file: str, selector: str, timeout: float = DEFAULT_TIMEOUT) -> list[dict]:
        resp = self.run(["query", file, selector, "--json"], timeout=timeout)
        data = resp.data
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list):
                return [r for r in results if isinstance(r, dict)]
            return []
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return []

    def batch(self, file: str, commands: list[dict], timeout: float = BATCH_TIMEOUT) -> list[BatchItemResult]:
        """通过输入文件执行批量命令（规避 Windows 命令行长度上限）。

        批量接口即使整体 ``success=false`` 也会带回逐项结果，因此这里不抛异常，
        由调用方根据每项 success/error 决定如何提示。
        """
        if not commands:
            return []
        tmp_dir = Path(tempfile.mkdtemp(prefix="otr-batch-"))
        payload_path = tmp_dir / "commands.json"
        try:
            payload_path.write_text(
                json.dumps(commands, ensure_ascii=False), encoding="utf-8"
            )
            payload = self._call(
                ["batch", file, "--input", str(payload_path), "--json"], timeout
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            # 整批都没跑起来：把顶层错误抛出去
            raise CliError(*_payload_error(payload))
        out: list[BatchItemResult] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            output = str(item.get("output") or "")
            error = item.get("error")
            if isinstance(error, dict):
                error_text = str(error.get("error") or "")
            else:
                error_text = str(error or "")
            out.append(
                BatchItemResult(
                    index=int(item.get("index") if item.get("index") is not None else len(out)),
                    success=bool(item.get("success")),
                    output=output,
                    error=error_text,
                    matched=parse_matched(output),
                )
            )
        return out

    def validate(self, file: str, timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, str]:
        try:
            resp = self.run(["validate", file, "--json"], timeout=timeout)
        except CliError as exc:
            return False, exc.message
        text = resp.data if isinstance(resp.data, str) else (resp.message or "校验通过")
        # run() 只有在 success=true 时才返回，所以能走到这里就说明没有结构性错误。
        return True, text

    def list_sheets(self, file: str, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
        rows = self.query(file, "sheet", timeout=timeout)
        names: list[str] = []
        for row in rows:
            path = str(row.get("path") or "")
            if path.startswith("/") and len(path) > 1:
                names.append(path[1:])
        return names

    def close(self, file: str) -> None:
        """尽力关闭驻留会话，失败不抛异常。"""
        try:
            self._exec(["close", file], timeout=30)
        except CliError:
            pass


_MATCHED_RE = re.compile(r"\((\d+)\s+matched\)")


def _payload_error(payload: dict) -> tuple[str, str, str]:
    """把 office-cli 的错误载荷整理成 (message, code, detail)。"""
    err = payload.get("error")
    if isinstance(err, dict):
        return (
            str(err.get("error") or "office-cli 返回错误"),
            str(err.get("code") or ""),
            str(err.get("suggestion") or ""),
        )
    if isinstance(err, str) and err:
        return err, "", ""
    data = payload.get("data")
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and not item.get("success"):
                    code = str(item.get("code") or "")
                    message = str(item.get("error") or "批量命令执行失败")
                    return message, code, ""
    return str(payload.get("message") or "office-cli 返回错误"), "", ""


def parse_matched(output: str) -> int:
    """从 "Updated /body/p[3]: find=x, replace=y (2 matched)" 里取出命中数。"""
    match = _MATCHED_RE.search(output or "")
    return int(match.group(1)) if match else 0


_FRIENDLY: dict[str, str] = {
    "corrupt_file": "文件已损坏，或不是有效的 Office 文档",
    "invalid_value": "参数或正则表达式无效",
    "not_found": "文档结构已变化，目标元素不存在",
    "file_locked": "文件正被其他程序占用（例如已在 Office 中打开）",
    "permission_denied": "没有访问权限",
    "access_denied": "没有访问权限",
    "password_protected": "文档已加密，无法处理",
    "unsupported_format": "不支持的文件格式",
    "timeout": "office-cli 响应超时",
    "cli_missing": "未找到 office-cli",
    "no_output": "office-cli 没有返回可解析的结果",
}


def friendly_message(code: str, message: str) -> str:
    base = _FRIENDLY.get(code or "")
    if base and message and base not in message:
        return f"{base}（{message}）"
    return message or base or "未知错误"
