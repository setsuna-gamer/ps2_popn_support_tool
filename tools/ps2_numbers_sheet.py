"""数字の枠を、作品・画面の全画像について並べた一覧画像を作る (正解値を人が読むための開発者用ツール)

    python tools/ps2_numbers_sheet.py <title_id> <result|play> [出力 png] [拡大率]
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ps2_layouts import fields, segment_field  # noqa: E402
from src.ps2_numbers import crop_box, segment  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    title, screen = sys.argv[1:3]
    out = sys.argv[3] if len(sys.argv) > 3 else "sheet.png"
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    folder = "popnbesthits" if title == "besthits" else title
    files = sorted(glob.glob(f"screenshots/{folder}/{screen}/*.png"))
    items = fields(title, screen)
    names = list(items)
    cells = []
    for f in files:
        im = Image.open(f).convert("RGB")
        row = []
        for n in names:
            arr = crop_box(im, items[n])
            pic = Image.fromarray(arr)
            row.append((pic.resize((pic.width * scale, pic.height * scale), Image.Resampling.NEAREST), len(segment_field(arr, title, screen))))
        cells.append((Path(f).stem[-6:], row))
    cw = max(c.width for _, r in cells for c, _ in r)
    ch = max(c.height for _, r in cells for c, _ in r)
    sheet = Image.new("RGB", ((cw + 6) * len(cells), (ch + 16) * len(names)), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, (stamp, row) in enumerate(cells):
        x = i * (cw + 6)
        for j, (c, n) in enumerate(row):
            y = j * (ch + 16)
            sheet.paste(c, (x, y + 14))
            d.text((x + 2, y + 1), f"{stamp} {names[j]} ({n} glyphs)", fill=(255, 255, 0))
    sheet.save(out)
    print(len(files), "images", sheet.size)


if __name__ == "__main__":
    main()
