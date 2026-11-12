"""无控制台启动入口：双击本文件即可，只启动 2.0 版 shadcn/ui 界面。

.pyw 由 Windows 关联到 pythonw.exe（GUI 子系统），双击不会创建命令行窗口。
但 pyw.exe 可能挑到没装 PySide6 的解释器，所以这里做一次静默引导：
找不到依赖时，自动在 PATH / 项目 venv / 常见安装目录中挑选一个带
PySide6 的 pythonw.exe，重新拉起 main.py，随后自己退出。全程无窗口。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
MAIN = APP_DIR / "main.py"
CREATE_NO_WINDOW = 0x08000000

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / "OfficeTextReplacer"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def log(message: str) -> None:
    try:
        with (log_dir() / "launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{message}\n")
    except OSError:
        pass


def has_gui_stack() -> bool:
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def probe(python_exe: Path) -> bool:
    """用目标解释器验证依赖，隐藏窗口、短超时。"""
    code = "import PySide6, PySide6.QtWebEngineWidgets"
    try:
        result = subprocess.run(
            [str(python_exe), "-c", code],
            capture_output=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def last_good() -> Path | None:
    """上次成功启动用的解释器，优先复用，避免每次按 PATH 顺序换环境。"""
    try:
        lines = (log_dir() / "launcher.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith("LAUNCH "):
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                candidate = Path(parts[1])
                if candidate.is_file():
                    return candidate
    return None


def interpreter_candidates() -> list[Path]:
    out: list[Path] = []
    previous = last_good()
    if previous is not None:
        out.append(previous)
    configured = os.environ.get("OTR_PYTHONW")
    if configured:
        out.append(Path(configured))
    for name in (".venv", "venv"):
        out.append(APP_DIR / name / "Scripts" / "pythonw.exe")
    for item in os.environ.get("PATH", "").split(os.pathsep):
        item = item.strip().strip('"')
        if item:
            out.append(Path(item) / "pythonw.exe")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        root = Path(local) / "Programs" / "Python"
        if root.is_dir():
            for folder in sorted(root.iterdir(), reverse=True):
                out.append(folder / "pythonw.exe")
    for version in range(39, 30, -1):
        out.append(Path(f"C:/Python{version}/pythonw.exe"))
    out.append(Path(sys.executable).with_name("pythonw.exe"))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            unique.append(path)
    return unique


def fail(message: str) -> int:
    """不弹任何窗口，只在项目目录留下可见的排查线索。"""
    log("ERROR " + message)
    try:
        (APP_DIR / "启动失败.txt").write_text(
            "Office 文字替换器启动失败\n\n"
            + message
            + "\n\n请确认已安装 Python 3.10+ 与 PySide6：\n"
            "    python -m pip install -r requirements.txt\n\n"
            "详细日志：%LOCALAPPDATA%\\OfficeTextReplacer\\launcher.log\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return 1


def launch(pythonw: Path) -> int:
    log("LAUNCH " + str(pythonw) + " " + str(MAIN))
    try:
        subprocess.Popen(
            [str(pythonw), str(MAIN)],
            cwd=str(APP_DIR),
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
    except OSError as exc:
        return fail(f"无法启动解释器：{exc}")
    log("OK")
    return 0


def main() -> int:
    if not MAIN.is_file():
        return fail(f"找不到主程序：{MAIN}")
    if not (APP_DIR / "web" / "dist" / "index.html").is_file():
        return fail("界面资源缺失，请先在 web 目录执行 npm install 与 npm run build")

    # 已经由正确的解释器执行：直接进主程序，不额外开进程。
    if has_gui_stack():
        from app.web_main import main as run_app

        return run_app()

    for pythonw in interpreter_candidates():
        python = pythonw.with_name("python.exe")
        if not python.is_file():
            continue
        if probe(python):
            return launch(pythonw)

    return fail("没有找到带 PySide6 的 Python 解释器（已检查 PATH、项目 venv 与常见安装目录）")


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit:
        raise
    except BaseException as exc:  # pythonw 没有控制台，异常必须落盘
        import traceback

        log("CRASH " + traceback.format_exc())
        fail(f"{type(exc).__name__}: {exc}")
        code = 1
    raise SystemExit(code)
