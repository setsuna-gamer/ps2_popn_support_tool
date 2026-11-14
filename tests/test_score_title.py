"""スコア記録に、プレーした作品 (title_id) が付くことのテスト"""
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs(os.path.join(ROOT, "log"), exist_ok=True)

from src.classes import PopnScoreRecord  # noqa: E402
from src.db import CSV_HEADERS, PopnDatabase  # noqa: E402
from src.play_env import modernize_text, parse_modernize, platform_code, platform_name  # noqa: E402
from src.titles import title_name, title_short_name  # noqa: E402


def _add_music(db: PopnDatabase, music_id="m1") -> None:
    with db._conn:
        db._conn.execute("INSERT INTO musics (music_id, title) VALUES (?, ?)", (music_id, "テスト曲"))


class ScoreTitleTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "popn.db")
        self.db = PopnDatabase(self.path)
        _add_music(self.db)

    def tearDown(self):
        self.db.close()
        self._dir.cleanup()

    def test_saved_and_loaded(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=90000, difficulty="H", title_id="popn8"))
        self.db.save_score(PopnScoreRecord(music_id="m1", score=80000, difficulty="H"))   # 作品が不明の記録
        loaded = self.db.load_scores()
        self.assertEqual([r.title_id for r in loaded], ["popn8", ""])

    def test_update_keeps_title(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=90000, difficulty="H", title_id="popn9"))
        record = self.db.load_scores()[0]
        record.score = 95000
        self.db.update_score(record)
        self.assertEqual(self.db.load_scores()[0].title_id, "popn9")

    def test_csv_round_trip(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=90000, difficulty="H", title_id="besthits"))
        csv_path = os.path.join(self._dir.name, "out.csv")
        self.db.export_csv(csv_path)
        with open(csv_path, encoding="utf-8-sig") as f:
            header = f.readline().strip().split(",")
        self.assertEqual(header, CSV_HEADERS)
        self.assertIn("作品", header)
        with self.db._conn:
            self.db._conn.execute("DELETE FROM scores")
        self.assertEqual(self.db.import_csv(csv_path), 1)
        self.assertEqual(self.db.load_scores()[0].title_id, "besthits")

    def test_migrates_old_database(self):
        """作品の列が無い既存の DB を開くと、列が足されて既存の記録は作品なしになる。"""
        self.db.save_score(PopnScoreRecord(music_id="m1", score=70000, difficulty="N", title_id="popn7"))
        self.db.close()
        conn = sqlite3.connect(self.path)
        conn.execute("ALTER TABLE scores DROP COLUMN title_id")
        conn.commit()
        conn.close()
        self.db = PopnDatabase(self.path)
        loaded = self.db.load_scores()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title_id, "")

    def test_environment_saved_and_loaded(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=1, difficulty="H", platform="real", modernize_patch=False))
        self.db.save_score(PopnScoreRecord(music_id="m1", score=2, difficulty="H", platform="pcsx2", modernize_patch=True))
        self.db.save_score(PopnScoreRecord(music_id="m1", score=3, difficulty="H"))   # 環境が不明の記録
        loaded = self.db.load_scores()
        self.assertEqual([(r.platform, r.modernize_patch) for r in loaded],
                         [("real", False), ("pcsx2", True), ("", None)])
        record = loaded[2]
        record.score = 4
        record.platform, record.modernize_patch = "other", True
        self.db.update_score(record)
        self.assertEqual((self.db.load_scores()[2].platform, self.db.load_scores()[2].modernize_patch), ("other", True))

    def test_environment_csv_round_trip(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=1, difficulty="H", platform="real", modernize_patch=False,
                                           title_id="popn7"))
        self.db.save_score(PopnScoreRecord(music_id="m1", score=2, difficulty="H", platform="pcsx2", modernize_patch=True,
                                           title_id="popn7", timestamp="2026-01-02 03:04:05"))
        self.db.save_score(PopnScoreRecord(music_id="m1", score=3, difficulty="H", timestamp="2026-01-03 03:04:05"))
        csv_path = os.path.join(self._dir.name, "env.csv")
        self.db.export_csv(csv_path)
        with self.db._conn:
            self.db._conn.execute("DELETE FROM scores")
        self.assertEqual(self.db.import_csv(csv_path), 3)
        self.assertEqual(sorted((r.score, r.platform, r.modernize_patch) for r in self.db.load_scores()),
                         [(1, "real", False), (2, "pcsx2", True), (3, "", None)])

    def test_migrates_old_database_environment(self):
        self.db.save_score(PopnScoreRecord(music_id="m1", score=70000, difficulty="N", platform="real", modernize_patch=True))
        self.db.close()
        conn = sqlite3.connect(self.path)
        conn.execute("ALTER TABLE scores DROP COLUMN platform")
        conn.execute("ALTER TABLE scores DROP COLUMN modernize_patch")
        conn.commit()
        conn.close()
        self.db = PopnDatabase(self.path)
        loaded = self.db.load_scores()
        self.assertEqual((loaded[0].platform, loaded[0].modernize_patch), ("", None))   # 既存の記録は環境不明

    def test_play_env_helpers(self):
        self.assertEqual((platform_code("実機"), platform_code("PCSX2"), platform_code("???"), platform_code("")),
                         ("real", "pcsx2", "", ""))
        self.assertEqual((platform_name("real"), platform_name(""), platform_name("x")), ("実機", "", "x"))
        self.assertEqual([parse_modernize(v) for v in ("1", "0", "", None, "あり", 1, True)],
                         [True, False, None, None, True, True, True])
        self.assertEqual([modernize_text(v) for v in (True, False, None)], ["あり", "なし", ""])

    def test_titles(self):
        self.assertEqual(title_name("popn12"), "pop'n music 12 いろは")
        self.assertEqual(title_short_name("besthits"), "best hits!")
        self.assertEqual(title_name("popn99"), "popn99")   # 未知の作品はそのまま


class ScoreManagerTitleTest(unittest.TestCase):
    def test_record_gets_current_title(self):
        from src.score_manager import ScoreManager
        with tempfile.TemporaryDirectory() as d:
            manager = ScoreManager(db_path=os.path.join(d, "popn.db"), csv_path=os.path.join(d, "x.csv"),
                                   music_json_path=os.path.join(d, "none.json"))
            try:
                _add_music(manager.db)
                manager.set_current_title_id("popn10")
                manager.set_play_environment("pcsx2", True)
                self.assertTrue(manager.add_record(PopnScoreRecord(music_id="m1", score=1, difficulty="EX"),
                                                   min_interval_sec=0))
                # 明示した作品は上書きしない
                self.assertTrue(manager.add_record(PopnScoreRecord(music_id="m1", score=2, difficulty="EX",
                                                                   title_id="popn7"), min_interval_sec=0))
                self.assertEqual([r.title_id for r in manager.db.load_scores()], ["popn10", "popn7"])
                # 設定の環境が記録に付く。記録側で明示していればそちらを優先する
                self.assertTrue(manager.add_record(PopnScoreRecord(music_id="m1", score=3, difficulty="EX",
                                                                   platform="real", modernize_patch=False),
                                                   min_interval_sec=0))
                self.assertEqual([(r.platform, r.modernize_patch) for r in manager.db.load_scores()],
                                 [("pcsx2", True), ("pcsx2", True), ("real", False)])
                manager.reset_current_song()   # 曲が変わっても作品は保持する
                self.assertEqual(manager.current_title_id, "popn10")
            finally:
                manager.db.close()


if __name__ == "__main__":
    unittest.main()
