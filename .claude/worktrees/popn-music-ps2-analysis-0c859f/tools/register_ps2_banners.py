"""PS2 の画面から曲のバナー特徴量を登録する (開発者用)

Lively 版に無い曲は、曲リストに banner 特徴量が無くオプション画面で特定できない。
PS2 のオプション画面の画像から特徴量を作り、曲に登録する。

    python tools/register_ps2_banners.py scan [--screenshots screenshots]
        screenshots/<title_id>/**/option/ の画像を調べ、特定できないバナーを一覧にする。
        バナーの切り出し画像は tmp_ps2_banners/ に保存する (どの曲か目で確認するため)。
    python tools/register_ps2_banners.py add <画像> <曲名> [--title popn7]
        画像のバナーを、曲名 (部分一致) の曲に登録する。title は画像のパス (screenshots/<title_id>/...) から決まる。

登録した特徴量は tools/ps2_banners.json (music_id → 特徴量) に保存し、ps2_music_list.json にも反映する。
generate_ps2_music_list.py は曲リストを作り直すときに tools/ps2_banners.json を取り込む。

登録に使う画像は「Next Music だけが表示されている (OPTIONS ポップアップが開く前)」もの。
ポップアップが開いた画像はバナーの下半分が隠れているので登録できない。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.banner_reader import decode_feature, encode_feature  # noqa: E402
from src.ps2_banner import BANNER_BOXES, POPUP_COVERS_BANNER, Ps2BannerIndex, crop_option_banner, read_option_banner  # noqa: E402

LIST_PATH = ROOT / "ps2_music_list.json"
REGISTRY_PATH = ROOT / "tools" / "ps2_banners.json"
PREVIEW_DIR = ROOT / "tmp_ps2_banners"
TITLE_FOLDERS = {"popnbesthits": "besthits", "popnbest": "besthits"}
# OPTIONS ポップアップのオレンジ色 (255,102,0 付近)。バナーの範囲にこれが多ければポップアップが開いている
_POPUP_RGB = np.array([255, 102, 0])


def title_of(path: Path, root: Path) -> str | None:
    try:
        name = path.resolve().relative_to(root.resolve()).parts[0].lower()
    except ValueError:
        return None
    return TITLE_FOLDERS.get(name, name)


def banner_crop(image: Image.Image, title: str) -> Image.Image:
    return crop_option_banner(image, title)


def popup_open(image: Image.Image, title: str) -> bool:
    if title not in POPUP_COVERS_BANNER:
        return False
    arr = np.asarray(banner_crop(image, title), dtype=np.int16)
    near = np.abs(arr - _POPUP_RGB).max(axis=2) <= 40
    return bool(near.mean() > 0.05)


def load_list(path: Path = LIST_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_index(songs: list[dict]) -> Ps2BannerIndex:
    return Ps2BannerIndex([(s["music_id"], decode_feature(s["banner"]), s["titles"]) for s in songs if s["banner"]])


def find_songs(songs: list[dict], title: str, name: str) -> list[dict]:
    """その作品の収録曲から、曲名 (完全一致 → 部分一致) で探す。"""
    pool = [s for s in songs if title in s["titles"]]
    exact = [s for s in pool if s["title"] == name]
    return exact or [s for s in pool if name.lower() in s["title"].lower()]


def register(songs: list[dict], music_id: str, feature: np.ndarray, registry_path: Path = REGISTRY_PATH) -> None:
    """特徴量を曲 (songs の要素) と登録ファイルに書き込む。呼び出し側で曲リストを保存する。"""
    encoded = encode_feature(feature)
    next(s for s in songs if s["music_id"] == music_id)["banner"] = encoded
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    registry[music_id] = encoded
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def save_list(songs: list[dict], path: Path = LIST_PATH) -> None:
    path.write_text(json.dumps(songs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def cmd_scan(root: Path) -> None:
    songs = load_list()
    index = build_index(songs)
    names = {s["music_id"]: s["title"] for s in songs}
    unknown: dict[str, list[tuple[Path, np.ndarray]]] = {}
    for path in sorted(root.rglob("*.png")):
        if "option" not in (p.lower() for p in path.relative_to(root).parts[:-1]):
            continue
        title = title_of(path, root)
        if title not in BANNER_BOXES:
            print(f"対象外: {path.name} ({title} はバナーの位置が未登録 → src/ps2_banner.py の BANNER_BOXES に追加)")
            continue
        with Image.open(path) as im:
            im = im.convert("RGB")
            feature = read_option_banner(im, title)
            popup = popup_open(im, title)
        got = index.match(feature, title)
        if got:
            print(f"特定済み: {path.name} → {names[got[0]]} ({got[1]:.3f})")
        elif popup:
            print(f"スキップ: {path.name} (ポップアップが開いていて特定できない)")
        else:
            group = next((g for g in unknown.setdefault(title, []) if float(g[0][1] @ feature) > 0.97), None)
            if group is None:
                unknown[title].append([(path, feature)])
            else:
                group.append((path, feature))
    PREVIEW_DIR.mkdir(exist_ok=True)
    for title, groups in unknown.items():
        missing = [s["title"] for s in songs if title in s["titles"] and not s["banner"]]
        print(f"\n{title}: 特定できないバナー {len(groups)} 種 (バナー未登録の曲 {len(missing)} 曲)")
        for n, group in enumerate(groups):
            path = group[0][0]
            out = PREVIEW_DIR / f"{title}_{n}.png"
            with Image.open(path) as im:
                banner_crop(im, title).save(out)
            print(f"  [{n}] {path.name} (同じバナーの画像 {len(group)} 枚) 切り出し: {out.relative_to(ROOT)}")
            print(f"      python tools/register_ps2_banners.py add \"{path}\" \"<曲名>\"")


def cmd_add(image_path: Path, name: str, title: str | None, root: Path) -> None:
    title = title or title_of(image_path, root)
    if title not in BANNER_BOXES:
        raise SystemExit(f"{title}: バナーの位置が未登録です (--title で作品を指定、または src/ps2_banner.py の BANNER_BOXES に追加)")
    songs = load_list()
    hits = find_songs(songs, title, name)
    if not hits:
        raise SystemExit(f"{title} の収録曲に「{name}」が見つかりません")
    if len(hits) > 1:
        lines = "\n".join(f"  {s['title']} / {s['artist']}" for s in hits[:20])
        raise SystemExit(f"「{name}」に複数の曲が当たりました。曲名を絞ってください:\n{lines}")
    song = hits[0]
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        if popup_open(im, title):
            raise SystemExit("ポップアップが開いている画像は登録できません (Next Music だけの画像を使ってください)")
        feature = read_option_banner(im, title)
    # 別の曲として登録済みのバナーと同じ画像なら、取り違えの可能性が高い
    found = build_index([s for s in songs if s["music_id"] != song["music_id"]]).match(feature, title)
    if found:
        other = next(s["title"] for s in songs if s["music_id"] == found[0])
        raise SystemExit(f"この画像は「{other}」のバナーと一致します (相関 {found[1]:.3f})。登録しません")
    if song["banner"]:
        print(f"注意: 「{song['title']}」には登録済みのバナーがあります。上書きします")
    register(songs, song["music_id"], feature)
    save_list(songs)
    print(f"登録: {title} / {song['title']} / {song['artist']}")
    print(f"  {REGISTRY_PATH.relative_to(ROOT)} と {LIST_PATH.name} に書き込みました")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--screenshots", default="screenshots")
    p = sub.add_parser("add")
    p.add_argument("image")
    p.add_argument("name")
    p.add_argument("--title")
    p.add_argument("--screenshots", default="screenshots")
    args = ap.parse_args()
    root = Path(args.screenshots)
    if args.cmd == "scan":
        cmd_scan(root)
    else:
        cmd_add(Path(args.image), args.name, args.title, root)


if __name__ == "__main__":
    main()
