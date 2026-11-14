"""PS2 版 pop'n music の画面上の数字 (判定の内訳・スコア・コンボ) の読み取り

作品ごとにフォント・位置・桁数・ゼロ埋めの有無が違うので、固定座標のテンプレート照合ではなく、次の方法で読む。

1. 数字の枠 (画面に対する比率。4:3 の画面なら解像度に依存しない) を切り出す。
2. 枠の背景色 (画素の中央値) から離れた画素を「文字」とする。文字の色が暗くても明るくても、色付きでも使える。
3. 文字のある列の連なりごとに 1 文字ずつに分け、文字の形を 16x24 に正規化する。
4. 正規化した形と縦横比を、作品・画面ごとに学習したテンプレート (`ps2_digit_templates.json`) と照合する。

テンプレートは `tools/build_ps2_digit_templates.py` が、正解値付きのスクリーンショット
(`tools/ps2_number_samples.json`) から自動生成する。手で編集しない。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

GLYPH_W, GLYPH_H = 16, 24
DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("ps2_digit_templates.json")

INK_DISTANCE = 60          # 背景色からのこの距離 (RGB の各チャンネルの最大差) 以上を文字とみなす
MIN_GLYPH_HEIGHT = 0.35    # 文字の高さの下限 (枠の高さに対する比率)。ノイズを除く
MAX_MATCH_DISTANCE = 0.18  # これを超える距離は「読めなかった」とみなす (同じ数字の別画像との距離は 0.1 未満、違う数字とは 0.125 以上)
MERGE_GAP_PX = 2           # これ以下の隙間で隣り合う、どちらも細い塊は、1 文字が割れたものとして繋ぐ
MERGE_NARROW = 0.55        # 「細い」とみなす幅 (文字の高さに対する比率)
SPLIT_WIDTH_RATIO = 1.3    # 塊の幅が高さのこの倍率を超えたら、繋がった文字として分ける谷を探す
EDGE_SLIVER_ASPECT = 0.5   # 枠の端に接した、縦横比がこれ未満の細い塊は、隣の文字の一部とみなして除く
ASPECT_WEIGHT = 0.5        # 縦横比の差を距離に加える重み (「1」と他の数字の区別に使う)


def shape_distance(a: Glyph, b: Glyph) -> float:
    """2 つの文字の形の距離: 形の相関 (1 - 相関) の半分 + 縦横比の差。0 に近いほど同じ形。"""
    x, y = a.shape.ravel() - a.shape.mean(), b.shape.ravel() - b.shape.mean()
    nx, ny = float(np.linalg.norm(x)), float(np.linalg.norm(y))
    corr = float(x @ y) / (nx * ny) if nx > 1e-6 and ny > 1e-6 else 0.0
    return (1.0 - corr) / 2.0 + ASPECT_WEIGHT * abs(a.aspect - b.aspect)


@dataclass(frozen=True)
class Glyph:
    shape: np.ndarray   # (GLYPH_H, GLYPH_W) float32 0..1 (文字らしさ)
    aspect: float       # 幅 / 高さ
    x: int              # 枠の中での左端


def ink_strength(rgb: np.ndarray) -> np.ndarray:
    """枠の背景色からの距離 (H, W) float32。RGB の各チャンネルの差の最大値。

    背景色は、枠の外周の画素の中央値。枠の中の画素全体の中央値だと、文字が枠の大半を占めるとき (大きな数字が
    縁取りで繋がっているときなど) に文字の色を背景と取り違える。
    """
    h, w = rgb.shape[:2]
    b = max(2, min(h, w) // 12)
    ring = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
                           rgb[b:-b, :b].reshape(-1, 3), rgb[b:-b, -b:].reshape(-1, 3)]).astype(np.int16)
    bg = np.median(ring, axis=0)
    return np.abs(rgb.astype(np.int16) - bg).max(axis=2).astype(np.float32)


def ink_mask(rgb: np.ndarray, distance: int = INK_DISTANCE) -> np.ndarray:
    """枠の背景色 (中央値) から離れた画素を文字とする (H, W) bool。"""
    return ink_strength(rgb) >= distance


def _split_glued(counts: np.ndarray, height: int, ratio: float = SPLIT_WIDTH_RATIO) -> list[tuple[int, int]]:
    """隣の文字と縁取りで繋がった幅の広い塊を、列のインクが少ない谷で分ける。(開始, 終了) のリストを返す。

    文字の幅は高さの 0.35～0.9 倍ほど。塊の幅が高さの 1.3 倍を超えるときだけ、谷を探す。
    谷 = 左右の山 (±高さの 0.6 倍の範囲の最大) の低いほうの 6 割以下の列。
    """
    w = len(counts)
    if w <= height * ratio:
        return [(0, w)]
    smooth = np.convolve(counts.astype(np.float32), np.ones(3, dtype=np.float32) / 3, mode="same")
    min_part = max(int(height * 0.45), 3)
    reach = max(int(height * 0.6), 3)
    cuts: list[int] = []
    for x in range(min_part, w - min_part):
        left, right = smooth[max(0, x - reach):x + 1].max(), smooth[x:x + reach + 1].max()
        if smooth[x] > 0.6 * min(left, right):
            continue
        lo, hi = max(0, x - 2), min(w, x + 3)
        if smooth[x] > smooth[lo:hi].min() + 1e-6:
            continue
        if cuts and x - cuts[-1] < min_part:
            if smooth[x] < smooth[cuts[-1]]:
                cuts[-1] = x
            continue
        cuts.append(x)
    edges = [0, *cuts, w]
    return [(a, b) for a, b in zip(edges[:-1], edges[1:])]


def segment(rgb: np.ndarray, distance: int = INK_DISTANCE, split_ratio: float = SPLIT_WIDTH_RATIO) -> list[Glyph]:
    """枠の画像 (H, W, 3) から、文字を左から順に切り出す。"""
    strength = ink_strength(rgb)
    mask = strength >= distance
    h, w = mask.shape
    # 幅の大半を占める横線 (パネルの縁・罫線) は文字ではないので除く
    mask[mask.mean(axis=1) > 0.9] = False
    # 小さなノイズ (1 画素の点) を除く
    cols = mask.sum(axis=0) >= 2
    glyphs: list[Glyph] = []
    runs: list[list[int]] = []
    x = 0
    while x < w:
        if not cols[x]:
            x += 1
            continue
        x0 = x
        while x < w and cols[x]:
            x += 1
        runs.append([x0, x])
    # 1 文字が細く 2 つに割れたもの (線の途切れ・低いコントラスト) を戻す: どちらも細く、隙間がほぼ無いものを繋ぐ
    ys = np.flatnonzero(mask.any(axis=1))
    row_h = float(ys[-1] - ys[0] + 1) if len(ys) else 0.0
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= MERGE_GAP_PX and (r[1] - r[0]) < MERGE_NARROW * row_h                 and (merged[-1][1] - merged[-1][0]) < MERGE_NARROW * row_h:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    for x0, x in merged:
        blob = mask[:, x0:x]
        rows = np.flatnonzero(blob.sum(axis=1) >= 1)
        if len(rows) == 0:
            continue
        by0, by1 = rows[0], rows[-1] + 1
        if (by1 - by0) < h * MIN_GLYPH_HEIGHT:
            continue
        for a, b in _split_glued(blob[by0:by1].sum(axis=0), by1 - by0, split_ratio):
            part = mask[:, x0 + a:x0 + b]
            prow = np.flatnonzero(part.sum(axis=1) >= 1)
            if len(prow) == 0:
                continue
            y0, y1 = prow[0], prow[-1] + 1
            if (y1 - y0) < h * MIN_GLYPH_HEIGHT or (b - a) < 2:
                continue
            # 形は、背景からの距離をその文字の中の最大に合わせて 0..1 にした濃淡で持つ (文字の色の濃さに依らないように)
            sub = strength[y0:y1, x0 + a:x0 + b]
            sub = np.clip(sub / max(float(np.percentile(sub, 98)), 1.0), 0.0, 1.0)
            img = Image.fromarray((sub * 255).astype(np.uint8)).resize((GLYPH_W, GLYPH_H), Image.Resampling.BOX)
            glyphs.append(Glyph(np.asarray(img, dtype=np.float32) / 255.0, (b - a) / (y1 - y0), x0 + a))
    # 枠の左右の端に接した細い塊 (枠のすぐ外にある別の文字・縁の一部) は数字ではない
    return [g for g in glyphs if not (g.aspect < EDGE_SLIVER_ASPECT and (g.x == 0 or g.x + g.aspect * h >= w - 2))]


def segment_fixed(rgb: np.ndarray, digits: int, distance: int = INK_DISTANCE) -> list[Glyph]:
    """等幅で 0 埋めされた数字 (桁数が決まっている) を、文字の連なりの幅を等分して切り出す。

    輪郭が太く隣の文字と繋がって、谷で分けられない作品・画面 (popn10 のプレー画面など) 用。
    文字の連なりの左端から右端までを `digits` 等分し、各区画の中の文字を 1 文字とする。
    """
    strength = ink_strength(rgb)
    mask = strength >= distance
    h = mask.shape[0]
    cols = np.flatnonzero(mask.sum(axis=0) >= 2)
    if len(cols) == 0:
        return []
    left, right = int(cols[0]), int(cols[-1]) + 1
    pitch = (right - left) / digits
    glyphs: list[Glyph] = []
    for i in range(digits):
        a, b = left + round(i * pitch), left + round((i + 1) * pitch)
        part = mask[:, a:b]
        rows = np.flatnonzero(part.sum(axis=1) >= 1)
        if len(rows) == 0 or (rows[-1] + 1 - rows[0]) < h * MIN_GLYPH_HEIGHT:
            continue
        y0, y1 = int(rows[0]), int(rows[-1]) + 1
        sub = strength[y0:y1, a:b]
        sub = np.clip(sub / max(float(np.percentile(sub, 98)), 1.0), 0.0, 1.0)
        img = Image.fromarray((sub * 255).astype(np.uint8)).resize((GLYPH_W, GLYPH_H), Image.Resampling.BOX)
        glyphs.append(Glyph(np.asarray(img, dtype=np.float32) / 255.0, (b - a) / (y1 - y0), a))
    return glyphs


class DigitTemplates:
    """作品・画面ごとの文字テンプレート。キーは (title, screen)、値は {数字: [Glyph...]}。"""

    def __init__(self, data: dict[tuple[str, str], dict[str, list[Glyph]]] | None = None):
        self._data = data or {}

    @classmethod
    def load(cls, path: str | Path = DEFAULT_TEMPLATE_PATH) -> "DigitTemplates":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        data: dict[tuple[str, str], dict[str, list[Glyph]]] = {}
        for key, digits in raw.get("templates", {}).items():
            title, screen = key.split("/", 1)
            table: dict[str, list[Glyph]] = {}
            for digit, items in digits.items():
                table[digit] = [Glyph(np.frombuffer(base64.b64decode(i["shape"]), dtype=np.uint8)
                                      .reshape(GLYPH_H, GLYPH_W).astype(np.float32) / 255.0, i["aspect"], 0)
                                for i in items]
            data[(title, screen)] = table
        return cls(data)

    def has(self, title: str, screen: str) -> bool:
        return bool(self._data.get((title, screen)))

    def digits(self, title: str, screen: str) -> dict[str, list[Glyph]]:
        return self._data.get((title, screen), {})

    def recognize(self, glyph: Glyph, title: str, screen: str) -> tuple[str, float] | None:
        """文字に最も近い数字と距離。テンプレートが無い・遠すぎるときは None。"""
        best: tuple[str, float] | None = None
        for digit, items in self.digits(title, screen).items():
            for t in items:
                d = shape_distance(glyph, t)
                if best is None or d < best[1]:
                    best = (digit, d)
        if best is None or best[1] > MAX_MATCH_DISTANCE:
            return None
        return best


def crop_box(image: Image.Image, box: tuple[float, float, float, float]) -> np.ndarray:
    """画面に対する比率の枠 (x0, y0, x1, y1) を切り出す。"""
    w, h = image.size
    x0, y0, x1, y1 = box
    return np.asarray(image.convert("RGB").crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h))))


def read_digits(image: Image.Image, box: tuple[float, float, float, float], title: str, screen: str,
                templates: DigitTemplates, split_ratio: float = SPLIT_WIDTH_RATIO, fixed_digits: int = 0) -> str | None:
    """枠の中の数字列を読む。1 文字でも読めなければ None。文字が 1 つも無いときは空文字。"""
    arr = crop_box(image, box)
    glyphs = segment_fixed(arr, fixed_digits) if fixed_digits else segment(arr, split_ratio=split_ratio)
    out = []
    for g in glyphs:
        r = templates.recognize(g, title, screen)
        if r is None:
            return None
        out.append(r[0])
    return "".join(out)
