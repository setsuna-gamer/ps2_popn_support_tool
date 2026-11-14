"""PS2 版のリザルト・プレー画面の数字の読み取りのテスト (screenshots/ が無い環境では画像を使うテストを飛ばす)"""
import glob
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ps2_numbers import DigitTemplates, Glyph, segment  # noqa: E402
from src.ps2_readers import ResultValues, missing_digits, read_result, supported  # noqa: E402

SAMPLES = json.loads((ROOT / "tools" / "ps2_number_samples.json").read_text(encoding="utf-8"))["samples"]


def _image(ref: str) -> Image.Image | None:
    title, screen, stamp = ref.split("/")
    folder = "popnbesthits" if title == "besthits" else title
    found = glob.glob(str(ROOT / "screenshots" / folder / screen / f"*{stamp}.png"))
    return Image.open(found[0]).convert("RGB") if found else None


def test_result_values_consistency():
    ok = ResultValues(cool=10, great=5, good=3, bad=2, combo=9, stage_score=1000, total_score=1000)
    assert ok.consistent()
    assert not ResultValues(10, 5, 3, 2, 21, 1000, 1000).consistent()      # コンボが総ノーツ数を超える
    assert not ResultValues(10, 5, 3, 2, 9, 1000, 900).consistent()        # 累計スコアが今回のスコア未満


def test_unsupported_title_is_not_read():
    img = Image.new("RGB", (1325, 994), (200, 200, 200))
    assert not supported("popn99", "result")
    assert read_result(img, "popn99") is None
    assert missing_digits("popn99", "result") == "0123456789"


def test_incomplete_templates_are_not_read():
    """0～9 が揃っていないテンプレートでは、見本に無い数字を取り違えないよう読まない。"""
    import numpy as np
    shape = np.zeros((24, 16), dtype=np.float32)
    tpl = DigitTemplates({("popn11", "result"): {"0": [Glyph(shape, 0.7, 0)]}})
    assert missing_digits("popn11", "result", tpl) == "123456789"
    assert read_result(Image.new("RGB", (1325, 994)), "popn11", tpl) is None


def test_segment_splits_digits():
    arr = np_digits()
    assert len(segment(arr)) == 3


def np_digits():
    import numpy as np
    img = np.full((60, 200, 3), 230, dtype=np.uint8)
    for x0 in (20, 80, 140):
        img[10:50, x0:x0 + 30] = (20, 20, 120)
    return img


@pytest.mark.skipif(not (ROOT / "screenshots").exists(), reason="screenshots/ がありません")
def test_result_samples_are_read():
    """正解値を付けたリザルト画面を、(数字が揃っている作品では) 正しく読める。"""
    checked = 0
    for s in SAMPLES:
        title, screen, _ = s["image"].split("/")
        if screen != "result" or not supported(title, "result"):
            continue
        img = _image(s["image"])
        if img is None:
            continue
        got = read_result(img, title)
        assert got is not None, s["image"]
        for name, label in s["values"].items():
            assert getattr(got, name) == int(label), (s["image"], name)
        checked += 1
    assert checked > 0


@pytest.mark.skipif(not (ROOT / "screenshots").exists(), reason="screenshots/ がありません")
def test_play_samples_are_read():
    from src.ps2_readers import read_play
    checked = 0
    for s in SAMPLES:
        title, screen, _ = s["image"].split("/")
        if screen != "play" or not supported(title, "play"):
            continue
        img = _image(s["image"])
        if img is None:
            continue
        got = read_play(img, title)
        assert got is not None
        for name, label in s["values"].items():
            read = getattr(got, name)
            # 読めなかった項目 (None) は許す。読めたのに違う値 (誤読) は許さない
            assert read is None or read == int(label), (s["image"], name, read, label)
            checked += read is not None
    assert checked > 0


@pytest.mark.skipif(not (ROOT / "screenshots").exists(), reason="screenshots/ がありません")
def test_screen_reader_uses_confirmed_title():
    """確定した作品のレイアウトで、リザルトの値を読む。作品が未確定なら読まない。"""
    from src.screen_reader import ScreenReader
    img = _image("popn11/result/151218")
    if img is None:
        pytest.skip("画像がありません")
    reader = ScreenReader()
    assert reader.read_result_values(img) is None          # 作品が未確定
    for _ in range(3):
        reader.detect_mode(img)
    assert reader.current_title == "popn11"
    got = reader.read_result_values(img)
    assert (got.cool, got.great, got.good, got.bad, got.combo, got.score) == (29, 5, 22, 137, 37, 21623)
