"""CLAUDE.md を AGENT.md に、CLAUDE.local.md を AGENT.local.md にコピーして、内容をそろえる (開発者用)

    python tools/sync_agent_md.py [--check]

編集するのは CLAUDE.md / CLAUDE.local.md だけ。--check は書き換えずに、ずれていれば終了コード 1 を返す。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = (("CLAUDE.md", "AGENT.md"), ("CLAUDE.local.md", "AGENT.local.md"))


def main() -> int:
    check = "--check" in sys.argv[1:]
    bad = 0
    for src, dst in PAIRS:
        s, d = ROOT / src, ROOT / dst
        if not s.exists():
            continue
        if d.exists() and d.read_bytes() == s.read_bytes():
            continue
        if check:
            print(f"{dst} が {src} と違います")
            bad = 1
        else:
            d.write_bytes(s.read_bytes())
            print(f"{src} -> {dst}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
