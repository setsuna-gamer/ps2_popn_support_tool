"""プレー画面から読み取った曲情報 (PS2 版は読まないので常に空)"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlaySongInfo:
    """プレー画面から読み取った曲情報。読めなかった項目は空文字。"""
    text: str = ""         # OCR で読んだ曲名 (未照合)
    difficulty: str = ""   # 難易度区分
