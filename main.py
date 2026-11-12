"""程序入口：只启动 2.0 版 shadcn/ui 界面。

* 双击 ``run.pyw``：无控制台窗口（推荐）
* 命令行：``python main.py`` / ``python -m app``
* ``--devtools``：开启 Chromium 远程调试端口 9223

1.0 的 Qt Widgets 界面仅作为开发回退保留在 ``app/main_entry.py``，
不再由本入口或任何启动脚本调用，避免误开旧版窗口。
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):  # 直接执行 main.py 时，把项目根目录加入 sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))

ARGS = set(sys.argv[1:])


def _log_error(text: str) -> None:
    """pythonw 下没有控制台，异常必须落盘，绝不弹额外窗口。"""
    try:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        folder = Path(base) / "OfficeTextReplacer"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "launcher.log").open("a", encoding="utf-8") as handle:
            handle.write("[main.py] " + text.rstrip() + "\n")
        (Path(__file__).resolve().parent / "启动失败.txt").write_text(
            "启动失败，请把下面的信息发给开发者：\n\n" + text,
            encoding="utf-8",
        )
    except OSError:
        pass


try:
    from app.web_main import main
except ModuleNotFoundError as exc:
    missing = exc.name or "依赖"
    _log_error(
        f"缺少依赖：{missing}\n"
        "请先执行：python -m pip install -r requirements.txt\n"
        "替换引擎另需：npm install -g @officecli/officecli"
    )
    raise SystemExit(1)
except BaseException:
    _log_error(traceback.format_exc())
    raise SystemExit(1)

if __name__ == "__main__":
    try:
        raise SystemExit(main(devtools="--devtools" in ARGS))
    except SystemExit:
        raise
    except BaseException:
        _log_error(traceback.format_exc())
        raise SystemExit(1)
