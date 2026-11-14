"""PS2 版 pop'n music のオプション画面の OCR による曲の特定 (バナー照合で決まらないときの補助)

曲名・アーティスト名はバナー画像の装飾フォントで、Windows OCR は一部しか読めない
(英字の曲名・アーティスト名はほぼ読めるが、日本語の装飾文字は崩れる)。
そこで曲リストの「曲名 + アーティスト名」と、2 文字ずつの並び (バイグラム) の一致率で照合する。
- 曲名はバナー部分の OCR 結果と、アーティスト名はアーティスト帯の OCR 結果と突き合わせる。
- 一致率が高く、2 位との差も十分あるときだけ採用する (誤読の文字列で別の曲に決めない)。
- 曲リストの `titles` で、その作品に収録された曲に絞る。

OCR は 1 回に数百 ms かかるので、先に `src/ps2_banner.py` のバナー照合を行い、決まらないときだけ使う。
バナー・アーティスト帯の位置は `src/ps2_banner.py` の `BANNER_BOXES` (歪む作品は `BANNER_QUADS` も) と、このファイルの `ARTIST_BOXES` (作品ごと)。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from src.ps2_banner import BANNER_BOXES, Ps2BannerIndex, crop_option_banner, read_option_banner
from src.win_ocr import _ocr

# 作品ごとのアーティスト名の帯の位置 (x0, y0, x1, y1)。画面に対する 0..1 の比率
ARTIST_BOXES: dict[str, tuple[float, float, float, float]] = {
    "popn7": (37 / 1325, 440 / 994, 668 / 1325, 522 / 994),
    "popn8": (42 / 1325, 556 / 994, 672 / 1325, 602 / 994),
    "popn9": (130 / 1325, 230 / 994, 560 / 1325, 292 / 994),   # バナーの下の吹き出しの、アーティスト名
    "popn11": (185 / 1325, 268 / 994, 560 / 1325, 330 / 994),   # バナーの下の、アーティスト名
    "popn12": (880 / 1325, 292 / 994, 1325 / 1325, 352 / 994),   # バナーの下の、アーティスト名 (暗い帯に白文字)
    "popn14": (740 / 1325, 160 / 994, 1325 / 1325, 240 / 994),   # バナーの右の、アーティスト名 (暗い帯に白文字)
    "popn13": (780 / 1325, 355 / 994, 1325 / 1325, 420 / 994),   # バナーの下の、アーティスト名 (暗い板に白文字)
    "besthits": (38 / 1325, 436 / 994, 667 / 1325, 515 / 994),
}

# 作品ごとの、バナーとは別に曲名が平文字で表示される位置 (バナーの OCR 結果と同じく、曲名として照合する)
TITLE_BOXES: dict[str, tuple[float, float, float, float]] = {
    "popn10": (210 / 1325, 372 / 994, 775 / 1325, 448 / 994),   # バナーの下の曲名の板
}

MIN_SCORE = 0.70        # 曲名 + アーティスト名のバイグラムの一致率の下限
MIN_MARGIN = 0.15       # 2 位との差の下限
MIN_EVIDENCE = 5        # 一致したバイグラムの数の下限 (短い文字列の偶然の一致を避ける)
# 曲名が読めなくても、アーティスト名がこの割合以上読めて (バイグラムが ARTIST_MIN_BIGRAMS 個以上)、
# 2 位との差も十分あれば採用する (同じアーティストの曲が複数あれば差が出ないので採用されない)
ARTIST_MIN_COVERAGE = 0.90
ARTIST_MIN_BIGRAMS = 4


def _crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = image.size
    x0, y0, x1, y1 = box
    return image.convert("RGB").crop((round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)))


def _variants(im: Image.Image) -> list[Image.Image]:
    """OCR の読み取りが画像の拡大率や色で変わるので、いくつかの前処理で読む。"""
    gray = ImageOps.autocontrast(im.convert("L").resize((im.width * 3, im.height * 3), Image.Resampling.LANCZOS))
    return [im.resize((im.width * s, im.height * s), Image.Resampling.LANCZOS) for s in (2, 3)] + [gray]


def _white_text_variants(im: Image.Image) -> list[Image.Image]:
    """白い文字だけを取り出して、白地に黒文字にした画像 (アーティスト帯は色付きの地に白い文字)。"""
    mask = np.asarray(im.convert("RGB")).min(axis=2) > 170
    bw = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).convert("L")
    out = []
    for s in (2, 3):
        scaled = bw.resize((bw.width * s, bw.height * s), Image.Resampling.LANCZOS)
        padded = Image.new("L", (scaled.width + 40, scaled.height + 40), 255)   # OCR は余白が無いと読めないことがある
        padded.paste(scaled, (20, 20))
        out.append(padded)
    return out


@dataclass
class OptionTexts:
    banner: list[str]   # バナー部分 (曲名) の OCR 結果
    artist: list[str]   # アーティスト帯の OCR 結果


def read_option_texts(image: Image.Image, title: str) -> OptionTexts | None:
    """オプション画面のバナー (と曲名の板)・アーティスト帯を OCR で読む。その作品のバナー位置が未登録なら None。"""
    if title not in BANNER_BOXES:
        return None
    banner = [_ocr.read(v) for v in _variants(crop_option_banner(image, title))]
    if title in TITLE_BOXES:
        banner += [_ocr.read(v) for v in _variants(_crop(image, TITLE_BOXES[title]))]
    artist: list[str] = []
    if title in ARTIST_BOXES:
        band = _crop(image, ARTIST_BOXES[title])
        artist = [_ocr.read(v) for v in _variants(band) + _white_text_variants(band)]
    return OptionTexts([t for t in banner if t], [t for t in artist if t])


def _key(s: str) -> str:
    """照合用の文字列。大文字小文字・全半角・空白・記号の違いを吸収する。"""
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKC", s or "").lower() if ch.isalnum())


def _bigrams(s: str) -> set[str]:
    k = _key(s)
    return {k[i:i + 2] for i in range(len(k) - 1)} if len(k) >= 2 else set()


class OcrSongIndex:
    """曲名・アーティスト名のバイグラムを持ち、OCR 結果に最も近い曲を返す。"""

    def __init__(self, items: list[tuple[str, str, str, list[str]]]):
        """items: (music_id, 曲名, アーティスト名, 収録タイトルのリスト)"""
        self._by_title: dict[str, list[tuple[str, set[str], set[str]]]] = {}
        for music_id, name, artist, titles in items:
            entry = (music_id, _bigrams(name), _bigrams(artist))
            for t in titles:
                self._by_title.setdefault(t, []).append(entry)

    def match(self, texts: OptionTexts, title: str) -> tuple[str, float, float] | None:
        """(music_id, 一致率, 2 位との差) を返す。基準に満たなければ None。"""
        banner = set().union(*(_bigrams(t) for t in texts.banner)) if texts.banner else set()
        artist = set().union(*(_bigrams(t) for t in texts.artist)) if texts.artist else set()
        scored = []
        for music_id, tb, ab in self._by_title.get(title, []):
            total = len(tb) + len(ab)
            if not total:
                continue
            hit_a = len(ab & artist)
            hit = len(tb & banner) + hit_a
            artist_ok = len(ab) >= ARTIST_MIN_BIGRAMS and hit_a / len(ab) >= ARTIST_MIN_COVERAGE
            scored.append((hit / total, hit, artist_ok, music_id))
        if len(scored) < 2:
            return None
        scored.sort(key=lambda r: r[0], reverse=True)
        (score, hit, artist_ok, music_id), second = scored[0], scored[1][0]
        if score - second < MIN_MARGIN or not ((score >= MIN_SCORE and hit >= MIN_EVIDENCE) or artist_ok):
            return None
        return music_id, score, score - second


def identify_option_song(image: Image.Image, title: str, banner_index: Ps2BannerIndex,
                         ocr_index: OcrSongIndex) -> tuple[str, str] | None:
    """オプション画面から曲を特定する。(music_id, 方法 "banner" / "ocr") を返す。特定できなければ None。

    先にバナー照合を行い、決まらないときだけ OCR を使う。
    """
    feature = read_option_banner(image, title)
    if feature is not None:
        found = banner_index.match(feature, title)
        if found is not None:
            return found[0], "banner"
    texts = read_option_texts(image, title)
    if texts is not None:
        found = ocr_index.match(texts, title)
        if found is not None:
            return found[0], "ocr"
    return None
