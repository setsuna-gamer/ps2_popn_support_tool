"""PS2 版 pop'n music のリザルト画面の目印 (STAGE FAILED・NEW RECORD) の検出

どちらも作品ごとに絵柄・位置が違う (popn12 の赤い判子、popn10 の黄色い文字など) ので、
決まった枠 (`MARK_BOXES`、1325x994 のピクセル座標) を小さな RGB サムネイルにして、
正解付きの見本から作った参照 (`ps2_mark_templates.json`) との相関で判定する。

- 見本に「ある」画像の参照との相関が `POS_MIN` 以上で、「ない」見本の参照があればそれより `MARGIN` 以上高いとき「ある」。
- その作品・目印の見本が無い (参照が無い) ときは判定できない (None)。**無いものを有ると誤認しないため、見本に「ある」
  画像が 1 枚も無い目印は検出しない**。
- STAGE FAILED は「クリア失敗」 (ゲージが足りずにステージが終わった)。**PS2 版に Retire (途中でやめる) に相当するものは無い**ので、
  Lively の retire とは関係なく、独立した「クリア失敗」として記録する (`ResultValues.failed` → `PopnScoreRecord.failed`)。

参照は `tools/build_ps2_marks.py` が `tools/ps2_mark_samples.json` から自動生成する。手で編集しない。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

REF_W, REF_H = 1325, 994
THUMB_W, THUMB_H = 32, 16
POS_MIN = 0.80
MARGIN = 0.05
DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("ps2_mark_templates.json")

Box = tuple[int, int, int, int]
MARKS = ("failed", "new_record")

# 作品 × 目印 → 枠 (1325x994 のピクセル座標)。枠は、目印が出る場所を少し広めに取る
MARK_BOXES: dict[str, dict[str, Box]] = {
    "popn10": {"failed": (730, 100, 1325, 250), "new_record": (355, 614, 530, 648)},
    "popn11": {"failed": (730, 100, 1325, 230), "new_record": (330, 597, 505, 625)},
    "popn12": {"failed": (770, 110, 1325, 280), "new_record": (312, 612, 405, 695)},
    "popn13": {"failed": (770, 120, 1325, 300)},
    "popn14": {"failed": (750, 700, 1325, 900)},
}


def feature(image: Image.Image, box: Box) -> np.ndarray:
    """枠を 32x16 の RGB サムネイルにして、平均を引いて長さ 1 にしたベクトル。"""
    w, h = image.size
    x0, y0, x1, y1 = box
    crop = image.convert("RGB").crop((round(x0 * w / REF_W), round(y0 * h / REF_H),
                                      round(x1 * w / REF_W), round(y1 * h / REF_H)))
    v = np.asarray(crop.resize((THUMB_W, THUMB_H), Image.Resampling.BOX), dtype=np.float32).ravel()
    v = v - v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else v * 0.0


def encode(v: np.ndarray) -> str:
    return base64.b64encode(np.clip(np.round((v + 0.5) * 255), 0, 255).astype(np.uint8).tobytes()).decode("ascii")


def decode(s: str) -> np.ndarray:
    q = np.frombuffer(base64.b64decode(s), dtype=np.uint8).astype(np.float32) / 255 - 0.5
    q = q - q.mean()
    n = float(np.linalg.norm(q))
    return q / n if n > 1e-6 else q


@dataclass
class Marks:
    """リザルト画面の目印。判定できない (対応していない作品・見本が無い) ものは None。"""
    failed: bool | None = None
    new_record: bool | None = None


class MarkTemplates:
    def __init__(self, data: dict[str, dict[str, list[np.ndarray]]] | None = None):
        # key: "<title>/<mark>" → {"pos": [...], "neg": [...]}
        self._data = data or {}

    @classmethod
    def load(cls, path: str | Path = DEFAULT_TEMPLATE_PATH) -> "MarkTemplates":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls({k: {"pos": [decode(s) for s in v.get("pos", [])], "neg": [decode(s) for s in v.get("neg", [])]}
                    for k, v in raw.get("templates", {}).items()})

    def has(self, title: str, mark: str) -> bool:
        """その作品・目印を判定できるか (枠があり、「ある」見本の参照がある)。"""
        return bool(MARK_BOXES.get(title, {}).get(mark)) and bool(self._data.get(f"{title}/{mark}", {}).get("pos"))

    def detect(self, image: Image.Image, title: str, mark: str) -> bool | None:
        if not self.has(title, mark):
            return None
        v = feature(image, MARK_BOXES[title][mark])
        ref = self._data[f"{title}/{mark}"]
        pos = max(float(v @ r) for r in ref["pos"])
        neg = max((float(v @ r) for r in ref["neg"]), default=-1.0)
        return pos >= POS_MIN and (not ref["neg"] or pos - neg >= MARGIN)


@lru_cache(maxsize=1)
def default_templates() -> MarkTemplates:
    return MarkTemplates.load()


def read_marks(image: Image.Image, title: str, templates: MarkTemplates | None = None) -> Marks:
    tpl = templates or default_templates()
    return Marks(**{m: tpl.detect(image, title, m) for m in MARKS})
