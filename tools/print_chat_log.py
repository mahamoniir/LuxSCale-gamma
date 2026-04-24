"""
Print recent chat audit lines (JSON) from ``logs/chat/chat_YYYY_Www.log``.

Run from project root (same as app.py):
  py tools/print_chat_log.py
  py tools/print_chat_log.py --lines 500
  py tools/print_chat_log.py --file logs/chat/chat_2026_W17.log
"""
from __future__ import annotations

import argparse
import os
import sys

# project root = parent of tools/
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    p = argparse.ArgumentParser(description="Print LuxScaleAI weekly chat file log tail.")
    p.add_argument("--lines", type=int, default=200, help="Lines from end (default 200).")
    p.add_argument(
        "--file",
        type=str,
        default="",
        help="Explicit log file path. Default: current ISO week file under logs/chat/.",
    )
    args = p.parse_args()

    if args.file:
        path = args.file
        if not os.path.isabs(path):
            path = os.path.join(_ROOT, path)
    else:
        from luxscale.chat_file_log import current_weekly_log_path

        path = current_weekly_log_path()

    if not os.path.isfile(path):
        print(f"(no file yet: {path})\n", file=sys.stderr)
        return

    from luxscale.chat_file_log import list_chat_log_files, read_chat_log_tail

    if args.file:
        out = read_chat_log_tail(path, max_lines=args.lines)
    else:
        # If current week is empty, show the most recent file that has data
        out = read_chat_log_tail(path, max_lines=args.lines)
        if not out.strip():
            for f in list_chat_log_files()[:3]:
                out = read_chat_log_tail(f, max_lines=args.lines)
                if out.strip():
                    print(f"# {f}\n", file=sys.stderr)
                    break

    if not out.strip():
        print("(log empty)", file=sys.stderr)
        return

    print(out, end="")


if __name__ == "__main__":
    main()
