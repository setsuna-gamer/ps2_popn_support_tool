"""PS2 版の画面識別 (src/screen_profile.py) のテスト。screenshots/ の画像が無い環境では画像を使うテストを飛ばす。"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from src.screen_profile import ScreenProfiles  # noqa: E402

PROFILE = ROOT / "src" / "screen_profiles.json"
SHOTS = ROOT / "screenshots"


def _trained_samples(profiles):
    """screenshots/ の画像のうち、テンプレートを作ってある作品のもの (画像だけ先に増えている作品は除く)。"""
    from build_screen_profiles import load_samples
    titles = {t.title for t in profiles.templates}
    return [s for s in load_samples(SHOTS) if s.title in titles]


@pytest.fixture(scope="module")
def profiles():
    if not PROFILE.exists():
        pytest.skip("screen_profiles.json がありません (tools/build_screen_profiles.py で生成)")
    return ScreenProfiles.load(PROFILE)


def test_blank_and_noise_frames_are_not_identified(profiles):
    black = Image.new("RGB", (1325, 994), (0, 0, 0))
    noise = Image.fromarray(np.random.default_rng(0).integers(0, 255, (994, 1325, 3), dtype=np.uint8))
    assert profiles.identify(noise) is None
    # 黒一色は loading の一部と似るため、少なくとも他のモードとは判定されない
    got = profiles.identify(black)
    assert got is None or got.mode == "loading"


@pytest.mark.skipif(not SHOTS.exists(), reason="screenshots/ がありません")
def test_training_images_are_identified(profiles):
    samples = _trained_samples(profiles)
    assert samples
    for s in samples:
        # 実行時 (src/screen_tracker.py) と同じく、モードは確定した作品のテンプレートだけで決める
        scores = [r for r in profiles.scores_from_features(s.features) if r.title == s.title]
        got = ScreenProfiles.decide(scores)
        assert got is not None and got.mode == s.mode, s.path.name


def test_resolution_independence(profiles):
    """同じ 4:3 の画像は、解像度を変えても同じ画面と判定される。"""
    if not SHOTS.exists():
        pytest.skip("screenshots/ がありません")
    s = _trained_samples(profiles)[0]
    with Image.open(s.path) as im:
        small = im.convert("RGB").resize((640, 480), Image.Resampling.BILINEAR)
    from src.screen_profile import cell_features
    scores = [r for r in profiles.scores_from_features(cell_features(small)) if r.title == s.title]
    got = ScreenProfiles.decide(scores)
    assert got is not None and got.mode == s.mode


def _ranked(*items):
    from src.screen_profile import Identification
    return [Identification(t, m, s, f"{t}/{m}") for t, m, s in items]


def test_title_wins_over_mode_select_when_ambiguous():
    """タイトル画面のメニュー選択中の状態はモード選択と紛れやすいので、迷ったら title に寄せる。"""
    got = ScreenProfiles.decide(_ranked(("popn9", "mode_select", 0.90), ("popn9", "title", 0.88), ("popn9", "play", 0.1)))
    assert (got.title, got.mode) == ("popn9", "title")
    # 先頭が title のときも title (従来どおり、差が小さければ迷ったことになるが、title に寄せる)
    got = ScreenProfiles.decide(_ranked(("popn9", "title", 0.90), ("popn9", "mode_select", 0.85)))
    assert got.mode == "title"
    # 差が十分あれば、その画面のまま
    got = ScreenProfiles.decide(_ranked(("popn9", "mode_select", 0.95), ("popn9", "title", 0.40)))
    assert got.mode == "mode_select"
    # title と mode_select 以外が競っているとき、別の作品が競っているときは寄せない
    assert ScreenProfiles.decide(_ranked(("popn9", "play", 0.90), ("popn9", "title", 0.88))) is None
    assert ScreenProfiles.decide(_ranked(("popn9", "mode_select", 0.90), ("popn10", "title", 0.88))) is None
    # title の採用の最低スコアに満たないときは決めない
    assert ScreenProfiles.decide(_ranked(("popn9", "mode_select", 0.52), ("popn9", "title", 0.49))) is None


def test_title_like_mode_select_images_are_relabeled(capsys):
    from build_screen_profiles import Sample, relabel_title_like
    from src.screen_profile import CELLS, CellFeatures
    rng = np.random.default_rng(1)

    def feat(base):
        return CellFeatures(np.clip(base + rng.normal(0, 3, (CELLS, 3)), 0, 255).astype(np.float32))

    title_look, other_look = rng.uniform(0, 255, (CELLS, 3)), rng.uniform(0, 255, (CELLS, 3))
    samples = [
        Sample(Path("t.png"), "popn9", "title", feat(title_look), []),
        Sample(Path("menu.png"), "popn9", "mode_select", feat(title_look), []),     # タイトルの menu 状態 = 見た目が同じ
        Sample(Path("real.png"), "popn9", "mode_select", feat(other_look), []),     # 本物のモード選択
        Sample(Path("menu10.png"), "popn10", "mode_select", feat(title_look), []),  # 同じ作品のタイトル画面が無ければそのまま
        Sample(Path("load_t.png"), "popn9", "loading", feat(title_look), []),        # ロードのフォルダに入ったタイトル画面
        Sample(Path("load.png"), "popn9", "loading", feat(other_look), []),          # 本物のロード画面
    ]
    relabel_title_like(samples)
    assert [s.mode for s in samples] == ["title", "title", "mode_select", "mode_select", "title", "loading"]
