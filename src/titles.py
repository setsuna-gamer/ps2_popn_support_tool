"""PS2 版 pop'n music の作品 (タイトル) の識別子と表示名。

title_id は、画面識別 (src/screen_profiles.json)・曲リストの `titles`・スコア記録の `title_id` で共通に使う。
"""
from __future__ import annotations

TITLE_NAMES: dict[str, str] = {
    "popn7": "pop'n music 7",
    "popn8": "pop'n music 8",
    "popn9": "pop'n music 9",
    "popn10": "pop'n music 10",
    "popn11": "pop'n music 11",
    "popn12": "pop'n music 12 いろは",
    "popn13": "pop'n music 13 カーニバル",
    "popn14": "pop'n music 14 FEVER!",
    "besthits": "pop'n music best hits!",
}

# 一覧表示用の短い名前
TITLE_SHORT_NAMES: dict[str, str] = {
    "popn7": "7", "popn8": "8", "popn9": "9", "popn10": "10", "popn11": "11",
    "popn12": "12", "popn13": "13", "popn14": "14", "besthits": "best hits!",
}


def title_name(title_id: str) -> str:
    """作品の表示名。未知の title_id (将来の作品など) はそのまま返す。"""
    return TITLE_NAMES.get(title_id, title_id)


def title_short_name(title_id: str) -> str:
    return TITLE_SHORT_NAMES.get(title_id, title_id)
