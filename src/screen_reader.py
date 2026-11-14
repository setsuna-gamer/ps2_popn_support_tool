"""pop'n music (PS2) 画面状態検出・判定内訳読み取り"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np
from PIL import Image

from src.classes import DetectMode, PopnJudge, PopnOptions, PopnScoreRecord, ResultValues
JUDGE_NAMES = ("cool", "great", "good", "bad")
from src.logger import get_logger
from src.option_reader import read_option_icons, read_option_list
from src.ps2_marks import read_marks
from src.ps2_readers import read_play, read_result
from src.screen_tracker import ScreenTracker
from src.song_info import PlaySongInfo

logger = get_logger(__name__)

# 判定内訳: 1 フレームでこれを超えて増えた値は、次のフレームでも裏付けが取れてから採用する
_JUDGE_MAX_STEP = 20
# 判定内訳: 全判定が減った状態がこのフレーム数続いたら、次の曲 (またはリトライ) が始まったとみなす
_JUDGE_RESTART_FRAMES = 5


class ScreenReader:
    """pop'n music (PS2) の画面状態検出と判定内訳読み取りを担う。

    判定内訳の読み取り方針:
        プレー画面下部バーに「BAD 0010 GOOD 0010 GREAT 0003 COOL 0003」が
        リアルタイムで表示される。この累計値を数字として読み取り (src/ps2_readers.py)、
        読み誤りを弾きながら曲ごとの判定内訳として保持する。
    """

    def __init__(self, tracker: ScreenTracker | None = None):
        self.tracker = tracker if tracker is not None else ScreenTracker()
        self.reset_judge()

    def reset_judge(self) -> None:
        """保持している判定内訳をリセットする（スコア記録後・カウントリセット時）。"""
        self._judge = dict.fromkeys(JUDGE_NAMES, 0)
        self._judge_pending: dict[str, int] = {}
        self._judge_restart_frames = 0

    # ------------------------------------------------------------------
    # 画面状態検出
    # ------------------------------------------------------------------

    def is_valid_game_screen(self, image: Image.Image) -> bool:
        """有効なゲーム画面が取り込めているかどうかを判定する。
        OBS接続中に対象ウィンドウが未起動・フック前・最小化中などの場合、
        完全な黒画面（全ピクセル0）または極めて低輝度・無変化の画像が返される。
        """
        try:
            # 高速化のため縮小してピクセル統計を計算 (160x90)
            small = image.resize((160, 90), Image.Resampling.NEAREST)
            arr = np.array(small)
            # 黒画面または極端な低輝度の場合は未取得
            if arr.max() < 25 or arr.mean() < 8.0:
                return False
            # 単色ブランク画面の排除
            return bool(arr.std() >= 5.0)
        except Exception:
            return False


    def detect_mode(self, image: Image.Image) -> DetectMode:
        """現在の画面状態を返す (PS2 版: タイトル × モードの識別。src/screen_tracker.py)。

        黒画面・未取得時は unknown。作品 (タイトル) は `current_title` に確定する。
        """
        if not self.is_valid_game_screen(image):
            return DetectMode.unknown
        return self.tracker.update(image).mode

    @property
    def current_title(self) -> str | None:
        """確定した作品 (title_id: popn7 など)。未確定なら None。"""
        return self.tracker.title

    def reset_title(self) -> None:
        """確定した作品を捨てる (ゲームの切り替え・取り込みのやり直しなど)。"""
        self.tracker.reset()


    # ------------------------------------------------------------------
    # 判定内訳読み取り
    # ------------------------------------------------------------------

    def detect_judge(self, image: Image.Image) -> tuple[PopnJudge, bool]:
        """プレー画面から現在の曲の判定内訳 (累計値) を読み取る。

        累計値は増える一方なので、減った値や急に増えた値は読み誤りとして採用しない。
        読めなかった判定は直前の値のまま。

        Returns:
            (判定内訳の累計値, 次の曲の開始を検出して累計値が巻き戻ったか)
        """
        counts = dict.fromkeys(JUDGE_NAMES)
        title = self.current_title
        if title:
            try:
                play = read_play(image, title)
            except Exception as e:
                logger.error("プレー画面の判定読み取りエラー: %s", e)
                play = None
            if play is not None:
                counts = {name: getattr(play, name) for name in JUDGE_NAMES}
        current = self._judge

        # 全判定が読めていて大きく減っている状態が続く → 次の曲が始まり 0 から数え直している
        restarted = False
        if (
            None not in counts.values()
            and all(counts[n] <= current[n] for n in JUDGE_NAMES)
            and sum(counts.values()) * 2 <= sum(current.values())
            and sum(current.values()) > 0
        ):
            self._judge_restart_frames += 1
            if self._judge_restart_frames >= _JUDGE_RESTART_FRAMES:
                self.reset_judge()
                current = self._judge
                restarted = True
        else:
            self._judge_restart_frames = 0

        for name in JUDGE_NAMES:
            value = counts[name]
            if value is None or value < current[name]:
                continue
            base = current[name]
            if value > base + _JUDGE_MAX_STEP:
                # 急な増加は、前フレームの値からも無理なく続いている場合だけ採用する
                base = self._judge_pending.get(name, -1)
                if not base <= value <= base + _JUDGE_MAX_STEP:
                    self._judge_pending[name] = value
                    continue
            self._judge_pending.pop(name, None)
            current[name] = value

        return PopnJudge(**current), restarted

    # ------------------------------------------------------------------
    # オプション認識 (オプション画面)
    # ------------------------------------------------------------------

    def read_options(self, image: Image.Image) -> dict[str, str] | None:
        """オプション画面から使用オプションを読み取る。

        設定を開いている間は右下の設定一覧、開いていない OptionSelect 画面では
        オプションアイコンから読む。戻り値は {項目キー: 値} (読めなかった項目は含まない)。
        どちらも表示されていなければ None。
        """
        try:
            values = read_option_list(image)
            return values if values is not None else read_option_icons(image)
        except Exception as e:
            logger.error("オプション読み取りエラー: %s", e)
            return None

    # ------------------------------------------------------------------
    # 曲名認識 (プレー画面上部)
    # ------------------------------------------------------------------

    def read_play_song(self, image: Image.Image) -> PlaySongInfo:
        """プレー画面の曲名・難易度区分を読む (PS2 版は読まない)。

        PS2 版のプレー画面の曲名は画像フォントで OCR できず、難易度の表示も作品ごとに違う。曲はオプション画面のバナー
        (src/ps2_songs.py) で特定して使うので、ここは何も読まない (空)。
        """
        return PlaySongInfo()

    @staticmethod
    def save_unread_title(image: Image.Image) -> None:
        """曲を特定できなかったプレー画面の曲名バーを保存する (調査用)。"""
        # PS2 版は曲名バーを読まない (画像フォント)。オプション画面のバナーで曲を特定する (src/ps2_songs.py)
        return None

    # ------------------------------------------------------------------
    # リザルト画面認識
    # ------------------------------------------------------------------

    def read_result_values(self, image: Image.Image) -> ResultValues | None:
        """リザルト画面の数値を、確定した作品のレイアウトで読み取る (src/ps2_readers.py)。

        作品が未確定・未対応 (数字のテンプレートが揃っていない)・読めない項目がある・値のつじつまが合わない
        ときは None (呼び出し側がプレー中の集計値で補う)。
        """
        title = self.current_title
        if not title:
            return None
        try:
            r = read_result(image, title)
            if r is None:
                return None
            marks = read_marks(image, title)
            return ResultValues(score=r.stage_score, cool=r.cool, great=r.great, good=r.good, bad=r.bad,
                                combo=r.combo, score_verified=True,
                                # STAGE FAILED = クリア失敗 (PS2 に Retire は無い。src/ps2_marks.py)。
                                # 判定できない作品は None のまま
                                failed=marks.failed, new_record=bool(marks.new_record))
        except Exception as e:
            logger.error("リザルト読み取りエラー: %s", e)
            return None

    def read_result(
        self,
        image: Image.Image,
        live_judge: PopnJudge | None = None,
        options: PopnOptions | None = None,
        title: str = "Unknown",
        level: int | str = "",
        difficulty: str = "",
        values: ResultValues | None = None,
    ) -> PopnScoreRecord:
        """リザルト画面からスコア、COOL等の判定数、コンボ数を取得する。

        values を省略した場合は image から読み取る。
        読めなかった項目のみ、プレー中のライブ集計値 (live_judge) や推定値で補う。
        """
        if values is None:
            values = self.read_result_values(image)

        try:
            os.makedirs("out", exist_ok=True)
            image.save("out/last_result.png")
        except Exception:
            pass

        if values is None:
            logger.warning("リザルト: スコアパネルを検出できませんでした。ライブ集計値で代用します")
            values = ResultValues()
        if values.notes or not values.is_complete:
            for note in values.notes:
                logger.warning("リザルト読み取り: %s", note)
            self._save_unread_result(image)

        live = live_judge or PopnJudge()
        judge = {
            name: read if (read := getattr(values, name)) is not None else getattr(live, name)
            for name in JUDGE_NAMES
        }

        score = values.score
        if score is None:
            # スコア推定値 (画像から読めなかった場合の補助)
            total = sum(judge.values())
            weighted = judge["cool"] * 100000 + judge["great"] * 70000 + judge["good"] * 40000
            score = int(weighted / total) if total > 0 else 0

        return PopnScoreRecord(
            title=title,
            level=level,
            difficulty=difficulty,
            score=score,
            **judge,
            combo=values.combo if values.combo is not None else 0,
            options=options or PopnOptions(),
            failed=values.failed,
        )

    @staticmethod
    def _save_unread_result(image: Image.Image) -> None:
        """読み取りに不確かな点があったリザルト画面を保存する。

        tools/build_digit_templates.py の SAMPLES に正解値とともに追加すれば、
        未収録の数字のテンプレートを増やせる。
        """
        try:
            os.makedirs("out/result_unread", exist_ok=True)
            image.save(f"out/result_unread/{datetime.now():%Y%m%d_%H%M%S}.png")
        except Exception as e:
            logger.debug("未読リザルト保存失敗: %s", e)

