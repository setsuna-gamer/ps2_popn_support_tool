"""PS2 版 pop'n music の数字の位置 (作品 × 画面 × 項目)

座標は、1325x994 (4:3) の画面でのピクセル位置 (x0, y0, x1, y1)。読み取り時に画面に対する比率へ直すので、
4:3 であれば解像度に依存しない。枠は「数字の列が必ず収まる、少し広めの範囲」にする (数字の位置・桁数は
`src/ps2_numbers.py` が枠の中で見つける)。他の文字や縁取りを含めすぎないこと。

画面 (screen):
    result : リザルト画面。項目は cool / great / good / bad / combo / stage_score / total_score
    play   : プレー画面。項目は 判定の累計 (cool / great / good / bad)、score、combo
"""
from __future__ import annotations

REF_W, REF_H = 1325, 994

Box = tuple[int, int, int, int]

LAYOUTS: dict[str, dict[str, dict[str, Box]]] = {
    "popn7": {
        "result": {
            "cool": (345, 405, 590, 465),
            "great": (345, 480, 590, 540),
            "good": (345, 555, 590, 615),
            "bad": (345, 630, 590, 690),
            "combo": (345, 705, 590, 765),
            "stage_score": (775, 490, 1140, 555),
            "total_score": (775, 650, 1140, 715),
        },
        "play": {
            "bad": (378, 884, 456, 913),
            "good": (541, 884, 621, 913),
            "great": (716, 884, 794, 913),
            "cool": (874, 884, 954, 913),
        },
    },
    "popn8": {
        "result": {
            "cool": (345, 400, 595, 460),
            "great": (345, 478, 595, 538),
            "good": (345, 558, 595, 618),
            "bad": (345, 635, 595, 695),
            "combo": (345, 718, 595, 778),
            "stage_score": (770, 560, 1150, 625),
            "total_score": (770, 725, 1150, 785),
        },
        "play": {
            "bad": (392, 891, 476, 920),
            "good": (558, 891, 642, 920),
            "great": (731, 891, 816, 920),
            "cool": (896, 891, 979, 920),
        },
    },
    "popn9": {
        "result": {
            "cool": (335, 232, 505, 302),
            "great": (335, 310, 505, 378),
            "good": (335, 386, 505, 455),
            "bad": (335, 462, 505, 532),
            "combo": (335, 542, 505, 608),
            "stage_score": (65, 685, 485, 765),
            "total_score": (65, 828, 485, 905),
        },
        "play": {
            "bad": (568, 944, 654, 968),
            "good": (668, 944, 754, 968),
            "great": (768, 944, 854, 968),
            "cool": (868, 944, 956, 968),
        },
    },
    "popn12": {
        "result": {
            "cool": (540, 148, 718, 218),
            "great": (540, 240, 718, 312),
            "good": (540, 335, 718, 402),
            "bad": (540, 428, 718, 497),
            "combo": (540, 523, 718, 592),
            "stage_score": (440, 612, 718, 686),
            "total_score": (440, 708, 718, 780),
        },
        "play": {
            "bad": (414, 938, 494, 966),
            "good": (571, 938, 649, 966),
            "great": (738, 938, 816, 966),
            "cool": (891, 938, 971, 966),
        },
    },
    "popn13": {
        "result": {
            "cool": (560, 312, 718, 368),
            "great": (560, 384, 718, 442),
            "good": (560, 456, 718, 512),
            "bad": (560, 528, 718, 586),
            "combo": (560, 598, 718, 658),
            "stage_score": (480, 670, 718, 727),
            "total_score": (480, 748, 718, 808),
        },
        "play": {
            "bad": (431, 953, 501, 981),
            "good": (586, 953, 654, 981),
            "great": (736, 953, 806, 981),
            "cool": (886, 953, 957, 981),
        },
    },
    "popn14": {
        "result": {
            "cool": (520, 232, 758, 292),
            "great": (520, 320, 758, 380),
            "good": (520, 408, 758, 468),
            "bad": (520, 496, 758, 556),
            "combo": (520, 582, 758, 642),
            "stage_score": (440, 670, 758, 730),
            "total_score": (440, 758, 758, 818),
        },
        "play": {
            "bad": (401, 945, 471, 973),
            "good": (569, 945, 641, 973),
            "great": (748, 945, 818, 973),
            "cool": (909, 945, 984, 973),
        },
    },
    "besthits": {
        "result": {
            "cool": (345, 405, 590, 465),
            "great": (345, 480, 590, 540),
            "good": (345, 555, 590, 615),
            "bad": (345, 630, 590, 690),
            "combo": (345, 705, 590, 765),
            "stage_score": (775, 490, 1140, 555),
            "total_score": (775, 650, 1140, 715),
        },
        "play": {
            "bad": (406, 905, 484, 925),
            "good": (572, 905, 652, 925),
            "great": (742, 905, 822, 925),
            "cool": (912, 905, 990, 925),
        },
    },
    "popn10": {
        "result": {
            "cool": (535, 210, 775, 268),
            "great": (535, 288, 775, 346),
            "good": (535, 368, 775, 426),
            "bad": (535, 446, 775, 503),
            "combo": (535, 526, 775, 583),
            "stage_score": (528, 604, 775, 662),
            "total_score": (528, 684, 775, 745),
        },
        "play": {
            "bad": (382, 950, 458, 978),
            "good": (562, 950, 638, 978),
            "great": (752, 950, 834, 978),
            "cool": (928, 950, 1008, 978),
        },
    },
    "popn11": {
        "result": {
            "cool": (585, 180, 775, 245),
            "great": (585, 260, 775, 325),
            "good": (585, 340, 775, 405),
            "bad": (585, 418, 775, 483),
            "combo": (585, 497, 775, 562),
            "stage_score": (510, 572, 775, 632),
            "total_score": (510, 650, 775, 710),
        },
        "play": {
            "bad": (381, 938, 459, 968),
            "good": (554, 938, 636, 968),
            "great": (750, 938, 832, 968),
            "cool": (916, 938, 1002, 968),
        },
    },
}

# 隣の文字と繋がって見える塊を分けるときの、幅 / 高さの下限 (既定は src/ps2_numbers.py の SPLIT_WIDTH_RATIO)。
# 文字が詰まって繋がる作品・画面だけ小さくする
SPLIT_RATIOS: dict[tuple[str, str], float] = {
}

# 等幅で 0 埋めされた (桁数が決まっている) 数字で、隣の文字と繋がって谷で分けられない作品・画面の桁数。
# 文字の連なりの幅を等分して切り出す (`src/ps2_numbers.py` の segment_fixed)
FIXED_DIGITS: dict[tuple[str, str], int] = {
    ("popn10", "play"): 4,
}

RESULT_FIELDS = ("cool", "great", "good", "bad", "combo", "stage_score", "total_score")
JUDGE_FIELDS = ("cool", "great", "good", "bad")


def fraction_box(box: Box) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    return x0 / REF_W, y0 / REF_H, x1 / REF_W, y1 / REF_H


def fields(title: str, screen: str) -> dict[str, tuple[float, float, float, float]]:
    """作品・画面の項目 → 比率の枠。未対応なら空。"""
    return {k: fraction_box(v) for k, v in LAYOUTS.get(title, {}).get(screen, {}).items()}


def split_ratio(title: str, screen: str) -> float:
    from src.ps2_numbers import SPLIT_WIDTH_RATIO
    return SPLIT_RATIOS.get((title, screen), SPLIT_WIDTH_RATIO)


def fixed_digits(title: str, screen: str) -> int:
    return FIXED_DIGITS.get((title, screen), 0)


def segment_field(arr, title: str, screen: str):
    """枠の画像から、作品・画面に合った方法で文字を切り出す。"""
    from src.ps2_numbers import segment, segment_fixed
    n = fixed_digits(title, screen)
    return segment_fixed(arr, n) if n else segment(arr, split_ratio=split_ratio(title, screen))
