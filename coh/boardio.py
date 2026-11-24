"""Austauschformat zwischen Overlay und Client: erkanntes Brett, Kopfwerte, Plan, Korrekturen.

Das Overlay schreibt je Analyse `dataset/analysis/<Zeit>.json` (siehe analysis_record). Der Client
zeigt es an und speichert Meldungen unter `dataset/corrections/<Zeit>/` (siehe save_correction).
Format versioniert ("format": 1), siehe docs/CLIENT.md.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from .model import Hero, Piece, Side, State

FORMAT = 1
ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "dataset" / "analysis"
CORRECTIONS = ROOT / "dataset" / "corrections"

PIECE_FIELDS = [f.name for f in fields(Piece)]
# Echte Farben je Fraktion (Auswahl im Client); "?" = unbekannt
COLOR_NAMES = ["Gold", "Blau", "Weiss", "Rot", "Gruen", "Lila", "Schwarz", "Grau", "?"]


def piece_to_dict(p: Piece) -> dict:
    return {k: getattr(p, k) for k in PIECE_FIELDS}


def piece_from_dict(d: dict) -> Piece:
    return Piece(**{k: d[k] for k in PIECE_FIELDS if k in d})


def side_from_dicts(pieces: list[dict], hero: Hero | None = None) -> Side:
    s = Side(hero or Hero())
    s.pieces = [piece_from_dict(d) for d in pieces]
    s.next_uid = max((p.uid for p in s.pieces), default=0) + 1
    return s


def analysis_record(stem: str, state: State, ui=None, meta: dict | None = None, lines: list[str] | None = None,
                    plan=None, stock_text: tuple[str, str] | None = None) -> dict:
    """Alles, worauf ein Vorschlag beruht, als JSON-faehiges dict."""
    meta = meta or {}
    kopf = {
        "zuege": state.moves_left,
        "reserve_ich": state.me.reserve, "reserve_gegner": state.enemy.reserve,
        "hp_ich": state.me.hero.hp, "hp_gegner": state.enemy.hero.hp,
        "mp_ich": state.me.hero.mp, "mp_gegner": state.enemy.hero.mp,
        "kontingent_ich": stock_text[0] if stock_text else None,
        "kontingent_gegner": stock_text[1] if stock_text else None,
    }
    if ui is not None:
        kopf["cursor_spalte"] = ui.cursor_col
        kopf["gelesen"] = {"zuege": ui.moves, "reserve_ich": ui.my_reserve, "reserve_gegner": ui.enemy_reserve,
                           "hp_ich": ui.my_hp, "hp_gegner": ui.enemy_hp, "mp_ich": ui.my_mp, "mp_gegner": ui.enemy_mp}
    # Je Klasse eine Beispielzelle (fuer die Farb-Legende im Client)
    klassen = {}
    for who, side in (("ich", state.me), ("gegner", state.enemy)):
        k = {}
        for p in side.pieces:
            if p.kind == "unit" and p.color and p.color[0].isalpha() and p.color not in k:
                k[p.color] = [p.col, p.row]
        klassen[who] = k
    return {
        "format": FORMAT,
        "stem": stem,
        "bild": f"{stem}.png",
        "kopf": kopf,
        "ich": [piece_to_dict(p) for p in state.me.pieces],
        "gegner": [piece_to_dict(p) for p in state.enemy.pieces],
        "klassen": klassen,
        "geschaetzt": [list(x) for x in meta.get("guessed", [])],
        "plan": {
            "zeilen": list(lines or []),
            "aktionen": [list(a) for a in plan.actions] if plan is not None else [],
            "score": plan.score if plan is not None else None,
        },
    }


def write_analysis(stem: str, record: dict) -> Path:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    path = ANALYSIS / f"{stem}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # atomar: der Client liest nie eine halbe Datei
    return path


def load_analysis(stem: str) -> dict | None:
    path = ANALYSIS / f"{stem}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def record_to_state(rec: dict) -> State:
    k = rec["kopf"]
    me = side_from_dicts(rec["ich"], Hero(name="Ich", hp=k.get("hp_ich") or 100, mp=k.get("mp_ich") or 0))
    en = side_from_dicts(rec["gegner"], Hero(name="Gegner", hp=k.get("hp_gegner") or 100, mp=k.get("mp_gegner") or 0))
    me.reserve, en.reserve = k.get("reserve_ich") or 0, k.get("reserve_gegner") or 0
    return State(me, en, k.get("zuege") or 3)


def save_correction(stem: str, erkannt: dict, korrigiert: dict | None = None, zug: dict | None = None,
                    notiz: str = "") -> Path:
    """Meldung als eigener Ordner: Screenshot(s), erkannt.json, korrigiert.json / zug.json, notiz.txt."""
    when = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = CORRECTIONS / f"{when}_{stem}"
    n = 1
    while out.exists():
        n += 1
        out = CORRECTIONS / f"{when}_{stem}_{n}"
    out.mkdir(parents=True)
    for suffix in (".png", "_debug.png"):
        src = ANALYSIS / f"{stem}{suffix}"
        if src.exists():
            shutil.copy2(src, out / f"screenshot{suffix}")
    (out / "erkannt.json").write_text(json.dumps(erkannt, ensure_ascii=False, indent=1), encoding="utf-8")
    if korrigiert is not None:
        korrigiert = dict(korrigiert, format=FORMAT, stem=stem)
        (out / "korrigiert.json").write_text(json.dumps(korrigiert, ensure_ascii=False, indent=1), encoding="utf-8")
    if zug is not None:
        zug = dict(zug, format=FORMAT, stem=stem)
        (out / "zug.json").write_text(json.dumps(zug, ensure_ascii=False, indent=1), encoding="utf-8")
    if notiz.strip():
        (out / "notiz.txt").write_text(notiz.strip() + "\n", encoding="utf-8")
    return out


def corrected_stems() -> set[str]:
    """Analysen, zu denen es schon eine Meldung gibt."""
    out = set()
    if CORRECTIONS.exists():
        for d in CORRECTIONS.iterdir():
            f = d / "erkannt.json"
            if f.exists():
                try:
                    out.add(json.loads(f.read_text(encoding="utf-8")).get("stem"))
                except (OSError, ValueError):
                    pass
    return out
