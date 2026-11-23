"""Ziffernleser fuer die Spiel-UI (Reserve-Zaehler, Zuganzeige).

Vorlagen werden einmalig aus installierten Serifenschriften gerendert und per normierter
Korrelation verglichen. Eingabe ist immer eine Binaermaske (True = Ziffernpixel).
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = (20, 28)  # (w, h) der normierten Glyphe
FONTS = ["georgia.ttf", "georgiab.ttf", "times.ttf", "timesbd.ttf", "pala.ttf", "palab.ttf",
         "BKANT.TTF", "cambria.ttc", "cambriab.ttf", "constan.ttf", "constanb.ttf"]
_templates: list[tuple[int, np.ndarray, float]] | None = None


def _norm(mask: np.ndarray) -> tuple[np.ndarray, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) < 8:
        return None
    sub = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    aspect = sub.shape[1] / sub.shape[0]
    img = Image.fromarray((sub * 255).astype(np.uint8)).resize(SIZE, Image.BILINEAR)
    a = np.asarray(img, np.float32) / 255
    a = a - a.mean()
    return a / (np.linalg.norm(a) + 1e-6), aspect


def _build():
    global _templates
    _templates = []
    for fname in FONTS:
        try:
            font = ImageFont.truetype(fname, 64)
        except OSError:
            continue
        for d in range(10):
            img = Image.new("L", (80, 100), 0)
            ImageDraw.Draw(img).text((10, 5), str(d), fill=255, font=font)
            n = _norm(np.asarray(img) > 128)
            if n:
                _templates.append((d, n[0], n[1]))


def classify_glyph(mask: np.ndarray) -> tuple[int | None, float]:
    if _templates is None:
        _build()
    n = _norm(mask)
    if n is None:
        return None, 0.0
    a, asp = n
    best, bs = None, -1.0
    for d, t, tasp in _templates:
        s = float((a * t).sum()) - 0.6 * abs(np.log(asp / tasp))
        if s > bs:
            best, bs = d, s
    return best, bs


def split_glyphs(mask: np.ndarray, min_pixels: int = 15) -> list[np.ndarray]:
    """Trennt Ziffern an leeren Spalten (kleine Stoerflecken werden verworfen)."""
    cols = mask.sum(0) > 0
    groups, cur = [], []
    for x, on in enumerate(cols):
        if on:
            cur.append(x)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        sub = mask[:, g[0]:g[-1] + 1]
        if sub.sum() >= min_pixels:
            out.append(sub)
    return out


def read_mask(mask: np.ndarray, min_score: float = 0.35, max_digits: int = 2) -> int | None:
    glyphs = split_glyphs(mask)
    if not glyphs:
        return None
    # Hoehe der groessten Glyphe als Referenz; deutlich kleinere Teile sind Rauschen
    def height(g):
        ys = np.flatnonzero(g.any(1))
        return int(ys[-1] - ys[0] + 1)
    hmax = max(height(g) for g in glyphs)
    glyphs = [g for g in glyphs if height(g) >= 0.5 * hmax][:max_digits]
    digits = []
    for g in glyphs:
        d, s = classify_glyph(g)
        if d is None or s < min_score:
            return None
        digits.append(str(d))
    return int("".join(digits)) if digits else None


def components(mask: np.ndarray, min_pixels: int = 1) -> list[np.ndarray]:
    """Alle 8-zusammenhaengenden Flaechen als Arrays von (y, x)-Punkten."""
    h, w = mask.shape
    seen = np.zeros_like(mask, bool)
    out = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, pts = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(pts) >= min_pixels:
            out.append(np.array(pts))
    return out


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Groesste 4-zusammenhaengende Flaeche der Maske (einfaches Flood-Fill)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, bool)
    best: list = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(comp) > len(best):
            best = comp
    out = np.zeros_like(mask, bool)
    for y, x in best:
        out[y, x] = True
    return out
