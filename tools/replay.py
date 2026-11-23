"""Replay-Auswertung: gespeicherte L1-Analysen eines oder mehrerer Kaempfe nachrechnen und
Vorhersage gegen Wirklichkeit abgleichen.

  .venv\\Scripts\\python tools\\replay.py                 # alle Aufnahmen in dataset\\analysis
  .venv\\Scripts\\python tools\\replay.py --day 20261113  # nur ein Tag

Vorgehen
- Jede Aufnahme wird neu erkannt (Brett, UI, Kontingent). Die Asset-Bibliothek wird nur gelesen.
- Aufnahmen werden zu Kaempfen und Zuegen gruppiert. Mehrere L1 im selben Zug zaehlen einmal (die erste).
- Fuer zwei aufeinanderfolgende eigene Zuege A -> B wird A ohne eigene Zuege eine Runde weiter-
  simuliert (Gegner-Start, eigener Start) und mit B verglichen: Heldenschaden, Formationen
  (abgefeuert / weiter am Laden / vernichtet) und Kontingent.

Abweichungen sind Hinweise, keine Beweise: Dazwischen lagen deine und die gegnerischen Zuege.
Was sich wiederholt, zeigt eine falsche Regel oder einen Erkennungsfehler.
Ergebnis: dataset\\replay\\bericht_<Zeit>.md
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from coh.assets import AssetLib  # noqa: E402
from coh.rules import start_turn  # noqa: E402
from coh.solver import _ht_count  # noqa: E402
from coh.stock import StockTracker, read_stock  # noqa: E402
from coh.ui import read_ui  # noqa: E402
from coh.uncertain import uncertainties  # noqa: E402
from coh.vision import analyze  # noqa: E402

ANALYSIS = ROOT / "dataset" / "analysis"
OUT = ROOT / "dataset" / "replay"
NEW_BATTLE_GAP = 45 * 60  # Sekunden ohne Aufnahme -> neuer Kampf (Hauptmerkmal: HP steigen wieder)


class ReadOnlyLib(AssetLib):
    """Erkennt wie im Overlay, schreibt aber keine Beispielbilder und speichert nichts."""

    def add(self, uid, state, feat, crop=None):
        super().add(uid, state, feat, None)

    def save(self):
        pass


@dataclass
class Snap:
    stem: str
    time: datetime
    state: object
    ui: object
    stock: dict
    suggestion: list[str] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)

    @property
    def my_forms(self):
        return [p for p in self.state.me.pieces if p.kind == "form"]

    def turn_key(self):
        """Gleicher Schluessel = vermutlich derselbe Zug (mehrfach L1 gehalten). Nur stabile
        UI-Anzeigen: Brett-Details (Cursor-Vorschau, gelesene Ladezeiten) schwanken zu sehr."""
        u = self.ui
        mp = lambda v: None if v is None else round(v, 1)  # noqa: E731
        # (Pausen sind kein Signal: oft wird im selben Zug mehrfach analysiert. Im normalen Spiel
        # aendert sich jede Runde etwas an HP, Reserve oder Zauberleisten.)
        return (u.my_hp, u.enemy_hp, u.my_reserve, u.enemy_reserve, mp(u.my_mp), mp(u.enemy_mp))


def load(day: str | None) -> list[Snap]:
    lib, tracker, snaps = ReadOnlyLib(), StockTracker(), []
    files = sorted(f for f in ANALYSIS.glob("*.png") if not f.stem.endswith("_debug"))
    if day:
        files = [f for f in files if f.stem.startswith(day)]
    for i, f in enumerate(files, 1):
        if i % 20 == 0 or i == len(files):
            print(f"{i}/{len(files)} Aufnahmen erkannt", flush=True)
        img = np.asarray(Image.open(f).convert("RGB"))
        ui = read_ui(img)
        if not ui.my_turn:
            continue
        try:
            state, _ = analyze(img, moves=ui.moves or 3, cursor_col=ui.cursor_col, lib=lib)
        except Exception as e:  # einzelne kaputte Aufnahme ueberspringen
            print(f"  {f.name}: Erkennung fehlgeschlagen ({e})")
            continue
        tracker.update(read_stock(img))
        state.me.stock, state.enemy.stock = tracker.tiers("me"), tracker.tiers("enemy")
        for side, hp in ((state.me, ui.my_hp), (state.enemy, ui.enemy_hp)):
            if hp is not None:
                side.hero.hp = hp
        if ui.my_reserve is not None:
            state.me.reserve = ui.my_reserve
        txt = f.with_suffix(".txt")
        lines = txt.read_text(encoding="utf-8").splitlines() if txt.exists() else []
        snaps.append(Snap(f.stem, datetime.strptime(f.stem, "%Y%m%d_%H%M%S"), state, ui,
                          dict(state.me.stock or {}),
                          [ln for ln in lines if ln[:1].isdigit() or ln.startswith("Verst")],
                          uncertainties(state, ui, tracker)))
    return snaps


def battles(snaps: list[Snap]) -> list[list[Snap]]:
    """Kaempfe (Luecke oder HP steigen wieder) und darin Zuege (erste Aufnahme je Zug)."""
    out: list[list[Snap]] = []
    last = None
    for s in snaps:
        gap = (s.time - last.time).total_seconds() if last else None
        new = (last is None or gap > NEW_BATTLE_GAP
               or (s.ui.enemy_hp or 0) > (last.ui.enemy_hp or 0) + 5  # Gegner geheilt? meist neuer Kampf
               or (s.ui.my_hp or 0) > (last.ui.my_hp or 0) + 15)
        if new:
            out.append([s])
        elif s.turn_key() != last.turn_key():
            out[-1].append(s)
        last = s
    return out


def _match(a, forms_b):
    """Gleiche Formation in B: gleiche Spalte und Breite."""
    for q in forms_b:
        if q.col == a.col and q.w == a.w:
            return q
    return None


def compare(a: Snap, b: Snap) -> tuple[list[str], dict]:
    """A eine Runde weiter simulieren (ohne eigene Zuege) und mit B vergleichen."""
    notes, stats = [], Counter()
    # Zwei Zuege uebersprungen? Ladezeiten der gemeinsamen Formationen zeigen den Abstand.
    gaps = [p.ct - q.ct for p in a.my_forms if (q := _match(p, b.my_forms)) and q.ct <= p.ct]
    step = Counter(gaps).most_common(1)[0][0] if gaps else 1
    if step >= 2:
        notes.append(f"vermutlich {step} Runden dazwischen (L1 nicht in jedem Zug) - nur grob vergleichbar")
        stats["uebersprungen"] += 1
    s = a.state.copy()
    for _ in range(max(1, step)):
        start_turn(s, "enemy")
        start_turn(s, "me")
    pe, po = s.enemy.hero.hp, b.ui.enemy_hp
    if po is not None and abs(pe - po) >= 3:
        notes.append(f"Gegner-HP: erwartet {pe}, gesehen {po} ({po - pe:+d})")
        stats["gegner_hp"] += 1
    me_pred, me_obs = s.me.hero.hp, b.ui.my_hp
    if me_obs is not None and abs(me_pred - me_obs) >= 3:
        notes.append(f"Eigene HP: erwartet {me_pred}, gesehen {me_obs} ({me_obs - me_pred:+d})")
        stats["eigene_hp"] += 1
    for p in a.my_forms:
        q = _match(p, b.my_forms)
        what = f"Formation Spalte {p.col + 1} ({'Champion' if p.w == 2 else p.unit}, CT {p.ct})"
        if p.ct <= step:
            if q is not None and q.ct >= p.ct:
                notes.append(f"{what}: sollte angegriffen haben, steht noch da (CT {q.ct})")
                stats["nicht_abgefeuert"] += 1
        elif q is None:
            notes.append(f"{what}: sollte noch laden, ist weg (vom Gegner vernichtet = Angriff staerker "
                         "als berechnet, oder Runden ohne L1 dazwischen)")
            stats["vernichtet"] += 1
        elif q.ct != p.ct - step:
            notes.append(f"{what}: erwartet CT {p.ct - step}, gesehen CT {q.ct} (Ladezeit-Lesefehler oder Druid)")
            stats["ct"] += 1
    for t in ("elite", "champion"):
        if a.stock.get(t) is not None and b.stock.get(t) is not None:
            lost_obs = a.stock[t] - b.stock[t]
            lost_pred = max(0, _ht_count(a.state.me)[t] - _ht_count(s.me)[t]
                            - sum(1 for p in a.my_forms if p.tier == t and p.ct <= step))
            if lost_obs != lost_pred:
                notes.append(f"Kontingent {t}: erwartet -{lost_pred}, gesehen -{lost_obs}")
                stats["kontingent"] += 1
    return notes, stats


def report(groups: list[list[Snap]]) -> str:
    total, lines, questions = Counter(), [], Counter()
    for bi, g in enumerate(groups, 1):
        lines.append(f"\n## Kampf {bi}: {g[0].time:%d.%m. %H:%M} - {g[-1].time:%H:%M}, {len(g)} Zuege mit L1\n")
        for s in g:
            questions.update(s.unsure)
        for a, b in zip(g, g[1:]):
            notes, stats = compare(a, b)
            total.update(stats)
            head = f"- **{a.time:%H:%M:%S} -> {b.time:%H:%M:%S}**"
            if a.suggestion:
                head += f"  (Vorschlag war: {' / '.join(a.suggestion[:3])})"
            lines.append(head + ("" if notes else ": passt"))
            lines.extend(f"  - {n}" for n in notes)
    summary = ["# Replay-Bericht", "", f"Erstellt {datetime.now():%d.%m.%Y %H:%M}. "
               "Abweichungen sind Hinweise (dazwischen lagen eigene und gegnerische Zuege).", "",
               "## Zusammenfassung", ""]
    names = {"gegner_hp": "Gegner-HP weicht ab", "eigene_hp": "Eigene HP weicht ab",
             "nicht_abgefeuert": "Formation hat nicht wie erwartet angegriffen",
             "vernichtet": "eigene Formation unerwartet weg", "ct": "Ladezeit passt nicht",
             "kontingent": "Kontingent passt nicht", "uebersprungen": "Zuege ohne L1 dazwischen"}
    summary += [f"- {names.get(k, k)}: {n}" for k, n in total.most_common()] or ["- keine Abweichungen"]
    summary += ["", "## Offene Fragen (Unsicherheiten der Erkennung, nach Haeufigkeit)", ""]
    summary += [f"- {q} ({n}x)" for q, n in questions.most_common(15)] or ["- keine"]
    return "\n".join(summary + lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", help="nur Aufnahmen dieses Tages, z. B. 20261113")
    args = ap.parse_args()
    groups = battles(load(args.day))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"bericht_{datetime.now():%Y%m%d_%H%M%S}.md"
    path.write_text(report(groups), encoding="utf-8")
    print(f"{sum(len(g) for g in groups)} Zuege in {len(groups)} Kaempfen -> {path}")


if __name__ == "__main__":
    main()
