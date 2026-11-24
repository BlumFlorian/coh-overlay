"""Trainings-Auswertung: aktuelle Erkennung gegen gespeicherte Korrekturen (dataset/corrections).

Je Korrektur wird der Screenshot neu erkannt und Feld fuer Feld mit korrigiert.json verglichen.
Farben: Die Erkennung benennt Klassen mit Buchstaben (je Bild beliebig). Fuer den Vergleich wird
jeder Buchstabe der echten Farbe zugeordnet, die in der Korrektur auf seinen Feldern am haeufigsten
steht. So misst die Auswertung, ob die Gruppierung stimmt, unabhaengig von den Buchstaben.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .boardio import CORRECTIONS
from .model import COLS, ROWS, TIER

KOPF_KEYS = ["zuege", "reserve_ich", "reserve_gegner", "hp_ich", "hp_gegner"]


def cell_map(pieces: list[dict]) -> dict:
    """(col, row) -> Kurzbeschreibung des Pieces auf diesem Feld."""
    out = {}
    for p in pieces:
        for c in range(p["col"], p["col"] + p.get("w", 1)):
            for r in range(p["row"], p["row"] + p.get("h", 1)):
                if 0 <= c < COLS and 0 <= r < ROWS:
                    out[(c, r)] = p
    return out


def _tier(p: dict) -> str | None:
    u = p.get("unit")
    return TIER.get(u) if u else None


def describe(p: dict | None) -> str:
    if p is None:
        return "leer"
    kind = p["kind"]
    if kind == "wall":
        return f"Wand {p.get('hp')}"
    if kind == "block":
        return "Hindernis"
    t = _tier(p) or "?"
    base = "Formation " if kind == "form" else ""
    return f"{base}{t} {p.get('unit')} {p.get('color')}"


@dataclass
class Result:
    name: str
    cells: int = 0
    kind_ok: int = 0
    tier_ok: int = 0
    color_ok: int = 0
    color_n: int = 0
    wall_ok: int = 0
    wall_n: int = 0
    kopf_ok: int = 0
    kopf_n: int = 0
    diffs: list = field(default_factory=list)


def compare(recognized: dict, corrected: dict, name: str = "") -> Result:
    """recognized: Analyse-Record (Buchstaben-Farben); corrected: korrigiert.json (echte Farben)."""
    res = Result(name)
    for side in ("ich", "gegner"):
        rc, cc = cell_map(recognized.get(side, [])), cell_map(corrected.get(side, []))
        # Buchstabe -> haeufigste echte Farbe laut Korrektur
        votes = defaultdict(Counter)
        for cell, p in rc.items():
            q = cc.get(cell)
            if q is not None and p.get("color") and q.get("color"):
                votes[p["color"]][q["color"]] += 1
        letter = {k: v.most_common(1)[0][0] for k, v in votes.items()}
        for c in range(COLS):
            for r in range(ROWS):
                p, q = rc.get((c, r)), cc.get((c, r))
                if p is None and q is None:
                    continue
                res.cells += 1
                kind_ok = (p is None) == (q is None) and (p is None or p["kind"] == q["kind"])
                res.kind_ok += kind_ok
                tier_ok = kind_ok and (p is None or _tier(p) == _tier(q))
                res.tier_ok += tier_ok
                ok = tier_ok
                if q is not None and q["kind"] in ("unit", "form") and q.get("color") and not str(q["color"]).startswith("?"):
                    res.color_n += 1
                    col_ok = p is not None and letter.get(p.get("color")) == q["color"]
                    res.color_ok += col_ok
                    ok = ok and col_ok
                if q is not None and q["kind"] == "wall":
                    res.wall_n += 1
                    w_ok = p is not None and p["kind"] == "wall" and p.get("hp") == q.get("hp")
                    res.wall_ok += w_ok
                    ok = ok and w_ok
                if not ok:
                    res.diffs.append((side, c + 1, r + 1, describe(p), describe(q)))
    rk, ck = recognized.get("kopf", {}), corrected.get("kopf", {})
    for k in KOPF_KEYS:
        if ck.get(k) is not None:
            res.kopf_n += 1
            if rk.get(k) == ck.get(k):
                res.kopf_ok += 1
            else:
                res.diffs.append(("kopf", k, "", rk.get(k), ck.get(k)))
    return res


def corrections() -> list[Path]:
    if not CORRECTIONS.exists():
        return []
    return sorted(d for d in CORRECTIONS.iterdir() if (d / "korrigiert.json").exists())


def evaluate_all(recognize, progress=None) -> list[Result]:
    """recognize(png_path) -> Analyse-Record mit der aktuellen Erkennung."""
    out = []
    dirs = corrections()
    for i, d in enumerate(dirs):
        corrected = json.loads((d / "korrigiert.json").read_text(encoding="utf-8"))
        png = d / "screenshot.png"
        if not png.exists():
            continue
        out.append(compare(recognize(png), corrected, d.name))
        if progress:
            progress(i + 1, len(dirs))
    return out


def summary(results: list[Result]) -> dict:
    tot = Result("gesamt")
    for r in results:
        for k in ("cells", "kind_ok", "tier_ok", "color_ok", "color_n", "wall_ok", "wall_n", "kopf_ok", "kopf_n"):
            setattr(tot, k, getattr(tot, k) + getattr(r, k))
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {"Korrekturen": len(results), "Felder": tot.cells, "Art %": pct(tot.kind_ok, tot.cells),
            "Typ %": pct(tot.tier_ok, tot.cells), "Farbe %": pct(tot.color_ok, tot.color_n),
            "Wand-HP %": pct(tot.wall_ok, tot.wall_n), "Kopfwerte %": pct(tot.kopf_ok, tot.kopf_n)}


def recognize_png(png: Path) -> dict:
    """Aktuelle Erkennung eines Screenshots als Analyse-Record (ohne Zugsuche)."""
    import numpy as np
    from PIL import Image

    from .boardio import analysis_record
    from .stock import StockTracker, read_stock
    from .ui import read_ui
    from .vision import analyze

    img = np.asarray(Image.open(png).convert("RGB"))
    ui = read_ui(img)
    state, meta = analyze(img, moves=ui.moves or 3, cursor_col=ui.cursor_col)
    if ui.my_reserve is not None:
        state.me.reserve = ui.my_reserve
    if ui.enemy_reserve is not None:
        state.enemy.reserve = ui.enemy_reserve
    if ui.my_hp is not None:
        state.me.hero.hp = ui.my_hp
    if ui.enemy_hp is not None:
        state.enemy.hero.hp = ui.enemy_hp
    if ui.my_mp is not None:
        state.me.hero.mp = round(ui.my_mp * state.me.hero.max_mp)
    if ui.enemy_mp is not None:
        state.enemy.hero.mp = round(ui.enemy_mp * state.enemy.hero.max_mp)
    tr = StockTracker(confirm=1)
    tr.update(read_stock(img))
    rec = analysis_record(png.stem, state, ui, meta, stock_text=(tr.describe("me"), tr.describe("enemy")))
    rec["nachtraeglich_erkannt"] = True
    return rec
