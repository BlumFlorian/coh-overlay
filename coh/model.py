"""Spielfeld-Modell: Einheiten-Datenbank, Pieces, Seiten, Zustand und Text-Format.

Koordinaten pro Seite: col 0..7 (links -> rechts, wie auf dem Bildschirm),
row 0 = Frontreihe (zur Mittellinie), row 5 = hinterste Reihe (vor dem eigenen Helden).
Meine Spalte c steht der gegnerischen Spalte c direkt gegenueber.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data" / "units.json").read_text(encoding="utf-8"))
UNITS: dict = DATA["units"]
FACTIONS: dict = {k: v for k, v in DATA["factions"].items() if not k.startswith("_")}
RULES: dict = DATA["rules"]
MAX_LEVEL: int = DATA["max_level"]
CODE_TO_UNIT = {u["code"]: name for name, u in UNITS.items()}
COLS: int = RULES["cols"]
ROWS: int = RULES["rows"]

# Footprint (Breite, Hoehe) idle bzw. als Formation (inkl. der Core-Einheiten dahinter).
IDLE_FOOT = {"core": (1, 1), "elite": (1, 2), "champion": (2, 2)}
FORM_FOOT = {"core": (1, 3), "elite": (1, 2), "champion": (2, 2)}  # DE: Core hinter Elite/Champion verschwinden
# Wie viele Einheiten eine Formation verbraucht (fuer den Reserve-Zaehler beim Aufloesen).
FORM_UNITS = {"core": 3, "elite": 3, "champion": 5}


TIER: dict[str, str] = {name: u["tier"] for name, u in UNITS.items()}  # schneller als UNITS[...]["tier"]


def tier(unit: str) -> str:
    return TIER[unit]


def stat(unit: str, key: str, level: int) -> int:
    lo, hi = UNITS[unit][key]
    level = max(1, min(MAX_LEVEL, level))
    return round(lo + (hi - lo) * (level - 1) / (MAX_LEVEL - 1))


@dataclass
class Piece:
    kind: str  # "unit" | "wall" | "form" | "block" (erkannt, aber unbekannt; merged=True -> steht vorn)
    col: int
    row: int
    w: int = 1
    h: int = 1
    unit: str | None = None
    color: str | None = None
    hp: int = 0  # Wand-HP
    max_power: int = 0
    start_power: int = 0
    deficit: int = 0  # erlittener Schaden / Plague, wird von der Lade-Kurve abgezogen
    ct: int = 0
    ct_total: int = 0
    fused: int = 1
    plague: int = 0
    merged: bool = False  # Wand bereits fusioniert
    uid: int = 0

    @property
    def tier(self) -> str:
        return TIER[self.unit] if self.unit else "wall"

    def copy(self) -> "Piece":
        """Flache Kopie (alle Felder sind unveraenderliche Werte); deutlich schneller als copy.copy."""
        q = object.__new__(Piece)
        q.__dict__ = self.__dict__.copy()
        return q

    @property
    def power(self) -> int:
        """Aktuelle PWR einer ladenden Formation: lineare Kurve Start -> Max minus Schaden."""
        if self.kind != "form":
            return 0
        done = self.ct_total - self.ct
        sched = self.start_power + (self.max_power - self.start_power) * done / max(1, self.ct_total)
        return math.ceil(min(sched, self.max_power) - 1e-9) - self.deficit  # aufrunden: passt zu Screenshots

    def cols(self) -> range:
        return range(self.col, self.col + self.w)

    def cells(self):
        for c in range(self.col, self.col + self.w):
            for r in range(self.row, self.row + self.h):
                yield c, r

    def sig(self) -> tuple:
        return (self.kind, self.col, self.row, self.unit, self.color, self.hp,
                self.max_power, self.deficit, self.ct, self.fused, self.plague, self.merged)


@dataclass
class Hero:
    name: str = "?"
    faction: str = "haven"
    hp: int = 100
    max_hp: int = 100
    mp: int = 0
    max_mp: int = 100
    level: int = 10  # Heldenlevel (1-10) fuer die Werte-Interpolation
    artifacts: frozenset = frozenset()
    spell: str | None = None  # simulierter Heldenzauber, z. B. "holy_shield" (Godric)
    shield: int = -1  # Holy Shield: verbleibende Schild-HP; -1 = kein Schild aktiv

    def spell_ready(self) -> bool:
        return self.spell is not None and self.shield < 0 and self.mp >= 0.97 * self.max_mp


@dataclass
class Side:
    hero: Hero
    pieces: list[Piece] = field(default_factory=list)
    reserve: int = 0
    bonus_moves: int = 0
    next_uid: int = 1
    # Verbleibendes Kontingent je Tier {"elite": n, "champion": m} aus dem Kasten neben dem Feld;
    # None = unbekannt. Sinkt nur, wenn eine Einheit stirbt (nicht beim Angriff).
    stock: dict | None = None

    def grid(self) -> dict[tuple[int, int], Piece]:
        g = {}
        for p in self.pieces:
            for c in range(p.col, p.col + p.w):
                for r in range(p.row, p.row + p.h):
                    g[(c, r)] = p
        return g

    def fill(self, exclude: Piece | None = None) -> list[int]:
        """Pro Spalte: erste freie Reihe hinter dem hintersten belegten Feld."""
        f = [0] * COLS
        for p in self.pieces:
            if p is exclude:
                continue
            for c in p.cols():
                f[c] = max(f[c], p.row + p.h)
        return f

    def has(self, artifact: str) -> bool:
        return artifact in self.hero.artifacts

    def wall_stats(self) -> dict:
        return FACTIONS[self.hero.faction]

    def copy(self) -> "Side":
        # Heisspfad der Suche: flache Kopien ueber __dict__ statt copy.copy (gleiches Ergebnis).
        s = object.__new__(Side)
        d = s.__dict__
        d.update(self.__dict__)
        h = object.__new__(Hero)
        h.__dict__.update(self.hero.__dict__)
        d["hero"] = h
        new = object.__new__
        pieces = []
        for p in self.pieces:
            q = new(Piece)
            q.__dict__ = p.__dict__.copy()
            pieces.append(q)
        d["pieces"] = pieces
        d["stock"] = dict(self.stock) if self.stock is not None else None
        return s

    def sig(self) -> tuple:
        return tuple(sorted(p.sig() for p in self.pieces))


@dataclass
class State:
    me: Side
    enemy: Side
    moves_left: int = 3

    def side(self, who: str) -> Side:
        return self.me if who == "me" else self.enemy

    def other(self, who: str) -> Side:
        return self.enemy if who == "me" else self.me

    def copy(self) -> "State":
        return State(self.me.copy(), self.enemy.copy(), self.moves_left)

    def key(self) -> tuple:
        return (self.me.sig(), self.moves_left, self.me.hero.shield)


def make_formation(side: Side, unit: str, color: str, col: int, row: int, *, fused: int = 1) -> Piece:
    t = tier(unit)
    w, h = FORM_FOOT[t]
    max_p = stat(unit, "attack", side.hero.level) * fused
    start = math.ceil(max_p * RULES["start_power_ratio"])
    if unit == "knight" and side.has("knights_armor"):
        start = max_p
    ct = UNITS[unit]["ct"]
    if unit == "griffin" and side.has("feathered_helm"):
        ct -= 1
    if unit == "pit_fiend" and side.has("pit_masters_tail"):
        ct -= 1
    p = Piece("form", col, row, w, h, unit, color, max_power=max_p, start_power=start,
              ct=ct, ct_total=ct, fused=fused, uid=side.next_uid)
    side.next_uid += 1
    return p


# --------------------------------------------------------------------------- Text-Format
#
#   [me] / [enemy]   key = value  (hero, faction, hp, max_hp, mp, max_mp, level, artifacts, reserve)
#   [state]          moves = 3
#   [board]          6 Zeilen Gegner (oberste = hinterste Reihe), eine Trennzeile "----",
#                    6 Zeilen ich (oberste = Frontreihe) -- also genau wie auf dem Bildschirm.
#
#   Zellen (durch Leerzeichen getrennt):
#     .                 leer
#     swb               idle Einheit: Code (siehe units.json) + Farbe (1 Zeichen)
#     W8                Wandsegment mit 8 HP
#     F:swb:2:7         ladende Formation: Einheit+Farbe, Restladezeit, aktuelle PWR [, :Fusionen]
#   Mehrfeldrige Pieces (Elite 1x2, Champion 2x2, Formationen 1x3/1x4/2x4) schreibt man in
#   jedes belegte Feld mit identischem Token; sie werden von der Front aus nach Footprint gruppiert.


def _parse_kv(lines: list[str]) -> dict:
    out = {}
    for ln in lines:
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _hero_from(kv: dict) -> Hero:
    hp = int(kv.get("hp", 100))
    max_hp = int(kv.get("max_hp", max(hp, 100)))
    arts = frozenset(a.strip() for a in kv.get("artifacts", "").split(",") if a.strip())
    return Hero(name=kv.get("hero", "?"), faction=kv.get("faction", "haven").lower(), hp=hp,
                max_hp=max_hp, mp=int(kv.get("mp", 0)), max_mp=int(kv.get("max_mp", max_hp)),
                level=int(kv.get("level", MAX_LEVEL)), artifacts=arts)


def _parse_token(tok: str):
    if tok == ".":
        return None
    if tok[0] == "W" and tok[1:].isdigit():
        return ("wall", int(tok[1:]))
    if tok.startswith("F:"):
        parts = tok.split(":")
        code, color = parts[1][:-1], parts[1][-1]
        fused = int(parts[4]) if len(parts) > 4 else 1
        return ("form", CODE_TO_UNIT[code], color, int(parts[2]), int(parts[3]), fused)
    code, color = tok[:-1], tok[-1]
    if code not in CODE_TO_UNIT:
        raise ValueError(f"Unbekannter Einheiten-Code '{code}' in Token '{tok}'")
    return ("unit", CODE_TO_UNIT[code], color)


def _build_side(side: Side, rows: list[list[str]]):
    """rows[r][c] mit r=0 Front. Gruppiert mehrfeldrige Tokens nach Footprint."""
    taken = set()
    for c in range(COLS):
        for r in range(ROWS):
            if (c, r) in taken:
                continue
            tok = rows[r][c]
            info = _parse_token(tok)
            if info is None:
                continue
            if info[0] == "wall":
                w, h = 1, 1
                p = Piece("wall", c, r, hp=info[1], uid=side.next_uid)
                side.next_uid += 1
            elif info[0] == "unit":
                w, h = IDLE_FOOT[tier(info[1])]
                p = Piece("unit", c, r, w, h, info[1], info[2], uid=side.next_uid)
                side.next_uid += 1
            else:
                _, unit, color, ct, pwr, fused = info
                p = make_formation(side, unit, color, c, r, fused=fused)
                w, h = p.w, p.h
                # Lade-Fortschritt aus Restladezeit ableiten, Rest = Schaden.
                p.ct = ct
                p.deficit = max(0, p.power - pwr)
            for cc in range(c, c + w):
                for rr in range(r, r + h):
                    if cc >= COLS or rr >= ROWS or rows[rr][cc] != tok:
                        raise ValueError(f"Piece '{tok}' bei Spalte {c + 1}, Reihe {r + 1} passt nicht "
                                         f"zum Footprint {w}x{h}")
                    taken.add((cc, rr))
            side.pieces.append(p)


def parse_state(text: str) -> State:
    sections: dict[str, list[str]] = {}
    cur = None
    for raw in text.splitlines():
        ln = raw.split("#", 1)[0]
        if not ln.strip():
            continue
        if ln.strip().startswith("[") and ln.strip().endswith("]"):
            cur = ln.strip()[1:-1].lower()
            sections[cur] = []
            continue
        if cur:
            sections[cur].append(ln.strip())
    me_kv, en_kv = _parse_kv(sections.get("me", [])), _parse_kv(sections.get("enemy", []))
    st_kv = _parse_kv(sections.get("state", []))
    me, en = Side(_hero_from(me_kv)), Side(_hero_from(en_kv))
    me.reserve, en.reserve = int(me_kv.get("reserve", 0)), int(en_kv.get("reserve", 0))
    board = sections.get("board", [])
    sep = next(i for i, ln in enumerate(board) if ln.startswith("-"))
    en_lines, me_lines = board[:sep], board[sep + 1:]
    if len(en_lines) != ROWS or len(me_lines) != ROWS:
        raise ValueError(f"Board braucht je {ROWS} Zeilen pro Seite")
    grid_en = [ln.split() for ln in reversed(en_lines)]  # -> r=0 Front
    grid_me = [ln.split() for ln in me_lines]
    for g in (grid_en, grid_me):
        for row in g:
            if len(row) != COLS:
                raise ValueError(f"Zeile mit {len(row)} statt {COLS} Zellen: {' '.join(row)}")
    _build_side(en, grid_en)
    _build_side(me, grid_me)
    default_moves = RULES["moves_per_turn"] + (1 if me.has("celerity_ring") else 0)
    return State(me, en, int(st_kv.get("moves", default_moves)))


def piece_token(p: Piece) -> str:
    if p.kind == "wall":
        return f"W{p.hp}"
    if p.kind == "block":
        return "FF" if p.merged else "XX"
    code = UNITS[p.unit]["code"] + p.color
    if p.kind == "unit":
        return code
    tok = f"F:{code}:{p.ct}:{p.power}"
    return tok + (f":{p.fused}" if p.fused > 1 else "")


def render_side(side: Side, front_on_top: bool) -> list[str]:
    g = side.grid()
    lines = []
    for r in range(ROWS):
        lines.append(" ".join(piece_token(g[(c, r)]) if (c, r) in g else "." for c in range(COLS)))
    return lines if front_on_top else list(reversed(lines))


def render_state(s: State, compact: bool = False) -> str:
    """Brett wie auf dem Bildschirm. compact=True -> kurze Zellen fuer die Konsole."""
    def short(tok: str) -> str:
        if not compact:
            return tok
        if tok.startswith("F:"):
            _, u, ct, pw, *_ = tok.split(":")
            return f"{u.upper()}{ct}"
        return tok

    def fmt(lines):
        out = []
        for ln in lines:
            cells = [short(t) for t in ln.split()]
            out.append(" ".join(f"{c:>{6 if compact else 12}}" for c in cells))
        return out

    hdr = " ".join(f"{i + 1:>{6 if compact else 12}}" for i in range(COLS))
    e, m = s.enemy.hero, s.me.hero
    parts = [f"Gegner {e.name} ({e.faction}) HP {e.hp}/{e.max_hp} MP {e.mp}/{e.max_mp}", hdr]
    parts += fmt(render_side(s.enemy, front_on_top=False))
    parts.append("-" * len(hdr))
    parts += fmt(render_side(s.me, front_on_top=True))
    parts += [hdr, f"Ich {m.name} ({m.faction}) HP {m.hp}/{m.max_hp} MP {m.mp}/{m.max_mp}  Zuege: {s.moves_left}"]
    return "\n".join(parts)
