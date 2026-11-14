"""作品 (タイトル) の追跡と画面モードの識別のテスト"""
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.classes import DetectMode  # noqa: E402
from src.screen_profile import Identification, ScreenProfiles  # noqa: E402
from src.screen_tracker import CONFIRM_FRAMES, SWITCH_FRAMES, ScreenTracker, to_4x3  # noqa: E402

IMG = Image.new("RGB", (640, 480), (90, 60, 160))


class FakeProfiles:
    """フレームごとに決めたスコア表を返す (画像は見ない)。"""

    def __init__(self, frames):
        self.frames = iter(frames)
        self.templates = []

    def scores_from_features(self, _f):
        return [Identification(t, m, s, f"{t}/{m}") for t, m, s in next(self.frames)]


def _tracker(frames):
    return ScreenTracker(FakeProfiles(frames))   # type: ignore[arg-type]


def test_title_confirmed_after_consecutive_frames():
    play7 = [("popn7", "play", 0.9), ("popn8", "play", 0.2)]
    t = _tracker([play7] * (CONFIRM_FRAMES + 1))
    for _ in range(CONFIRM_FRAMES - 1):
        s = t.update(IMG)
        assert s.title is None and s.mode == DetectMode.play   # モードは確定前から分かる
    assert t.update(IMG).title == "popn7"


def test_unconfirmed_when_interrupted():
    a = [("popn7", "play", 0.9)]
    none = [("popn7", "play", 0.1)]
    t = _tracker([a, a, none, a, a, none])
    for _ in range(6):
        assert t.update(IMG).title is None


def test_mode_decided_within_confirmed_title():
    """黒一色のロード画面のように、作品をまたいで同じに見える画面は、確定した作品の中で決める。"""
    play7 = [("popn7", "play", 0.9)]
    loading = [("popn7", "loading", 1.0), ("popn8", "loading", 1.0)]   # 全体では作品が決まらない
    t = _tracker([play7] * CONFIRM_FRAMES + [loading])
    for _ in range(CONFIRM_FRAMES):
        t.update(IMG)
    s = t.update(IMG)
    assert (s.title, s.mode) == ("popn7", DetectMode.loading)


def test_title_switch_needs_consecutive_votes():
    p7 = [("popn7", "title", 0.9), ("popn8", "title", 0.1)]
    p8 = [("popn8", "title", 0.9), ("popn7", "title", 0.1)]
    # 1 フレームだけ別作品に見えても切り替えない
    t = _tracker([p7] * CONFIRM_FRAMES + [p8, p7, p7])
    for _ in range(CONFIRM_FRAMES + 3):
        s = t.update(IMG)
    assert s.title == "popn7"
    # 続けば切り替える
    t = _tracker([p7] * CONFIRM_FRAMES + [p8] * SWITCH_FRAMES)
    for _ in range(CONFIRM_FRAMES + SWITCH_FRAMES):
        s = t.update(IMG)
    assert s.title == "popn8"


def test_unmapped_mode_is_unknown():
    s = _tracker([[("popn8", "buttonselect", 0.9)]]).update(IMG)
    assert s.mode_name == "buttonselect" and s.mode == DetectMode.unknown


def test_to_4x3():
    assert to_4x3(Image.new("RGB", (1325, 994))).size == (1325, 994)
    assert to_4x3(Image.new("RGB", (1920, 1080))).size == (1440, 1080)    # 左右の余白を削る
    assert to_4x3(Image.new("RGB", (800, 800))).size == (800, 600)


def test_real_profiles_popn7():
    shots = ROOT / "screenshots" / "popn7" / "play"
    files = sorted(shots.glob("*.png")) if shots.exists() else []
    if not files:
        pytest.skip("screenshots/popn7/play が無い")
    t = ScreenTracker(ScreenProfiles.load())
    for _ in range(CONFIRM_FRAMES):
        with Image.open(files[0]) as im:
            s = t.update(im)
    assert (s.title, s.mode) == ("popn7", DetectMode.play)
    t.reset()
    assert t.title is None


def test_no_profiles_is_unknown():
    s = ScreenTracker(ScreenProfiles([])).update(IMG)
    assert s.title is None and s.mode == DetectMode.unknown
