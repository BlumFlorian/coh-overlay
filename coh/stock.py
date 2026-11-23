"""Kontingent der Elite- und Champion-Einheiten beider Spieler (Kaesten neben dem Spielfeld).

Layout bei 1920x1080 (aus den L1-Aufnahmen):
- Mein Kasten oben links, der des Gegners unten rechts (halb durchsichtig, solange ich am Zug bin).
- Je Kasten zwei feste Plaetze untereinander: Icon, darunter "aktuell/max".
  Ein freier Platz bleibt leer (nur eine High-Tier-Einheit gewaehlt).
- Die Zahl sinkt nur, wenn eine Einheit stirbt (idle getroffen oder beim Laden vernichtet),
  nicht beim Angreifen.

Elite oder Champion wird an der Icon-Flaeche erkannt (Elites ~2.000-4.100 px, Champions
~6.000-7.300 px bei 1080p). Das Maximum taugt dafuer nicht: Einhorn (Elite) und Engel haben beide 5.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from . import digits as D

# Mittelpunkt der Zahl "aktuell/max" je Platz (Referenz 1920x1080)
SLOTS = {"me": [(420, 315), (420, 462)], "enemy": [(1500, 707), (1500, 855)]}
CHAMPION_ICON_AREA = 5000  # Pixel bei 1080p
EMPTY_ICON_AREA = 1200  # darunter ist kein Icon da -> Platz leer
THRESHOLDS = (0.8, 0.7, 0.6, 0.5)
EMPTY = "leer"


@dataclass(frozen=True)
class Slot:
    cur: int
    max: int
    tier: str  # "elite" | "champion"


def _box(c):
    return c[:, 0].min(), c[:, 0].max(), c[:, 1].min(), c[:, 1].max()


def _is_slash(c) -> bool:
    y0, y1, x0, x1 = _box(c)
    h = y1 - y0 + 1
    top = c[c[:, 0] < y0 + h / 3]
    bot = c[c[:, 0] > y1 - h / 3]
    return (h >= 12 and len(top) > 0 and len(bot) > 0
            and top[:, 1].mean() - bot[:, 1].mean() > 0.3 * (x1 - x0 + 1) and (x1 - x0 + 1) < 0.9 * h)


def _number(cs) -> int | None:
    cs = sorted(cs, key=lambda c: c[:, 1].min())
    merged = []
    for c in cs:  # eine duenn gezeichnete Null zerfaellt manchmal in zwei Teile
        if merged:
            _, _, px0, px1 = _box(merged[-1])
            _, _, x0, x1 = _box(c)
            if min(px1, x1) - max(px0, x0) >= 0.5 * min(px1 - px0 + 1, x1 - x0 + 1):
                merged[-1] = np.vstack([merged[-1], c])
                continue
        merged.append(c)
    s = ""
    for c in merged:
        y0, y1, x0, x1 = _box(c)
        g = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
        g[c[:, 0] - y0, c[:, 1] - x0] = True
        d, score = D.classify_glyph(g)
        if d is None or score < 0.3:
            return None
        s += str(d)
    return int(s) if s else None


def _read_count(band: np.ndarray, t: float) -> tuple[int, int] | None:
    """band: RGB-Ausschnitt nur der Textzeile. Am Schraegstrich verankert, Ziffern links/rechts davon."""
    a = band.astype(int)
    lum = a.min(-1)
    peak = np.percentile(lum, 99.7)
    if peak < 120:
        return None
    mask = (lum > t * peak) & (a.max(-1) - a.min(-1) < 60)  # weiss/grau, nicht bunt
    cs = D.components(mask, min_pixels=8)
    slashes = [c for c in cs if _is_slash(c)]
    if not slashes:
        return None
    s = max(slashes, key=len)
    sy0, sy1, sx0, sx1 = _box(s)
    H = sy1 - sy0 + 1
    left, right = [], []
    for c in cs:
        if c is s:
            continue
        y0, y1, x0, x1 = _box(c)
        if not (y0 >= sy0 - 0.25 * H and y1 <= sy1 + 0.25 * H and y1 - y0 + 1 >= 0.3 * H):
            continue  # nicht in der Textzeile (Icon-Reste)
        if x1 < sx0 + 2:
            left.append(c)
        elif x0 > sx1 - 2:
            right.append(c)

    def chain(cl, leftwards):
        cl = sorted(cl, key=lambda c: c[:, 1].min(), reverse=leftwards)
        out, edge = [], (sx0 if leftwards else sx1)
        for c in cl:
            _, _, x0, x1 = _box(c)
            if ((edge - x1) if leftwards else (x0 - edge)) > 0.7 * H:
                break
            out.append(c)
            edge = min(edge, x0) if leftwards else max(edge, x1)
        return out

    cur, mx = _number(chain(left, True)), _number(chain(right, False))
    if cur is None or mx is None or not (1 <= mx <= 12 and 0 <= cur <= mx):
        return None
    return cur, mx


def _icon_area(img, cx, cy, sx, sy) -> float:
    """Icon-Flaeche ueber der Zahl, auf 1080p normiert."""
    a = img[int((cy - 115) * sy):int((cy - 14) * sy), int((cx - 78) * sx):int((cx + 78) * sx)].astype(int)
    bg = np.median(a[:, :max(2, int(6 * sx))].reshape(-1, 3), 0)  # Kasten-Hintergrund am Rand
    return float((np.abs(a - bg).sum(-1) > 45).sum()) / (sx * sy)


def read_stock(img: np.ndarray) -> dict[str, list]:
    """Pro Seite zwei Plaetze: Slot, EMPTY (Platz sichtbar leer) oder None (nicht lesbar)."""
    h, w = img.shape[:2]
    sx, sy = w / 1920, h / 1080
    out = {}
    for side, slots in SLOTS.items():
        res = []
        for cx, cy in slots:
            band = img[int((cy - 14) * sy):int((cy + 15) * sy), int((cx - 80) * sx):int((cx + 80) * sx)]
            if sx != 1 or sy != 1:  # Ziffernleser ist auf 1080p abgestimmt
                from PIL import Image
                band = np.asarray(Image.fromarray(band).resize((160, 29), Image.BILINEAR))
            area = _icon_area(img, cx, cy, sx, sy)
            reads = [r for t in THRESHOLDS if (r := _read_count(band, t))]
            if not reads:
                res.append(EMPTY if area < EMPTY_ICON_AREA else None)
                continue
            (cur, mx), _ = Counter(reads).most_common(1)[0]
            # Alle 10er-Kontingente sind Elites; darunter (Einhorn 5 vs. Engel 5) entscheidet das Icon.
            tier = "elite" if mx >= 8 else ("champion" if area > CHAMPION_ICON_AREA else "elite")
            res.append(Slot(cur, mx, tier))
        out[side] = res
    return out


class StockTracker:
    """Merkt sich das Kontingent ueber mehrere Analysen.

    - Ein unlesbarer Platz behaelt den letzten bekannten Wert.
    - Gleiches Maximum: Die Zahl darf nur sinken (Steigen = Lesefehler, ausser es bestaetigt sich).
    - Anderes Maximum oder anderer Tier: neuer Kampf oder Lesefehler. Uebernommen erst,
      wenn derselbe Wert zweimal hintereinander gelesen wird. Ebenso jede gelesene 0.
    - Ein sichtbar leerer Platz loescht den Eintrag (neuer Kampf mit nur einer High-Tier-Einheit).
    """

    def __init__(self, confirm: int = 2):
        self.confirm = confirm
        self.slots: dict[str, list[Slot | None]] = {"me": [None, None], "enemy": [None, None]}
        self._pending: dict[tuple[str, int], tuple[Slot, int]] = {}

    def update(self, reads: dict[str, list[Slot | None]]) -> None:
        for side, rs in reads.items():
            for i, r in enumerate(rs):
                if r is None:
                    continue
                if r == EMPTY:
                    self.slots[side][i] = None
                    self._pending.pop((side, i), None)
                    continue
                known = self.slots[side][i]
                # "0/x" ist der typische Lesefehler bei abgedunkelter Schrift -> immer bestaetigen lassen
                plausible = r.cur > 0 and (known is None or (r.max == known.max and r.tier == known.tier
                                                             and r.cur <= known.cur))
                if plausible:
                    self.slots[side][i] = r
                    self._pending.pop((side, i), None)
                    continue
                prev, n = self._pending.get((side, i), (None, 0))
                n = n + 1 if prev == r else 1
                if n >= self.confirm:
                    self.slots[side][i] = r
                    self._pending.pop((side, i), None)
                else:
                    self._pending[(side, i)] = (r, n)

    def tiers(self, side: str) -> dict[str, int] | None:
        """Verbleibende Einheiten je Tier (beide Plaetze addiert); None, wenn nichts bekannt ist."""
        known = [s for s in self.slots[side] if s]
        if not known:
            return None
        out = {"elite": 0, "champion": 0}
        for s in known:
            out[s.tier] += s.cur
        return out

    def describe(self, side: str) -> str:
        parts = [f"{'C' if s.tier == 'champion' else 'E'} {s.cur}/{s.max}" for s in self.slots[side] if s]
        return ", ".join(parts) if parts else "?"

    def warnings(self) -> list[str]:
        out = []
        for side, who in (("me", "Eigene"), ("enemy", "Gegnerische")):
            for s in self.slots[side]:
                if s and s.cur <= 1:
                    name = "Champions" if s.tier == "champion" else "Elites"
                    out.append(f"{who} {name}: nur noch {s.cur} uebrig!" if s.cur else f"{who} {name}: Kontingent leer")
        return out
