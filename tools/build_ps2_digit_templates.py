"""正解値付きのスクリーンショットから、PS2 版の数字テンプレート (src/ps2_digit_templates.json) を生成する (開発者用)

    python tools/build_ps2_digit_templates.py [--out src/ps2_digit_templates.json] [--eval]

入力: tools/ps2_number_samples.json
    {"samples": [{"image": "popn11/result/151218",   # screenshots/<title_id>/<画面フォルダ>/*<この文字列>.png
                  "values": {"cool": "0029", ...}}]}  # 画面に表示されている数字列 (ゼロ埋めがあればそのまま)
    画面 (result / play) は image のフォルダ名から決まる。項目名は src/ps2_layouts.py の LAYOUTS と同じ。
    ゼロ埋めの 0 が暗くて文字として切り出されない作品は、先頭の 0 を除いた桁数が切り出されれば、残りの桁だけを学習する。

出力: 作品/画面ごとに、数字ごとの文字の形 (16x24) と縦横比。同じ数字の形は最大 MAX_PER_DIGIT 個まで持つ。
--eval: 画像 1 枚を除いてテンプレートを作り直し、その画像の数字を読めるかを確かめる (読み取りの精度の目安)。
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.ps2_layouts import fields, segment_field  # noqa: E402
from src.ps2_numbers import DEFAULT_TEMPLATE_PATH, DigitTemplates, Glyph, crop_box, segment, shape_distance  # noqa: E402

SAMPLES_PATH = ROOT / "tools" / "ps2_number_samples.json"
MAX_PER_DIGIT = 8
SAME_SHAPE_DISTANCE = 0.03   # これより近い形は、同じ数字の別の見本としては持たない


def resolve(image_ref: str) -> tuple[str, str, Path]:
    """'popn11/result/151218' → (title, screen, path)"""
    title, screen, stamp = image_ref.split("/")
    folder = "popnbesthits" if title == "besthits" else title
    matches = glob.glob(str(ROOT / "screenshots" / folder / screen / f"*{stamp}.png"))
    if len(matches) != 1:
        raise SystemExit(f"画像が 1 枚に決まりません: {image_ref} → {matches}")
    return title, screen, Path(matches[0])


def labeled_glyphs(image: Image.Image, title: str, screen: str, values: dict[str, str], where: str
                   ) -> list[tuple[str, Glyph]]:
    """画像の各項目から、(数字, 文字) の組を取り出す。切り出した桁数が合わない項目は警告して除く。"""
    out = []
    layout = fields(title, screen)
    for name, label in values.items():
        if name not in layout:
            raise SystemExit(f"{where}: {title}/{screen} に項目 {name} がありません (src/ps2_layouts.py)")
        glyphs = segment_field(crop_box(image, layout[name]), title, screen)
        if len(glyphs) < len(label) and set(label[:len(label) - len(glyphs)]) <= {"0"}:
            label = label[len(label) - len(glyphs):]    # 暗い 0 埋めは文字として切り出されない
        if len(glyphs) != len(label):
            print(f"  警告: {where} {name}: 正解 {label!r} ({len(label)} 桁) に対して {len(glyphs)} 文字を切り出した。除外",
                  file=sys.stderr)
            continue
        out.extend(zip(label, glyphs))
    return out


def build(pairs: dict[tuple[str, str], list[tuple[str, Glyph]]]) -> DigitTemplates:
    data: dict[tuple[str, str], dict[str, list[Glyph]]] = {}
    for key, items in pairs.items():
        table: dict[str, list[Glyph]] = defaultdict(list)
        for digit, g in items:
            have = table[digit]
            if len(have) >= MAX_PER_DIGIT:
                continue
            if any(shape_distance(g, h) < SAME_SHAPE_DISTANCE for h in have):
                continue
            have.append(g)
        data[key] = dict(table)
    return DigitTemplates(data)


def to_json(templates: DigitTemplates) -> dict:
    out = {}
    for (title, screen), table in sorted(templates._data.items()):
        out[f"{title}/{screen}"] = {
            digit: [{"aspect": round(g.aspect, 3),
                     "shape": base64.b64encode(np.round(g.shape * 255).astype(np.uint8).tobytes()).decode("ascii")}
                    for g in items]
            for digit, items in sorted(table.items())
        }
    return {"version": 1, "templates": out}


def read_values(image: Image.Image, title: str, screen: str, templates: DigitTemplates) -> dict[str, str | None]:
    from src.ps2_numbers import read_digits
    from src.ps2_layouts import fixed_digits, split_ratio
    return {name: read_digits(image, box, title, screen, templates, split_ratio(title, screen), fixed_digits(title, screen))
            for name, box in fields(title, screen).items()}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_TEMPLATE_PATH))
    ap.add_argument("--eval", action="store_true")
    args = ap.parse_args()

    samples = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))["samples"]
    loaded = []   # (ref, title, screen, image, values, pairs)
    for s in samples:
        title, screen, path = resolve(s["image"])
        with Image.open(path) as im:
            im = im.convert("RGB")
        loaded.append((s["image"], title, screen, im, s["values"],
                       labeled_glyphs(im, title, screen, s["values"], s["image"])))

    all_pairs: dict[tuple[str, str], list[tuple[str, Glyph]]] = defaultdict(list)
    for _ref, title, screen, _im, _v, pairs in loaded:
        all_pairs[(title, screen)].extend(pairs)
    templates = build(all_pairs)
    Path(args.out).write_text(json.dumps(to_json(templates), indent=0) + "\n", encoding="utf-8", newline="\n")
    for (title, screen), table in sorted(templates._data.items()):
        missing = [d for d in "0123456789" if d not in table]
        print(f"  {title}/{screen}: 数字 {len(table)} 種 / 見本 {sum(len(v) for v in table.values())} 個"
              + (f" (足りない数字: {''.join(missing)})" if missing else ""))
    print(f"出力: {args.out}")

    def score(tpl_for) -> tuple[int, int, list[str]]:
        ok = total = 0
        bad = []
        for ref, title, screen, im, values, _pairs in loaded:
            got = read_values(im, title, screen, tpl_for(ref, title, screen))
            for name, label in values.items():
                total += 1
                g = got.get(name)
                same = g is not None and g != "" and int(g) == int(label)
                ok += same
                if not same:
                    bad.append(f"{ref} {name}: 正解 {label} / 読み取り {g}")
        return ok, total, bad

    ok, total, bad = score(lambda ref, t, s: templates)
    print(f"学習画像の読み取り: {ok}/{total} 項目が正解")
    for b in bad:
        print("  誤り:", b)

    if args.eval:
        def loo(ref, title, screen):
            rest: dict[tuple[str, str], list[tuple[str, Glyph]]] = defaultdict(list)
            for r2, t2, s2, _im, _v, pairs in loaded:
                if r2 != ref:
                    rest[(t2, s2)].extend(pairs)
            return build(rest)
        cache: dict[str, DigitTemplates] = {}
        ok, total, bad = score(lambda ref, t, s: cache.setdefault(ref, loo(ref, t, s)))
        print(f"除外検証 (その画像を除いて学習): {ok}/{total} 項目が正解")
        for b in bad:
            print("  誤り:", b)


if __name__ == "__main__":
    main()
