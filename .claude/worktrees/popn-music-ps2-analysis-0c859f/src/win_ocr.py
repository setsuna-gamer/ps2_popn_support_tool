"""Windows 標準 OCR (Windows.Media.Ocr) のラッパーと、画素の連なりを数える補助

PS2 版のオプション画面の OCR (src/ps2_ocr.py) とオプション読み取り (src/option_reader.py) が使う。
winrt パッケージや日本語 OCR が使えない環境では、常に空文字を返す。
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from src.logger import get_logger

logger = get_logger(__name__)

_OCR_TIMEOUT_SEC = 3.0
_OCR_SCALE = 2


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """flags が True の連続区間 [start, end) のリストを返す。"""
    padded = np.concatenate(([False], flags, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(edges[i]), int(edges[i + 1])) for i in range(0, len(edges), 2)]


# ----------------------------------------------------------------------
# OCR (Windows.Media.Ocr)
# ----------------------------------------------------------------------

class _WindowsOcr:
    """Windows 標準 OCR のラッパー。

    GUI スレッドの COM アパートメントと干渉しないよう、専用スレッドで実行する。
    winrt パッケージや日本語 OCR が使えない環境では常に空文字を返す。
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self._engine = None
        self._unavailable = False

    def _create_engine(self):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        engine = OcrEngine.try_create_from_language(Language("ja"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError("OCR 言語パックがインストールされていません")
        return engine

    def _recognize(self, image: Image.Image) -> str:
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winrt.windows.storage.streams import DataWriter

        if self._engine is None:
            self._engine = self._create_engine()

        rgba = image.convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(rgba.tobytes())
        bitmap = SoftwareBitmap.create_copy_with_alpha_from_buffer(
            writer.detach_buffer(),
            BitmapPixelFormat.RGBA8,
            rgba.width,
            rgba.height,
            BitmapAlphaMode.PREMULTIPLIED,
        )

        async def run():
            return await self._engine.recognize_async(bitmap)

        return asyncio.run(run()).text

    def read(self, image: Image.Image) -> str:
        if self._unavailable:
            return ""
        try:
            return self._executor.submit(self._recognize, image).result(_OCR_TIMEOUT_SEC)
        except (ImportError, RuntimeError) as e:
            self._unavailable = True
            logger.warning("Windows OCR が利用できないため曲名認識を無効化します: %s", e)
        except Exception as e:
            logger.debug("OCR エラー: %s", e)
        return ""


_ocr = _WindowsOcr()
