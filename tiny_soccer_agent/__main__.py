"""命令行入口：允许通过 `python -m tiny_soccer_agent` 调用 CLI。"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
