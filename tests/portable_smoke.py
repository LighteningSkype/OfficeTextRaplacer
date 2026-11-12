"""便携单 EXE 的独立目录烟测（需 Windows，测试后自动关闭测试进程）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

if os.name != "nt":
    raise SystemExit("此脚本仅用于 Windows")

import ctypes
import ctypes.wintypes as w

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "OfficeTextReplacer.exe"
user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
CONSOLES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow"}


def windows():
    result = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, len(title))
        user32.GetClassNameW(hwnd, cls, len(cls))
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        result.append((hwnd, pid.value, cls.value, title.value))
        return True

    user32.EnumWindows(EnumProc(callback), 0)
    return result


def check_in_directory(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / EXE.name
    shutil.copy2(EXE, target)
    process = subprocess.Popen([str(target)], cwd=str(folder), creationflags=0x08000000)
    try:
        for _ in range(80):
            current = windows()
            matches = [x for x in current if "Office 文字替换器" in x[3]]
            if matches:
                break
            if process.poll() is not None:
                raise AssertionError(f"EXE 提前退出，退出码 {process.returncode}")
            time.sleep(0.5)
        else:
            raise AssertionError("等待主窗口超时")
        time.sleep(2)
        current = windows()
        matches = [x for x in current if "Office 文字替换器" in x[3]]
        consoles = [x for x in current if x[2] in CONSOLES and x[1] in {process.pid, *(x[1] for x in matches)}]
        assert len(matches) == 1, f"主窗口数异常: {matches}"
        assert not consoles, f"检测到控制台窗口: {consoles}"
        assert (folder / "OfficeTextReplacer-data").is_dir(), "同级便携配置目录未创建"
        print("WINDOW_TITLE:", matches[0][3])
        print("CONSOLE_COUNT:", len(consoles))
        print("PORTABLE_DATA:", folder / "OfficeTextReplacer-data")
        print("EXE_MOVED_TO:", target)
        print("PASS: 单文件在非项目目录启动，主窗口唯一、无控制台、同级保存配置")
    finally:
        for hwnd, _pid, _cls, title in windows():
            if "Office 文字替换器" in title:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)


def main() -> int:
    if not EXE.is_file():
        raise FileNotFoundError(EXE)
    with tempfile.TemporaryDirectory(prefix="otr portable test ") as tmp:
        check_in_directory(Path(tmp) / "Moved App 中文路径")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
