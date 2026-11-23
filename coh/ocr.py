"""Texterkennung ueber die in Windows eingebaute OCR (Windows.Media.Ocr)."""
from __future__ import annotations

import asyncio

import numpy as np
from PIL import Image

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        _engine = OcrEngine.try_create_from_language(Language("en-GB")) or OcrEngine.try_create_from_user_profile_languages()
    return _engine


async def _recognize(rgb: np.ndarray):
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter
    h, w = rgb.shape[:2]
    bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], np.full((h, w), 255, np.uint8)])
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)
    return await _get_engine().recognize_async(bmp)


def read_words(rgb: np.ndarray, scale: int = 3) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Woerter mit Box (x, y, w, h) in Koordinaten des uebergebenen Ausschnitts."""
    img = Image.fromarray(rgb.astype(np.uint8)).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.LANCZOS)
    res = asyncio.run(_recognize(np.asarray(img)))
    out = []
    for line in res.lines:
        for wd in line.words:
            r = wd.bounding_rect
            out.append((wd.text, (r.x / scale, r.y / scale, r.width / scale, r.height / scale)))
    return out


def read_int(rgb: np.ndarray, scale: int = 3) -> int | None:
    """Erste Zahl im Ausschnitt (haeufige Verwechslungen O->0, l/I->1 werden korrigiert)."""
    fix = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5", "Z": "2", "B": "8"})
    for text, _ in read_words(rgb, scale):
        t = "".join(ch for ch in text.translate(fix) if ch.isdigit())
        if t:
            return int(t)
    return None
