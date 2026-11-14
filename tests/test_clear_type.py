from src.classes import PopnScoreRecord


def _r(cool=100, great=0, good=0, bad=0, failed=None):
    return PopnScoreRecord(cool=cool, great=great, good=good, bad=bad, failed=failed)


def test_clear_type():
    assert _r(great=5, good=0, bad=0).clear_type == "PERFECT"
    assert _r(good=3).clear_type == "FULLCOMBO"
    assert _r(bad=2, failed=False).clear_type == "CLEAR"
    assert _r(bad=2, failed=True).clear_type == "FAILED"
    assert _r(bad=2).clear_type == ""          # 失敗かどうか不明
    assert _r(cool=0).clear_type == ""         # 判定なし
