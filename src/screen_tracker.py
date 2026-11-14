"""プレー中の作品 (タイトル) の追跡と、画面モードの識別

`src/screen_profile.py` の識別 (1 フレームごとの (タイトル, モード)) を、連続したフレームで安定させる。

- タイトル未確定: 全作品のテンプレートで識別し、同じタイトルが CONFIRM_FRAMES 回続いたら確定する。
- タイトル確定後: そのタイトルのテンプレートだけでモードを識別する。黒一色のロード画面のように、
  作品をまたいで見た目が同じ画面でも、確定した作品の中なら決められる。
- 別の作品に切り替わった判定 (全作品で識別して、確定中のタイトルと別の作品が明確に勝つ) が SWITCH_FRAMES 回続いたら
  タイトルを切り替える。1 フレームだけの別作品の判定 (画面の遷移中など) では切り替えない。
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from src.classes import DetectMode
from src.screen_profile import Identification, ScreenProfiles, cell_features

CONFIRM_FRAMES = 3
SWITCH_FRAMES = 5
_ASPECT = 4 / 3
_ASPECT_TOLERANCE = 0.02

# 画面識別のモード名 (src/screen_profile.py / tools/build_screen_profiles.py) → DetectMode
MODE_TO_DETECT = {
    "title": DetectMode.title,
    "mode_select": DetectMode.mode_select,
    "character_select": DetectMode.character_select,
    "music_select": DetectMode.select,
    "freetraining": DetectMode.freetraining,
    "option": DetectMode.option,
    "play": DetectMode.play,
    "result": DetectMode.result,
    "loading": DetectMode.loading,
}


def to_4x3(image: Image.Image) -> Image.Image:
    """4:3 でない入力 (レターボックス・ウィンドウ枠で比率が違うもの) を、中央で 4:3 に切り出す。"""
    w, h = image.size
    if h == 0 or abs(w / h - _ASPECT) <= _ASPECT * _ASPECT_TOLERANCE:
        return image
    if w / h > _ASPECT:
        cw = round(h * _ASPECT)
        x0 = (w - cw) // 2
        return image.crop((x0, 0, x0 + cw, h))
    ch = round(w / _ASPECT)
    y0 = (h - ch) // 2
    return image.crop((0, y0, w, y0 + ch))


@dataclass
class ScreenState:
    title: str | None          # 確定したタイトル (title_id)。未確定なら None
    mode_name: str | None      # このフレームで識別したモード名。識別できなければ None
    mode: DetectMode           # mode_name に対応する DetectMode (対応が無い・識別できなければ unknown)


class ScreenTracker:
    def __init__(self, profiles: ScreenProfiles | None = None):
        self.profiles = profiles if profiles is not None else _load_default()
        self.reset()

    def reset(self) -> None:
        """確定したタイトルと投票を捨てる (ゲームを切り替えたときなど)。"""
        self.title: str | None = None
        self._pending: str | None = None
        self._pending_count = 0

    def update(self, image: Image.Image) -> ScreenState:
        ranked = self.profiles.scores_from_features(cell_features(to_4x3(image)))
        overall = ScreenProfiles.decide(ranked)

        if self.title is None:
            # タイトル未確定: 全作品の識別結果で投票する
            if overall is None:
                self._pending, self._pending_count = None, 0
            elif self._vote(overall.title, CONFIRM_FRAMES):
                self.title = overall.title
            current = overall
        else:
            if overall is not None and overall.title != self.title:
                if self._vote(overall.title, SWITCH_FRAMES):
                    self.title = overall.title
            else:
                self._pending, self._pending_count = None, 0
            # モードは確定したタイトルのテンプレートだけで決める
            current = ScreenProfiles.decide([r for r in ranked if r.title == self.title])

        return self._state(current)

    def _vote(self, title: str, needed: int) -> bool:
        """title への投票を 1 つ足し、needed 回続いたら True (投票は空にする)。"""
        if title == self._pending:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = title, 1
        if self._pending_count >= needed:
            self._pending, self._pending_count = None, 0
            return True
        return False

    def _state(self, ident: Identification | None) -> ScreenState:
        name = ident.mode if ident else None
        return ScreenState(self.title, name, MODE_TO_DETECT.get(name, DetectMode.unknown))


def _load_default() -> ScreenProfiles:
    try:
        return ScreenProfiles.load()
    except (OSError, ValueError, KeyError):
        return ScreenProfiles([])   # 生成物が無いときは、何も識別しない (unknown のまま)
