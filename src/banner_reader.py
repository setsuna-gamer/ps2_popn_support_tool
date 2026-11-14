"""曲バナーの特徴量 (16x4 の RGB サムネイル) と、その相関による照合

曲リスト (ps2_music_list.json) の `banner` 列は、バナー画像から作ったこの特徴量。内積がそのまま相関になる。
PS2 版の画面 (オプション・リザルト) からのバナーの切り出しと、作品ごとの基準は `src/ps2_banner.py`。

特徴量の作り方 (banner_feature) は tools / generate_music_list.py / generate_ps2_music_list.py も使うので、
変えたら曲リストを作り直すこと。
"""
from __future__ import annotations

import base64

import numpy as np
from PIL import Image

FEATURE_W = 16
FEATURE_H = 4
_INSET = 0.025          # 縁取りの内側の余白 (バナーの幅・高さに対する比率)

MIN_SCORE = 0.80        # 最も近い曲の相関がこれ未満なら特定しない
MIN_MARGIN = 0.04       # 2 位との相関の差がこれ未満なら特定しない
# 公式サイトのバナーと、ゲーム内のバナーの文字などが違う曲は相関が低くなる。
# その場合は、2 位との差が十分大きいときだけ採用する
LOW_SCORE = 0.60
LOW_SCORE_MARGIN = 0.15


# ----------------------------------------------------------------------
# 特徴量
# ----------------------------------------------------------------------

def banner_feature(image: Image.Image) -> np.ndarray:
    """バナー画像 (縁取りを含まない) から特徴量を作る。正規化済みの float32 ベクトルを返す。

    サムネイルを RGB 平均値で引いて長さ 1 にするので、内積がそのまま相関になる。
    透過部分 (公式サイトの画像は角が透過) は黒として扱う。
    """
    rgba = image.convert("RGBA")
    base = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    base.alpha_composite(rgba)
    w, h = base.size
    mx, my = round(w * _INSET), round(h * _INSET)
    crop = base.convert("RGB").crop((mx, my, w - mx, h - my))
    thumb = crop.resize((FEATURE_W, FEATURE_H), Image.Resampling.BOX)
    v = np.asarray(thumb, dtype=np.float32).ravel()
    return _normalize(v)


def _normalize(v: np.ndarray) -> np.ndarray:
    v = v - v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else v * 0.0


def encode_feature(v: np.ndarray) -> str:
    """特徴量を曲リストに書き込む文字列にする (0～255 に量子化した base64)。"""
    q = np.clip(np.round((v + 0.5) * 255), 0, 255).astype(np.uint8)
    return base64.b64encode(q.tobytes()).decode("ascii")


def decode_feature(s: str) -> np.ndarray | None:
    try:
        q = np.frombuffer(base64.b64decode(s), dtype=np.uint8)
    except ValueError:
        return None
    if q.size != FEATURE_W * FEATURE_H * 3:
        return None
    return _normalize(q.astype(np.float32) / 255 - 0.5)


# ----------------------------------------------------------------------
# 照合
# ----------------------------------------------------------------------

class BannerIndex:
    """曲ごとのバナー特徴量を持ち、画面から読んだ特徴量に最も近い曲を返す。"""

    def __init__(self, items: list[tuple[str, np.ndarray]] | None = None):
        self._ids: list[str] = []
        self._matrix = np.zeros((0, FEATURE_W * FEATURE_H * 3), dtype=np.float32)
        if items:
            self._ids = [i for i, _ in items]
            self._matrix = np.stack([v for _, v in items]).astype(np.float32)

    def __len__(self) -> int:
        return len(self._ids)

    def match(self, feature: np.ndarray) -> tuple[str, float, float] | None:
        """(music_id, 相関, 2 位との差) を返す。基準に満たなければ None。

        同じバナーを使う別の曲 (ウラ譜面・別バージョンなど) があると 2 位との差が 0 になり、
        特定できない (曲名 OCR に任せる)。
        """
        if len(self) < 2:
            return None
        sims = self._matrix @ feature
        first, second = (int(i) for i in np.argsort(-sims)[:2])
        score = float(sims[first])
        margin = score - float(sims[second])
        if score < LOW_SCORE or (score < MIN_SCORE and margin < LOW_SCORE_MARGIN) or margin < MIN_MARGIN:
            return None
        return self._ids[first], score, margin
