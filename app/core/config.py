"""本地配置与目录约定（不写注册表，全部放在用户的 LocalAppData 下）。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "OfficeTextReplacer"
APP_TITLE = "Office 文字替换器"
APP_SUBTITLE = "基于 office-cli · 支持 Word / Excel / PowerPoint"


def app_data_dir() -> Path:
    """绿色版仅在 EXE 所在目录写配置/备份；源码运行仍沿用 LocalAppData。"""
    if getattr(sys, "frozen", False):
        path = Path(sys.executable).resolve().parent / "OfficeTextReplacer-data"
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def default_backup_root() -> str:
    return str(app_data_dir() / "backups")


def wallpaper_dir() -> Path:
    """仅在浏览器环境（无原生对话框）下，把用户选的图片复制到这里保存。"""
    path = app_data_dir() / "wallpapers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def prune_wallpapers(keep: str = "", limit: int = 8) -> None:
    """清理浏览器上传留下的旧图片，只保留最近若干张与当前正在使用的那张。"""
    try:
        items = [p for p in wallpaper_dir().iterdir() if p.is_file()]
    except OSError:
        return
    keep_path = Path(keep) if keep else None
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for index, item in enumerate(items):
        if keep_path is not None and item.name == keep_path.name:
            continue
        if index < limit:
            continue
        try:
            item.unlink()
        except OSError:
            pass


WALLPAPER_SOURCES = ("none", "preset", "custom")
WALLPAPER_MAX_BLUR = 40
# 功能面板（卡片）不透明度下限：低于此值小字会被壁纸吃掉，失去工具意义
PANEL_OPACITY_MIN = 45
PANEL_OPACITY_MAX = 100
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif"}


def _clamp_int(value, low: int, high: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def normalize_wallpaper(
    source: str, wallpaper_id: str, path: str, blur: int, panel_opacity: int = 100
) -> tuple[str, str, str, int, int]:
    """把前端传来的壁纸设置收敛到安全取值，避免写坏的配置影响启动。"""
    source = source if source in WALLPAPER_SOURCES else "none"
    wallpaper_id = str(wallpaper_id or "").strip()
    path = str(path or "").strip()
    blur = _clamp_int(blur, 0, WALLPAPER_MAX_BLUR, 0)
    panel_opacity = _clamp_int(
        panel_opacity, PANEL_OPACITY_MIN, PANEL_OPACITY_MAX, PANEL_OPACITY_MAX
    )
    if source == "preset" and not wallpaper_id:
        source = "none"
    if source == "custom" and not path:
        source = "none"
    return source, wallpaper_id, path, blur, panel_opacity


def wallpaper_available(path: str) -> bool:
    if not path:
        return False
    target = Path(path)
    try:
        return target.is_file() and target.suffix.lower() in IMAGE_EXT
    except OSError:
        return False


@dataclass
class Settings:
    cli_path: str = ""
    keep_backup: bool = True
    verify_after: bool = True
    backup_root: str = field(default_factory=default_backup_root)
    last_dir: str = ""
    recursive_scan: bool = True
    max_files: int = 500
    theme: str = "dark"      # light | dark
    accent: str = "blue"     # zinc | blue | violet | emerald | rose | amber

    # 背景壁纸：与主题一起保存，独立于 theme / accent 生效
    wallpaper_source: str = "none"  # none | preset | custom
    wallpaper_id: str = ""          # 预设 id，见 web/src/lib/api.ts
    wallpaper_path: str = ""        # 自定义图片的绝对路径
    wallpaper_blur: int = 0         # 0-40，0 表示无虚化
    wallpaper_panel_opacity: int = 100  # 30-100，功能面板（卡片）不透明度

    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        settings = cls()
        for key, value in (raw or {}).items():
            if hasattr(settings, key) and isinstance(value, type(getattr(settings, key))):
                setattr(settings, key, value)
            elif hasattr(settings, key) and getattr(settings, key) is None:
                setattr(settings, key, value)
        if not settings.backup_root:
            settings.backup_root = default_backup_root()
        elif getattr(sys, "frozen", False):
            # 旧目录迁移后，默认备份路径应跟着 EXE 所在位置走；手动自定义路径保留。
            previous = Path(settings.backup_root)
            if previous.name.lower() == "backups" and previous.parent.name.lower() == "officetextreplacer-data":
                settings.backup_root = default_backup_root()
        settings.wallpaper_panel_opacity = _clamp_int(
            settings.wallpaper_panel_opacity,
            PANEL_OPACITY_MIN,
            PANEL_OPACITY_MAX,
            PANEL_OPACITY_MAX,
        )
        return settings

    def save(self) -> None:
        try:
            config_path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
