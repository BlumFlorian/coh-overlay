"""Was das Tool bei einer Analyse nicht sicher weiss -- als kurze Hinweise fuer Overlay und Replay.

Die Hinweise erscheinen im Overlay als "Unsicher: ..." und landen in der Analyse-Datei. So kann
der Spieler im Zweifel selbst entscheiden, und die Replay-Auswertung sammelt sie als offene Fragen.
"""
from __future__ import annotations

from .model import State

KNAPP = 3.0  # Punkte: darunter gelten die beiden besten Plaene als gleichwertig


def uncertainties(state: State, ui=None, stock=None) -> list[str]:
    out = []
    me = state.me
    blocks = sorted({p.col + 1 for p in me.pieces if p.kind == "block"})
    if blocks:
        out.append(f"Felder in Spalte {', '.join(map(str, blocks))} nicht erkannt (als Hindernis gerechnet)")
    for p in me.pieces:
        if p.kind == "unit" and p.tier != "core" and p.color.startswith("~"):
            name = "Champion" if p.tier == "champion" else "Elite"
            out.append(f"Farbe {name} Spalte {p.col + 1} unbekannt (Cursor drauf oder nicht eindeutig) - Aktivierung nicht geplant")
        elif p.kind == "unit" and p.tier == "core" and p.color.startswith("~"):
            out.append(f"Einheit unter dem Cursor (Spalte {p.col + 1}) unbekannt")
    # Eine Armee hat hoechstens 3 Kernfarben. Eine vierte Klasse mit nur einer Einheit ist fast
    # immer eine Fehlerkennung (z. B. Bogenschuetze in anderer Animationsphase) -> nie verbunden.
    core = [p for p in me.pieces if p.kind == "unit" and p.tier == "core" and not p.color.startswith("~")]
    counts: dict[str, int] = {}
    for p in core:
        counts[p.color] = counts.get(p.color, 0) + 1
    if len(counts) > 3:
        for p in core:
            if counts[p.color] == 1:
                out.append(f"Einheit Spalte {p.col + 1}, Reihe {p.row + 1} keiner Farbe zugeordnet "
                           f"(eigene Klasse {p.color.upper()}) - wird nie verbunden")
    # Gegner: gleich lang ladende Formationen koennten gelinkt sein (Farben meist unbekannt)
    by_ct: dict[int, list[int]] = {}
    for p in state.enemy.pieces:
        if p.kind == "form":
            by_ct.setdefault(p.ct, []).append(p.col + 1)
    for ct, cols in sorted(by_ct.items()):
        if len(cols) >= 2:
            out.append(f"Gegner Spalte {', '.join(map(str, sorted(cols)))} greifen zusammen an (in {ct}): "
                       "bei gleicher Farbe Link, staerker als berechnet")
    if ui is not None:
        if ui.moves is None:
            out.append("Zuganzeige nicht gelesen")
        if ui.my_reserve is None:
            out.append("Eigene Reserve nicht gelesen")
    if stock is not None and stock.tiers("me") is None:
        out.append("Eigenes Kontingent nicht gelesen")
    return out


def close_call(plans) -> float | None:
    """Abstand der beiden besten Plaene, wenn er unter KNAPP liegt (sonst None)."""
    if len(plans) < 2:
        return None
    gap = plans[0].score - plans[1].score
    return gap if gap < KNAPP else None
