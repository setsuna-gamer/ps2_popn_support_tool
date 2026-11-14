"""CLAUDE.md と AGENT.md (ローカル用も) が同一内容であることを確認する。ずれたら tools/sync_agent_md.py を実行する"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("src,dst", [("CLAUDE.md", "AGENT.md"), ("CLAUDE.local.md", "AGENT.local.md")])
def test_same_content(src, dst):
    s, d = ROOT / src, ROOT / dst
    if not s.exists() and not d.exists():
        pytest.skip("ローカル用ファイルが無い")
    assert s.exists() and d.exists(), f"{src} と {dst} は両方そろえる (python tools/sync_agent_md.py)"
    assert s.read_bytes() == d.read_bytes(), f"{dst} が {src} と違う (python tools/sync_agent_md.py)"
