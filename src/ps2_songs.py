"""PS2 版: 画面から曲を特定する (オプション画面・リザルト画面)

- オプション画面: バナーの特徴量で特定する (src/ps2_banner.py)。決まらなければ OCR (src/ps2_ocr.py) を補助に使う。
- リザルト画面: バナーが出る作品 (popn13 / popn14) だけ、バナーで特定する。そのほかの作品のリザルトは曲名が文字
  (画像フォント) だけなので、オプション画面で決めた曲を使う。
どちらも、曲リストの `titles` (収録作品) で、その作品に収録された曲だけに絞る。

OCR は 1 回に数百 ms かかり、読めない画面では毎回失敗するので、`OCR_EVERY` 回に 1 回だけ試す。
"""
from __future__ import annotations

from PIL import Image

from src.banner_reader import decode_feature
from src.ps2_banner import Ps2BannerIndex, read_option_banner, read_result_banner
from src.ps2_ocr import OcrSongIndex, read_option_texts

OCR_EVERY = 5


class Ps2SongIdentifier:
    def __init__(self, rows: list[dict]):
        """rows: Database.ps2_song_rows() の戻り値"""
        items = []
        for r in rows:
            v = decode_feature(r["banner"]) if r["banner"] else None
            if v is not None:
                items.append((r["music_id"], v, r["titles"]))
        self.banners = Ps2BannerIndex(items)
        self.ocr = OcrSongIndex([(r["music_id"], r["title"], r["artist"], r["titles"]) for r in rows])
        self._misses = 0

    def identify_option(self, image: Image.Image, title: str) -> str:
        """オプション画面から曲を特定して music_id を返す。特定できなければ空文字。"""
        feature = read_option_banner(image, title)
        if feature is not None:
            found = self.banners.match(feature, title)
            if found is not None:
                self._misses = 0
                return found[0]
        # バナーで決まらない: 数回に 1 回だけ OCR を試す
        self._misses += 1
        if (self._misses - 1) % OCR_EVERY != 0:
            return ""
        texts = read_option_texts(image, title)
        found = self.ocr.match(texts, title) if texts is not None else None
        return found[0] if found is not None else ""

    def identify_result(self, image: Image.Image, title: str) -> str:
        """リザルト画面のバナーから曲を特定する。バナーが出ない作品・特定できないときは空文字。"""
        feature = read_result_banner(image, title)
        found = self.banners.match(feature, title) if feature is not None else None
        return found[0] if found is not None else ""
