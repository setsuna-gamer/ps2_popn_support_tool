"""数字の枠の確認用: 画像の枠を切り出して拡大し、文字ごとの区切りを描いた画像を作る (開発者用)

    python tools/preview_ps2_numbers.py <title_id> <result|play> <画像の時刻 (ファイル名の末尾)> [出力 png]

正解値 (tools/ps2_number_samples.json) を人が読んで付けるとき、枠が合っているか見るときに使う。
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ps2_layouts import fields, segment_field  # noqa: E402
from src.ps2_numbers import crop_box, segment  # noqa: E402

SCALE = 3


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    title, screen, stamp = sys.argv[1:4]
    out = sys.argv[4] if len(sys.argv) > 4 else "preview.png"
    folder = {"popnbesthits": "popnbesthits"}.get(title, title)
    path = glob.glob(f"screenshots/{folder}/{screen}/*{stamp}.png")[0]
    im = Image.open(path).convert("RGB")
    items = fields(title, screen)
    crops = []
    for name, box in items.items():
        arr = crop_box(im, box)
        glyphs = segment_field(arr, title, screen)
        c = Image.fromarray(arr).resize((arr.shape[1] * SCALE, arr.shape[0] * SCALE), Image.Resampling.NEAREST)
        d = ImageDraw.Draw(c)
        d.text((2, 2), f"{name} ({len(glyphs)})", fill=(255, 0, 255))
        for g in glyphs:
            d.line([(g.x * SCALE, 0), (g.x * SCALE, c.height)], fill=(255, 0, 0))
        crops.append(c)
        print(name, len(glyphs), [round(g.aspect, 2) for g in glyphs])
    w = max(c.width for c in crops)
    sheet = Image.new("RGB", (w, sum(c.height + 4 for c in crops)), (0, 0, 0))
    y = 0
    for c in crops:
        sheet.paste(c, (0, y))
        y += c.height + 4
    sheet.save(out)


if __name__ == "__main__":
    main()
