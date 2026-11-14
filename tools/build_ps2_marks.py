"""正解付きのリザルト画像から、STAGE FAILED / NEW RECORD の参照 (src/ps2_mark_templates.json) を生成する (開発者用)

    python tools/build_ps2_marks.py [--eval]

入力: tools/ps2_mark_samples.json
    {"samples": [{"image": "popn12/result/152100", "failed": true, "new_record": true}, ...]}
    項目を書かなかった目印は、その画像では使わない (その作品・目印の枠が無い画像など)。
--eval: 画像を 1 枚ずつ除いて作り直し、その画像の判定が合うかを確かめる。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.ps2_marks import DEFAULT_TEMPLATE_PATH, MARK_BOXES, MARKS, MarkTemplates, encode, feature  # noqa: E402

SAMPLES = ROOT / "tools" / "ps2_mark_samples.json"
MAX_REFS = 8


def resolve(ref: str) -> tuple[str, Path]:
    title, screen, stamp = ref.split("/")
    folder = "popnbesthits" if title == "besthits" else title
    found = glob.glob(str(ROOT / "screenshots" / folder / screen / f"*{stamp}.png"))
    if len(found) != 1:
        raise SystemExit(f"画像が 1 枚に決まりません: {ref} → {found}")
    return title, Path(found[0])


def build(items) -> MarkTemplates:
    data = defaultdict(lambda: {"pos": [], "neg": []})
    for _ref, title, image, labels in items:
        for mark, value in labels.items():
            box = MARK_BOXES.get(title, {}).get(mark)
            if box is None:
                continue
            refs = data[f"{title}/{mark}"]["pos" if value else "neg"]
            if len(refs) < MAX_REFS:
                refs.append(feature(image, box))
    return MarkTemplates(dict(data))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--out", default=str(DEFAULT_TEMPLATE_PATH))
    args = ap.parse_args()
    items = []
    for s in json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]:
        title, path = resolve(s["image"])
        with Image.open(path) as im:
            items.append((s["image"], title, im.convert("RGB"), {m: s[m] for m in MARKS if m in s}))

    tpl = build(items)
    out = {"version": 1, "templates": {k: {"pos": [encode(v) for v in r["pos"]], "neg": [encode(v) for v in r["neg"]]}
                                       for k, r in sorted(tpl._data.items())}}
    Path(args.out).write_text(json.dumps(out, indent=0) + "\n", encoding="utf-8", newline="\n")
    for k, r in sorted(tpl._data.items()):
        print(f"  {k}: 「ある」{len(r['pos'])} / 「ない」{len(r['neg'])}")

    def score(get):
        ok = tot = 0
        bad = []
        for ref, title, image, labels in items:
            t = get(ref)
            for mark, value in labels.items():
                if not t.has(title, mark):
                    continue
                tot += 1
                got = t.detect(image, title, mark)
                ok += got == value
                if got != value:
                    bad.append(f"{ref} {mark}: 正解 {value} / 判定 {got}")
        return ok, tot, bad

    ok, tot, bad = score(lambda ref: tpl)
    print(f"学習画像: {ok}/{tot} 項目が正解")
    for b in bad:
        print("  誤り:", b)
    if args.eval:
        cache = {}
        ok, tot, bad = score(lambda ref: cache.setdefault(ref, build([i for i in items if i[0] != ref])))
        print(f"除外検証: {ok}/{tot} 項目が正解 (参照が残る項目のみ)")
        for b in bad:
            print("  誤り:", b)


if __name__ == "__main__":
    main()
