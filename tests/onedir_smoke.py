"""目录版（onedir）烟测：复制到独立中文路径后启动，检查窗口与便携数据目录。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

if os.name != "nt":
    raise SystemExit("此脚本仅用于 Windows")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dist" / "OfficeTextReplacer-2.0.0-win64"
user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
CONSOLES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow"}


def windows() -> list[tuple[int, int, str, str]]:
    found: list[tuple[int, int, str, str]] = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, len(title))
        user32.GetClassNameW(hwnd, cls, len(cls))
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append((hwnd, pid.value, cls.value, title.value))
        return True

    user32.EnumWindows(EnumProc(callback), 0)
    return found


def close_apps() -> None:
    for hwnd, _pid, _cls, title in windows():
        if "Office 文字替换器" in title:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)


def main() -> int:
    if not (SRC / "OfficeTextReplacer.exe").is_file():
        raise FileNotFoundError(SRC / "OfficeTextReplacer.exe")

    with tempfile.TemporaryDirectory(prefix="otr onedir test ") as tmp:
        target = Path(tmp) / "Moved App 中文路径"
        shutil.copytree(SRC, target)
        exe = target / "OfficeTextReplacer.exe"
        print("COPIED_TO:", target)
        print("TOTAL_MB:", round(sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / 1048576, 1))

        close_apps()
        time.sleep(1)
        process = subprocess.Popen([str(exe)], cwd=str(target), creationflags=0x08000000)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise AssertionError(f"进程提前退出，退出码 {process.returncode}")
                if any("Office 文字替换器" in x[3] for x in windows()):
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("等待主窗口超时")
            time.sleep(2)
            current = windows()
            apps = [x for x in current if "Office 文字替换器" in x[3]]
            consoles = [x for x in current if x[2] in CONSOLES and x[1] == process.pid]
            data_dir = target / "OfficeTextReplacer-data"
            print("WINDOW_TITLE:", apps[0][3] if apps else "<none>")
            print("WINDOW_COUNT:", len(apps))
            print("CONSOLE_COUNT:", len(consoles))
            print("PORTABLE_DATA:", data_dir, "exists=", data_dir.is_dir())
            assert len(apps) == 1, f"主窗口数异常: {apps}"
            assert not consoles, f"检测到控制台窗口: {consoles}"
            assert data_dir.is_dir(), "未在程序目录创建便携数据目录"
            print("PASS: 目录版在独立中文路径启动，主窗口唯一、无控制台、配置写在程序目录")
        finally:
            close_apps()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
