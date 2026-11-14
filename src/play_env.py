"""スコア記録に付けるプレー環境 (実機 / PCSX2 / その他) とモダナイズパッチの有無。

モダナイズパッチ (https://github.com/setsuna-gamer/popn_modernize_patcher) を当てると、COOL の判定が 25ms になり、
ハイスピードの選択肢も増える (CLAUDE.md §4.2)。判定が変わるので、スコアを比べるときの区別に使う。
"""
from __future__ import annotations

PLATFORMS: dict[str, str] = {
    "real": "実機",
    "pcsx2": "PCSX2",
    "other": "その他",
}
DEFAULT_PLATFORM = "pcsx2"

_ALIASES = {name.lower(): code for code, name in PLATFORMS.items()}


def platform_code(value: str) -> str:
    """環境の識別子 (real / pcsx2 / other)。表示名 (実機 など) も受け付ける。不明・空は空文字。"""
    v = (value or "").strip().lower()
    if v in PLATFORMS:
        return v
    return _ALIASES.get(v, "")


def platform_name(code: str) -> str:
    """環境の表示名。不明 (空) は空文字、未知の値はそのまま返す。"""
    return PLATFORMS.get(code, code)


def modernize_text(value: bool | None) -> str:
    """モダナイズパッチの表示。不明 (None) は空文字。"""
    return "" if value is None else ("あり" if value else "なし")


def parse_modernize(value) -> bool | None:
    """CSV・DB の値からモダナイズパッチの有無を読む。空・不明は None。"""
    if value is None or isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("1", "true", "あり", "yes"):
        return True
    if v in ("0", "false", "なし", "no"):
        return False
    return None
