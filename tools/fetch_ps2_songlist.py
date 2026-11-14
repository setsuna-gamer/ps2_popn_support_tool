"""PS2 版 pop'n music (7 ～ 14, best hits!) の収録曲リスト HTML を pmdream.net から取得する (開発者用)

    python tools/fetch_ps2_songlist.py [出力フォルダ (既定: tmp_ps2_songlist)] [--force]

保存したファイルは generate_ps2_music_list.py が読む。取得は 9 ページだけで、2 秒以上あけて順に行う。
取得済みのファイルは再取得しない (--force で取得し直す)。
ページの文字コードは Shift_JIS (CP932) で、そのままのバイト列で保存する。
"""
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://pmdream.net/popn/{}/music.html"

# title_id → (ページ名, 表示名)。title_id はスコア・曲リスト・プロファイルで共通に使う
TITLES = {
    "popn7": ("cs7", "pop'n music 7"),
    "popn8": ("cs8", "pop'n music 8"),
    "popn9": ("cs9", "pop'n music 9"),
    "popn10": ("cs10", "pop'n music 10"),
    "popn11": ("cs11", "pop'n music 11"),
    "popn12": ("cs12", "pop'n music 12 いろは"),
    "popn13": ("cs13", "pop'n music 13 カーニバル"),
    "popn14": ("cs14", "pop'n music 14 FEVER!"),
    "besthits": ("csbest", "pop'n music best hits!"),
}
USER_AGENT = "ps2-popn-support-tool-songlist-fetcher"
INTERVAL_SEC = 2


def fetch(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as res:
                data = res.read()
            if b"<TABLE" not in data.upper():
                raise ValueError("表が見つかりません")
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"取得に失敗しました ({url}): {last}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv[1:]
    out = Path(args[0] if args else "tmp_ps2_songlist")
    out.mkdir(parents=True, exist_ok=True)
    fetched = False
    for title_id, (page, name) in TITLES.items():
        path = out / f"{page}.html"
        if path.exists() and not force:
            print(f"{path.name}: 取得済み ({name})")
            continue
        if fetched:
            time.sleep(INTERVAL_SEC)
        data = fetch(BASE.format(page))
        path.write_bytes(data)
        fetched = True
        print(f"{path.name}: {len(data)} バイト ({name})")


if __name__ == "__main__":
    main()
