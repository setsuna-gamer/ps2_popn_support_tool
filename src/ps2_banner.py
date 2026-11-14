"""PS2 版 pop'n music のオプション画面の曲バナーによる曲の特定

オプション画面 (「Next Music」パネル) の左上に、選んだ曲のバナーが表示される。
PS2 版のバナーは、曲リストの `banner` 列 (Lively 版のバナー画像から作った特徴量) と同じ画像なので、
`src/banner_reader.py` の特徴量 (16x4 の RGB サムネイルの相関) でそのまま照合できる
(popn7 の「マシュマロ・マーチ」で相関 0.997、2 位との差 0.2)。

オプション画面には 2 つの状態がある。
    1. Next Music だけが表示されている状態: バナー全体が見える。
    2. OPTIONS のポップアップが開いた状態: バナーは暗くなり、下半分がポップアップに隠れる。
   1 は特徴量の 4 行すべてで、2 は上の 2 行だけで照合する (2 でも相関 0.996 で一致する)。

バナーの位置は作品ごとに違うので、`BANNER_BOXES` に 4:3 の画面に対する比率で持つ。
4:3 以外の入力は、呼び出し側で 4:3 に切り出してから渡すこと (src/screen_profile.py と同じ)。
曲リストの `titles` で、その作品に収録されている曲だけに絞って照合する。
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from src.banner_reader import FEATURE_H, FEATURE_W, BannerIndex, banner_feature

# 作品ごとのバナーの位置 (x0, y0, x1, y1)。画面に対する 0..1 の比率。黒い縁取りの内側
BANNER_BOXES: dict[str, tuple[float, float, float, float]] = {
    "popn7": (37 / 1325, 305 / 994, 668 / 1325, 437 / 994),
    "popn8": (42 / 1325, 426 / 994, 672 / 1325, 556 / 994),   # 下のアーティスト名の帯は含めない
    "popn9": (38 / 1325, 96 / 994, 667 / 1325, 222 / 994),   # 左上。ポップアップは重ならない (暗くなるだけ)
    "popn10": (40 / 1325, 176 / 994, 684 / 1325, 330 / 994),   # 暗くなるだけで、ポップアップは重ならない
    "popn11": (187 / 1325, 107 / 994, 817 / 1325, 254 / 994),   # 同上
    "popn12": (680 / 1325, 118 / 994, 1308 / 1325, 264 / 994),   # 右上。ポップアップ (設定の帯) は重ならない
    "popn13": (683 / 1325, 139 / 994, 1311 / 1325, 269 / 994),   # 右上。ポップアップ (設定の帯) は重ならない
    "popn14": (52 / 1325, 172 / 994, 716 / 1325, 352 / 994),    # 傾いて表示される。外接の範囲 (OCR 用)。照合は BANNER_QUADS
    "besthits": (38 / 1325, 306 / 994, 667 / 1325, 436 / 994),
}

# 傾き・歪んで表示される作品の、バナーの 4 隅 (左上, 右上, 右下, 左下)。画面に対する 0..1 の比率。
# 4 隅を長方形に補正して切り出す。既知の曲の特徴量との相関が最大になるように探索して決めた (popn14: 相関 0.998。
# 矩形で切り出すと 0.8 程度までしか上がらず、別の曲に取り違えない代わりに特定もできない)
BANNER_QUADS: dict[str, tuple[tuple[float, float], ...]] = {
    "popn14": ((66 / 1325, 217 / 994), (696 / 1325, 172 / 994), (714 / 1325, 304 / 994), (80 / 1325, 350 / 994)),
}
_QUAD_SIZE = (640, 128)

# OPTIONS のポップアップがバナーに重なる作品 (これ以外は、ポップアップが開いてもバナーは隠れない)
POPUP_COVERS_BANNER = {"popn7", "besthits"}

# リザルト画面にも、同じバナーが出る作品の位置 (popn13 / popn14 は右上ではなく左上に大きく出る。ほかの作品は文字だけ)
RESULT_BANNER_BOXES: dict[str, tuple[float, float, float, float]] = {
    "popn13": (80 / 1325, 115 / 994, 710 / 1325, 245 / 994),
    "popn14": (85 / 1325, 57 / 994, 716 / 1325, 185 / 994),
}


def read_result_banner(image: Image.Image, title: str) -> np.ndarray | None:
    """リザルト画面からバナーの特徴量を作る。その作品のリザルトにバナーが出ない (位置が未登録) なら None。"""
    box = RESULT_BANNER_BOXES.get(title)
    if box is None:
        return None
    w, h = image.size
    x0, y0, x1, y1 = box
    return banner_feature(image.convert("RGB").crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))))


PARTIAL_ROWS = 2        # ポップアップで下半分が隠れているときに使う、特徴量の上からの行数
# PS2 では同じ画像どうしの照合なので、正しい一致は 0.99 以上になる。Lively 用の基準 (0.80、banner_reader.py) だと、
# バナーを登録していない曲が別の曲に 0.80 で誤って一致する (best hits の MELO CORE → 魔法の扉 0.802) ため、引き上げる
FULL_MIN_SCORE = 0.92
PARTIAL_MIN_SCORE = 0.95
PARTIAL_MIN_MARGIN = 0.08


def crop_option_banner(image: Image.Image, title: str) -> Image.Image | None:
    """オプション画面からバナーを切り出す (歪んで表示される作品は長方形に補正する)。位置が未登録なら None。"""
    w, h = image.size
    rgb = image.convert("RGB")
    quad = BANNER_QUADS.get(title)
    if quad is not None:
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = quad
        # PIL の QUAD は 左上・左下・右下・右上 の順
        data = (tlx * w, tly * h, blx * w, bly * h, brx * w, bry * h, trx * w, try_ * h)
        return rgb.transform(_QUAD_SIZE, Image.Transform.QUAD, data, Image.Resampling.BILINEAR)
    box = BANNER_BOXES.get(title)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    return rgb.crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))


def read_option_banner(image: Image.Image, title: str) -> np.ndarray | None:
    """オプション画面からバナーの特徴量を作る。その作品のバナー位置が未登録なら None。"""
    crop = crop_option_banner(image, title)
    return None if crop is None else banner_feature(crop)


def _rows(v: np.ndarray, rows: int) -> np.ndarray:
    """特徴量の上からの `rows` 行を、平均を引いて長さ 1 にしたもの。"""
    a = v.reshape(FEATURE_H, FEATURE_W, 3)[:rows].ravel().astype(np.float32)
    a = a - a.mean()
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-6 else a * 0.0


class Ps2BannerIndex:
    """曲ごとのバナー特徴量を持ち、作品を指定して、画面から読んだ特徴量に最も近い曲を返す。"""

    def __init__(self, items: list[tuple[str, np.ndarray, list[str]]]):
        """items: (music_id, 特徴量, 収録タイトルのリスト)"""
        self._by_title: dict[str, list[tuple[str, np.ndarray]]] = {}
        for music_id, feature, titles in items:
            for t in titles:
                self._by_title.setdefault(t, []).append((music_id, feature))
        self._full: dict[str, BannerIndex] = {}
        self._partial: dict[str, np.ndarray] = {}

    def count(self, title: str) -> int:
        """その作品で照合に使える (バナーを持つ) 曲数。"""
        return len(self._by_title.get(title, []))

    def _full_index(self, title: str) -> BannerIndex:
        if title not in self._full:
            self._full[title] = BannerIndex(self._by_title.get(title, []))
        return self._full[title]

    def _partial_matrix(self, title: str) -> np.ndarray:
        if title not in self._partial:
            items = self._by_title.get(title, [])
            self._partial[title] = (np.stack([_rows(v, PARTIAL_ROWS) for _, v in items])
                                    if items else np.zeros((0, 1), dtype=np.float32))
        return self._partial[title]

    def match(self, feature: np.ndarray, title: str) -> tuple[str, float, float] | None:
        """(music_id, 相関, 2 位との差) を返す。基準に満たなければ None。

        まずバナー全体で照合し、決まらなければ (ポップアップで隠れているとき) 上半分だけで、より厳しい基準で照合する。
        """
        found = self._full_index(title).match(feature)
        if found is not None and found[1] >= FULL_MIN_SCORE:
            return found
        matrix = self._partial_matrix(title)
        if len(matrix) < 2:
            return None
        sims = matrix @ _rows(feature, PARTIAL_ROWS)
        first, second = (int(i) for i in np.argsort(-sims)[:2])
        score, margin = float(sims[first]), float(sims[first] - sims[second])
        if score < PARTIAL_MIN_SCORE or margin < PARTIAL_MIN_MARGIN:
            return None
        return self._by_title[title][first][0], score, margin
