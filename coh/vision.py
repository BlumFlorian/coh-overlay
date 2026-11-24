"""Bilderkennung auf der L1-Werteansicht (Raster + Icons).

Pro Zelle (unabhaengig vom Arena-Hintergrund):
  - Herz-Icon oben links + gelbgruene Zahl  -> idle Einheit; Zahl = Toughness
        1-3 -> Core, andere einstellige Zahl -> Elite (1x2), zweistellig -> Champion (2x2)
  - Burg-Icon + cyanfarbene Zahl            -> Wandsegment
  - cyanfarbener Ladebalken                 -> unterer Bildrand einer ladenden Formation
Core-Einheiten werden pro Seite nach Aussehen (Farbhistogramm des Rumpfs, ohne Hintergrundfarben)
in Klassen a, b, c, ... gruppiert. Gleiche Klasse = gleicher Typ + gleiche Farbe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .model import COLS, ROWS, Hero, Piece, Side, State, RULES

# Referenzgeometrie bei 1920x1080 Client-Flaeche (aus Screenshots gemessen).
REF_W, REF_H = 1920, 1080
GRID = {"me": (617, 572, 1302, 960), "enemy": (617, 118, 1302, 508)}
# Typische Max-PWR einer Formation bei Heldenlevel 10 (Staerke = Fuellstand des Balkens x Max)
TYPICAL_MAX = {"core": 10, "elite": 30, "champion": 100}
_DIGITS = {k: v for k, v in np.load(Path(__file__).parent / "data" / "digits.npz").items()}


@dataclass
class CellInfo:
    kind: str  # "empty" | "unit" | "wall"
    feat: np.ndarray | None = None
    cls: str | None = None
    tough: int | None = None  # gelesene Toughness (None = unbekannt)
    tier: str = "core"
    cursor: bool = False  # vom Cursor eingefaerbt -> Aussehen unzuverlaessig
    torso: np.ndarray | None = None
    afeat: np.ndarray | None = None  # Merkmal jeder Zelle (auch Formationen), fuer die Asset-Sammlung
    sat: float | None = None  # Anteil kraeftig farbiger Pixel (ohne Sandboden), Ersatzmerkmal fuer die Farbe
    guessed: bool = False  # Farbe nur geschaetzt (Farbton der ganzen Figur oder Saettigung)
    wide: np.ndarray | None = None  # Pixel der ganzen Figur rechts von Herz/Zahl (fuer die Elite-Farbe)
    hue: np.ndarray | None = None  # Farbton-Histogramm der ganzen Figur ohne Bodenfarben
    vivid: np.ndarray | None = None  # nur kraeftige Farben (Ruestung statt Haut/Leder) + Weiss, siehe _vivid_hist
    hfeat: np.ndarray | None = None  # Kopf/Helm-Merkmal ohne Cursor-Hintergrund (Farbe der Einheit unter dem Cursor)


@dataclass
class SideScan:
    cells: dict = field(default_factory=dict)  # (c, r) -> CellInfo; r = Modellreihe (0 = Front)
    bars: list = field(default_factory=list)  # (col_start, col_end, row)
    bar_info: dict = field(default_factory=dict)  # (c0, c1, row) -> Bar
    floor: object = None  # Background der Bodenfarben (fuer Farbton-Messungen)
    hcents: dict = field(default_factory=dict)  # Klasse (Buchstabe) -> Farbton-Profil der ganzen Figur


class Geometry:
    def __init__(self, width: int, height: int):
        self.sx, self.sy = width / REF_W, height / REF_H

    def grid(self, who: str):
        x0, y0, x1, y1 = GRID[who]
        return x0 * self.sx, y0 * self.sy, x1 * self.sx, y1 * self.sy

    def cell_box(self, who: str, c: int, r: int):
        """Pixelbox (x0, y0, x1, y1) der Modellzelle (c, r). Gegner: Front unten."""
        x0, y0, x1, y1 = self.grid(who)
        cw, ch = (x1 - x0) / COLS, (y1 - y0) / ROWS
        sr = r if who == "me" else ROWS - 1 - r  # Bildschirmreihe von oben
        return x0 + c * cw, y0 + sr * ch, x0 + (c + 1) * cw, y0 + (sr + 1) * ch

    def cell_center(self, who: str, c: float, r: float):
        gx0, gy0, gx1, gy1 = self.grid(who)
        cw, ch = (gx1 - gx0) / COLS, (gy1 - gy0) / ROWS
        sr = r if who == "me" else ROWS - 1 - r
        return gx0 + (c + 0.5) * cw, gy0 + (sr + 0.5) * ch


def _rgb(img: np.ndarray, x0, y0, x1, y1) -> np.ndarray:
    return img[int(y0):int(y1), int(x0):int(x1), :3].astype(np.int16)


def _frac(mask: np.ndarray) -> float:
    return float(mask.mean()) if mask.size else 0.0


def _icon_red(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (r > 80) & (r > g * 1.7) & (r > b * 1.7) & (g < 100)


def _yellow(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (g > 170) & (r > 140) & (b < 140) & (g >= r + 10)  # Ziffern sind gelbgruen, Sand ist gelbrot


def _cyan(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (b > 190) & (g > 160) & (r < 160)


def _cursor_tint(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (g > r + 30) & (b > r + 20) & (r < 140)


def _cursor_bg(px):
    """Nur der helle Cyan-Hintergrund des Cursors (~RGB 62/200/222 bis 63/228/249), nicht die
    dunklere tuerkise Ruestung der Bogenschuetzen (die _cursor_tint mit erfasst)."""
    r, g, b = px[..., 0].astype(int), px[..., 1].astype(int), px[..., 2].astype(int)
    return (g > 170) & (b > 190) & (r < 130) & (b > r + 90)


def _bar_mask(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (b > 200) & (g > 170) & (r > 60) & (r < 190) & (b - r > 50)


def read_number(mask: np.ndarray) -> int | None:
    """Liest eine Toughness-Zahl aus einer Binaermaske. Zweistellig -> 10 (nur 'mind. 10').
    Einstellig: Vorlagen 2/3/6, schmale Ziffer -> 1, sonst 5 (= 'irgendeine Elite-Zahl')."""
    if mask.sum() < 25:
        return None
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
    groups = [g for g in groups if mask[:, g].sum() > 20]
    if len(groups) >= 2:
        return 10
    if not groups:
        return None
    sub = mask[:, groups[0][0]:groups[0][-1] + 1]
    ys = np.flatnonzero(sub.sum(1) > 0)
    sub = sub[ys[0]:ys[-1] + 1]
    h, w = sub.shape
    if w < 0.45 * h:
        return 1
    from PIL import Image
    norm = np.asarray(Image.fromarray((sub * 255).astype(np.uint8)).resize((12, 18), Image.BILINEAR),
                      np.float32) / 255
    best, bv = None, -1.0
    for k, t in _DIGITS.items():
        a, b = norm - norm.mean(), t - t.mean()
        v = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))
        if v > bv:
            best, bv = k, v
    return int(best) if bv >= 0.75 else 5


def _two_digits(mask: np.ndarray, gap: float) -> bool:
    """Zwei Ziffern-Gruppen (je > 20 Pixel), die zweite hoechstens `gap` Pixel nach der ersten."""
    cols = np.flatnonzero(mask.sum(0) > 0)
    if len(cols) == 0:
        return False
    groups = np.split(cols, np.flatnonzero(np.diff(cols) > 1) + 1)
    groups = [g for g in groups if mask[:, g].sum() > 20]
    return len(groups) >= 2 and groups[1][0] - groups[0][-1] <= gap


@dataclass
class Bar:
    c0: int
    c1: int
    srow: int  # Bildschirmreihe (von oben) der Zelle mit dem Balken
    xa: float  # Pixel: Balkenanfang, -ende (inkl. leerem Rest), Hoehe der Fuellung
    xb: float
    y: float
    fill: float  # gefuellter Anteil 0..1
    ct: int | None = None  # gelesene Restladezeit (None = keine Ziffer -> vermutlich 1)
    power: int | None = None


def _orange(px):
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (r > 170) & (g > 110) & (b < 110) & (r > b + 80)


def find_bars(img: np.ndarray, geo: Geometry, who: str) -> list[Bar]:
    """Ladebalken: duenne cyanfarbene Fuellung, rechts davon der dunkle, noch leere Rest,
    darueber/darunter ein goldener Rahmen."""
    x0, y0, x1, y1 = geo.grid(who)
    cw, ch = (x1 - x0) / COLS, (y1 - y0) / ROWS
    px = _rgb(img, x0, y0, x1, y1)
    m = _bar_mask(px)
    dark = px.max(-1) < 75
    orange = _orange(px)
    found = []
    for y in range(m.shape[0]):
        xs = np.flatnonzero(m[y])
        if len(xs) < cw * 0.12:
            continue
        splits = np.flatnonzero(np.diff(xs) > 3)
        for seg in np.split(xs, splits + 1):
            n = len(seg)
            if n < cw * 0.12 or n > cw * 2.2:
                continue
            # Direkt hinter der Fuellung kann eine schmale orange Fuellstandsmarke sitzen -> bis zu
            # 4 Pixel ueberspringen, bevor der dunkle Rest gemessen wird (sonst Laenge 0 und ein
            # ladender Champion wird zur 1-spaltigen Formation).
            right = dark[y, seg[-1] + 2:seg[-1] + 2 + int(cw * 2)]
            skip = next((i for i in range(min(5, right.size)) if right[i]), None)
            if skip and not orange[y, seg[-1] + 2:seg[-1] + 2 + skip].any():
                skip = None  # uebersprungen wird nur die orange Marke, nichts anderes
            if skip is None:
                dlen = 0
            else:
                rest = right[skip:]
                dlen = skip + (int(np.argmin(rest)) if not rest.all() else rest.size)
            if n < cw * 0.45 and dlen < cw * 0.1:
                continue
            total = n + dlen
            if total < cw * 0.5:
                continue
            # goldener Rahmen ober- oder unterhalb (Engelsfluegel u. ae. haben keinen)
            span = slice(seg[0], seg[0] + total)
            frame = max(orange[max(0, y - dy), span].mean() for dy in range(2, 9))
            frame = max(frame, max(orange[min(m.shape[0] - 1, y + dy), span].mean() for dy in range(4, 16)))
            if frame < 0.3:
                continue
            found.append((seg[0], seg[0] + total, y, n / total))
    out = []
    for xa, xb, y, f in found:
        if any(abs(y - oy) < 14 and abs(xa - oa) < 20 for oa, ob, oy, of in out):
            continue
        out.append((xa, xb, y, f))
    res = []
    for xa, xb, y, f in out:
        thick = m[max(0, y - 2):y + 14, xa + 2].sum()  # Balken sind duenn, Cursor flaechig
        if thick > 13:
            continue
        if xb - xa < 0.6 * cw:  # zu kurz fuer einen Ladebalken (z. B. Kante des Cursor-Rahmens)
            continue
        bar = Bar(int(xa // cw), int(min(COLS - 1, (xb - 4) // cw)), int((y - 6) // ch),
                  x0 + xa, x0 + xb, y0 + y, float(f))
        _read_bar_numbers(img, geo, bar)
        res.append(bar)
    return res


CT_GLYPHS = Path(__file__).parent / "data" / "ct_glyphs"
_ct_cache: list | None = None


def ct_silhouette(a: np.ndarray) -> np.ndarray:
    """Ziffer = vom braunen Umriss eingeschlossene Flaeche (Flood-Fill von aussen)."""
    from . import digits as D
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    outline = (r > 50) & (r < 200) & (g < r - 15) & (b < g + 15) & (a.max(-1) < 210)
    h, w = outline.shape
    seen = np.zeros_like(outline)
    stack = [(y, x) for y in range(h) for x in (0, w - 1)] + [(y, x) for x in range(w) for y in (0, h - 1)]
    stack = [p for p in stack if not outline[p]]
    for p in stack:
        seen[p] = True
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and not outline[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return D.largest_component(~seen)


def _ct_templates():
    global _ct_cache
    if _ct_cache is None:
        from PIL import Image
        from . import digits as D
        _ct_cache = []
        for f in sorted(CT_GLYPHS.glob("*.png")):
            n = D._norm(np.asarray(Image.open(f)) > 128)
            if n:
                _ct_cache.append((int(f.name.split("_")[0]), n[0], n[1]))
    return _ct_cache


def _open1(m: np.ndarray) -> np.ndarray:
    """Morphologische Oeffnung (3x3): trennt duenne Bruecken, z. B. Federn, die an der Ziffer haengen."""
    p = np.pad(m, 1)
    h, w = m.shape
    er = np.ones_like(m)
    for dy in range(3):
        for dx in range(3):
            er &= p[dy:dy + h, dx:dx + w]
    p = np.pad(er, 1)
    di = np.zeros_like(m)
    for dy in range(3):
        for dx in range(3):
            di |= p[dy:dy + h, dx:dx + w]
    return di & m


def read_ct_digit(a: np.ndarray) -> tuple[int | None, float]:
    from . import digits as D
    sil = ct_silhouette(a)
    best, bs = None, -1.0
    # Zweite Lesart ohne duenne Anhaengsel (Analyse 20261124_145258: Greifenfeder an der "4",
    # Vorlage passte nur zu 37 % -> Ersatzwert 2). Die bessere Uebereinstimmung zaehlt.
    for m in (sil, D.largest_component(_open1(sil))):
        n = D._norm(m)
        if n is None:
            continue
        for d, t, tasp in _ct_templates():
            s = float((n[0] * t).sum()) - 0.6 * abs(np.log(n[1] / tasp))
            if s > bs:
                best, bs = d, s
    return best, bs


def _ct_crop(img: np.ndarray, geo: Geometry, bar: "Bar") -> np.ndarray:
    s = geo.sy
    mid = (bar.xa + bar.xb) / 2
    return img[int(bar.y - 34 * s):int(bar.y - 3 * s), int(mid - 18 * s):int(mid + 18 * s), :3].astype(int)


def _read_bar_numbers(img: np.ndarray, geo: Geometry, bar: Bar) -> None:
    """Restladezeit ueber dem Balken: Ziffer vorhanden (cyanfarbene untere Haelfte) -> per
    Umriss-Vorlagen lesen; nicht lesbar -> 2. Keine Ziffer -> 1."""
    s = geo.sy
    mid = (bar.xa + bar.xb) / 2
    a = img[int(bar.y - 30 * s):int(bar.y - 6 * s), int(mid - 14 * s):int(mid + 14 * s), :3].astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    cyan = int(((b > 190) & (g > 140) & (r < 130) & (b > r + 90)).sum())
    if cyan <= 5 * s * s:
        bar.ct = 1
        return
    d, sc = read_ct_digit(_ct_crop(img, geo, bar))
    bar.ct = d if d is not None and sc >= 0.6 else 2


class Background:
    """Haeufige Farben leerer Zellen (8 Stufen je Kanal) -> werden aus den Merkmalen entfernt."""

    def __init__(self, samples: list[np.ndarray]):
        self.bins = np.zeros(512, bool)
        if samples:
            q = np.concatenate([(s.reshape(-1, 3) // 32) for s in samples])
            idx = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
            cnt = np.bincount(idx, minlength=512)
            self.bins = cnt > 0.004 * len(idx)

    def mask(self, px: np.ndarray) -> np.ndarray:
        q = px // 32
        return self.bins[q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]]


def _features(px: np.ndarray, bg: Background) -> np.ndarray:
    """Farbhistogramm der Nicht-Hintergrund-Pixel: 12 Farbtoene x 2 Saettigung + Weiss + Dunkel."""
    keep = ~bg.mask(px).reshape(-1)
    f = px.reshape(-1, 3).astype(np.float32)[keep] / 255.0
    if len(f) < 20:
        f = px.reshape(-1, 3).astype(np.float32) / 255.0
    mx, mn = f.max(1), f.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = f[:, 0], f[:, 1], f[:, 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.select([mx == r, mx == g], [((g - b) / d) % 6, (b - r) / d + 2], (r - g) / d + 4) / 6.0
    hist = np.zeros(26, np.float32)
    colored = (sat > 0.25) & (mx > 0.25)
    hb = np.minimum((hue[colored] * 12).astype(int), 11)
    sb = (sat[colored] > 0.6).astype(int)
    np.add.at(hist, hb * 2 + sb, 1)
    hist[24] = ((sat <= 0.25) & (mx > 0.7)).sum()
    hist[25] = (mx <= 0.25).sum()
    return hist / max(hist.sum(), 1)


def _hue_hist(px: np.ndarray, floor: Background) -> np.ndarray:
    """12 Farbtoene kraeftiger Pixel + Anteil heller grauer/weisser Pixel, ohne Bodenfarben."""
    keep = ~floor.mask(px).reshape(-1)
    f = px.reshape(-1, 3)[keep].astype(np.float32) / 255.0
    out = np.zeros(13, np.float32)
    if len(f) < 20:
        return out
    mx, mn = f.max(1), f.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = f[:, 0], f[:, 1], f[:, 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.select([mx == r, mx == g], [((g - b) / d) % 6, (b - r) / d + 2], (r - g) / d + 4) / 6.0
    strong = (sat > 0.3) & (mx > 0.35)
    np.add.at(out, np.minimum((hue[strong] * 12).astype(int), 11), 1)
    out[12] = ((sat <= 0.3) & (mx > 0.55)).sum()
    return out / max(out.sum(), 1)


def _vivid_hist(px: np.ndarray, floor: "Background") -> np.ndarray:
    """Nur kraeftige, helle Farben (24 Farbtoene, Saettigung > 0.5) + Anteil Weiss/Hellgrau, bezogen
    auf alle Pixel ohne Boden. Haut, Leder und Schatten fallen heraus; uebrig bleibt v. a. die
    Ruestung. Trennt z. B. den goldenen Greif klar von blauen/weissen Klassen, was das grobe
    Farbton-Profil (_hue_hist) nicht schafft (Analysen 20261124_143157 bis _144125)."""
    keep = ~floor.mask(px).reshape(-1)
    f = px.reshape(-1, 3)[keep].astype(np.float32) / 255.0
    out = np.zeros(25, np.float32)
    if len(f) < 20:
        return out
    mx, mn = f.max(1), f.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = f[:, 0], f[:, 1], f[:, 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.select([mx == r, mx == g], [((g - b) / d) % 6, (b - r) / d + 2], (r - g) / d + 4) / 6.0
    vivid = (sat > 0.5) & (mx > 0.55)
    np.add.at(out, np.minimum((hue[vivid] * 24).astype(int), 23), 1)
    out[24] = ((sat < 0.18) & (mx > 0.65)).sum()
    return out / len(f)


def _vivid_pick(h, vcents: dict, margin: float = 1.5, limit: float = 0.5):
    """Klasse nach kraeftigen Farben, nur bei klarem Vorsprung (sonst None)."""
    if h is None or not h.any() or len(vcents) < 2:
        return None
    vd = sorted((float(np.abs(vc - h).sum()), k) for k, vc in vcents.items())
    if vd[0][0] < limit and vd[1][0] >= margin * vd[0][0]:
        return vd[0][1]
    return None


def _sat_pick(sat: float | None, sats: dict):
    """Klasse mit der naechsten Saettigung, nur bei klarem Abstand (>= 0.08) zur zweitnaechsten."""
    if sat is None or not sats:
        return None
    ds = sorted((abs(sat - cs), n) for n, cs in sats.items())
    if len(ds) == 1 or ds[1][0] - ds[0][0] >= 0.08:
        return ds[0][1]
    return None


def _saturation(px: np.ndarray) -> float:
    """Anteil kraeftig farbiger Pixel ohne den sandfarbenen Boden. Weisse Einheiten (und der
    graue Schwertmeister) liegen niedrig, blaue und goldene deutlich hoeher."""
    f = px.reshape(-1, 3).astype(np.float32) / 255.0
    mx, mn = f.max(1), f.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = f[:, 0], f[:, 1], f[:, 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.select([mx == r, mx == g], [((g - b) / d) % 6, (b - r) / d + 2], (r - g) / d + 4) / 6.0
    sand = (hue > 0.06) & (hue < 0.13) & (sat > 0.25) & (sat < 0.55) & (mx > 0.6)
    return float(((sat > 0.3) & (mx > 0.25) & ~sand).mean()) if len(f) else 0.0


def _cursor_col_from_tint(img: np.ndarray, geo: Geometry, cursor_col: int) -> int:
    """Gegenprobe zur Cursor-Spalte aus dem Zug-Emblem. Der Cursor springt sofort, das Emblem
    gleitet hinterher. Steht der Cursor auf einem leeren Feld (glatte Cyan-Flaeche, >= 0.8) in einer
    anderen Spalte, gilt diese -- nur wenn genau eine Zelle so aussieht und die Emblem-Spalte
    kein Cursor-Anzeichen hat. (Analysen 20261113_000246, _001246, 20261124_125533)"""
    tint = {(c, r): _frac(_cursor_tint(_rgb(img, *geo.cell_box("me", c, r))))
            for c in range(COLS) for r in range(ROWS)}
    if max(tint[(cursor_col, r)] for r in range(ROWS)) >= 0.25:
        return cursor_col
    strong = [k for k, t in tint.items() if t >= 0.8]
    if len(strong) == 1 and not any(t >= 0.6 for k, t in tint.items() if k != strong[0]):
        return strong[0][0]
    return cursor_col


def scan_side(img: np.ndarray, geo: Geometry, who: str, cursor_col: int | None = None) -> SideScan:
    scan = SideScan()
    torsos = {}
    cursor_cell = None
    if cursor_col is not None and who == "me":
        cursor_col = _cursor_col_from_tint(img, geo, cursor_col)
    if cursor_col is not None:
        fr =[(_frac(_cursor_tint(_rgb(img, *geo.cell_box(who, cursor_col, r)))), r) for r in range(ROWS)]
        fr.sort(reverse=True)
        if fr[0][0] > 0.6 or (fr[0][0] > 0.25 and fr[0][0] > 2.5 * fr[1][0]):  # deutlich eingefaerbt
            cursor_cell = (cursor_col, fr[0][1])
    for c in range(COLS):
        for r in range(ROWS):
            x0, y0, x1, y1 = geo.cell_box(who, c, r)
            w, h = x1 - x0, y1 - y0
            corner = _rgb(img, x0 + 0.04 * w, y0 + 0.06 * h, x0 + 0.30 * w, y0 + 0.40 * h)
            numpx = _rgb(img, x0 + 0.02 * w, y0 + 0.48 * h, x0 + 0.36 * w, y0 + 0.97 * h)
            yel, cya = _yellow(numpx), _cyan(numpx)
            info = CellInfo("empty")
            if _frac(_icon_red(corner)) > 0.07 and max(_frac(yel), _frac(cya)) > 0.08:
                if _frac(yel) >= _frac(cya):
                    info.kind = "unit"
                    info.tough = t = read_number(yel)
                    if t is not None and t < 10 and yel[:, -2:].any():
                        # Ziffer am Rand abgeschnitten (z. B. "27" beim Schwertmeister): breiter lesen,
                        # aber nur, wenn die zweite Ziffer direkt anschliesst (keine gelbe Ruestung).
                        wide = _yellow(_rgb(img, x0 + 0.02 * w, y0 + 0.48 * h, x0 + 0.52 * w, y0 + 0.97 * h))
                        if _two_digits(wide, gap=0.08 * w):
                            info.tough = t = 10
                    info.tier = "core" if t is not None and t <= 3 else ("champion" if t and t >= 10 else "elite")
                else:
                    info.kind = "wall"
                    # Wand-HP: Schriftvorlagen lesen 7/9/10/14 usw. genau; Ersatz: alte Vorlagen (1-3, 10)
                    from .digits import read_mask
                    info.tough = read_mask(_cyan(_rgb(img, x0 + 0.02 * w, y0 + 0.48 * h,
                                                      x0 + 0.55 * w, y0 + 0.97 * h))) or read_number(cya)
            # Rumpf: ohne Icon/Zahl, ohne Leuchten oben und Koepfe der Reihe dahinter
            torsos[(c, r)] = _rgb(img, x0 + 0.50 * w, y0 + 0.25 * h, x0 + 0.65 * w, y0 + 0.55 * h)
            info.cursor = (c, r) == cursor_cell
            info.torso = torsos[(c, r)]
            info.wide = _rgb(img, x0 + 0.38 * w, y0 + 0.08 * h, x0 + 0.95 * w, y0 + 0.95 * h)
            scan.cells[(c, r)] = info
    front = -1 if who == "me" else 1  # Modellrichtung zur Front
    nobg = Background([])
    # Referenz "leerer Boden": icon-lose Zellen der beiden hintersten Reihen
    back_rows = (ROWS - 1, ROWS - 2) if who == "me" else (0, 1)
    empties = [_features(torsos[(c, r)], nobg) for c in range(COLS) for r in back_rows
               if scan.cells[(c, r)].kind == "empty" and (c, r) != cursor_cell]
    floor = np.mean(empties, 0) if empties else None

    def looks_occupied(cell) -> bool:
        if floor is None:
            return True
        return float(np.abs(_features(torsos[cell], nobg) - floor).sum()) > 0.6

    for bar in find_bars(img, geo, who):
        c0, c1, srow = bar.c0, bar.c1, bar.srow
        r = srow if who == "me" else ROWS - 1 - srow
        if c1 > c0 and cursor_col is not None and c0 <= cursor_col <= c1 and bar.fill <= 0.56:
            # Cursor auf einem idle Champion: Das Spiel zeigt eine Vorschau (Balken mit Start-PWR,
            # halb gefuellt, Herz ausgeblendet). Kein ladender Champion, sondern ein idle 2x2-Piece.
            # (Ein gerade erst aktivierter Champion sieht genauso aus -- seltener und harmloser.)
            top = r + front  # Herz-Zelle = bildschirm-obere linke Zelle des Pieces
            if 0 <= top < ROWS:
                cell = scan.cells[(c0, top)]
                cell.kind, cell.tier, cell.cursor, cell.cls = "unit", "champion", True, None
                for c in (c0, c1):
                    for rr in (top, r):
                        if (c, rr) != (c0, top):
                            scan.cells[(c, rr)].kind = "empty"
            continue
        if (c0, r) == cursor_cell:
            # Der Cursor steht auf dem hintersten Element der Spalte (oder dem ersten freien Feld).
            # Echter Balken: davor liegen Formationsfelder (belegt, aber ohne Herz-Symbol).
            # Sonst ist es die Vorschau einer idle Einheit unter dem Cursor bzw. eines leeren Feldes.
            above = (c0, r + front)
            real = 0 <= above[1] < ROWS and scan.cells[above].kind == "empty" and looks_occupied(above)
            # ...aber nicht, wenn das Feld davor zu einer idle Elite/Champion gehoert (Herz oben links)
            for ac in (c0, c0 - 1):
                anchor = scan.cells.get((ac, r + 2 * front))
                if anchor and anchor.kind == "unit" and anchor.tier != "core" and                         (ac == c0 or anchor.tier == "champion"):
                    real = False
            if not real:
                ahead = [scan.cells[(c0, rr)].kind for rr in range(ROWS) if (rr - r) * front > 0]
                if any(k != "empty" for k in ahead) and scan.cells[(c0, r)].kind == "empty" \
                        and _frac(_cursor_tint(_rgb(img, *geo.cell_box(who, c0, r)))) < 0.7:  # glatt cyan = leer
                    scan.cells[(c0, r)].kind = "unit"  # Einheit unter dem Cursor, Typ unbekannt
                continue
        scan.bars.append((c0, c1, r))
        scan.bar_info[(c0, c1, r)] = bar
        # Wo ein Ladebalken liegt, steht keine Wand. Ein roter/oranger Champion (Greif) taeuscht
        # das Herz-Symbol vor, die Balken-Ziffer wirkt wie Wand-HP (Analyse 20261124_145258:
        # "Wand 5" mitten im ladenden Greif -> Champion zerfiel in Hindernisse).
        for c in range(c0, c1 + 1):
            if scan.cells[(c, r)].kind == "wall":
                scan.cells[(c, r)].kind, scan.cells[(c, r)].tough = "empty", None
    # Cursor auf einer Einheit ohne etwas davor (z. B. Reihe 1): Herz verdeckt, keine Ersatzregel
    # oben greift. Ein leeres Feld zeigt der Cursor als glatte Cyan-Flaeche (>= 84 % Cyan in 139
    # Bildern), eine Einheit mit Figur + Zahl/Balken (<= 52 %). Analyse 20261123_122949: Schwert-
    # kaempfer in Spalte 1 fehlte, dadurch fehlte der beste Zug.
    # Nicht bei einer ladenden Formation in der Spalte (deren Felder haben auch kein Herz).
    if cursor_cell is not None and scan.cells[cursor_cell].kind == "empty" \
            and not any(c0 <= cursor_cell[0] <= c1 for c0, c1, _ in scan.bars):
        if _frac(_cursor_tint(_rgb(img, *geo.cell_box(who, *cursor_cell)))) < 0.7:
            scan.cells[cursor_cell].kind = "unit"
    # Hintergrund aus sicher leeren Zellen lernen: hinter allem Belegten jeder Spalte.
    occupied = {c: [r for r in range(ROWS) if scan.cells[(c, r)].kind != "empty"] for c in range(COLS)}
    for c0, c1, r in scan.bars:
        for c in range(c0, c1 + 1):
            occupied[c].append(r)
    samples = []
    for c in range(COLS):
        last = max(occupied[c], default=-1)
        for r in range(last + 2, ROWS):  # +2: Platz fuer Elite-Fortsetzung
            samples.append(torsos[(c, r)])
    # Hintergrund-Entfernung ist abgeschaltet: helle Boeden (Ziegel, Sand) schnitten sonst weisse
    # Ruestungen weg. Der schmale Rumpf-Ausschnitt besteht fast nur aus der Einheit selbst.
    bg = Background([])
    # Elite-Farbe: Farbtoene der ganzen Figur, Bodenfarben (aus sicher leeren Zellen) entfernt.
    # Der schmale Rumpf trifft bei Reitern nur Visier und Edelstein, nicht die Ruestung.
    floor = Background([scan.cells[(c, r)].wide for c in range(COLS)
                        for r in range(max(occupied[c], default=-1) + 2, ROWS)])
    scan.floor = floor
    for k, v in scan.cells.items():
        if v.kind == "unit":
            v.hue = _hue_hist(v.wide, floor)
            v.vivid = _vivid_hist(v.wide, floor)
            if v.tier != "core":  # ganze Figur: 1x2 (Elite) bzw. 2x2 (Champion), Bildschirm abwaerts
                down = 1 if who == "me" else -1
                cells = [(k[0] + dc, k[1] + dr) for dc in range(2 if v.tier == "champion" else 1)
                         for dr in (0, down)]
                px = np.concatenate([scan.cells[cc].wide.reshape(-1, 3) for cc in cells if cc in scan.cells])
                v.hue = _hue_hist(px, floor)
                v.vivid = _vivid_hist(px, floor)
    for k, v in scan.cells.items():
        v.afeat = _features(torsos[k], bg)
        if v.kind == "unit":
            v.feat = v.afeat
            v.sat = _saturation(torsos[k])
            if v.tier == "core":
                # Kopf/Helm (oben in der Zelle): Unter dem Cursor verdeckt die grosse Vorschau-Ziffer
                # den Rumpf, der Kopf bleibt frei und traegt die Farbe (Helm). Ohne den hell-cyanen
                # Cursor-Hintergrund. Pruefung an 52 Cursor-Faellen mit derselben Einheit ohne
                # Cursor in einer Nachbaraufnahme: Kopf 43 richtig, Rumpf 31 (Grundrauschen ~90 %).
                x0, y0, x1, y1 = geo.cell_box(who, *k)
                hp = _rgb(img, x0 + 0.30 * (x1 - x0), y0, x0 + 0.80 * (x1 - x0), y0 + 0.24 * (y1 - y0)).reshape(-1, 3)
                hp = hp[~_cursor_bg(hp)]
                if len(hp) >= 20:
                    v.hfeat = _features(hp.reshape(1, -1, 3), bg)
            if v.tier != "core":  # Elite/Champion: Rumpf ueber beide Zellen (Bildschirm abwaerts)
                below = scan.cells.get((k[0], k[1] + (1 if who == "me" else -1)))
                if below is not None and below.torso is not None:
                    v.feat = (v.feat + _features(below.torso, bg)) / 2
                dirs = [(dc, dr) for dc in range(2 if v.tier == "champion" else 1)
                        for dr in (0, 1 if who == "me" else -1)]
                parts = [torsos[(k[0] + dc, k[1] + dr)] for dc, dr in dirs if (k[0] + dc, k[1] + dr) in torsos]
                v.sat = float(np.mean([_saturation(t) for t in parts]))
    return scan


def merge_scans(scans: list[SideScan]) -> SideScan:
    """Mehrere Aufnahmen kurz hintereinander zusammenfassen (gegen Idle-Animationen):
    Art und Toughness per Mehrheit, Merkmale gemittelt, Balken per Mehrheit."""
    if len(scans) == 1:
        return scans[0]
    out = SideScan()
    for k in scans[0].cells:
        vs = [s.cells[k] for s in scans]
        kinds = [v.kind for v in vs]
        kind = max(set(kinds), key=lambda x: (kinds.count(x), x != "empty"))
        sel = [v for v in vs if v.kind == kind]
        tough = [v.tough for v in sel]
        info = CellInfo(kind, cursor=any(v.cursor for v in vs))
        info.tough = max(set(tough), key=tough.count) if tough else None
        tiers = [v.tier for v in sel]
        info.tier = max(set(tiers), key=tiers.count)
        feats = [v.feat for v in sel if v.feat is not None]
        info.feat = np.mean(feats, 0) if feats else None
        info.afeat = np.mean([v.afeat for v in vs], 0)
        info.wide = vs[0].wide
        hues = [v.hue for v in sel if v.hue is not None]
        info.hue = np.mean(hues, 0) if hues else None
        vivids = [v.vivid for v in sel if v.vivid is not None]
        info.vivid = np.mean(vivids, 0) if vivids else None
        for name in ("hfeat",):  # Kopf/Helm (Einheit unter dem Cursor)
            vals = [getattr(v, name) for v in sel if getattr(v, name) is not None]
            setattr(info, name, np.mean(vals, 0) if vals else None)
        sats = [v.sat for v in sel if v.sat is not None]
        info.sat = float(np.mean(sats)) if sats else None
        out.cells[k] = info
    out.floor = scans[0].floor
    bars = [b for s in scans for b in s.bars]
    out.bars = sorted({b for b in bars if bars.count(b) * 2 > len(scans)})
    for s in scans:
        for k, b in s.bar_info.items():
            out.bar_info.setdefault(k, b)
    return out


def classify(scan: SideScan, link: float = 0.62, attach: float = 0.62, keep3: float = 0.45,
             relax: float = 0.9) -> None:
    """Average-Linkage-Clustering der Core-Einheiten; Einzelgaenger werden der naechsten Klasse
    zugeordnet, wenn sie nah genug sind."""
    units = [v for _, v in sorted(scan.cells.items()) if v.kind == "unit" and v.tier == "core" and not v.cursor]
    if not units:
        return
    F = np.array([v.feat for v in units])
    D = np.abs(F[:, None] - F[None]).sum(-1)
    T = np.array([v.tough if v.tough is not None else -1 for v in units])
    D = D + 9.0 * ((T[:, None] != T[None]) & (T[:, None] >= 0) & (T[None] >= 0))  # andere Toughness = anderer Typ
    clusters = [[i] for i in range(len(units))]
    while len(clusters) > 1:
        best, bi, bj = 9.0, -1, -1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = D[np.ix_(clusters[i], clusters[j])].mean()
                if d < best:
                    best, bi, bj = d, i, j
        if best > link:
            # Mehr als 3 Gruppen (je >= 2 Einheiten) gleicher Toughness sind meist eine zerfallene
            # Farbe (Bogenschuetzen: Arm/Bogen je nach Animation, Blau-Blau bis 1.33). Dann auch
            # etwas weiter auseinander noch verschmelzen. Analyse 20261124_145258: Blau als B und C
            # -> blaue Mauern (waagerecht) wurden nicht gesehen.
            n_two = sum(1 for c in clusters if len(c) >= 2)
            if not (n_two > 3 and best <= relax and len(clusters[bi]) >= 2 and len(clusters[bj]) >= 2):
                break
        # Eine Armee hat 3 Kernfarben. Zwei grosse Gruppen (je >= 3 Einheiten) nur dann noch
        # verschmelzen, wenn sie sich sehr aehnlich sind, solange es dadurch weniger als 3 Gruppen
        # gaebe. Analyse 20261124_134539: Blau und Weiss (Bogenschuetzen) bei 0.54 zu einer Klasse
        # verschmolzen -> erfundene Formationen ("Chain +7").
        n_big = sum(1 for c in clusters if len(c) >= 3)
        if len(clusters[bi]) >= 3 and len(clusters[bj]) >= 3 and n_big <= 3 and best > keep3:
            break
        clusters[bi] += clusters.pop(bj)
    # Einzelgaenger: der naechsten Klasse zuordnen, wenn nah genug -- sonst eigene Klasse
    # (eine Einheit, die als einzige ihrer Art auf dem Feld steht, ist trotzdem beweglich).
    big = sorted((c for c in clusters if len(c) >= 2), key=len, reverse=True)
    singles = [c[0] for c in clusters if len(c) == 1]
    for i in singles:
        if big:
            dists = [D[i, m].mean() for m in big]
            k = int(np.argmin(dists))
            if dists[k] < attach:
                big[k].append(i)
                continue
        big.append([i])
    letters = "abcdefghijklmnopqrstuvwxyz"
    for n, c in enumerate(big):
        for i in c:
            units[i].cls = letters[n]
    # Elite/Champion: Farbe = naechste Core-Klasse (grob; ihr Sprite unterscheidet sich vom Core)
    cents = [F[c].mean(0) for c in big]
    _classify_cursor_unit(scan, units, big, cents, letters)
    sats = {}
    for n, c in enumerate(big):
        vals = [units[i].sat for i in c if units[i].sat is not None]
        if vals:
            sats[n] = float(np.mean(vals))
    # Farbton-Profile der ganzen Figur je Klasse (nur Klassen mit >= 2 Einheiten)
    hcents = {n: np.mean([units[i].hue for i in c], 0) for n, c in enumerate(big)
              if len(c) >= 2 and all(units[i].hue is not None for i in c)}
    scan.hcents = {letters[n]: hc for n, hc in hcents.items()}
    vcents = {letters[n]: np.mean([units[i].vivid for i in c], 0) for n, c in enumerate(big)
              if len(c) >= 2 and all(units[i].vivid is not None for i in c)}
    for v in scan.cells.values():
        if v.kind == "unit" and v.tier != "core" and not v.cursor and v.feat is not None and cents:
            d = [float(np.abs(cn - v.feat).sum()) for cn in cents]
            k = int(np.argmin(d))
            second = sorted(d)[1] if len(d) > 1 else 9.0
            pick = _hue_pick(v.hue, scan.hcents)
            # Nur eindeutige Treffer: Die Merkmale sehen bei manchen Sprites (Schwertmeister mit
            # dunklem Umhang) eher Sand und Schatten -> lieber "Farbe unbekannt" als falsch.
            if d[k] < 0.35 or (d[k] < 0.7 and second >= 2 * d[k]):
                v.cls = letters[k]
            elif pick:
                # Farbton der ganzen Figur (Ruestung statt Visier) eindeutig naeher an einer Klasse.
                # Als "geschaetzt" markiert -> erscheint im Overlay als "Unsicher".
                v.cls, v.guessed = pick, True
            elif (vpick := _vivid_pick(v.vivid, vcents)) is not None:
                # Kraeftige Farben (Ruestung) eindeutig naeher an einer Klasse, als "geschaetzt".
                v.cls, v.guessed = vpick, True
            elif (spick := _sat_pick(v.sat, sats)) is not None:
                # Ersatz: Saettigung (weiss/grau vs. blau/gold). Nur bei klarem Abstand, als "geschaetzt".
                v.cls, v.guessed = letters[spick], True
            elif vcents and v.vivid is not None and v.vivid.any():
                # Letzte Stufe (Nutzer, 2026-11-24): Eine Armee hat nur 3 Farben -> immer die aehnlichste
                # nehmen statt "unbekannt". Sonst wird der Champion nie aktiviert. Als "geschaetzt".
                v.cls = min(vcents, key=lambda c: float(np.abs(vcents[c] - v.vivid).sum()))
                v.guessed = True


def _classify_cursor_unit(scan: SideScan, units: list, big: list, cents: list, letters: str) -> None:
    """Einheit unter dem Cursor: der Klasse (>= 2 Einheiten) mit dem aehnlichsten Kopf/Helm zuordnen.
    Vorher war sie 'Farbe unbekannt' und passte zu nichts -> je nach Cursor-Position andere
    Vorschlaege (Nutzer, 2026-11-24)."""
    hc = {}
    for n, c in enumerate(big):
        hs = [units[i].hfeat for i in c if units[i].hfeat is not None]
        if len(hs) >= 2:
            hc[n] = np.mean(hs, 0)
    if not hc:
        return
    for v in scan.cells.values():
        if v.kind != "unit" or not v.cursor or v.tier != "core" or v.cls or v.hfeat is None:
            continue
        v.cls = letters[min(hc, key=lambda n: float(np.abs(hc[n] - v.hfeat).sum()))]


def build_side(scan: SideScan, hero: Hero, who: str) -> Side:
    side = Side(hero)
    used: set = set()
    back = 1 if who == "me" else -1  # Modellrichtung, die auf dem Bildschirm "nach unten" zeigt

    def add(p: Piece) -> bool:
        cells = list(p.cells())
        if any(not (0 <= c < COLS and 0 <= r < ROWS) or (c, r) in used for c, r in cells):
            return False
        side.pieces.append(p)
        used.update(cells)
        p.uid = side.next_uid
        side.next_uid += 1
        return True

    # 1) Waende
    for (c, r), v in scan.cells.items():
        if v.kind == "wall":
            ws = side.wall_stats()
            # Gelesene Wand-HP (eigene und gegnerische); ueber dem Grundwert = schon verschmolzen.
            hp = v.tough if v.tough and v.tough <= 20 else ws["wall_base"]  # > 20: verlesen (z. B. 44)
            if who == "me":
                hp = min(hp, ws["wall_max"])  # eigene Werte sind bekannt (Haven 7/14)
            add(Piece("wall", c, r, hp=hp, merged=hp > ws["wall_base"]))
    # 2) Ladende Formationen (Front zuerst): vom Balken bildschirm-aufwaerts, max. 3 Reihen
    #    (Champion 2), bis eine Wand / andere Formation / Einheit kommt.
    for c0, c1, r in sorted(scan.bars, key=lambda b: b[2] * back):
        rows = [r]
        while len(rows) < (2 if c1 > c0 else 3):
            nr = rows[-1] - back
            if not (0 <= nr < ROWS) or (c0, nr) in used or scan.cells[(c0, nr)].kind != "empty":
                break
            rows.append(nr)
        bar = scan.bar_info.get((c0, c1, r))
        tier = "champion" if c1 > c0 else ("elite" if len(rows) == 2 else "core")
        maxp = TYPICAL_MAX[tier]
        power = max(1, round(maxp * (bar.fill if bar else 0.75)))
        ct = bar.ct if bar and bar.ct else 1
        add(Piece("form", c0, min(rows), c1 - c0 + 1, len(rows), unit=tier, color=f"?{c0}{r}",
                  max_power=max(maxp, power), start_power=power, ct=ct, ct_total=ct))
    # 3) Idle Einheiten. Das Herz sitzt in der Bildschirm-oberen linken Zelle des Pieces.
    for (c, r), v in sorted(scan.cells.items(), key=lambda kv: (kv[0][1] * back, kv[0][0])):
        if v.kind != "unit" or (c, r) in used:
            continue
        if v.tier == "core":
            if v.cls:
                add(Piece("unit", c, r, unit="core", color=v.cls))
            elif v.cursor:
                add(Piece("unit", c, r, unit="core", color="~"))  # unter dem Cursor: beweglich, Farbe unbekannt
            else:
                add(Piece("block", c, r, hp=3))
        else:
            w = 2 if v.tier == "champion" else 1
            top = min(r, r + back)
            # Unklare Farbe: trotzdem beweglich (eindeutige Farbe '~..' -> wird nie aktiviert)
            ok = add(Piece("unit", c, top, w, 2, unit=v.tier, color=v.cls or f"~{c}{r}"))
            if not ok:
                add(Piece("block", c, r, 1, 1, hp=v.tough or 6))
    # 4) Luecken mitten in einer Spalte (z. B. Cursor verdeckt ein Icon) als unbekannte Blocker.
    #    Ausnahme: direkt dahinter steht ein 2 breites Piece (Champion). Es haengt an der
    #    volleren Nachbarspalte, die Luecke davor ist echt (und Fluegel ragen oft hinein).
    at = {cell: p for p in side.pieces for cell in p.cells()}
    for c in range(COLS):
        rows = [r for r in range(ROWS) if (c, r) in used]
        for r in range(0, max(rows, default=0)):
            if (c, r) in used:
                continue
            nxt = next((at[(c, q)] for q in range(r + 1, ROWS) if (c, q) in at), None)
            if nxt is not None and nxt.w == 2:
                continue
            add(Piece("block", c, r, hp=3))
    return side


def analyze(frames, me_hero: Hero | None = None, en_hero: Hero | None = None,
            moves: int | None = None, cursor_col: int | None = None, lib=None) -> tuple[State, dict]:
    """frames: ein Bild oder eine Liste kurz hintereinander aufgenommener Bilder.
    lib: optionale AssetLib -> dauerhafte Kennungen, Formationsfarben, neue Beispielbilder."""
    if isinstance(frames, np.ndarray):
        frames = [frames]
    h, w = frames[0].shape[:2]
    geo = Geometry(w, h)
    scans, uid_of = {}, {}
    for who in ("me", "enemy"):
        cc = cursor_col if who == "me" else None
        scans[who] = merge_scans([scan_side(f, geo, who, cc) for f in frames])
        classify(scans[who])
        uid_of[who] = _link_assets(scans[who], lib, frames[0], geo, who) if lib else {}
    me = build_side(scans["me"], me_hero or Hero(name="Ich"), "me")
    en = build_side(scans["enemy"], en_hero or Hero(name="Gegner", faction="necropolis"), "enemy")
    if lib:
        for who, side in (("me", me), ("enemy", en)):
            _color_formations(side, scans[who], lib, uid_of[who])
            _name_units(side, lib, uid_of[who])
    # Elite/Champions, deren Farbe nur geschaetzt ist (Hinweis "Unsicher"): idle und ladend
    guessed = [(c, r) for (c, r), v in scans["me"].cells.items() if v.kind == "unit" and v.guessed]
    _hue_color_forms(me, scans["me"], guessed)
    _hue_color_forms(en, scans["enemy"], [])
    issues = sanitize(me) + sanitize(en)
    state = State(me, en, moves if moves is not None else RULES["moves_per_turn"])
    return state, {"geo": geo, "scans": scans, "issues": issues, "uid_of": uid_of, "guessed": guessed}


def cell_crop(img: np.ndarray, geo: Geometry, who: str, cells) -> np.ndarray:
    boxes = [geo.cell_box(who, c, r) for c, r in cells]
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    return img[int(y0):int(y1), int(x0):int(x1), :3]


def formation_feature(scan: SideScan, p: Piece) -> np.ndarray:
    return np.mean([scan.cells[c].afeat for c in p.cells()], 0)


def _link_assets(scan: SideScan, lib, img, geo, who) -> dict:
    """Ordnet jeder Core-Klasse (a, b, ...) eine dauerhafte Kennung zu und speichert Beispiele."""
    groups: dict[str, list] = {}
    for k, v in sorted(scan.cells.items()):
        if v.kind == "unit" and v.tier == "core" and v.cls and not v.cursor:
            groups.setdefault(v.cls, []).append((k, v))
    uid_of: dict = {}
    taken: set = set()
    # Groesste Gruppen zuerst; jede Kennung hoechstens einmal pro Bild vergeben.
    # Neue Kennungen nur fuer Gruppen mit >= 2 Einheiten (Einzelgaenger sind oft verrauscht).
    for letter, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        feat = np.mean([v.feat for _, v in members], 0)
        uid = lib.match_or_create(feat, members[0][1].tough, exclude=taken, create=len(members) >= 2)
        if uid is None:
            continue
        uid_of[letter] = uid
        taken.add(uid)
        for k, v in members[:2]:  # pro Analyse hoechstens 2 Beispiele je Klasse
            lib.add(uid, "idle", v.feat, cell_crop(img, geo, who, [k]))
    return uid_of


def _hue_pick(h, hcents: dict):
    """Klasse fuer ein Elite/Champion-Farbton-Profil, nur bei eindeutigem Ergebnis (sonst None).
    1) Gesamtabstand klar kleiner. 2) Sonst: Hauptfarbe der Figur (z. B. reines Blau der Ruestung)
    kommt bei einer Klasse deutlich haeufiger vor (Haut/Leder machen den Gesamtvergleich knapp)."""
    if h is None or not h.any() or len(hcents) < 2:
        return None
    hd = sorted((float(np.abs(hc - h).sum()), k) for k, hc in hcents.items())
    if hd[0][0] < 0.45 and hd[1][0] >= 1.5 * hd[0][0]:
        return hd[0][1]
    d = int(np.argmax(h))
    if h[d] < 0.3:
        return None
    share = sorted(((float(hc[d]), k) for k, hc in hcents.items()), reverse=True)
    if share[0][0] >= 0.1 and share[0][0] >= 1.8 * share[1][0]:
        return share[0][1]
    return None


def _hue_color_forms(side: Side, scan: SideScan, guessed: list) -> None:
    """Ladende Elite/Champions ohne Farbe (kein gespeichertes Beispiel): Farbton der ganzen Figur
    mit den Core-Klassen vergleichen, nur eindeutige Treffer (wie bei idle Elites)."""
    if scan.floor is None or len(scan.hcents) < 2:
        return
    for p in side.pieces:
        if p.kind != "form" or p.tier == "core" or not p.color.startswith("?"):
            continue
        cells = [scan.cells[c] for c in p.cells() if c in scan.cells and scan.cells[c].wide is not None]
        if not cells:
            continue
        pick = _hue_pick(_hue_hist(np.concatenate([c.wide.reshape(-1, 3) for c in cells]), scan.floor),
                         scan.hcents)
        if pick:
            p.color = pick
            guessed.append((p.col, p.row))


def _name_units(side: Side, lib, uid_of: dict) -> None:
    """Idle Core-Einheiten bekommen ihren echten Typ, wenn die Klasse in names.json benannt ist.
    Wichtig fuer die Ladezeit: Platzhalter 'core' laedt 2 Runden, Schwert/Speer bei Haven 3 --
    sonst fallen z. B. gebundene Angriffe mit einem Elite (gleiche Restladezeit) nicht auf."""
    from .model import UNITS
    for p in side.pieces:
        if p.kind != "unit" or p.unit != "core" or p.color not in uid_of:
            continue
        name = lib.name(uid_of[p.color])
        if name in UNITS and UNITS[name]["tier"] == "core":
            p.unit = name


def _color_formations(side: Side, scan: SideScan, lib, uid_of: dict) -> None:
    """Ladende Formationen ueber gespeicherte 'geladen'-Beispiele einer Klasse zuordnen.
    Nur sichere Treffer; sonst bleibt die Farbe unbekannt (keine Fusion/Links geplant)."""
    letter_of = {u: l for l, u in uid_of.items()}
    for p in side.pieces:
        if p.kind != "form" or not p.color.startswith("?"):
            continue
        uid, d = lib.match(formation_feature(scan, p), None, "geladen")
        if uid is not None and d < 0.45:
            p.color = letter_of.get(uid, "#" + uid)


def sanitize(side: Side) -> int:
    """Ein erkanntes Brett ist im Spiel immer 'aufgeloest': Es kann keine fertige, aber noch nicht
    gebildete Formation/Wand enthalten. Findet sich doch eine, ist die Erkennung falsch:
    beteiligte Elite/Champions verlieren ihre (geschaetzte) Farbe und werden zu Blockern.
    Rueckgabe: Anzahl verbleibender Widersprueche nur mit Core-Einheiten."""
    from .rules import find_matches
    for _ in range(10):
        matches = find_matches(side)
        bad = [p for m in matches for p in m.pieces if p.kind == "unit" and p.tier != "core"]
        if not bad:
            return len(matches)
        for p in bad:
            p.color = f"~{p.col}{p.row}"  # Farbe war falsch geschaetzt -> unbekannt, aber beweglich
    return 0
