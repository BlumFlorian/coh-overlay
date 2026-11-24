"""Auslesen der Spiel-UI: wer ist am Zug, verbleibende Zuege, Reserve-Zaehler, Cursor-Spalte.

- Zuganzeige (eigene): tuerkises Emblem unter dem Raster, immer unter der Spalte mit dem Cursor.
  Ist es nicht da, ist der Gegner am Zug.
- Reserve: weisse Zahl im Kasten rechts unten (ich) bzw. links oben (Gegner).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from . import digits as D
from .model import COLS
from .vision import Geometry

ROOT = Path(__file__).resolve().parent.parent
GLYPHS = Path(__file__).parent / "data" / "move_glyphs"
UNKNOWN = ROOT / "dataset" / "glyphs"

# Referenzkoordinaten bei 1920x1080
MOVES_BAND = (590, 978, 1330, 1018)  # unter der cyanfarbenen Heldenlinie (y~965), dort sitzt nur das Emblem
RESERVE_ME = (1415, 925, 1495, 980)
RESERVE_EN = (430, 100, 510, 160)
# Lebensbalken (voll = 223 px): Gegner leert sich von links, ich von rechts.
HP_EN = (1378, 1601, 95, 112)
HP_ME = (316, 539, 958, 980)
LEGEND_RIGHT = 419  # in der L1-Ansicht verdeckt die Steuerungs-Legende meinen Balken links davon


def _green(a):
    a = a.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g > 140) & (g > r + 50) & (g > b + 50)


def _hp_bar(a):
    """Lebensbalken in jeder Fuellfarbe: gruen (viel HP), orange (mittel), rot (wenig).
    Analyse 20261124_152341: roter Balken bei 18 HP nicht erkannt -> Gegner-HP 100 angenommen."""
    a = a.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = np.maximum(r, g)
    return _green(a) | ((mx > 130) & (b < 60) & (mx - b > 90) & (r > g + 40) & (np.abs(r - g) > 40))         | ((r > 150) & (g > 90) & (g < r - 30) & (b < 50))


# Zauberleiste: Feld am Portraet, fuellt sich von unten (ich: cyan, Gegner: rot)
MP_ME = (305, 872, 385, 944)
MP_EN = (1535, 140, 1610, 208)


def read_mp(img, geo) -> tuple[float, float]:
    """Fuellstand = Hoehe der obersten 'gefuellten' Zeile, wenn darunter ueberwiegend gefuellt ist.
    Pixelweise, weil das Zaubersymbol in der Mitte und der Rahmen die Zeilenmittel stoeren."""
    def fill(box, pix):
        x0, y0, x1, y1 = box
        a = img[int(y0 * geo.sy):int(y1 * geo.sy), int(x0 * geo.sx):int(x1 * geo.sx), :3].astype(int)
        rowfrac = pix(a).mean(1)
        filled = rowfrac >= 0.25
        n = len(filled)
        for top in range(n):
            below = filled[top:]
            if filled[top] and below.mean() >= 0.6:
                return (n - top) / n
        return 0.0
    # ich: cyan (unter der halbdurchsichtigen L1-Legende nur noch leicht gruenlich)
    me = fill(MP_ME, lambda a: (a[..., 1] - a[..., 0] > 15) & (a[..., 1] > 120))
    en = fill(MP_EN, lambda a: (a[..., 0] - a[..., 1] > 80) & (a[..., 0] > 150))
    return round(me, 2), round(en, 2)


def _run(on: np.ndarray, from_right: bool, gap: int = 3):
    """Ende des zusammenhaengenden Balkens: von der vollen Seite aus bis zur ersten Luecke > gap.
    So zaehlen Verzierungen neben dem leeren Teil des Balkens nicht mit."""
    idx = np.flatnonzero(on)
    if not len(idx):
        return None
    seq = idx[::-1] if from_right else idx
    end = seq[0]
    for i in seq[1:]:
        if abs(int(i) - int(end)) > gap + 1:
            break
        end = i
    return int(end)


def read_hp(img, geo) -> tuple[int | None, int | None]:
    sx, sy = geo.sx, geo.sy
    x0, x1, y0, y1 = HP_EN
    m = _hp_bar(img[int(y0 * sy):int(y1 * sy), int((x0 - 20) * sx):int((x1 + 5) * sx)])
    cols = _run(m.sum(0) >= 3, from_right=True)  # Gegnerbalken fuellt von rechts
    en = None
    if cols is not None:
        left = (x0 - 20) * sx + cols
        en = int(round(100 * (x1 * sx - left) / ((x1 - x0) * sx)))
    x0, x1, y0, y1 = HP_ME
    m = _hp_bar(img[int(y0 * sy):int(y1 * sy), int(LEGEND_RIGHT * sx):int((x1 + 20) * sx)])
    cols = _run(m.sum(0) >= 3, from_right=False)  # mein Balken fuellt von links
    if cols is not None:
        right = LEGEND_RIGHT * sx + cols
        me = int(round(100 * (right - x0 * sx) / ((x1 - x0) * sx)))
    else:
        me = 40  # Balkenende hinter der Legende -> hoechstens ~46
    return max(0, min(100, me)), (max(0, min(100, en)) if en is not None else None)


@dataclass
class UiState:
    my_turn: bool
    moves: int | None
    cursor_col: int | None
    my_reserve: int | None
    enemy_reserve: int | None
    my_hp: int | None = None  # aus dem gruenen Lebensbalken (Max-HP 100 angenommen)
    enemy_hp: int | None = None
    my_mp: float | None = None  # Fuellstand der Zauberleiste 0..1 (Feld mit dem Zaubersymbol)
    enemy_mp: float | None = None

    @property
    def my_spell_ready(self) -> bool:
        return (self.my_mp or 0) >= 0.97

    @property
    def enemy_spell_ready(self) -> bool:
        return (self.enemy_mp or 0) >= 0.97


def _crop(img, box, geo: Geometry):
    x0, y0, x1, y1 = box
    return img[int(y0 * geo.sy):int(y1 * geo.sy), int(x0 * geo.sx):int(x1 * geo.sx)]


def _teal(a):
    a = a.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g > 170) & (r > 90) & (r < 175) & (g - r > 40) & (b > 130) & (g > b)


def _digit_fill(a):
    a = a.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lavender = (b >= g) & (b > r + 12) & (b > 150)
    white = (a.min(-1) > 215) & (b >= g - 6)  # oberer, fast weisser Teil der Ziffer
    return lavender | white


def _white(a):
    return a.astype(int).min(-1) > 225


_glyph_cache: list | None = None


def _glyph_templates():
    global _glyph_cache
    if _glyph_cache is None:
        _glyph_cache = []
        for f in sorted(GLYPHS.glob("*.png")):
            n = D._norm(np.asarray(Image.open(f)) > 128)
            if n:
                _glyph_cache.append((int(f.name.split("_")[0]), n[0], n[1]))
    return _glyph_cache


def read_move_glyph(mask: np.ndarray) -> tuple[int | None, float]:
    n = D._norm(mask)
    if n is None:
        return None, 0.0
    a, asp = n
    best, bs = None, -1.0
    for d, t, tasp in _glyph_templates():
        s = float((a * t).sum()) - 0.6 * abs(np.log(asp / tasp))
        if s > bs:
            best, bs = d, s
    return best, bs


def read_ui(img: np.ndarray) -> UiState:
    h, w = img.shape[:2]
    geo = Geometry(w, h)
    band = _crop(img, MOVES_BAND, geo)
    teal = _teal(band)
    moves = cursor_col = None
    my_turn = int(teal.sum()) > 150 * geo.sx * geo.sy
    if my_turn:
        colsum = np.convolve(teal.sum(0), np.ones(31), mode="same")  # Emblem = dichteste Stelle
        cx = MOVES_BAND[0] * geo.sx + float(np.argmax(colsum))
        gx0, _, gx1, _ = geo.grid("me")
        cursor_col = int(min(COLS - 1, max(0, (cx - gx0) // ((gx1 - gx0) / COLS))))
        # Emblem genau unter der Cursor-Spalte ausschneiden
        ccx = gx0 + (cursor_col + 0.5) * (gx1 - gx0) / COLS
        y0 = 968 * geo.sy
        crop = img[int(y0):int(y0 + 44 * geo.sy), int(ccx - 25 * geo.sx):int(ccx + 25 * geo.sx)]
        mask = D.largest_component(_digit_fill(crop))
        d, score = read_move_glyph(mask)
        if d is not None and score >= 0.7:
            moves = d
        else:
            fd, fs = D.classify_glyph(mask)  # Ersatz: Vergleich mit Systemschriften
            if fd is not None and fs >= 0.55 and fd <= 6:
                moves = fd
        if (d is None or score < 0.7) and mask.sum() > 30:
            UNKNOWN.mkdir(parents=True, exist_ok=True)
            Image.fromarray((mask * 255).astype(np.uint8)).save(
                UNKNOWN / f"zuege_{datetime.now():%Y%m%d_%H%M%S}.png")
    my_res = D.read_mask(_white(_crop(img, RESERVE_ME, geo)))
    en_res = D.read_mask(_white(_crop(img, RESERVE_EN, geo)))
    my_hp, en_hp = read_hp(img, geo)
    my_mp, en_mp = read_mp(img, geo)
    return UiState(my_turn, moves, cursor_col, my_res, en_res, my_hp, en_hp, my_mp, en_mp)
