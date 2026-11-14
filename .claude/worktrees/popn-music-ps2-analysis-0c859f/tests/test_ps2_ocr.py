"""PS2 版のオプション画面 OCR による曲の特定のテスト"""
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.banner_reader import decode_feature  # noqa: E402
from src.ps2_banner import Ps2BannerIndex  # noqa: E402
from src.ps2_ocr import OcrSongIndex, OptionTexts, identify_option_song  # noqa: E402

SONGS = [
    ("a", "Can't Stop My Love", "Yumi Kawamura", ["popn8"]),
    ("b", "Sweet Illusion", "Yumi Kawamura", ["popn8"]),
    ("c", "silent green", "ササラユキエ", ["popn8"]),
    ("d", "Marigold", "Aya Mizuno", ["popn8"]),
    ("e", "Can't Stop My Love", "Yumi Kawamura", ["popn9"]),
]


class OcrSongIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = OcrSongIndex(SONGS)

    def test_title_and_artist(self):
        # 実際の OCR 結果 (「'」が「j」に化けている)
        texts = OptionTexts(["J-R&B3 Canjt Stop My Love"], ["-Yumi Kawamura"])
        self.assertEqual(self.index.match(texts, "popn8")[0], "a")

    def test_artist_only_when_unique(self):
        # 曲名は読めないが、アーティスト名が確実に読めて、その曲だけがその人の曲
        self.assertEqual(self.index.match(OptionTexts(["FL 〇 Å 工 第"], ["サ サ ラ ユ キ エ"]), "popn8")[0], "c")
        # 同じアーティストの曲が複数あり、曲名も読めないときは決めない
        self.assertIsNone(self.index.match(OptionTexts(["e 四 0 e"], ["Yumi Kawamura"]), "popn8"))

    def test_garbage_and_other_title(self):
        self.assertIsNone(self.index.match(OptionTexts(["e 四 0 e"], ["50N 石"]), "popn8"))
        self.assertIsNone(self.index.match(OptionTexts([], []), "popn8"))
        texts = OptionTexts(["Canjt Stop My Love"], ["Yumi Kawamura"])
        self.assertIsNone(self.index.match(texts, "popn7"))   # 収録タイトルが違う曲は照合しない


def _ocr_available() -> bool:
    try:
        import winrt.windows.media.ocr  # noqa: F401
        return True
    except ImportError:
        return False


class OptionScreenTest(unittest.TestCase):
    @unittest.skipUnless(_ocr_available(), "winrt (Windows OCR) が使えない")
    def test_fallback_to_ocr(self):
        """実際の画面: バナーに特徴量が無い曲は OCR で特定し、ある曲はバナーで特定する。"""
        shots = ROOT / "screenshots" / "popn8" / "option"
        listing = ROOT / "ps2_music_list.json"
        files = sorted(shots.glob("*.png")) if shots.exists() else []
        if not files or not listing.exists():
            self.skipTest("screenshots/popn8/option が無い")
        songs = json.loads(listing.read_text(encoding="utf-8"))
        ids = {s["music_id"]: s["title"] for s in songs}
        banners = Ps2BannerIndex([(s["music_id"], decode_feature(s["banner"]), s["titles"])
                                  for s in songs if s["banner"] and s["title"] != "silent green"])
        ocr = OcrSongIndex([(s["music_id"], s["title"], s["artist"], s["titles"]) for s in songs])
        got = {}
        for f in files:
            with Image.open(f) as im:
                found = identify_option_song(im, "popn8", banners, ocr)
            self.assertIsNotNone(found, f.name)
            got.setdefault((ids[found[0]], found[1]), 0)
            got[(ids[found[0]], found[1])] += 1
        self.assertEqual(set(got), {("Can't Stop My Love", "banner"), ("silent green", "ocr")})


if __name__ == "__main__":
    unittest.main()
