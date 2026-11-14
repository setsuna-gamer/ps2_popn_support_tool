"""PS2 版 pop'n music の画面識別 (タイトル × 画面モード)。

入力は 4:3 のゲーム画面。ぼかした画面を 32x24 のセルに分け、セルごとの平均色を
サンプル画像から作ったテンプレートと比べ、一致したセルの割合で (タイトル, モード) を決める。
テンプレートは `tools/build_screen_profiles.py` が `screenshots/<title_id>/<mode>/` の画像から自動生成する
(`src/screen_profiles.json`)。ハッシュ・座標の手書きはしない。

座標はセル番号 (0..767) で持つので、4:3 であれば入力解像度に依存しない。
4:3 以外 (レターボックスなど) の入力は、呼び出し側で 4:3 に切り出してから渡すこと。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

GRID_COLS, GRID_ROWS = 32, 24   # 4:3 の画面を 32x24 のセルに分ける
CELLS = GRID_COLS * GRID_ROWS
_WORK_SIZE = (320, 240)        # 正規化サイズ (4:3)。1 セルは 10x10 px
_BLUR_RADIUS = 4               # 拡縮・ずれ・圧縮ノイズに強くするため、セルにする前にぼかす

# セルが一致とみなす条件 (平均色の各チャンネルの差)
COLOR_TOLERANCE = 36.0
# 識別の採用条件: 一致したセルの割合が MIN_SCORE 以上で、別の (タイトル, モード) の最高スコアより MIN_MARGIN 以上高いこと
MIN_SCORE = 0.5
MIN_MARGIN = 0.2


def _default_profile_path() -> Path:
    path = Path(__file__).with_name("screen_profiles.json")
    if not path.exists() and getattr(sys, "frozen", False):
        # cx_Freeze のビルドでは src のモジュールが zip の中に入るので、exe の隣の src/ に置いたものを使う
        return Path(sys.executable).parent / "src" / "screen_profiles.json"
    return path


DEFAULT_PROFILE_PATH = _default_profile_path()


@dataclass
class CellFeatures:
    colors: np.ndarray  # (CELLS, 3) float32。セルの平均色


def cell_features(image: Image.Image) -> CellFeatures:
    """画像から、セルごとの平均色を求める。"""
    im = image.convert("RGB").resize(_WORK_SIZE, Image.Resampling.BOX)
    im = im.filter(ImageFilter.GaussianBlur(_BLUR_RADIUS)).resize((GRID_COLS, GRID_ROWS), Image.Resampling.BOX)
    return CellFeatures(colors=np.asarray(im, dtype=np.float32).reshape(CELLS, 3))


def match_cells(a: CellFeatures, b: CellFeatures) -> np.ndarray:
    """2 つの画像のセルごとの一致 (CELLS,) bool。"""
    return np.abs(a.colors - b.colors).max(axis=1) <= COLOR_TOLERANCE


@dataclass
class Template:
    title: str
    mode: str
    name: str
    cells: list[int]
    features: CellFeatures   # cells の順に並んだ特徴 (len(cells), 3)

    def score(self, f: CellFeatures) -> float:
        idx = np.array(self.cells)
        sub = CellFeatures(f.colors[idx])
        return float(match_cells(self.features, sub).mean())


@dataclass
class Identification:
    title: str
    mode: str
    score: float
    template: str


class ScreenProfiles:
    """生成済みのテンプレートで (タイトル, モード) を識別する。"""

    def __init__(self, templates: list[Template]):
        self.templates = templates

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PROFILE_PATH) -> "ScreenProfiles":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        templates = []
        for t in data["templates"]:
            cells = [c["i"] for c in t["cells"]]
            templates.append(Template(
                title=t["title"], mode=t["mode"], name=t["name"], cells=cells,
                features=CellFeatures(np.array([c["rgb"] for c in t["cells"]], dtype=np.float32)),
            ))
        return cls(templates)

    def scores(self, image: Image.Image) -> list[Identification]:
        """全テンプレートのスコアを、高い順に返す。"""
        return self.scores_from_features(cell_features(image))

    def scores_from_features(self, f: CellFeatures) -> list[Identification]:
        result = [Identification(t.title, t.mode, t.score(f), t.name) for t in self.templates]
        result.sort(key=lambda r: r.score, reverse=True)
        return result

    def identify(self, image: Image.Image, min_score: float = MIN_SCORE,
                 min_margin: float = MIN_MARGIN) -> Identification | None:
        """最も一致するテンプレートの (タイトル, モード)。採用条件を満たさなければ None。"""
        return self.decide(self.scores(image), min_score, min_margin)

    @staticmethod
    def decide(ranked: list[Identification], min_score: float = MIN_SCORE,
               min_margin: float = MIN_MARGIN) -> Identification | None:
        """スコアの高い順のリストから採用する識別結果を決める。"""
        if not ranked or ranked[0].score < min_score:
            return None
        best = ranked[0]
        others = [r for r in ranked if (r.title, r.mode) != (best.title, best.mode)]
        rival = others[0].score if others else 0.0
        if best.score - rival >= min_margin:
            return best
        # タイトル画面のメニュー選択中の状態はモード選択と紛れやすいので、title と mode_select で迷ったら title に寄せる
        # (同じ作品の 2 つだけが競っていて、title が採用の最低スコアを満たすとき)
        close = [r for r in ranked if best.score - r.score < min_margin]
        if {(r.title, r.mode) for r in close} <= {(best.title, "title"), (best.title, "mode_select")}:
            titles = [r for r in close if r.mode == "title"]
            if titles and titles[0].score >= min_score:
                return titles[0]
        return None
