"""PS2 版 pop'n music のリザルト画面・プレー画面の数字の読み取り

位置は `src/ps2_layouts.py`、文字の読み取りは `src/ps2_numbers.py`。ここは項目をまとめて読み、
読み誤りを弾く (つじつまが合わない値は None にする)。

テンプレート (`src/ps2_digit_templates.json`) に 0～9 のすべてが揃っていない作品・画面は、見本に無い数字を別の数字に
取り違える恐れがあるので、読まない (None)。足りない数字は `missing_digits` で分かる。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PIL import Image

from src.ps2_layouts import JUDGE_FIELDS, RESULT_FIELDS, fields, fixed_digits, split_ratio
from src.ps2_numbers import DigitTemplates, read_digits

ALL_DIGITS = "0123456789"


@lru_cache(maxsize=1)
def default_templates() -> DigitTemplates:
    return DigitTemplates.load()


def missing_digits(title: str, screen: str, templates: DigitTemplates | None = None) -> str:
    """テンプレートに無い数字 (例: "69")。作品・画面が未対応なら "0123456789"。"""
    tpl = templates or default_templates()
    have = tpl.digits(title, screen)
    return "".join(d for d in ALL_DIGITS if d not in have)


def supported(title: str, screen: str, templates: DigitTemplates | None = None) -> bool:
    """その作品・画面の数字を読めるか (位置が登録済みで、テンプレートに 0～9 が揃っている)。"""
    return bool(fields(title, screen)) and not missing_digits(title, screen, templates)


def _to_int(text: str | None) -> int | None:
    return int(text) if text else None


@dataclass
class ResultValues:
    """リザルト画面の値。"""
    cool: int
    great: int
    good: int
    bad: int
    combo: int
    stage_score: int
    total_score: int

    @property
    def notes(self) -> int:
        return self.cool + self.great + self.good + self.bad

    def consistent(self) -> bool:
        """つじつまが合うか。コンボは総ノーツ数を超えず、累計スコアは今回のスコア以上。"""
        return self.combo <= self.notes and self.total_score >= self.stage_score


def read_result(image: Image.Image, title: str, templates: DigitTemplates | None = None) -> ResultValues | None:
    """リザルト画面の値を読む。未対応の作品・読めない項目・つじつまが合わない値は None。"""
    tpl = templates or default_templates()
    if not supported(title, "result", tpl):
        return None
    values = {}
    for name, box in fields(title, "result").items():
        v = _to_int(read_digits(image, box, title, "result", tpl, split_ratio(title, "result"), fixed_digits(title, "result")))
        if v is None:
            return None
        values[name] = v
    result = ResultValues(**{k: values[k] for k in RESULT_FIELDS})
    return result if result.consistent() else None


@dataclass
class PlayValues:
    """プレー画面の値 (判定の累計とスコア・コンボ)。読めなかった項目は None。"""
    cool: int | None = None
    great: int | None = None
    good: int | None = None
    bad: int | None = None
    score: int | None = None
    combo: int | None = None


def read_play(image: Image.Image, title: str, templates: DigitTemplates | None = None) -> PlayValues | None:
    """プレー画面の判定の累計・スコア・コンボを読む。未対応の作品なら None。読めなかった項目は None のまま。"""
    tpl = templates or default_templates()
    if not supported(title, "play", tpl):
        return None
    out = PlayValues()
    for name, box in fields(title, "play").items():
        if name in JUDGE_FIELDS or name in ("score", "combo"):
            setattr(out, name, _to_int(read_digits(image, box, title, "play", tpl, split_ratio(title, "play"), fixed_digits(title, "play"))))
    return out
