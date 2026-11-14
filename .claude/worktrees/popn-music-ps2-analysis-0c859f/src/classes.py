"""pop'n music Lively 専用データクラス・列挙型定義"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.option_master import OPTION_DEFAULTS, OPTION_KEYS, OPTION_LABELS

# 難易度区分コード (L/N/H/EX) → 曲テーブルのレベル列
DIFFICULTY_LEVEL_COLUMNS = {"L": "easy", "N": "normal", "H": "hyper", "EX": "ex"}

_DIFFICULTY_CODES = {
    "EASY": "L", "LIGHT": "L", "L": "L",
    "NORMAL": "N", "N": "N",
    "HYPER": "H", "H": "H",
    "EX": "EX", "E": "EX",   # 旧データでは "E" と記録されている
}

# 等速のハイスピード。旧データでは "OFF" / "x1.0" と記録されている
_HISPEED_OFF = ("OFF", "1.0", "x1.0")


def difficulty_code(difficulty: str) -> str:
    """難易度区分 (EASY / NORMAL / HYPER / EX など) をコード (L/N/H/EX) にする。

    該当しない文字列は大文字にしてそのまま返す。
    """
    d = str(difficulty).strip().upper()
    return _DIFFICULTY_CODES.get(d, d)


def format_song(title: str, difficulty: str = "", genre: str = "", style: str = "title") -> str:
    """「曲名 [難易度区分コード]」形式の表示用文字列。

    style: 'title'=曲名 / 'genre'=ジャンル名 / 'genre_title'=ジャンル名(曲名)。
    ジャンル名が不明なときは曲名で代用する。
    """
    if not genre:
        name = title
    elif style == "genre":
        name = genre
    elif style == "genre_title":
        name = f"{genre}({title})"
    else:
        name = title
    code = difficulty_code(difficulty)
    return f"{name} [{code}]" if code else name


@dataclass
class PopnJudge:
    """1 曲分の判定内訳"""
    cool: int = 0
    great: int = 0
    good: int = 0
    bad: int = 0

    @property
    def notes(self) -> int:
        """打鍵数 = COOL + GREAT + GOOD（BAD は基本的に見逃しなので含めない）"""
        return self.cool + self.great + self.good


@dataclass(eq=False, repr=False)
class PopnOptions:
    """使用オプション。

    項目 (属性名 = src/option_master.py の OPTION_KEYS) と各項目の選択肢は
    src/option_master.py を参照。
    """
    hispeed: str = OPTION_DEFAULTS["hispeed"]
    popkun: str = OPTION_DEFAULTS["popkun"]
    gauge_type: str = OPTION_DEFAULTS["gauge_type"]
    guide_se: str = OPTION_DEFAULTS["guide_se"]
    random: str = OPTION_DEFAULTS["random"]
    judge_plus: str = OPTION_DEFAULTS["judge_plus"]
    hidden: str = OPTION_DEFAULTS["hidden"]
    sudden: str = OPTION_DEFAULTS["sudden"]
    ojama1: str = OPTION_DEFAULTS["ojama1"]
    ojama2: str = OPTION_DEFAULTS["ojama2"]
    ojama1_zutto: str = OPTION_DEFAULTS["ojama1_zutto"]
    ojama2_zutto: str = OPTION_DEFAULTS["ojama2_zutto"]
    auto: str = OPTION_DEFAULTS["auto"]
    extra: dict = field(default_factory=dict)

    def to_summary(self) -> str:
        """既定値から変更されている項目だけを並べた要約文字列"""
        parts = []
        for key in OPTION_KEYS:
            value = getattr(self, key)
            if not value or value == OPTION_DEFAULTS[key]:
                continue
            if key == "hispeed" and value in _HISPEED_OFF:
                continue
            parts.append(f"{OPTION_LABELS[key]}:{value}")
        parts.extend(f"{k}:{v}" for k, v in self.extra.items() if v)
        return " / ".join(parts) if parts else "NORMAL"

    def to_dict(self) -> dict:
        return {**{key: getattr(self, key) for key in OPTION_KEYS}, "extra": dict(self.extra)}

    @classmethod
    def from_dict(cls, d: dict) -> "PopnOptions":
        if not isinstance(d, dict):
            return cls()
        return cls(
            **{key: d.get(key, OPTION_DEFAULTS[key]) for key in OPTION_KEYS},
            extra=d.get("extra", {}),
        )

    def __repr__(self) -> str:
        return f"PopnOptions({self.to_summary()})"


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_formula(text: str) -> str:
    """表計算ソフトで式として解釈されないよう、式の先頭文字で始まる文字列の頭に ' を付ける。"""
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def unescape_formula(text: str) -> str:
    """escape_formula の逆変換"""
    return text[1:] if text.startswith(tuple("'" + p for p in _FORMULA_PREFIXES)) else text


@dataclass(eq=False)
class PopnScoreRecord:
    """1プレーごとのスコア記録クラス"""
    title: str = "Unknown"
    level: int | str = ""
    difficulty: str = ""
    score: int = 0
    cool: int = 0
    great: int = 0
    good: int = 0
    bad: int = 0
    combo: int = 0
    options: PopnOptions = field(default_factory=PopnOptions)
    timestamp: str = ""
    """プレー日時。省略時は現在時刻"""
    music_id: str = ""
    record_id: int | None = None
    genre: str = ""
    artist: str = ""
    ver: str = ""
    modified: bool = False
    """記録後にスコア内容を手動修正したか"""
    screenshot_file: str = ""
    """リザルトのスクリーンショットのファイル名 (保存先フォルダ内)。保存していなければ空"""
    ocr_title: str = ""
    """プレー画面から OCR で読んだ曲名 (未照合)。曲の誤認識を直したときの学習に使う"""
    title_id: str = ""
    """プレーした作品 (popn7 など。src/titles.py)。曲の収録タイトルとは別。不明なら空"""
    platform: str = ""
    """プレー環境 (real: 実機 / pcsx2 / other。src/play_env.py)。不明なら空"""
    modernize_patch: bool | None = None
    """モダナイズパッチ (COOL 25ms) が有効だったか。不明なら None"""
    failed: bool | None = None
    """クリア失敗 (STAGE FAILED) だったか。クリアなら False。判定できなかった (対応していない作品など) なら None"""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @property
    def clear_type(self) -> str:
        """クリアの種類: "PERFECT" / "FULLCOMBO" / "CLEAR" / "FAILED"。判定できなければ空。

        FAILED = STAGE FAILED。PERFECT = BAD も GOOD も無い、FULLCOMBO = BAD が無い (コンボが切れていない)。
        BAD が無ければゲージは減らないので、失敗の判定が無くても PERFECT / FULLCOMBO は決まる。
        CLEAR は、失敗していないと分かったもの (failed が False) だけ。
        """
        if self.failed:
            return "FAILED"
        if self.total_notes > 0 and self.bad == 0:
            return "PERFECT" if self.good == 0 else "FULLCOMBO"
        return "CLEAR" if self.failed is False else ""

    @property
    def total_notes(self) -> int:
        return self.cool + self.great + self.good + self.bad

    @property
    def difficulty_code(self) -> str:
        """難易度区分コード (L: EASY / N: NORMAL / H: HYPER / EX: EX)"""
        return difficulty_code(self.difficulty)

    def to_csv_row(self) -> list:
        """CSV 1行分のリスト。列順は src/db.py の CSV_HEADERS"""
        return [
            self.level if self.level else "",
            escape_formula(self.title),
            self.difficulty_code,
            self.score,
            self.cool,
            self.great,
            self.good,
            self.bad,
            self.combo,
            *(getattr(self.options, key) for key in OPTION_KEYS),
            self.timestamp,
            self.title_id,
            self.platform,
            "" if self.modernize_patch is None else int(self.modernize_patch),
            "" if self.failed is None else int(self.failed),
            self.music_id,
            int(self.modified),
            self.screenshot_file,
        ]


class DetectMode(Enum):
    """現在の画面状態"""
    unknown          = 0
    select           = 1   # 選曲画面
    play             = 2   # プレー画面
    result           = 3   # リザルト画面
    option           = 4   # オプション画面
    title            = 5   # タイトル画面
    character_select = 7   # キャラクターセレクト画面 (作品による)
    exit             = 8   # 終了画面
    loading          = 9   # ロード画面（画面遷移中）
    mode_select      = 11  # ゲーム / モード選択画面
    freetraining     = 12  # フリートレーニング (スタイル選択・選曲など。独立したモード)


@dataclass
class ResultValues:
    """リザルト画面から読み取った値。読めなかった項目は None。"""
    score: int | None = None
    cool: int | None = None
    great: int | None = None
    good: int | None = None
    bad: int | None = None
    combo: int | None = None
    best: int | None = None
    diff: int | None = None
    score_verified: bool = False   # SCORE が「前回ベスト + 差分」と一致したか
    failed: bool | None = None     # クリア失敗 (STAGE FAILED の表示)。判定できない作品・画面は None (PS2 に Retire は無い)
    new_record: bool = False       # 「NEW RECORD!」の帯が表示されているか
    notes: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """記録に必要な全項目が読めているか"""
        return None not in (self.score, self.cool, self.great, self.good, self.bad, self.combo)

    def key(self) -> tuple:
        """フレーム間の一致判定用キー"""
        return (self.score, self.cool, self.great, self.good, self.bad, self.combo)
