"""在文件管理器中定位文件 / 打开目录 / 用默认程序打开。

Windows 优先用 Shell COM 的 ``SHOpenFolderAndSelectItems``：它能真正"选中"文件，
且不经过 shell 字符串拼接，路径里有引号、空格、中文都安全。
COM 不可用时再退回 ``explorer /select``，最后退回打开所在目录。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class RevealError(RuntimeError):
    pass


def _check(path: str, *, must_exist: bool = True) -> Path:
    target = Path(path)
    if not path:
        raise RevealError("路径为空")
    if must_exist and not target.exists():
        raise RevealError("文件不存在或已被移动：" + path)
    return target


def _windows_select(target: Path) -> bool:
    """返回 True 表示已成功交给 Shell 处理。"""
    try:
        import ctypes
        from ctypes import POINTER, byref, c_int, c_uint, c_void_p, c_wchar_p

        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        shell32.SHParseDisplayName.argtypes = [
            c_wchar_p,
            c_void_p,
            POINTER(c_void_p),
            c_uint,
            POINTER(c_uint),
        ]
        shell32.SHParseDisplayName.restype = c_int
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            c_void_p,
            c_uint,
            c_void_p,
            c_uint,
        ]
        shell32.SHOpenFolderAndSelectItems.restype = c_int
        ole32.CoInitialize(None)

        pidl = c_void_p()
        out = c_uint(0)
        hr = shell32.SHParseDisplayName(
            str(target), None, byref(pidl), 0, byref(out)
        )
        if hr != 0 or not pidl:
            return False
        try:
            # cidl=0 且 apidl=NULL 时，pidl 本身就是要选中的对象。
            return shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0
        finally:
            ole32.CoTaskMemFree(pidl)
    except Exception:  # noqa: BLE001 - COM 相关失败一律走降级路径
        return False


def reveal(path: str) -> str:
    """在文件管理器中显示并选中文件。"""
    target = _check(path)
    if sys.platform == "win32":
        if _windows_select(target):
            return "已在资源管理器中选中文件"
        try:
            subprocess.Popen(
                ["explorer", f"/select,{target}"],
                close_fds=True,
                creationflags=0x08000000,
            )
            return "已在资源管理器中选中文件"
        except OSError:
            pass
        return open_folder(str(target.parent))
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)], close_fds=True)
        return "已在 Finder 中显示文件"
    # Linux：优先 D-Bus 的 org.freedesktop.FileManager1.ShowItems
    try:
        subprocess.Popen(
            [
                "dbus-send",
                "--session",
                "--dest=org.freedesktop.FileManager1",
                "--type=method_call",
                "/org/freedesktop/FileManager1",
                "org.freedesktop.FileManager1.ShowItems",
                f"array:string:file://{target}",
                "string:",
            ],
            close_fds=True,
        )
        return "已在文件管理器中显示文件"
    except OSError:
        return open_folder(str(target.parent))


def open_folder(path: str) -> str:
    """打开所在目录（path 可以是文件，也可以是目录）。"""
    target = _check(path)
    folder = target if target.is_dir() else target.parent
    folder = _check(str(folder))
    if sys.platform == "win32":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", str(folder)], close_fds=True)
    return "已打开所在文件夹"


def open_file(path: str) -> str:
    """用系统默认程序打开文件本身（只用于用户主动点击，不自动执行）。"""
    target = _check(path)
    if not target.is_file():
        raise RevealError("不是文件：" + path)
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", str(target)], close_fds=True)
    return "已用默认程序打开"


def backup_folder(path: str) -> str:
    """返回备份目录路径（供「打开备份位置」使用）。"""
    return str(Path(path).parent) if path else ""
