"""screenshots/ のサンプル画像から、画面識別用テンプレート (src/screen_profiles.json) を生成する。

    python tools/build_screen_profiles.py [--screenshots screenshots] [--out src/screen_profiles.json] [--eval]

画像の置き場所: screenshots/<title_id>/<フォルダ名>/.../*.png
  title_id   : popn7 など。popnbesthits は besthits として扱う
  フォルダ名 : MODE_FOLDERS のいずれか (tilte のような綴り違いも吸収)。階層が深いときは
               いちばん深い既知のフォルダ名をモードとする (例: freetraining/musicselect → music_select)。
               freetraining (または free) 以下は階層によらず freetraining モード。そのほか既知でないフォルダ は、その名前をそのままモードとして扱う。

同じ (タイトル, モード) の画像のうち、見た目が大きく違うもの (別レイアウト) は自動で別テンプレートに分ける。
各テンプレートは「同じ画面の画像の間で変わらず、他の画面の画像とは違うセル」を最大 MAX_CELLS 個選んで持つ。

--eval を付けると、画像を 1 枚ずつ除いて作ったテンプレートでその画像を識別し直し、正答率を表示する
(同じ画面の画像が 2 枚以上あるものだけが対象)。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.screen_profile import (  # noqa: E402
    CELLS, CellFeatures, DEFAULT_PROFILE_PATH, GRID_COLS, GRID_ROWS, MIN_MARGIN, MIN_SCORE, ScreenProfiles, Template,
    cell_features, match_cells,
)

# フォルダ名 → モード名
MODE_FOLDERS = {
    "title": "title", "tilte": "title",
    "modeselect": "mode_select",
    "charaselect": "character_select", "characterselect": "character_select",
    "musicselect": "music_select",
    "option": "option",
    "play": "play",
    "result": "result",
    "load": "loading", "loading": "loading",
}
# フリートレーニング (独立したモード)。このフォルダ以下の画像は、階層が深くてもすべて freetraining モードにする
FREETRAINING_FOLDERS = {"freetraining", "free"}
TITLE_FOLDERS = {"popnbesthits": "besthits", "popnbest": "besthits"}

MAX_CELLS = 96            # 1 テンプレートが持つセル数の上限
MIN_CELLS = 24            # これ未満のセルしか選べないテンプレートは警告する
MIN_DISCRIMINATION = 0.9  # 他の画面の画像に対して「一致しない」割合の下限
SAME_LAYOUT_RATIO = 0.6   # 画像どうしでこの割合以上のセルが一致すれば同じレイアウトとみなす
# mode_select / loading として置かれた画像のうち、同じ作品のタイトル画面とこの割合以上のセルが一致するものは、
# タイトル画面として扱う (タイトルに寄せる)。タイトル画面のメニュー選択中の状態 (ARCADE / FREE などを選んでいる画面) は
# タイトルと背景・ロゴが同じで、モード選択やロード (ロードの直後にタイトルが出る) のフォルダに紛れ込みやすい。
# 本物のモード選択・ロード画面はタイトル画面と 0.6 未満しか一致しない
TITLE_LIKE_RATIO = 0.7
TITLE_LIKE_MODES = ("mode_select", "loading")


@dataclass
class Sample:
    path: Path
    title: str
    mode: str
    features: CellFeatures
    variants: list[CellFeatures]   # 拡縮・ずれ・ぼかし・明るさを少し変えた画像の特徴 (セルの安定性の確認用)


def augment(im: Image.Image) -> list[Image.Image]:
    """キャプチャ方式 (PCSX2 とキャプチャボードなど) の違いで起きうる、小さな変化を加えた画像を作る。"""
    w, h = im.size
    out = []
    for scale in (0.97, 1.0, 1.03):
        for dx, dy in ((0, 0), (0.01, 0.0), (-0.01, 0.0), (0.0, 0.01), (0.0, -0.01)):
            if scale == 1.0 and (dx, dy) == (0, 0):
                continue
            cw, ch = int(w * scale), int(h * scale)
            x0 = int((w - cw) / 2 + dx * w)
            y0 = int((h - ch) / 2 + dy * h)
            out.append(im.crop((x0, y0, x0 + cw, y0 + ch)))
    out.append(im.filter(ImageFilter.GaussianBlur(1.5)))
    out.append(ImageEnhance.Brightness(im).enhance(0.9))
    out.append(ImageEnhance.Brightness(im).enhance(1.1))
    return out


def folder_mode(parts: tuple[str, ...]) -> str:
    if any(name.lower() in FREETRAINING_FOLDERS for name in parts):
        return "freetraining"
    for name in reversed(parts):
        key = name.lower()
        if key in MODE_FOLDERS:
            return MODE_FOLDERS[key]
    return parts[0].lower()


def relabel_title_like(samples: list[Sample]) -> list[Sample]:
    """タイトル画面と見分けが付かない mode_select / loading の画像を、title に付け替える (タイトルに寄せる)。"""
    for s in samples:
        if s.mode not in TITLE_LIKE_MODES:
            continue
        titles = [o for o in samples if o.title == s.title and o.mode == "title"]
        best = max((float(match_cells(o.features, s.features).mean()) for o in titles), default=0.0)
        if best >= TITLE_LIKE_RATIO:
            print(f"  付け替え: {s.title}/{s.path.name} {s.mode} → title (タイトル画面と {best:.2f} 一致)")
            s.mode = "title"
    return samples


def load_samples(root: Path) -> list[Sample]:
    samples = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg") or path.parent == root:
            continue
        rel = path.relative_to(root).parts
        if len(rel) < 3:   # screenshots/<title>/<画像> は対象外
            continue
        title = TITLE_FOLDERS.get(rel[0].lower(), rel[0].lower())
        with Image.open(path) as im:
            im = im.convert("RGB")
            samples.append(Sample(path, title, folder_mode(rel[1:-1]), cell_features(im),
                                  [cell_features(v) for v in augment(im)]))
    return relabel_title_like(samples)


def subset(f: CellFeatures, idx: np.ndarray) -> CellFeatures:
    return CellFeatures(f.colors[idx])


def cluster(samples: list[Sample]) -> list[list[Sample]]:
    """見た目の大きく違う画像 (別レイアウト) を別のグループに分ける。"""
    groups: list[list[Sample]] = []
    for s in samples:
        for g in groups:
            if match_cells(g[0].features, s.features).mean() >= SAME_LAYOUT_RATIO:
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def build_templates(samples: list[Sample]) -> list[Template]:
    by_class: dict[tuple[str, str], list[Sample]] = defaultdict(list)
    for s in samples:
        by_class[(s.title, s.mode)].append(s)

    templates = []
    for (title, mode), members in sorted(by_class.items()):
        others = [s for s in samples if (s.title, s.mode) != (title, mode)]
        for n, group in enumerate(cluster(members)):
            ref = group[0].features
            stable = np.ones(CELLS, dtype=bool)
            for s in group:
                for f in [s.features, *s.variants]:
                    stable &= match_cells(ref, f)
            # 他の画面の画像と一致しない割合 (多いほど、そのセルは見分けるのに使える)
            if others:
                disc = 1.0 - np.mean([match_cells(ref, o.features) for o in others], axis=0)
            else:
                disc = np.ones(CELLS)
            # 同じ作品の別の画面 (背景が共通でよく似ているもの) との違い。実行時は作品の確定後、その作品の中で
            # モードを決めるので、ここを優先してセルを選ぶ (他の作品との違いは MIN_DISCRIMINATION で確保する)
            siblings = [s for s in others if s.title == title]
            if siblings:
                disc_same = 1.0 - np.mean([match_cells(ref, o.features) for o in siblings], axis=0)
            else:
                disc_same = np.ones(CELLS)
            candidates = [i for i in range(CELLS) if stable[i] and disc[i] >= MIN_DISCRIMINATION]
            candidates.sort(key=lambda i: (-round(float(disc_same[i]), 2), -disc[i], i))
            chosen = sorted(candidates[:MAX_CELLS])
            if len(chosen) < MIN_CELLS:
                print(f"  警告: {title}/{mode}#{n} は識別に使えるセルが {len(chosen)} 個しかありません "
                      f"(画像 {len(group)} 枚)", file=sys.stderr)
            templates.append(Template(
                title=title, mode=mode, name=f"{title}/{mode}#{n}", cells=chosen,
                features=subset(ref, np.array(chosen, dtype=int)) if chosen else subset(ref, np.array([], dtype=int)),
            ))
    return [t for t in templates if t.cells]


def to_json(templates: list[Template]) -> dict:
    return {
        "version": 1,
        "grid": [GRID_ROWS, GRID_COLS],
        "templates": [
            {
                "title": t.title, "mode": t.mode, "name": t.name,
                "cells": [
                    {"i": i, "rgb": [int(round(v)) for v in t.features.colors[k]]}
                    for k, i in enumerate(t.cells)
                ],
            }
            for t in templates
        ],
    }


def evaluate(samples: list[Sample]) -> None:
    """画像を 1 枚ずつ除いてテンプレートを作り直し、その画像を識別できるかを確かめる。

    実行時 (src/screen_tracker.py) と同じく、モードは「作品が確定したあと、その作品のテンプレートだけ」で決める。
    作品の判別 (全作品のテンプレートで決める) は別に数える。黒一色のロード画面は作品をまたいで同じに見えるので、
    作品の判別からは除く。
    同じ画面に、見た目の近い (同じレイアウトの) 別の画像がある場合だけを対象にする。
    他に似た画像が無い画像 (新しいレイアウト) は、学習していない画面なので識別できなくて当然のため数えない。
    """
    ok = total = novel = title_ok = title_total = 0
    worst_right, best_wrong = 1.0, 0.0
    for i, s in enumerate(samples):
        rest = samples[:i] + samples[i + 1:]
        peers = [o for o in rest if (o.title, o.mode) == (s.title, s.mode)
                 and match_cells(o.features, s.features).mean() >= SAME_LAYOUT_RATIO]
        scores = ScreenProfiles(build_templates(rest)).scores_from_features(s.features)
        if not peers:
            novel += 1
            continue
        total += 1
        in_title = [r for r in scores if r.title == s.title]
        right = max((r.score for r in in_title if r.mode == s.mode), default=0.0)
        wrong = max((r.score for r in in_title if r.mode != s.mode), default=0.0)
        worst_right, best_wrong = min(worst_right, right), max(best_wrong, wrong)
        hit = right >= MIN_SCORE and right - wrong >= MIN_MARGIN
        ok += hit
        if not hit:
            print(f"  誤り: {s.path.name} 正解 {s.title}/{s.mode} {right:.2f} / 同じ作品の他の画面の最高 {wrong:.2f}")
        if s.mode != "loading":
            title_total += 1
            got = ScreenProfiles.decide(scores)
            title_ok += got is not None and got.title == s.title
    print(f"除外検証 (モード、作品内で判定): {ok}/{total} 枚が正解 (同じレイアウトの画像が他にある画像のみ)")
    if total:
        print(f"  正解のスコアの最低 {worst_right:.2f} / 同じ作品の間違った画面のスコアの最高 {best_wrong:.2f}")
    print(f"除外検証 (作品の判別、ロード画面を除く): {title_ok}/{title_total} 枚が正解")
    print(f"新しいレイアウトで検証できない画像: {novel} 枚 (同じ画面の画像を増やすと識別できるようになる)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", default="screenshots")
    ap.add_argument("--out", default=str(DEFAULT_PROFILE_PATH))
    ap.add_argument("--eval", action="store_true")
    args = ap.parse_args()

    samples = load_samples(Path(args.screenshots))
    if not samples:
        raise SystemExit(f"{args.screenshots}/<title_id>/<mode>/ に画像がありません")
    print(f"画像 {len(samples)} 枚 / タイトル {sorted({s.title for s in samples})}")

    templates = build_templates(samples)
    for t in templates:
        print(f"  {t.name}: セル {len(t.cells)} 個")
    Path(args.out).write_text(json.dumps(to_json(templates), ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8", newline="\n")
    print(f"出力: {args.out} (テンプレート {len(templates)} 個)")

    # 学習に使った画像自身の識別結果 (モードは作品内で、作品は全体で決める。ロード画面は作品の判別から除く)
    profiles = ScreenProfiles(templates)
    ok = title_ok = title_total = 0
    for s in samples:
        scores = profiles.scores_from_features(s.features)
        got = ScreenProfiles.decide([r for r in scores if r.title == s.title])
        hit = got is not None and got.mode == s.mode
        ok += hit
        if not hit:
            print(f"  学習画像で誤り: {s.path.name} 正解 {s.title}/{s.mode} → "
                  f"{f'{got.mode} ({got.score:.2f})' if got else '判定なし'}")
        if s.mode != "loading":
            title_total += 1
            overall = ScreenProfiles.decide(scores)
            title_ok += overall is not None and overall.title == s.title
    print(f"学習画像のモード識別 (作品内): {ok}/{len(samples)} 枚が正解")
    print(f"学習画像の作品の判別 (ロード画面を除く): {title_ok}/{title_total} 枚が正解")
    if args.eval:
        evaluate(samples)


if __name__ == "__main__":
    main()
