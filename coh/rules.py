"""Regel-Simulator: Zuege, Formationserkennung, Chains, Fusion, Laden, Links und Angriffe.

Unsichere Regeln sind in units.json -> "rules" schaltbar und in docs/DATEN.md mit ⚠️ markiert.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import (COLS, FORM_UNITS, ROWS, RULES, TIER, Piece, Side, State, make_formation, stat)


# --------------------------------------------------------------------------- Aufraeumen / Ordnung

def rebuild(side: Side) -> None:
    """Ordnet jede Spalte: Waende vorn, dann ladende Formationen (alt -> neu), dann idle Einheiten.

    Entspricht gleichzeitig der Schwerkraft zur Front. Was nicht mehr passt, geht in die Reserve.
    """
    order = sorted(side.pieces, key=_rebuild_key)
    fill = [0] * COLS
    kept = []
    for p in order:
        c0, w, h = p.col, p.w, p.h
        if w == 1:
            row = fill[c0]
        else:
            row = max(fill[c0:c0 + w])
        if row + h > ROWS:
            side.reserve += FORM_UNITS[p.tier] if p.kind == "form" else (1 if p.kind == "unit" else 0)
            continue
        p.row = row
        if w == 1:
            fill[c0] = row + h
        else:
            for c in range(c0, c0 + w):
                fill[c] = row + h
        kept.append(p)
    side.pieces = kept


_PRIO = {"wall": 0, "form": 1, "unit": 2}


def _rebuild_key(p):
    kind = p.kind
    pr = (1 if p.merged else 2) if kind == "block" else _PRIO[kind]
    return (pr, p.uid if pr == 1 else p.row, p.col)


def _row_col(q):
    return (q.row, q.col)


@dataclass
class Match:
    kind: str  # "form" | "wall"
    pieces: list[Piece]
    col: int = 0
    row: int = 0
    unit: str | None = None
    color: str | None = None


def find_matches(side: Side) -> list[Match]:
    # Heisspfad der Suche (Hunderttausende Aufrufe je Analyse): Hilfsfunktionen sind eingeklappt,
    # das Brett liegt als Liste je Spalte/Reihe vor. Verhalten wie zuvor (Differenztest).
    grid = [None] * (COLS * ROWS)  # Index c * ROWS + r
    any_core = False
    high: list[Piece] = []
    for p in side.pieces:
        if p.kind != "unit":
            continue
        u = p.unit
        if u and TIER[u] == "core":
            base = p.col * ROWS
            for r in range(p.row, p.row + p.h):
                if 0 <= r < ROWS:  # nach rebuild() liegt alles im Feld
                    grid[base + r] = p
            any_core = True
        else:
            high.append(p)
    used: set[int] = set()
    out: list[Match] = []

    # High-Tier zuerst: Champion (2x2) bzw. Elite (1x2) mit gleichfarbigen Core dahinter.
    if high:
        for p in sorted(high, key=_row_col):
            if id(p) in used:
                continue
            color = p.color
            support = []
            for k in range(2):
                r = p.row + p.h + k
                for c in range(p.col, p.col + p.w):
                    q = grid[c * ROWS + r] if r < ROWS and 0 <= c < COLS else None
                    if q is None or id(q) in used or (color and q.color != color):
                        support = None
                        break
                    support.append(q)
                if support is None:
                    break
            if support is not None and len({id(s) for s in support}) == len(support):
                used.update(id(s) for s in support)
                used.add(id(p))
                out.append(Match("form", [p, *support], p.col, p.row, p.unit, p.color))

    if not any_core:
        return out

    # Core: 3 gleiche Einheiten gleicher Farbe senkrecht.
    for c in range(COLS):
        col = grid[c * ROWS:(c + 1) * ROWS]
        r = 0
        while r <= ROWS - 3:
            a = col[r]
            if a is not None and id(a) not in used:
                ac, au = a.color, a.unit
                b, d = col[r + 1], col[r + 2]
                if (b is not None and id(b) not in used and (not ac or b.color == ac) and (not au or b.unit == au)
                        and d is not None and id(d) not in used and (not ac or d.color == ac)
                        and (not au or d.unit == au)):
                    used.update((id(a), id(b), id(d)))
                    out.append(Match("form", [a, b, d], c, r, a.unit, a.color))
                    r += 3
                    continue
            r += 1

    # Waende: >= 3 gleichfarbige idle Core waagerecht (Typ egal). Einheiten, die gerade senkrecht
    # zu einer Formation werden, zaehlen fuer die Reihe mit (Combo), werden aber nicht zur Wand.
    vertical_used = set(used)

    for r in range(ROWS):
        row = grid[r::ROWS]
        c = 0
        while c < COLS:
            a = row[c]
            if a is None:
                c += 1
                continue
            run = [a]
            ac = a.color
            while c + len(run) < COLS:
                n = row[c + len(run)]
                if n is None or (ac and n.color != ac):
                    break
                run.append(n)
            free = [x for x in run if id(x) not in used]
            if len(run) >= 3 and free and any(id(x) not in vertical_used for x in run):
                used.update(id(x) for x in free)
                out.append(Match("wall", free, c, r, color=a.color))
            c += len(run)
    return out


def _fuse_and_merge(side: Side, new_forms: list[Piece]) -> None:
    g = side.grid()
    for f in new_forms:
        if f not in side.pieces or f.row == 0:
            continue
        front = g.get((f.col, f.row - 1))
        if (front and front is not f and front.kind == "form" and front.unit == f.unit
                and front.color == f.color and front.col == f.col and front.w == f.w
                and front.row + front.h == f.row):
            front.max_power += f.max_power
            front.start_power += f.start_power
            front.fused += f.fused
            side.hero.mp = min(side.hero.max_mp, side.hero.mp
                               + round(RULES.get("mp_per_fusion", 0) * side.hero.max_mp))
            side.pieces.remove(f)
            side.reserve += FORM_UNITS[f.tier]
            g = side.grid()
    # Wand-Fusion: zwei Segmente in einer Spalte verschmelzen genau einmal.
    ws = side.wall_stats()
    for c in range(COLS):
        walls = sorted((p for p in side.pieces if p.kind == "wall" and p.col == c), key=lambda p: p.row)
        i = 0
        while i + 1 < len(walls):
            a, b = walls[i], walls[i + 1]
            if not a.merged and not b.merged and a.row + 1 == b.row:
                a.hp = min(a.hp + b.hp, ws["wall_max"])
                a.merged = True
                side.pieces.remove(b)
                side.reserve += 1  # im Spiel geprueft (2026-11-23): verschmolzenes Segment -> Reserve
                i += 2
            else:
                i += 1


def settle(side: Side) -> list[int]:
    """Loest alle Formationen/Waende bis zur Ruhe auf. Rueckgabe: Anzahl neuer Formationen+Waende
    pro Kaskadenstufe (Index 0 = direkt durch die Aktion entstanden)."""
    rebuild(side)
    waves = []
    while True:
        matches = find_matches(side)
        if not matches:
            break
        new_forms = []
        for m in matches:
            for p in m.pieces:
                side.pieces.remove(p)
            if m.kind == "form":
                f = make_formation(side, m.unit, m.color, m.col, m.row)
                side.pieces.append(f)
                new_forms.append(f)
            else:
                base = side.wall_stats()["wall_base"]
                for p in m.pieces:
                    side.pieces.append(Piece("wall", p.col, p.row, hp=base, uid=side.next_uid))
                    side.next_uid += 1
        rebuild(side)
        _fuse_and_merge(side, new_forms)
        rebuild(side)
        waves.append(len(matches))
    return waves


# --------------------------------------------------------------------------- Aktionen

def backmost(side: Side, col: int) -> Piece | None:
    best = None
    for p in side.pieces:
        if col in p.cols() and (best is None or p.row + p.h > best.row + best.h):
            best = p
    if best is None or best.kind != "unit":
        return None
    fill = side.fill()
    if any(fill[c] != best.row + best.h for c in best.cols()):
        return None  # Champion, hinter dem in der Nachbarspalte noch etwas steht
    return best


def legal_moves(state: State) -> list[tuple]:
    side = state.me
    out = []
    seen = set()
    for src in range(COLS):
        p = backmost(side, src)
        if p is None or id(p) in seen:
            continue
        seen.add(id(p))
        fill = side.fill(exclude=p)
        for dst in range(COLS - p.w + 1):
            if dst == p.col:
                continue
            row = max(fill[c] for c in range(dst, dst + p.w))
            if row + p.h <= ROWS:
                out.append(("move", p.col, dst))
    return out


def legal_deletes(state: State) -> list[tuple]:
    # Elite/Champions sind begrenzt und tragen ihren spaeteren Angriff in sich: nie selbst loeschen
    # (Schalter "allow_delete_high_tier" in units.json -> rules, Standard aus).
    allow_ht = RULES.get("allow_delete_high_tier", False)
    return [("delete", p.col, p.row) for p in state.me.pieces
            if p.kind == "wall" or (p.kind == "unit" and (p.tier == "core" or allow_ht))]


def apply_action(state: State, action: tuple) -> tuple[State, int]:
    """Fuehrt eine Aktion fuer 'me' aus. Rueckgabe: neuer Zustand, gewonnene Extrazuege."""
    s = state.copy()
    side = s.me
    g = side.grid()
    kind, col, arg = action
    if kind == "reinforce":
        import random
        return apply_reinforce(state, random.Random(arg)), 0
    if kind == "spell":  # kostenlos, kein Zug
        cast_spell(side)
        return s, 0
    if kind == "move":
        p = backmost(side, col)
        if p is None:
            raise ValueError(f"Kein bewegbares Piece in Spalte {col + 1}")
        fill = side.fill(exclude=p)
        p.col = arg
        p.row = max(fill[c] for c in p.cols())
        p.uid = side.next_uid  # zuletzt gesetzt -> bleibt beim Ordnen hinten
        side.next_uid += 1
        waves = settle(side)
        # Mehrere Formationen/Waende durch eine Aktion: jede weitere gibt einen Zug (Combo),
        # ebenso alles, was durch Nachrutschen entsteht.
        extra = 0
        if waves and RULES.get("combo_on_move_gives_moves", True):
            extra += waves[0] - 1
        if RULES["cascade_on_move_gives_moves"]:
            extra += sum(waves[1:])
    elif kind == "delete":
        p = g[(col, arg)]
        side.pieces.remove(p)
        if p.kind == "unit":
            side.reserve += 1
        waves = settle(side)
        extra = sum(waves) * RULES["chain_extra_move_per_formation"]
        # Combo: Entstehen durch das Loeschen gleichzeitig mehrere Formationen/Waende, gibt es
        # zusaetzlich je weitere einen Zug (Spieler: Angriff + Wand durch eine Loeschung -> 3 auf 5).
        if waves and RULES.get("combo_on_delete_gives_moves", True):
            extra += waves[0] - 1
    else:
        raise ValueError(kind)
    s.moves_left += extra - 1
    if extra:  # Kettenreaktion / Combo: Extrazug und Magie (Schaetzwert, units.json -> rules)
        side.hero.mp = min(side.hero.max_mp, side.hero.mp
                           + round(RULES.get("mp_per_extra_move", 0.06) * side.hero.max_mp) * extra)
    return s, extra


# --------------------------------------------------------------------------- Laden und Angreifen

@dataclass
class TurnReport:
    hero_damage: int = 0  # Schaden am gegnerischen Helden
    destroyed: int = 0  # vernichtete gegnerische Staerke (Toughness/PWR/Wand-HP)
    shield_absorbed: int = 0  # vom eigenen Holy Shield abgefangener Schaden (beim Verteidiger)
    launched: list = field(default_factory=list)


def toughness(p: Piece, side: Side) -> int:
    return stat(p.unit, "toughness", side.hero.level)


def link_bonus(group: list[Piece], side: Side) -> dict[int, float]:
    lb = RULES["link_bonus"]
    mult = 1.5 if side.has("binding_orb") else 1.0
    out = {}
    for f in group:
        out[id(f)] = sum(lb[o.tier] * o.fused for o in group if o is not f) * mult
    return out


def resolve_attack(att: Piece, power: int, att_side: Side, def_side: Side, rep: TurnReport) -> None:
    g = def_side.grid()
    hit: list[Piece] = []
    for r in range(ROWS):
        for c in att.cols():
            p = g.get((c, r))
            if p and p not in hit:
                hit.append(p)
    P = power
    first_strike = att.unit == "spearman"
    for p in hit:
        if P <= 0:
            break
        if p.kind == "wall":
            if first_strike and att_side.has("golden_spear") and p.hp <= P:
                rep.destroyed += p.hp
                def_side.pieces.remove(p)
            elif P >= p.hp:
                P -= p.hp
                rep.destroyed += p.hp
                def_side.pieces.remove(p)
            else:
                p.hp -= P
                rep.destroyed += P
                P = 0
        elif p.kind == "block":  # unbekanntes Hindernis
            if P >= p.hp:
                P -= p.hp
                rep.destroyed += p.hp
                def_side.pieces.remove(p)
            else:
                p.hp -= P
                rep.destroyed += P
                P = 0
        elif p.kind == "unit":
            t = toughness(p, def_side)
            def_side.pieces.remove(p)
            rep.destroyed += t
            if att.unit == "bone_dragon":
                P += t * (2 if att_side.has("talons_talon") else 1)
            elif not first_strike:
                P = max(0, P - t)
        else:  # ladende Formation
            fp = p.power
            if p.unit == "ghost":
                P -= fp  # Ghost ist beim Laden unverwundbar, bremst aber
                continue
            if first_strike and fp <= P:
                def_side.pieces.remove(p)
                rep.destroyed += fp
            elif P >= fp:
                P -= fp
                rep.destroyed += fp
                def_side.pieces.remove(p)
            else:
                p.deficit += P
                rep.destroyed += P
                P = 0
                if att.unit == "druid":
                    p.ct += 2
                if att.unit == "zombie":
                    p.plague += 2 if att_side.has("plague_rat") else 1
    if P > 0 and def_side.hero.shield > 0:  # Holy Shield vor der Heldenzone
        absorbed = min(P, def_side.hero.shield)
        def_side.hero.shield -= absorbed
        rep.shield_absorbed += absorbed
        P -= absorbed
    if P > 0:
        def_side.hero.hp -= P
        rep.hero_damage += P
        if att.unit == "vampire":
            heal = round(P * (1.25 if att_side.has("blood_of_the_one") else 1.0))
            att_side.hero.hp = min(att_side.hero.max_hp, att_side.hero.hp + heal)
        att_side.hero.mp = min(att_side.hero.max_mp, att_side.hero.mp + P * RULES["mp_per_damage_dealt"])
        def_side.hero.mp = min(def_side.hero.max_mp, def_side.hero.mp + P * RULES["mp_per_damage_taken"])


def end_turn_mp(state: State) -> int:
    """Zug beenden mit ungenutzten Zuegen gibt Magie (je Zug ca. 3 %, units.json -> rules).
    Rueckgabe: neue MP (der Zustand wird nicht veraendert)."""
    h = state.me.hero
    gain = round(RULES.get("mp_per_unused_move", 0.03) * h.max_mp) * max(0, state.moves_left)
    return min(h.max_mp, h.mp + gain)


def cast_spell(side: Side) -> None:
    """Heldenzauber wirken (kostet keinen Zug). Bisher simuliert: Godrics Holy Shield."""
    if side.hero.spell == "holy_shield":
        side.hero.shield = round(RULES.get("holy_shield_ratio", 0.5) * side.hero.max_hp)
    side.hero.mp = 0


def _fire_shield(side: Side, opp: Side, rep: "TurnReport") -> None:
    """Holy Shield nach einer Runde: Rest x2 geht front-to-back auf den Gegner.
    Verteilung (units.json -> holy_shield_target): "all_columns" = gleichmaessig auf alle Spalten."""
    power = 2 * side.hero.shield
    side.hero.shield = -1
    if power <= 0:
        return
    per = power / COLS
    carry = 0.0
    for c in range(COLS):
        carry += per
        p = int(carry)
        carry -= p
        if p > 0:
            resolve_attack(Piece("form", c, 0, unit="holy_shield"), p, side, opp, rep)
    opp.bonus_moves += sum(settle(opp))


def start_turn(state: State, who: str) -> TurnReport:
    """Rundenbeginn von 'who': Waende regenerieren, Formationen laden, fertige greifen an."""
    side, opp = state.side(who), state.other(who)
    rep = TurnReport()
    if side.hero.shield >= 0:
        _fire_shield(side, opp, rep)
    ws = side.wall_stats()
    regen = ws["wall_regen"] * (2 if side.has("vine_gloves") else 1)
    if opp.has("crown_of_thorns"):
        side.hero.hp -= 2
    for p in list(side.pieces):
        if p.kind == "wall" and regen:
            p.hp = min(p.hp + regen, ws["wall_max"] if p.merged else ws["wall_base"])
        elif p.kind == "form":
            if p.plague:
                p.deficit += 2 * p.plague
            p.ct -= 1
            if p.power <= 0:
                side.pieces.remove(p)
    launching = sorted((p for p in side.pieces if p.kind == "form" and p.ct <= 0), key=lambda p: p.uid)
    groups: dict[str, list[Piece]] = {}
    for f in launching:
        groups.setdefault(f.color, []).append(f)
    bonus = {}
    for grp in groups.values():
        if len(grp) > 1:
            bonus.update(link_bonus(grp, side))
            # Gebundene Angriffe fuellen die Magieanzeige (Schaetzwert, units.json -> rules)
            side.hero.mp = min(side.hero.max_mp, side.hero.mp + round(
                RULES.get("mp_per_link_partner", 0) * side.hero.max_mp) * (len(grp) - 1))
    launching.sort(key=lambda f: (0 if bonus.get(id(f)) else 1, f.uid))
    atk_mult = 1.75 if side.has("spider_cloak") else 1.0
    for f in launching:
        mult = (1 + bonus.get(id(f), 0.0)) * atk_mult
        if f.fused > 1 and (side.has("doubling_cape") or side.has("lions_mane")):
            mult *= 1.5
        power = round(f.power * mult)
        side.pieces.remove(f)
        side.reserve += FORM_UNITS[f.tier]
        rep.launched.append((f.unit, f.color, f.col, power))
        resolve_attack(f, power, side, opp, rep)
        opp.bonus_moves += sum(settle(opp))
        side.bonus_moves += sum(settle(side))
    return rep


# --------------------------------------------------------------------------- Verstaerkung

HT_SLOTS = {"elite": 1, "champion": 2}  # High-Tier-Cap: 4 Elites, 2 Elites + 1 Champion oder 2 Champions
HT_CAP = 4


def _ht_on_field(side: Side) -> dict[str, int]:
    out = {"elite": 0, "champion": 0}
    for p in side.pieces:
        if p.kind in ("unit", "form") and p.unit and p.tier in out:
            out[p.tier] += 1
        elif p.kind == "block" and p.h == 2 and not p.merged:
            out["champion" if p.w == 2 else "elite"] += 1
    return out


def _ht_available(side: Side) -> dict[str, int]:
    """Wie viele Elites/Champions noch in der Reserve sein koennen: Kontingent minus Feld.
    Ohne gelesenes Kontingent nur die Tiers, die man auf dem Feld sieht (Annahme: je 1 uebrig)."""
    field = _ht_on_field(side)
    if side.stock is not None:
        return {t: max(0, side.stock.get(t, 0) - field[t]) for t in field}
    return {t: (1 if field[t] else 0) for t in field}


def _ht_positions(side: Side, tier: str) -> list[int]:
    """Spalten, in die eine Elite (1x2) bzw. ein Champion (2x2) noch passt."""
    fill = side.fill()
    if tier == "elite":
        return [c for c in range(COLS) if fill[c] + 2 <= ROWS]
    return [c for c in range(COLS - 1) if max(fill[c], fill[c + 1]) + 2 <= ROWS]


def apply_reinforce(state: State, rng) -> State:
    """Verstaerkung rufen: Reserve-Einheiten fallen zufaellig hinten in die Spalten.
    Regel (DATEN.md): Drops erzeugen nie sofort eine Formation oder Wand.
    Farben: umgekehrt zur Haeufigkeit auf dem Feld (dort Haeufiges ist in der Reserve selten).

    Elites/Champions fallen mit: pro Abwurf mit Wahrscheinlichkeit ht_drop_base x Anteil freier
    Felder, nur wenn sie passen (Elite 1x2, Champion 2x2 frei), noch im Kontingent sind und der
    High-Tier-Cap es erlaubt. Ein High-Tier-Abwurf zaehlt als eine Einheit der Reserve."""
    s = state.copy()
    side = s.me
    counts: dict[str, int] = {}
    for p in side.pieces:
        if p.kind == "unit" and p.tier == "core":
            counts[p.color] = counts.get(p.color, 0) + 1
    if not side.has("kings_crown"):
        s.moves_left -= 1
    if side.reserve <= 0:
        return s
    # Farben in der Reserve: die auf dem Feld (gewichtet) plus unbekannte bis mind. 3 Klassen
    for extra in "xyz":
        if len(counts) >= 3:
            break
        counts.setdefault(extra, 1)
    colors = sorted(counts)
    # In der Reserve steckt, was nicht auf dem Feld ist: bei etwa gleich grossen Anteilen je Farbe
    # ist eine Farbe, die schon oft auf dem Feld steht, in der Reserve seltener (nicht haeufiger).
    per_color = (sum(counts.values()) + side.reserve) / len(colors)
    weights = [max(0.5, per_color - counts[c]) for c in colors]
    avail = _ht_available(side)
    base = RULES.get("ht_drop_base", 0.3)
    placed = 0
    for _ in range(side.reserve):
        fill = side.fill()
        cols = [c for c in range(COLS) if fill[c] < ROWS]
        if not cols:
            break
        # High-Tier-Versuch: Chance waechst mit dem freien Platz
        free = sum(ROWS - f for f in fill) / (ROWS * COLS)
        dropped_ht = False
        if rng.random() < base * free:
            field = _ht_on_field(side)
            used = sum(HT_SLOTS[t] * n for t, n in field.items())
            tiers = [t for t in ("elite", "champion")
                     if avail[t] > 0 and used + HT_SLOTS[t] <= HT_CAP and _ht_positions(side, t)]
            if tiers:
                t = rng.choices(tiers, [avail[x] for x in tiers])[0]
                pos = _ht_positions(side, t)
                for _attempt in range(10):
                    c = rng.choice(pos)
                    w = 2 if t == "champion" else 1
                    row = max(fill[x] for x in range(c, c + w))
                    p = Piece("unit", c, row, w, 2, unit=t, color=rng.choices(colors, weights)[0],
                              uid=side.next_uid)
                    side.pieces.append(p)
                    if find_matches(side):
                        side.pieces.remove(p)
                        continue
                    side.next_uid += 1
                    avail[t] -= 1
                    placed += 1
                    dropped_ht = True
                    break
        if dropped_ht:
            continue
        for _attempt in range(15):
            c = rng.choice(cols)
            p = Piece("unit", c, fill[c], unit="core", color=rng.choices(colors, weights)[0], uid=side.next_uid)
            side.pieces.append(p)
            if find_matches(side):
                side.pieces.remove(p)
                continue
            side.next_uid += 1
            placed += 1
            break
        else:
            break
    side.reserve -= placed
    return s
