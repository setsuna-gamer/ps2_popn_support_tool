"""PS2 版 pop'n music (7 ～ 14, best hits!) の静的曲リストを生成する (開発者用)

    python tools/fetch_ps2_songlist.py            # 先に HTML を取得する
    python generate_ps2_music_list.py [--existing popn_music_list.json] [--out ps2_music_list.json]

1. tmp_ps2_songlist/ の pmdream.net の HTML から、9 タイトルの収録曲を読む
2. 同じ曲 (曲名 + アーティスト) を 1 レコードにまとめ、収録タイトルを `titles` に持たせる
3. 既存の曲リスト (Lively 版) と照合し、一致した曲は music_id と banner を引き継ぎ、
   既存の難易度を *_current に移す。一致しなかった曲は新しい UUID を採番する
4. 結果と、確認が必要な曲 (照合できなかった・あいまいな曲) を表示する

難易度: pmdream の N / H / EX / 5 は PS2 当時の基準なので *_old とする (-: 譜面なし = null)。
EASY は現行のみなので持たない。
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import unicodedata
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tools"))
from fetch_ps2_songlist import TITLES  # noqa: E402

# 区分見出し → 区分コード。見出しの先頭の語で判定する (PS2 / アーケード / ee'MALL など)
_VERSION_RE = re.compile(r"(ＣＳ|ＡＣ|CS|AC)ポップン([０-９0-9]+)|pop'n music (\d+)")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("～", "〜").replace("’", "'").replace("‘", "'").replace("`", "'")
    # ö → o のように、ラテン文字のアクセントは外す (かな・漢字の濁点などは触らない)
    s = "".join(d[0] if len(d := unicodedata.normalize("NFD", c)) > 1 and d[0].isascii() else c for c in s)
    return "".join(s.split()).lower()


def artist_compatible(a: str, b: str) -> bool:
    """アーティスト名が同じとみなせるか。片方が空 (best hits は「-」)、または一方が他方を含む場合も同じとする。"""
    a, b = norm(a), norm(b)
    return not a or not b or a == b or a in b or b in a


def cell_text(c: str) -> str:
    c = re.sub(r"<[^>]+>", " ", c)
    return " ".join(html.unescape(c).split())


def parse_level(v: str):
    v = v.strip()
    return int(v) if v.isdigit() else None


def origin_of(section: str) -> str:
    """区分見出しから、その曲の出自 (pop'n music N / CS N / ee'MALL など) を返す。分からなければ空。"""
    m = _VERSION_RE.search(section)
    if m:
        kind = m.group(1)
        num = unicodedata.normalize("NFKC", m.group(2) or m.group(3))
        return f"{'AC' if kind in ('ＡＣ', 'AC') else 'CS'}{num}"
    if "ee'MALL" in section:
        return "ee'MALL"
    return ""


def parse_page(path: Path) -> list[dict]:
    """1 ページ分の曲を、出現順のリストで返す。"""
    text = path.read_bytes().decode("cp932", errors="replace")
    tables = re.findall(r"<TABLE.*?</TABLE>", text, re.S | re.I)
    table = next(t for t in tables if "ジャンル" in t)
    rows = re.findall(r"<TR[^>]*>(.*?)</TR>", table, re.S | re.I)
    header = [cell_text(c) for c in re.findall(r"<T[DH][^>]*>(.*?)</T[DH]>", rows[0], re.S | re.I)]
    col = {name: i for i, name in enumerate(header)}
    five = next((i for name, i in col.items() if name in ("5", "５")), None)
    note = next((i for name, i in col.items() if name in ("備考", "TIME")), None)

    songs, section = [], ""
    for r in rows[1:]:
        cells = [cell_text(c) for c in re.findall(r"<T[DH][^>]*>(.*?)</T[DH]>", r, re.S | re.I)]
        if len(cells) <= 2:
            section = cells[0] if cells else ""
            continue
        genre_i, title_i, artist_i, chara_i = 0, 1, 2, 3
        songs.append({
            "genre": cells[genre_i],
            "title": cells[title_i],
            "artist": "" if cells[artist_i] in ("-", "－") else cells[artist_i],
            "character": cells[chara_i],
            "normal_old": parse_level(cells[col["N"]]),
            "hyper_old": parse_level(cells[col["H"]]),
            "ex_old": parse_level(cells[col["EX"]]),
            "five": parse_level(cells[five]) if five is not None and five < len(cells) else None,
            "bpm": cells[col["BPM"]].lstrip("*").strip(),
            "section": section,
            "origin": origin_of(section),
            "note": cells[note] if note is not None and note < len(cells) and col.get("備考") == note else "",
        })
    return songs


def merge_pages(pages: dict[str, list[dict]]) -> list[dict]:
    """タイトルをまたいで同じ曲を 1 レコードにまとめる。"""
    merged: list[dict] = []
    by_title: dict[str, list[dict]] = {}
    for title_id, songs in pages.items():
        for s in songs:
            candidates = by_title.get(norm(s["title"]), [])
            target = None
            for c in candidates:
                if artist_compatible(c["artist"], s["artist"]):
                    target = c
                    break
            if target is None:
                target = {
                    "genre": s["genre"], "title": s["title"], "artist": s["artist"],
                    "character": s["character"], "bpm": s["bpm"],
                    "normal_old": None, "hyper_old": None, "ex_old": None, "five": None,
                    "titles": [], "per_title": {},
                }
                merged.append(target)
                by_title.setdefault(norm(s["title"]), []).append(target)
            if not target["artist"]:
                target["artist"] = s["artist"]
            if title_id not in target["titles"]:
                target["titles"].append(title_id)
            # 難易度は、最初に見つかった値を採用し、タイトル間で食い違うものは per_title に残す
            for key in ("normal_old", "hyper_old", "ex_old", "five"):
                if target[key] is None:
                    target[key] = s[key]
            target["per_title"].setdefault(title_id, []).append({
                "genre": s["genre"], "section": s["section"], "origin": s["origin"],
                "normal_old": s["normal_old"], "hyper_old": s["hyper_old"],
                "ex_old": s["ex_old"], "five": s["five"], "bpm": s["bpm"],
                "character": s["character"],
            })
    return merged


def build_existing_index(existing: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for e in existing:
        index.setdefault(norm(e["title"]), []).append(e)
    return index


def load_manual_matches(path: Path) -> dict[str, str]:
    """表記ゆれで自動照合できない同一曲の対応表 (正規化した PS2 曲名 → 既存曲名)。"""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {norm(k): v for k, v in data.get("matches", {}).items()}


def match_existing(song: dict, index: dict[str, list[dict]], manual: dict[str, str] | None = None):
    """既存の曲リストから対応する曲を探す。(曲 or None, 確度) を返す。確度: exact / title / ambiguous"""
    cands = index.get(norm(song["title"]), [])
    if not cands and manual and norm(song["title"]) in manual:
        cands = index.get(norm(manual[norm(song["title"])]), [])
        if len(cands) >= 1:
            return cands[0], "manual"
    if not cands:
        return None, ""
    a = norm(song["artist"])
    exact = [c for c in cands if a and norm(c["artist"]) == a]
    if exact:
        return exact[0], "exact"
    compat = [c for c in cands if a and artist_compatible(c["artist"], song["artist"])]
    if len(compat) == 1:
        return compat[0], "title"
    if len(cands) == 1:
        return cands[0], "title"
    best = max(cands, key=lambda c: difflib.SequenceMatcher(None, a, norm(c["artist"])).ratio())
    return best, "ambiguous"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-dir", default="tmp_ps2_songlist")
    ap.add_argument("--existing", default="popn_music_list.json")
    ap.add_argument("--out", default="ps2_music_list.json")
    args = ap.parse_args()

    pages = {}
    for title_id, (page, _name) in TITLES.items():
        pages[title_id] = parse_page(Path(args.html_dir) / f"{page}.html")
        print(f"{title_id}: {len(pages[title_id])} 曲")
    songs = merge_pages(pages)
    print(f"統合後: {len(songs)} 曲")

    existing = json.loads(Path(args.existing).read_text(encoding="utf-8")) if Path(args.existing).exists() else []
    index = build_existing_index(existing)
    manual = load_manual_matches(Path(__file__).parent / "tools" / "ps2_manual_matches.json")
    used_ids: set[str] = set()
    # 前回の出力の music_id を引き継ぐ (新規採番した曲の ID が、生成のたびに変わらないようにする)
    out_path = Path(args.out) if Path(args.out).exists() else Path("ps2_music_list.json")
    previous = {}
    if out_path.exists():
        for o in json.loads(out_path.read_text(encoding="utf-8")):
            previous[(norm(o["title"]), norm(o["artist"]))] = o["music_id"]

    out, unmatched, ambiguous, merged_notes = [], [], [], []
    for s in songs:
        match, kind = match_existing(s, index, manual)
        if match and match["music_id"] in used_ids:
            # 表記ゆれで別々の PS2 曲になっていたものが同じ既存曲に当たった = 同一曲。1 レコードに統合する
            first = next(o for o in out if o["music_id"] == match["music_id"])
            for key in ("normal_old", "hyper_old", "ex_old", "five"):
                if first[key] is None:
                    first[key] = s[key]
            for t in s["titles"]:
                if t not in first["titles"]:
                    first["titles"].append(t)
            for t, v in s["per_title"].items():
                first["per_title"].setdefault(t, []).extend(v)
            merged_notes.append((s, match))
            continue
        if match:
            used_ids.add(match["music_id"])
            if kind not in ("exact", "manual"):
                ambiguous.append((s, match, kind))
        else:
            unmatched.append(s)
        out.append({
            "music_id": match["music_id"] if match else previous.get((norm(s["title"]), norm(s["artist"])), str(uuid.uuid4())),
            "title": s["title"],
            "genre": s["genre"],
            "artist": s["artist"],
            "character": s["character"],
            "bpm": s["bpm"],
            "ver": match["ver"] if match else "",
            "titles": s["titles"],
            "normal_old": s["normal_old"], "normal_current": match.get("normal") if match else None,
            "hyper_old": s["hyper_old"], "hyper_current": match.get("hyper") if match else None,
            "ex_old": s["ex_old"], "ex_current": match.get("ex") if match else None,
            "five": s["five"],
            "pack": match.get("pack", "") if match else "",
            "banner": match.get("banner", "") if match else "",
            "per_title": s["per_title"],
        })

    # PS2 の画面から登録したバナー (tools/register_ps2_banners.py) を取り込む
    registry_path = Path(__file__).parent / "tools" / "ps2_banners.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    applied = 0
    for o in out:
        if o["music_id"] in registry:
            o["banner"] = registry[o["music_id"]]
            applied += 1
    if registry:
        print(f"登録済みバナー: {applied}/{len(registry)} 曲を反映 (反映できないものは music_id が変わった曲)")

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"出力: {args.out} ({len(out)} 曲)")
    print(f"既存と一致: {len(used_ids)} 曲 (うち曲名のみ・あいまい {len(ambiguous)} 曲) / 一致なし: {len(unmatched)} 曲")
    print(f"banner 引き継ぎ: {sum(1 for o in out if o['banner'])} 曲")
    unused = [e for e in existing if e["music_id"] not in used_ids]
    print(f"既存で PS2 に対応しなかった曲: {len(unused)} / {len(existing)}")
    for s, m in merged_notes:
        print(f"  [統合] {s['title']} / {s['artist']} を既存「{m['title']}」の曲に統合")
    for s, m, kind in ambiguous:
        print(f"  [{kind}] PS2: {s['title']} / {s['artist']}  ←→  既存: {m['title']} / {m['artist']} ({m['ver']})")
    titles = {norm(e["title"]): e for e in existing}
    for s in unmatched:
        hint = difflib.get_close_matches(norm(s["title"]), list(titles), n=1, cutoff=0.8)
        extra = f"  ← 近い既存曲: {titles[hint[0]]['title']} / {titles[hint[0]]['artist']}" if hint else ""
        print(f"  [なし] {s['title']} / {s['artist']} ({','.join(s['titles'])}){extra}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
