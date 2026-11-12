"""``python -m app``：与 ``python main.py`` 一致，只启动 2.0 版界面。"""

from __future__ import annotations

import sys

from .web_main import main

raise SystemExit(main(devtools="--devtools" in sys.argv[1:]))
