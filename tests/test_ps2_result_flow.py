"""PS2 版: リザルト画面の目印・曲の特定・記録までの流れのテスト (screenshots/ が無い環境では画像を使うテストを飛ばす)"""
import glob
import os
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.makedirs(ROOT / "log", exist_ok=True)

from src.ps2_marks import MarkTemplates, read_marks  # noqa: E402

HAS_SHOTS = (ROOT / "screenshots").exists()


def _image(title_dir: str, screen: str, stamp: str) -> Image.Image:
    found = glob.glob(str(ROOT / "screenshots" / title_dir / screen / f"*{stamp}.png"))
    if not found:
        pytest.skip(f"画像がありません: {title_dir}/{screen}/{stamp}")
    return Image.open(found[0]).convert("RGB")


def test_marks_without_templates_are_undetermined():
    """参照が無い (見本が無い) 作品・目印は、有ると誤認せず判定しない。"""
    marks = read_marks(Image.new("RGB", (1325, 994), (200, 0, 0)), "popn7", MarkTemplates())
    assert (marks.failed, marks.new_record) == (None, None)


@pytest.mark.skipif(not HAS_SHOTS, reason="screenshots/ がありません")
def test_marks_on_real_results():
    got = read_marks(_image("popn12", "result", "152100"), "popn12")
    assert (got.failed, got.new_record) == (True, True)           # 判子の NEW RECORD あり
    got = read_marks(_image("popn12", "result", "152121"), "popn12")
    assert (got.failed, got.new_record) == (True, False)          # NEW RECORD なし
    got = read_marks(_image("popn10", "result", "150537"), "popn10")
    assert got.new_record is True
    got = read_marks(_image("popn10", "result", "150624"), "popn10")
    assert got.new_record is False
    assert read_marks(_image("popn13", "result", "153704"), "popn13").new_record is None   # 枠が未登録


def test_failed_is_stored_and_unknown_is_kept():
    from src.classes import PopnScoreRecord
    from src.db import PopnDatabase
    db = PopnDatabase(os.path.join(tempfile.mkdtemp(), "popn.db"))
    try:
        with db._conn:
            db._conn.execute("INSERT INTO musics (music_id, title) VALUES ('m', 't')")
        for i, f in enumerate((True, False, None)):
            db.save_score(PopnScoreRecord(music_id="m", score=i, difficulty="H", failed=f))
        assert [r.failed for r in db.load_scores()] == [True, False, None]
    finally:
        db.close()


def test_ps2_music_list_import_keeps_titles():
    from src.db import PopnDatabase
    db = PopnDatabase(os.path.join(tempfile.mkdtemp(), "popn.db"))
    try:
        assert db.import_music_list_json(str(ROOT / "ps2_music_list.json"), update_json=False) > 600
        rows = db.ps2_song_rows()
        assert len(rows) > 600
        assert all(r["titles"] for r in rows)
        assert any("popn7" in r["titles"] and "besthits" in r["titles"] for r in rows)   # 複数作品に収録された曲
        # レベルは PS2 当時の基準 (*_old) が入る
        music = db.get_music(rows[0]["music_id"])
        assert music["normal"] is None or isinstance(music["normal"], int)
    finally:
        db.close()


@pytest.mark.skipif(not HAS_SHOTS, reason="screenshots/ がありません")
def test_song_is_identified_from_option_and_result_banners():
    from src.ps2_songs import Ps2SongIdentifier
    from src.score_manager import ScoreManager
    d = tempfile.mkdtemp()
    sm = ScoreManager(db_path=os.path.join(d, "popn.db"), csv_path=os.path.join(d, "s.csv"),
                      music_json_path=str(ROOT / "ps2_music_list.json"))
    try:
        ident = Ps2SongIdentifier(sm.db.ps2_song_rows())
        names = {r["music_id"]: r["title"] for r in sm.db.ps2_song_rows()}
        assert names[ident.identify_option(_image("popn11", "option", "151018"), "popn11")] == "Space Dog"
        assert ident.identify_result(_image("popn11", "result", "151218"), "popn11") == ""   # 文字だけのリザルト
        assert names[ident.identify_result(_image("popn14", "result", "154122"), "popn14")] == "遠く"
        assert names[ident.identify_result(_image("popn13", "result", "153704"), "popn13")] == "Infinity Blue"
        # 作品が違えば、同じ画像でも別作品の曲としては特定しない
        assert ident.identify_option(_image("popn11", "option", "151018"), "popn12") == ""
    finally:
        sm.db.close()


@pytest.mark.skipif(not HAS_SHOTS, reason="screenshots/ がありません")
def test_result_is_read_and_recorded_with_title_and_marks():
    """作品を確定 → リザルトの値と目印を読む → 記録に作品・曲が付く、までの流れ。"""
    from src.screen_reader import ScreenReader
    from src.score_manager import ScoreManager
    d = tempfile.mkdtemp()
    sm = ScoreManager(db_path=os.path.join(d, "popn.db"), csv_path=os.path.join(d, "s.csv"),
                      music_json_path=str(ROOT / "ps2_music_list.json"))
    try:
        reader = ScreenReader()
        option = _image("popn11", "option", "151018")
        result = _image("popn11", "result", "151218")
        for _ in range(3):
            reader.detect_mode(result)
        sm.set_current_title_id(reader.current_title)
        sm.set_play_environment("pcsx2", False)
        music_id = sm.identify_screen_song(option, reader.current_title, "option")
        assert music_id
        sm.identify_music(music_id, "")
        values = reader.read_result_values(result)
        assert values is not None and values.failed is True and values.new_record
        record = reader.read_result(result, options=sm.current_options, title=sm.current_song_title, values=values)
        assert sm.add_record(record, min_interval_sec=0)
        saved = sm.db.load_scores()[-1]
        assert (saved.title_id, saved.title, saved.score, saved.cool, saved.bad, saved.combo) == \
               ("popn11", "Space Dog", 21623, 29, 137, 37)
        assert (saved.platform, saved.modernize_patch) == ("pcsx2", False)
        assert saved.failed is True                                  # クリア失敗 (PS2 に retire は無い)
        sm.db.export_csv(os.path.join(d, "out.csv"))
        sm.db.delete_scores([saved.record_id])
        assert sm.db.import_csv(os.path.join(d, "out.csv")) == 1
        assert sm.db.load_scores()[-1].failed is True                # CSV の往復で保持される
    finally:
        sm.db.close()
