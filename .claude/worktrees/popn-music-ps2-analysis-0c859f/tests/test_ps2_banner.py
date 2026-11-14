"""PS2 版のオプション画面バナーによる曲の特定のテスト"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.banner_reader import banner_feature, decode_feature  # noqa: E402
from src.ps2_banner import BANNER_BOXES, BANNER_QUADS, Ps2BannerIndex, crop_option_banner, read_option_banner  # noqa: E402


def _banner(seed: int, size=(631, 132)) -> Image.Image:
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (8, 32, 3), dtype=np.uint8)
    return Image.fromarray(small).resize(size, Image.Resampling.NEAREST)


def _screen(banner: Image.Image, title="popn7", size=(1325, 994), popup=False) -> Image.Image:
    im = Image.new("RGB", size, (30, 20, 90))
    w, h = size
    x0, y0, x1, y1 = (round(v * s) for v, s in zip(BANNER_BOXES[title], (w, h, w, h)))
    im.paste(banner.resize((x1 - x0, y1 - y0)), (x0, y0))
    if popup:   # 暗くして、下半分を隠す
        dark = Image.eval(im.crop((x0, y0, x1, y1)), lambda v: v * 6 // 10)
        im.paste(dark, (x0, y0))
        ImageDraw.Draw(im).rectangle((x0, (y0 + y1) // 2, x1, y1 + 50), fill=(255, 100, 0))
    return im


class Ps2BannerTest(unittest.TestCase):
    def setUp(self):
        self.banners = {f"s{i}": _banner(i) for i in range(30)}
        self.index = Ps2BannerIndex([(k, banner_feature(b), ["popn7"]) for k, b in self.banners.items()])

    def test_clear_state(self):
        for key in ("s3", "s17"):
            feature = read_option_banner(_screen(self.banners[key]), "popn7")
            self.assertEqual(self.index.match(feature, "popn7")[0], key)

    def test_popup_state_uses_top_half(self):
        feature = read_option_banner(_screen(self.banners["s5"], popup=True), "popn7")
        self.assertEqual(self.index.match(feature, "popn7")[0], "s5")

    def test_resolution_independent(self):
        feature = read_option_banner(_screen(self.banners["s9"], size=(640, 480)), "popn7")
        self.assertEqual(self.index.match(feature, "popn7")[0], "s9")

    def test_other_title_and_unknown_banner(self):
        feature = read_option_banner(_screen(self.banners["s3"]), "popn7")
        self.assertIsNone(self.index.match(feature, "popn99"))   # 収録タイトルが違う曲は照合しない
        self.assertIsNone(self.index.match(banner_feature(_banner(999)), "popn7"))
        self.assertIsNone(read_option_banner(_screen(self.banners["s3"]), "popn99"))   # 位置が未登録

    def test_weak_match_is_rejected(self):
        """登録していない曲のバナーが、別の曲に 0.8 程度の相関で一致しても、採用しない。"""
        base = banner_feature(self.banners["s1"])
        other = banner_feature(self.banners["s2"])
        mixed = base * 0.8 + other * 0.6     # base との相関は約 0.8
        mixed = mixed / np.linalg.norm(mixed)
        self.assertGreater(float(mixed @ base), 0.75)
        self.assertLess(float(mixed @ base), 0.9)
        self.assertIsNone(self.index.match(mixed, "popn7"))

    def test_quad_banner_is_straightened(self):
        """歪んで表示される作品 (popn14) は、4 隅を長方形に補正して切り出す。傾いた表示でも元の絵と相関する。"""
        w, h = 1325, 994
        banner = self.banners["s4"]
        canvas = Image.new("RGB", (w, h), (30, 120, 30))
        # 4 隅 (左上, 右上, 右下, 左下) の平行四辺形に banner を貼る: 逆変換で canvas 側から banner を引く
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = (
            (x * w, y * h) for x, y in BANNER_QUADS["popn14"])
        ys, xs = np.mgrid[0:h, 0:w]
        bw, bh = banner.size
        # 平行四辺形 (TL, TR, BL から BR が決まる) の座標系 (u, v) を逆算する
        ax, ay = trx - tlx, try_ - tly
        bx, by = blx - tlx, bly - tly
        det = ax * by - ay * bx
        u = ((xs - tlx) * by - (ys - tly) * bx) / det
        v = (ax * (ys - tly) - ay * (xs - tlx)) / det
        inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        src = np.asarray(banner.convert("RGB"))
        arr = np.asarray(canvas).copy()
        arr[inside] = src[(v[inside] * bh).astype(int), (u[inside] * bw).astype(int)]
        screen = Image.fromarray(arr)
        crop = crop_option_banner(screen, "popn14")
        self.assertEqual(crop.size, (640, 128))
        feature = read_option_banner(screen, "popn14")
        self.assertGreater(float(feature @ banner_feature(banner)), 0.9)
        self.assertEqual(Ps2BannerIndex([(k, banner_feature(b), ["popn14"]) for k, b in self.banners.items()])
                         .match(feature, "popn14")[0], "s4")

    def test_screenshots(self):
        """実際の画面 (screenshots/ はリポジトリに無いので、あるときだけ)。"""
        files = sorted((ROOT / "screenshots" / "popn7" / "option").glob("*.png"))
        listing = ROOT / "ps2_music_list.json"
        if not files or not listing.exists():
            self.skipTest("screenshots/popn7/option が無い")
        songs = json.loads(listing.read_text(encoding="utf-8"))
        index = Ps2BannerIndex([(s["music_id"], decode_feature(s["banner"]), s["titles"]) for s in songs if s["banner"]])
        found = set()
        for f in files:
            with Image.open(f) as im:
                got = index.match(read_option_banner(im, "popn7"), "popn7")
            self.assertIsNotNone(got, f.name)
            found.add(got[0])
        self.assertEqual(len(found), 1)   # 7 枚とも同じ曲 (マシュマロ・マーチ)
        title = next(s["title"] for s in songs if s["music_id"] in found)
        self.assertEqual(title, "マシュマロ・マーチ")


class RegisterToolTest(unittest.TestCase):
    def test_find_and_register(self):
        import tempfile
        sys.path.insert(0, str(ROOT / "tools"))
        from register_ps2_banners import find_songs, popup_open, register
        songs = [{"music_id": "a", "title": "silent green", "titles": ["popn8"], "banner": ""},
                 {"music_id": "b", "title": "silent green", "titles": ["popn9"], "banner": ""},
                 {"music_id": "c", "title": "Silent Night", "titles": ["popn8"], "banner": ""}]
        self.assertEqual([s["music_id"] for s in find_songs(songs, "popn8", "silent green")], ["a"])
        self.assertEqual(len(find_songs(songs, "popn8", "silent")), 2)   # 部分一致で複数 = 絞り込みが必要
        self.assertEqual(find_songs(songs, "popn8", "nothing"), [])
        feature = banner_feature(_banner(1))
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "banners.json"
            register(songs, "a", feature, reg)
            self.assertEqual(json.loads(reg.read_text(encoding="utf-8"))["a"], songs[0]["banner"])
        self.assertTrue(np.allclose(decode_feature(songs[0]["banner"]) @ feature, 1.0, atol=0.02))
        self.assertTrue(popup_open(_screen(_banner(2), popup=True), "popn7"))
        self.assertFalse(popup_open(_screen(_banner(2)), "popn7"))


if __name__ == "__main__":
    unittest.main()
