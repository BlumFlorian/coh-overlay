"""Zugsuche: Beam-Suche ueber die eigenen Aktionen einer Runde, Bewertung per Vorausschau-Simulation."""
from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass, field

from .model import COLS, RULES, ROWS, State, tier
from .rules import apply_action, end_turn_mp, legal_deletes, legal_moves, settle, start_turn

WIN = 1_000_000.0


@dataclass
class Weights:
    hero_damage: float = 1.0  # Schaden am gegnerischen Helden
    destroyed: float = 0.35  # vernichtete gegnerische Staerke
    damage_taken: float = 1.1  # Schaden am eigenen Helden
    lost: float = 0.35  # eigene vernichtete Staerke
    discount: float = 0.85  # pro Runde in der Zukunft
    pending_attack: float = 0.6  # Angriffe, die erst nach dem Horizont starten (z. B. Angel CT 6), abgezinst
    setup_elite: float = 6.0  # volle Vorbereitung (passende Core dahinter) einer idle Elite
    setup_champion: float = 20.0  # dito Champion: 4 passende Core im 2x2-Block dahinter
    # Fester Wert je ladender eigener Elite/Champion: muss ueber dem vollen Vorbereitungs-Bonus liegen,
    # sonst lohnt sich das Aktivieren nicht (sein Angriff liegt oft hinter dem Horizont).
    active_elite: float = 12.0
    active_champion: float = 40.0
    near_match: float = 0.6  # Paare, die mit einem Zug zur Formation werden
    walls: float = 0.08  # eigene Wand-HP
    # Verpasster Link (Nutzer, 2026-11-23): Gleichfarbige Core-Formation, die VOR einem ladenden
    # Elite/Champion derselben Farbe losgeht, verbraucht Einheiten, die spaeter mit ihm gebunden
    # angreifen koennten. Abzug = Anteil des entgangenen Link-Gewinns (Link-Bonus selbst geschaetzt).
    link_missed: float = 0.5
    unused_move: float = 0.35  # Wert ungenutzter Zuege (zusaetzlich zur simulierten Magie, siehe mp)
    idle_unit: float = 0.4  # Potenzial je idle Core-Einheit auf dem Feld (Material fuer spaetere Formationen)
    # Verlust von Elite/Champions (idle getroffen oder beim Laden vernichtet; Angreifen kostet nichts).
    # Wert = Basis * (1 + Knappheit / verbleibende), beim letzten Exemplar zusaetzlich der Leer-Zuschlag.
    ht_elite: float = 20.0
    ht_champion: float = 50.0
    ht_last_elite: float = 60.0
    ht_last_champion: float = 150.0
    ht_scarcity: float = 2.0
    ht_enemy: float = 0.8  # Anteil davon als Gewinn, wenn der Gegner sie verliert
    ht_unknown_left: int = 3  # angenommener Rest, wenn das Kontingent nicht gelesen wurde
    # Sieg/Niederlage in der Vorausschau. Sicher ist nur der Tod durch die schon ladenden Angriffe
    # des Gegners in seiner naechsten Runde (-> absolut). Alles Spaetere ist unsicher, weil die
    # Simulation keine Gegnerzuege kennt -> grosser, abgezinster Bonus, die Bewertung laeuft weiter.
    # Ein Sieg im naechsten Zug (k = 0) muss jede Kombination aus Einheitenverlusten aufwiegen
    # (3 Champions zuletzt ~ 3 x 250): nach dem Sieg zaehlt nichts mehr. Spaeter: Gegner hat mehr
    # Zuege zum Reagieren -> Faktor end_decay pro Runde.
    win_value: float = 2000.0
    loss_value: float = 2000.0  # eigener Tod ab Runde 2 (Runde 1 ist sicher -> -WIN)
    end_decay: float = 0.4
    # Verschuetteter idle Champion/Elite: fremde Einheit in den 2 Reihen direkt dahinter
    # (muss vor dem Aktivieren erst weggeraeumt werden, kostet Zuege).
    bury_champion: float = 5.0
    bury_elite: float = 2.5
    # Erreichbarkeit: idle Champion/Elite, der in wenigen Aktionen aktiviert werden kann (bis zu
    # 2 Zuege voraus, siehe activation_cost). Voll bei 0 fehlenden Aktionen, linear bis 0.
    # Muss zusammen mit setup_* unter active_* bleiben, sonst lohnt das Aktivieren nicht.
    reach_champion: float = 16.0
    reach_elite: float = 5.0
    mp: float = 0.05  # je Punkt eigener Magieanzeige (0..max_mp)
    # Volle Leiste aufheben hat einen Wert (spaeter gezielter einsetzen). Der Zauber selbst wird
    # simuliert (Holy Shield: abgefangener Schaden, Rueckschlag) und muss diesen Wert schlagen.
    spell_ready: float = 10.0


@dataclass
class Plan:
    actions: list[tuple]
    score: float
    state: State
    details: dict = field(default_factory=dict)


def _near_matches(state: State) -> int:
    """Grobe Potenzialschaetzung: zwei gleiche Core uebereinander mit Platz dahinter."""
    side = state.me
    g = side.grid()
    n = 0
    for p in side.pieces:
        if p.kind != "unit" or p.tier != "core":
            continue
        q = g.get((p.col, p.row + 1))
        if q and q.kind == "unit" and q.unit == p.unit and q.color == p.color and p.row + 2 < ROWS:
            n += 1
    return n


def _high_tier_setup(state: State, w: Weights) -> float:
    """Fortschritt beim Aktivieren idle Elite/Champions: gleichfarbige Core direkt dahinter
    (Elite: 2 in der Spalte, Champion: 2x2). Ohne Platz fuer die volle Formation zaehlt es halb.
    Fremde Einheiten in diesen Feldern verschuetten die Einheit (Abzug je Feld)."""
    side = state.me
    g = side.grid()
    total = 0.0
    for u in side.pieces:
        if u.kind != "unit" or u.tier == "core" or not u.color or u.color.startswith("~"):
            continue
        matched = buried = 0
        for c in u.cols():
            ok = True
            for r in range(u.row + u.h, min(ROWS, u.row + u.h + 2)):
                q = g.get((c, r))
                if q is None:
                    break
                good = q.kind == "unit" and q.tier == "core" and q.color == u.color
                if ok and good:
                    matched += 1
                else:
                    ok = False
                    buried += 1
        room = 1.0 if u.row + u.h + 2 <= ROWS else 0.5
        value = w.setup_champion if u.tier == "champion" else w.setup_elite
        total += value * room * matched / (2 * u.w)
        total -= buried * (w.bury_champion if u.tier == "champion" else w.bury_elite)
    return total


def _deletable(p) -> bool:
    return p.kind == "wall" or (p.kind == "unit" and p.tier == "core")


def _columns(side) -> dict:
    cols = {c: [] for c in range(COLS)}
    for p in side.pieces:
        for c in range(p.col, p.col + p.w):
            cols[c].append(p)
    for v in cols.values():
        v.sort(key=lambda p: p.row)
    return cols


def activation_cost(side, u, in_col: dict | None = None) -> int | None:
    """Geschaetzte Anzahl Aktionen bis zur Aktivierung der idle Elite/des idle Champions u
    (ohne Zufall, ohne Gegner). None = mit dem jetzigen Brett nicht erreichbar.

    - Platz: u braucht 2 Reihen dahinter. Steht es zu weit hinten, muss vor ihm je Spalte
      entsprechend viel geloescht werden (Einheiten oder Waende; ladende Formationen nicht).
    - Dahinter: fremde Einheiten bis zur 2. passenden muessen weg (je 1 Loeschung).
    - Fehlende gleichfarbige Core werden aus anderen Spalten geholt: 1 Zug plus je eine Loeschung
      fuer jede fremde Einheit, die dort noch dahinter steht.
    Bewusst grob, aber monoton: Jede Vorbereitung senkt den Wert, auch ueber zwei Zuege."""
    cols = list(u.cols())
    in_col = in_col or _columns(side)
    cost, missing = 0, 0
    target = ROWS - u.h - 2  # hinterste Reihe, in der u noch 2 Reihen Platz dahinter hat
    for c in cols:
        if u.row > target:
            # Nur so viele Loeschungen, wie diese Spalte vor u belegt ist (eine Spalte mit Luecke
            # vor dem Champion braucht keine).
            ahead = [p for p in in_col[c] if p.row < u.row]
            need = max(0, sum(p.h for p in ahead) - target)
            if sum(1 for p in ahead if _deletable(p)) < need:
                return None
            cost += need
        filled = 0
        for q in (p for p in in_col[c] if p.row >= u.row + u.h and p is not u):
            if filled == 2:
                break
            if q.kind == "unit" and q.tier == "core" and q.color == u.color:
                filled += 1
            elif q.kind == "unit" and q.tier == "core":
                cost += 1
            else:
                return None  # andere Elite/Champion oder Unbekanntes dahinter
        missing += 2 - filled
    if missing:
        supply = []
        for c, pieces in in_col.items():
            if c in cols:
                continue
            dig = 0
            for q in reversed(pieces):  # von hinten nach vorn
                if q.kind != "unit" or q.tier != "core":
                    break
                if q.color == u.color:
                    supply.append(1 + dig)
                    dig = 0
                else:
                    dig += 1
        if len(supply) < missing:
            return None
        cost += sum(sorted(supply)[:missing])
    return cost


REACH_TURNS = 2  # wie viele Zuege voraus eine Aktivierung noch als Fortschritt zaehlt


def _reach_bonus(state: State, w: Weights) -> float:
    """Je weniger Aktionen bis zur Aktivierung fehlen, desto mehr ist ein idle Champion/Elite wert.
    Reicht ueber den naechsten Zug hinaus (2 Zuege) und belohnt so auch Vorbereitungen wie
    Loeschen vor dem Champion, damit er nach vorn rutscht."""
    span = REACH_TURNS * RULES["moves_per_turn"]
    total = 0.0
    for u, c in _ht_idle_costs(state):
        if c is not None:
            total += (w.reach_champion if u.tier == "champion" else w.reach_elite) * max(0, span - c) / span
    return total


def _ht_idle_costs(state: State) -> list:
    side = state.me
    ht = [u for u in side.pieces
          if u.kind == "unit" and u.tier != "core" and u.color and not u.color.startswith("~")]
    if not ht:
        return []
    in_col = _columns(side)
    return [(u, activation_cost(side, u, in_col)) for u in ht]


def _ht_costs(state: State) -> tuple:
    return tuple(c for _, c in _ht_idle_costs(state))


def _missed_links(state: State) -> float:
    """Entgangener Link-Gewinn (in Schadenspunkten) durch Core-Formationen, die vor einem
    gleichfarbigen ladenden Elite/Champion losgehen (nur eigene Seite)."""
    lb = RULES["link_bonus"]
    forms = [p for p in state.me.pieces if p.kind == "form" and p.unit and p.color
             and not p.color.startswith(("?", "~", "#"))]
    total = 0.0
    for h in forms:
        if h.tier == "core":
            continue
        for f in forms:
            if f.tier == "core" and f.color == h.color and f.ct < h.ct:
                total += lb["core"] * h.power + lb[h.tier] * f.power
    return total


def static_bonus(state: State, w: Weights) -> float:
    idle = sum(1 for p in state.me.pieces if p.kind == "unit" and p.tier == "core")
    active = sum(w.active_champion if p.tier == "champion" else w.active_elite
                 for p in state.me.pieces if p.kind == "form" and p.unit and p.tier in ("elite", "champion"))
    return (w.near_match * _near_matches(state) + w.unused_move * state.moves_left + w.idle_unit * idle
            - w.link_missed * _missed_links(state)
            + _high_tier_setup(state, w) + _reach_bonus(state, w) + active + w.mp * end_turn_mp(state)
            + (w.spell_ready if state.me.hero.spell_ready() else 0.0))


def evaluate(state: State, w: Weights, horizon: int = 3) -> tuple[float, dict]:
    """Simuliert ab Rundenende: Gegner-Start, eigener Start, ... (ohne Gegnerzuege)."""
    s = state.copy()
    s.me.hero.mp = end_turn_mp(s)  # Zug beenden: ungenutzte Zuege geben Magie
    score = 0.0
    det = {"dealt": [], "taken": []}
    # Ziel: gegnerische HP auf 0, eigene HP halten. Je weniger HP eine Seite hat, desto mehr zaehlt
    # jeder Punkt Schaden dort (Angriff bei schwachem Gegner, Verteidigung bei eigener Not).
    att = 1 + 40 / max(state.enemy.hero.hp, 10)
    dfn = 1 + 40 / max(state.me.hero.hp, 10)
    det["ht_lost"], det["ht_killed"] = Counter(), Counter()
    for k in range(horizon):
        d = w.discount ** k
        hp_before = s.me.hero.hp
        pieces_before = sum(_material(s.me))
        ht_me, ht_en = _ht_count(s.me), _ht_count(s.enemy)
        r_en = start_turn(s, "enemy")
        taken = hp_before - s.me.hero.hp
        lost = max(0, pieces_before - sum(_material(s.me))) if r_en.launched else 0
        det["taken"].append(taken)
        if s.me.hero.hp <= 0:
            if k == 0:
                return -WIN, det
            score -= w.loss_value * w.end_decay ** (k - 1)
            det["end"] = ("loss", k)
            break
        ht = _ht_settle(s, ht_me, ht_en, Counter(), _launched_ht(r_en), w, det)
        ht_me, ht_en = _ht_count(s.me), _ht_count(s.enemy)
        r_me = start_turn(s, "me")
        det["dealt"].append(r_me.hero_damage)
        ht += _ht_settle(s, ht_me, ht_en, _launched_ht(r_me), Counter(), w, det)
        score += d * (w.hero_damage * att * r_me.hero_damage + w.destroyed * r_me.destroyed
                      - w.damage_taken * dfn * taken - w.lost * lost + ht)
        if s.enemy.hero.hp <= 0:
            score += w.win_value * w.end_decay ** k
            det["end"] = ("win", k)
            break
    # Noch ladende eigene Formationen: ihr Angriff liegt hinter dem Horizont, zaehlt aber
    # (sonst sind Champions mit CT 5-6 wertlos und werden fuer Core-Angriffe geopfert).
    for p in s.me.pieces:
        if p.kind == "form":
            at_launch = max(0, p.max_power - p.deficit)
            score += w.pending_attack * w.discount ** (horizon - 1 + max(p.ct, 1)) * at_launch
    score += w.walls * sum(p.hp for p in s.me.pieces if p.kind == "wall")
    return score, det


# Material idle Einheiten (vor Gewicht w.lost = 0.35), etwa ihre Toughness. Der eigentliche Wert
# von Elite/Champions (begrenztes Kontingent) steckt in _ht_settle.
IDLE_VALUE = {"core": 2, "elite": 6, "champion": 20}


def _ht_count(side) -> Counter:
    """Elite/Champions auf dem Feld (idle, ladend oder als unbewegliche Blocker erkannt)."""
    c = Counter()
    for p in side.pieces:
        if p.kind in ("unit", "form") and p.unit and p.tier in ("elite", "champion"):
            c[p.tier] += 1
        elif p.kind == "block" and p.h == 2 and not p.merged:
            c["champion" if p.w == 2 else "elite"] += 1
    return c


def _launched_ht(rep) -> Counter:
    c = Counter()
    for unit, *_ in rep.launched:
        t = tier(unit)
        if t != "core":
            c[t] += 1
    return c


def _ht_loss_value(side, losses: Counter, w: Weights) -> float:
    """Kosten der gestorbenen Elite/Champions einer Seite; zieht sie vom Kontingent ab."""
    total = 0.0
    for t in ("elite", "champion"):
        for _ in range(losses.get(t, 0)):
            known = side.stock is not None and side.stock.get(t, 0) > 0
            left = side.stock[t] - 1 if known else w.ht_unknown_left
            if known:
                side.stock[t] = left
            base = w.ht_champion if t == "champion" else w.ht_elite
            total += base * (1 + w.ht_scarcity / max(left, 1))
            if left <= 0:
                total += w.ht_last_champion if t == "champion" else w.ht_last_elite
    return total


def _ht_settle(s: State, me_before: Counter, en_before: Counter, me_launched: Counter,
               en_launched: Counter, w: Weights, det: dict) -> float:
    """Verluste seit me_before/en_before: verschwundene Elite/Champions minus die, die angegriffen haben."""
    me_after, en_after = _ht_count(s.me), _ht_count(s.enemy)
    lost = Counter({t: max(0, me_before[t] - me_after[t] - me_launched[t]) for t in ("elite", "champion")})
    killed = Counter({t: max(0, en_before[t] - en_after[t] - en_launched[t]) for t in ("elite", "champion")})
    det["ht_lost"].update(lost)
    det["ht_killed"].update(killed)
    return w.ht_enemy * _ht_loss_value(s.enemy, killed, w) - _ht_loss_value(s.me, lost, w)


def _material(side):
    for p in side.pieces:
        if p.kind == "form":
            yield p.power
        elif p.kind == "wall":
            yield p.hp
        elif p.kind == "unit":
            yield IDLE_VALUE[p.tier]
        elif p.kind == "block" and p.h == 2 and not p.merged:  # erkannte, aber unbewegliche Elite/Champion
            yield IDLE_VALUE["champion" if p.w == 2 else "elite"]


def _actions(state: State) -> list[tuple]:
    acts = legal_moves(state)
    if state.me.hero.spell_ready():
        acts.append(("spell", 0, 0))  # kostenlos
    # Loeschen mit Chain (netto kostenlos) immer; reines Loeschen ohne Chain nur als letzte Aktion
    # des Zuges (Vorbereitung fuer den naechsten Zug, z. B. Einheiten nach hinten holen) --
    # sonst explodiert die Suche.
    # Ausserdem jederzeit: Loeschen, das einen idle Champion/Elite der Aktivierung naeher bringt
    # (davor loeschen, damit er nach vorn rutscht, oder Fremde dahinter entfernen).
    last = state.moves_left == 1
    before = None
    for a in legal_deletes(state):
        s2, extra = apply_action(state, a)
        if extra > 0 or last:
            acts.append(a)
            continue
        if before is None:
            before = _ht_costs(state)
            if not before:
                before = ()
        if before and _closer(before, _ht_costs(s2)):
            acts.append(a)
    return acts


def _closer(before: tuple, after: tuple) -> bool:
    """Mindestens ein High-Tier naeher an der Aktivierung, keiner weiter weg."""
    if len(before) != len(after):
        return False
    big = 99
    b = [big if x is None else x for x in before]
    a = [big if x is None else x for x in after]
    return any(y < x for x, y in zip(b, a)) and all(y <= x for x, y in zip(b, a))


def _plain_delete(plan: "Plan") -> bool:
    return bool(plan.actions) and plan.actions[-1][0] == "delete" and plan.state.moves_left == 0


def _next_turn(state: State, w: Weights) -> tuple[State | None, float]:
    """Eine Runde weiter (Gegner-Start, eigener Start) bis zum Beginn meines naechsten Zuges.
    Rueckgabe: Zustand (None bei Spielende) und der Wert dieser Runde wie in evaluate()."""
    s = state.copy()
    s.me.hero.mp = end_turn_mp(s)
    att = 1 + 40 / max(state.enemy.hero.hp, 10)
    dfn = 1 + 40 / max(state.me.hero.hp, 10)
    det = {"ht_lost": Counter(), "ht_killed": Counter()}
    hp_before = s.me.hero.hp
    pieces_before = sum(_material(s.me))
    ht_me, ht_en = _ht_count(s.me), _ht_count(s.enemy)
    r_en = start_turn(s, "enemy")
    taken = hp_before - s.me.hero.hp
    lost = max(0, pieces_before - sum(_material(s.me))) if r_en.launched else 0
    if s.me.hero.hp <= 0:
        return None, -WIN
    # (Ein Sieg in dieser Runde wird unten wie in evaluate() als weicher Bonus gezaehlt.)
    ht = _ht_settle(s, ht_me, ht_en, Counter(), _launched_ht(r_en), w, det)
    ht_me, ht_en = _ht_count(s.me), _ht_count(s.enemy)
    r_me = start_turn(s, "me")
    ht += _ht_settle(s, ht_me, ht_en, _launched_ht(r_me), Counter(), w, det)
    value = (w.hero_damage * att * r_me.hero_damage + w.destroyed * r_me.destroyed
             - w.damage_taken * dfn * taken - w.lost * lost + ht)
    if s.enemy.hero.hp <= 0:
        return None, value + w.win_value
    s.moves_left = RULES["moves_per_turn"] + (1 if s.me.has("celerity_ring") else 0) + s.me.bonus_moves
    s.me.bonus_moves = s.enemy.bonus_moves = 0
    return s, value


# --------------------------------------------------------------------------- Parallele Vorausschau
#
# Die Kandidaten der Vorausschau sind voneinander unabhaengig und jeder fuer sich deterministisch.
# Sie koennen deshalb in einem Prozess-Pool laufen (Standardbibliothek). Ergebnis und Reihenfolge
# sind identisch zur seriellen Rechnung; bei jedem Problem mit dem Pool wird seriell weitergerechnet.
#
# Nur auf Anforderung (solve(..., parallel=True), so im Overlay): Unter Windows importieren die
# Hilfsprozesse das Startskript neu. Ein Skript ohne `if __name__ == "__main__":` wuerde dann in
# jedem Hilfsprozess erneut laufen. COH_WORKERS=1 schaltet das Parallelisieren auch dort ab.

# Verstaerkung im Folgezug der Vorausschau (Anzahl Wuerfe; 0 = aus)
LOOKAHEAD_REINFORCE = 0

_POOL = None
_POOL_FAILED = False


def _workers() -> int:
    try:
        return max(1, int(os.environ.get("COH_WORKERS", "0")) or min(8, os.cpu_count() or 1))
    except ValueError:
        return 1


def _pool():
    """Einmal gestartet, bleibt der Pool fuer weitere Analysen bestehen (Startkosten nur einmal)."""
    global _POOL, _POOL_FAILED
    if _POOL is None and not _POOL_FAILED and _workers() > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            _POOL = ProcessPoolExecutor(max_workers=_workers())
        except (OSError, ImportError, NotImplementedError):
            _POOL_FAILED = True
    return _POOL


def _lookahead_all(pick: list["Plan"], w: Weights, horizon: int, budget: int,
                   parallel: bool = False) -> list["Plan"]:
    global _POOL, _POOL_FAILED
    pool = _pool() if parallel and len(pick) > 1 else None
    if pool is not None:
        n = len(pick)
        try:
            return list(pool.map(_lookahead, pick, [w] * n, [horizon] * n, [budget] * n))
        except Exception:  # z. B. BrokenProcessPool -> ab jetzt seriell
            _POOL_FAILED, _POOL = True, None
    return [_lookahead(c, w, horizon, budget) for c in pick]


def _lookahead(plan: "Plan", w: Weights, horizon: int, budget: int) -> "Plan":
    """Bewertet einen Plan inklusive des besten eigenen Folgezuges (ohne Gegnerzuege).
    So zaehlen Vorbereitungen, deren Nutzen erst im naechsten Zug kommt (Champion aktivieren)."""
    states = plan.details.get("samples") or [plan.state]
    total, follow = 0.0, None
    for st in states:
        s2, value = _next_turn(st, w)
        if s2 is None:
            total += value
            continue
        sub = solve(s2, w, beam=20, max_depth=6, node_budget=budget, top=1,
                    horizon=max(2, horizon - 1), reinforce_samples=LOOKAHEAD_REINFORCE, lookahead=0)[0]
        total += value + w.discount * sub.score
        if follow is None:
            follow = (s2, sub.actions)
    total += plan.details.get("setup_correction", 0.0) * len(states)  # Erwartung statt nur 2 Wuerfe
    det = dict(plan.details)
    det["lookahead"] = True
    if follow:
        det["next_state"], det["next_actions"] = follow
    return Plan(plan.actions, total / len(states), plan.state, det)


def solve(state: State, w: Weights | None = None, beam: int = 80, max_depth: int = 8,
          node_budget: int = 3000, time_limit: float = 60.0, top: int = 3, horizon: int = 5,
          reinforce_samples: int = 4, lookahead: int = 8, lookahead_budget: int = 250,
          parallel: bool = False, complete: int = 6, complete_beam: int = 10, per_first: int = 2, extend_top: int = 3,
          reinforce_first: bool = True) -> list[Plan]:
    """Deterministisch: gleiche Eingabe -> gleiches Ergebnis. Begrenzt wird ueber die Anzahl
    bewerteter Stellungen (node_budget), nicht ueber die Zeit; time_limit ist nur Notbremse."""
    w = w or Weights()
    t0 = time.time()
    start = state.copy()
    settle(start.me)  # falls das eingegebene Brett noch nicht aufgeloest ist
    frontier = [Plan([], 0.0, start)]
    seen = {start.key()}
    candidates: list[Plan] = []
    nodes = 0

    def finish(p: Plan) -> Plan:
        sc, det = evaluate(p.state, w, horizon)
        return Plan(p.actions, sc + static_bonus(p.state, w), p.state, det)

    root = finish(frontier[0])  # Ausgangsstellung (fuer 'zuerst Verstaerkung')
    candidates.append(root)
    for _ in range(max_depth):
        children = []
        for plan in frontier:
            if plan.state.moves_left <= 0:
                continue
            for a in _actions(plan.state):
                s2, _ = apply_action(plan.state, a)
                k = s2.key()
                if k in seen:
                    continue
                seen.add(k)
                children.append(finish(Plan(plan.actions + [a], 0.0, s2)))
                nodes += 1
            if nodes >= node_budget or time.time() - t0 > time_limit:
                break
        if not children:
            break
        children.sort(key=lambda p: p.score, reverse=True)
        candidates.extend(children[:beam])
        frontier = children[:beam]
        if nodes >= node_budget or time.time() - t0 > time_limit:
            break
    if nodes >= node_budget and complete > 0:
        # Budget aufgebraucht, bevor alle Zuege ausgespielt waren (bei ~50 Moeglichkeiten je Aktion
        # oft schon in der 2. Ebene): die besten unfertigen Plaene gierig zu Ende spielen, sonst
        # fehlt z. B. der dritte Zug, der den Champion aktiviert.
        # Kleine Strahlsuche statt rein gieriger Schritte: Zweierschritte (bewegen + bewegen ->
        # Formation) bringen im ersten Schritt nichts und wurden sonst nie gefunden; dann blieben
        # Zuege ungenutzt (Zuege -> MP), obwohl Chains noch viele Aktionen erlaubt haetten.
        # Vielfalt: hoechstens per_first Plaene je erstem Zug. Sonst setzen sich nur Varianten eines
        # einzigen Anfangs fort, und ein Anfang, der erst zwei Aktionen spaeter gross wird
        # (z. B. Loeschen vorne -> zwei Waende, dann Elite aktivieren), geht verloren.
        def diverse(plans, n):
            out, per = [], Counter()
            for p in sorted(plans, key=lambda p: p.score, reverse=True):
                f = p.actions[0] if p.actions else None
                if per[f] < per_first:
                    per[f] += 1
                    out.append(p)
                    if len(out) >= n:
                        break
            return out

        frontier = diverse((c for c in candidates if c.state.moves_left > 0), complete)
        for _ in range(max_depth * 2):  # Chains geben Zuege zurueck -> mehr Ebenen als max_depth
            children = []
            for plan in frontier:
                if plan.state.moves_left <= 0:
                    continue
                for a in _actions(plan.state):
                    s2, _ = apply_action(plan.state, a)
                    k = s2.key()
                    if k in seen:
                        continue
                    seen.add(k)
                    children.append(finish(Plan(plan.actions + [a], 0.0, s2)))
            if not children or time.time() - t0 > time_limit:
                break
            frontier = diverse(children, complete_beam)
            candidates.extend(frontier)
    candidates.extend(finish(Plan(acts, 0.0, s)) for acts, s in _rescue_sequences(start))
    candidates.sort(key=lambda p: p.score, reverse=True)
    if reinforce_samples > 0:
        candidates = _add_reinforce(candidates, w, horizon, reinforce_samples) + candidates
        # Zuerst Verstaerkung: Danach haelt der Spieler L1 neu und plant mit den neuen Einheiten
        # (auch Elite/Champions, mehr Loesch-Optionen). Deshalb Fortsetzung per kleiner Suche
        # statt nur gierig -- sonst waere diese Option systematisch unterbewertet.
        first = _reinforce_first(root, w, horizon, reinforce_samples) if reinforce_first else None
        if first is not None:
            candidates.append(first)
    candidates.sort(key=lambda p: p.score, reverse=True)
    if lookahead > 0:
        # Die besten Kandidaten plus die besten Plaene mit Vorbereitungs-Loeschung am Zugende
        # mit dem eigenen Folgezug neu bewerten; nur diese stehen danach oben.
        pick, keys = [], set()
        # (Verstaerkung und Vorbereitungs-Loeschung zahlen sich oft erst im Folgezug aus -> immer dabei)
        pool = (candidates[:lookahead] + [c for c in candidates if _plain_delete(c)][:lookahead // 2]
                + [c for c in candidates if c.actions and c.actions[-1][0] == "reinforce"][:2]
                + [c for c in candidates if c.actions == [("reinforce", 0, 0)]][:1]
                + _closest_activation(candidates[:400], 3)
                # Zauber aufheben vs. jetzt wirken: Ein Schild wirkt erst in der naechsten Gegnerrunde.
                # Ohne diese Plaene saehe die Vorausschau nur Varianten mit sofortigem Zauber.
                + ([c for c in candidates if not any(a[0] == "spell" for a in c.actions)][:3]
                   if start.me.hero.spell_ready() else []))
        for c in pool:
            k = (c.state.key(), tuple(c.actions[-1:]))
            if k not in keys:
                keys.add(k)
                pick.append(c)
        ahead = sorted(_lookahead_all(pick, w, horizon, lookahead_budget, parallel),
                       key=lambda p: p.score, reverse=True)
        # Restzuege nutzen: Endet ein guter Plan mit ungenutzten Zuegen, die Aktionen seines
        # geplanten Folgezugs schon jetzt anhaengen (soweit hier legal) und ebenfalls vorausschauen.
        # Die Folgerunde beginnt dann wieder mit vollen Zuegen.
        ext = []
        for c in ahead[:extend_top]:
            if c.state.moves_left <= 0 or not c.details.get("next_actions"):
                continue
            if c.actions and c.actions[-1][0] == "reinforce":
                continue  # c.state ist der Stand VOR dem Wurf -> Folgeaktionen passen nicht
            s, acts = c.state, list(c.actions)
            for a in c.details["next_actions"]:
                if s.moves_left <= 0 or a not in _actions(s):
                    break
                s, _ = apply_action(s, a)
                acts.append(a)
            if len(acts) > len(c.actions) and s.key() not in keys:
                keys.add(s.key())
                ext.append(finish(Plan(acts, 0.0, s)))
        if ext:
            ahead = sorted(ahead + _lookahead_all(ext, w, horizon, lookahead_budget, parallel),
                           key=lambda p: p.score, reverse=True)
            pick = pick + ext
        candidates = ahead + [c for c in candidates if c not in pick]
    # Top-N mit unterschiedlichem ersten Zug.
    out, firsts = [], set()
    for c in candidates:
        f = c.actions[0] if c.actions else None
        if f in firsts:
            continue
        firsts.add(f)
        out.append(c)
        if len(out) >= top:
            break
    return out


def _closest_activation(cands: list[Plan], k: int) -> list[Plan]:
    """Plaene, nach denen ein idle Champion/Elite am wenigsten Aktionen bis zur Aktivierung braucht.
    Ihr Nutzen kommt erst im Folgezug und waere in der Einzelzug-Bewertung leicht zu weit unten."""
    scored = []
    for i, c in enumerate(cands):
        # nur, was im naechsten Zug (3 Aktionen) aktivierbar ist -- sonst hilft der Folgezug nicht
        costs = [x for x in _ht_costs(c.state) if x is not None and x <= RULES["moves_per_turn"]]
        if costs and c.actions:
            scored.append((min(costs), -c.score, i, c))
    scored.sort(key=lambda t: t[:3])
    return [t[3] for t in scored[:k]]


def _dies_next_enemy_turn(state: State, piece_key: tuple) -> bool:
    s = state.copy()
    start_turn(s, "enemy")
    return not any((p.kind, p.unit, p.color) == piece_key[:3] and p.uid == piece_key[3] for p in s.me.pieces)


def _rescue_sequences(state: State):
    """Gezielte Rettung bedrohter Elite/Champions (die Beam-Suche verwirft vorbereitende Zuege,
    deren Nutzen erst im letzten Zug sichtbar wird): Fuer jeden Zielplatz die noetigen
    Raeumzuege (Einheiten dahinter bzw. am Zielplatz) bestimmen, auf die beste Ablagespalte
    verschieben und zum Schluss die bedrohte Einheit umsetzen."""
    from .model import COLS, ROWS
    from .rules import backmost
    out = []
    for u in [p for p in state.me.pieces if p.kind == "unit" and p.tier != "core"]:
        key = (u.kind, u.unit, u.color, u.uid)
        if not _dies_next_enemy_turn(state, key):
            continue
        for dst in range(COLS - u.w + 1):
            if dst == u.col:
                continue
            s, acts, ok = state, [], True
            for _ in range(state.moves_left):
                cur = next(p for p in s.me.pieces if p.uid == u.uid)
                fill = s.me.fill(exclude=cur)
                row = max(fill[c] for c in range(dst, dst + cur.w))
                bm = backmost(s.me, cur.col)
                if bm is cur and row + cur.h <= ROWS and s.moves_left >= 1:
                    s2, _ = apply_action(s, ("move", cur.col, dst))
                    out.append((acts + [("move", cur.col, dst)], s2))
                    break
                # Raeumen: erst Einheiten hinter der bedrohten, sonst die hinterste am Zielplatz
                blockers = [c for c in cur.cols() if backmost(s.me, c) is not cur]
                cols = blockers or [c for c in range(dst, dst + cur.w) if fill[c] + cur.h > ROWS]
                src = next((c for c in cols if backmost(s.me, c) is not None), None)
                if src is None or s.moves_left <= 1:
                    ok = False
                    break
                p = backmost(s.me, src)
                avoid = set(cur.cols()) | set(range(dst, dst + cur.w))
                dumps = [a for a in legal_moves(s) if a[1] == p.col and not (set(range(a[2], a[2] + p.w)) & avoid)]
                if not dumps:
                    ok = False
                    break
                a = max(dumps, key=lambda a: evaluate(apply_action(s, a)[0], Weights(), 1)[0])
                s, _ = apply_action(s, a)
                acts.append(a)
            if not ok:
                continue
    return out


SETUP_SAMPLES = 32  # Wuerfe fuer den Erwartungswert "was faellt hinter Elite/Champions"


def _add_reinforce(cands: list[Plan], w: Weights, horizon: int, samples: int, k: int = 4) -> list[Plan]:
    """Verstaerkung als letzte Aktion eines Plans: Wert = Mittel ueber feste Zufalls-Seeds
    (deterministisch), jeweils mit gieriger Fortsetzung fuer die restlichen Zuege.

    Was hinter idle Elite/Champions faellt (passende Farbe = Vorbereitung, fremde = verschuettet),
    streut stark. Die teure Simulation laeuft nur ueber `samples` Wuerfe; dieser Teil wird
    zusaetzlich ueber SETUP_SAMPLES Wuerfe gemittelt und als Korrektur eingerechnet."""
    out = []
    done = set()
    for plan in cands:
        if len(out) >= k:
            break
        st = plan.state
        if st.moves_left < 1 or st.me.reserve <= 0 or st.key() in done:
            continue
        done.add(st.key())
        total, sample_states = 0.0, []
        for seed in range(samples):
            s, _ = apply_action(st, ("reinforce", 0, seed))
            for _ in range(s.moves_left):  # gierig weiter
                best = None
                for a in _actions(s):
                    s2, _ = apply_action(s, a)
                    sc = evaluate(s2, w, 2)[0]
                    if best is None or sc > best[0]:
                        best = (sc, s2)
                if best is None:
                    break
                s = best[1]
            sc, _ = evaluate(s, w, horizon)
            total += sc + static_bonus(s, w)
            sample_states.append(s)
        setups = [_high_tier_setup(apply_action(st, ("reinforce", 0, seed))[0], w)
                  for seed in range(max(samples, SETUP_SAMPLES))]
        correction = sum(setups) / len(setups) - sum(setups[:samples]) / samples
        out.append(Plan(plan.actions + [("reinforce", 0, 0)], total / samples + correction, st,
                        {"samples": sample_states[:2], "setup_expect": sum(setups) / len(setups),
                         "setup_correction": sum(setups) / len(setups) - sum(setups[:2]) / 2,
                         "setup_before": _high_tier_setup(st, w)}))
    return out


def _reinforce_first(root: Plan, w: Weights, horizon: int, samples: int) -> Plan | None:
    """Verstaerkung als ERSTE Aktion: Mittel ueber feste Wuerfe, danach jeweils der beste Rest-Zug
    aus einer kleinen Suche (wie der Spieler, der nach dem Nachrufen L1 neu haelt)."""
    st = root.state
    if st.moves_left < 1 or st.me.reserve <= 0 or samples <= 0:
        return None
    total, states = 0.0, []
    for seed in range(samples):
        s, _ = apply_action(st, ("reinforce", 0, seed))
        if s.moves_left > 0:
            sub = solve(s, w, beam=10, max_depth=4, node_budget=150, top=1, horizon=horizon,
                        reinforce_samples=0, lookahead=0, complete=2, complete_beam=4, extend_top=0,
                        reinforce_first=False)[0]
            total += sub.score
            states.append(sub.state)
        else:
            sc, _ = evaluate(s, w, horizon)
            total += sc + static_bonus(s, w)
            states.append(s)
    return Plan([("reinforce", 0, 0)], total / samples, st, {"samples": states[:2], "reinforce_first": True})


def describe(action: tuple, state: State) -> str:
    kind, col, arg = action
    if kind == "reinforce":
        return f"Verstaerkung rufen ({state.me.reserve} in Reserve)"
    if kind == "spell":
        return f"Heldenzauber ({state.me.hero.spell})"
    g = state.me.grid()
    if kind == "move":
        from .rules import backmost
        p = backmost(state.me, col)
        name = f"{p.unit} ({p.color})" if p else "?"
        return f"Bewege {name}: Spalte {col + 1} -> Spalte {arg + 1}"
    p = g.get((col, arg))
    what = "Wand" if p and p.kind == "wall" else (f"{p.unit} ({p.color})" if p else "?")
    return f"Loesche {what}: Spalte {col + 1}, Reihe {arg + 1}"


def explain(start: State, plan: Plan, w: Weights | None = None, horizon: int = 5) -> str:
    """Kurze Begruendung fuer das Overlay: Wirkung des Plans gegenueber 'sofort Zug beenden'
    (simuliert ueber `horizon` Runden, ohne Gegnerzuege)."""
    w = w or Weights()
    if plan.actions and plan.actions[0][0] == "reinforce":
        return "Warum: zuerst nachrufen bringt im Mittel mehr (neue Einheiten, evtl. Elite/Champion, mehr Loesch-Optionen)"
    s = start
    for a in plan.actions:
        if a[0] == "reinforce":
            break
        s, _ = apply_action(s, a)
    base, after = evaluate(start, w, horizon)[1], evaluate(s, w, horizon)[1]
    items = []
    for t, name in (("elite", "Elite"), ("champion", "Champion")):
        n = (sum(p.kind == "form" and p.unit and p.tier == t for p in s.me.pieces)
             - sum(p.kind == "form" and p.unit and p.tier == t for p in start.me.pieces))
        if n > 0:
            items.append(f"{n} {name} aktiviert" if n > 1 else f"{name} aktiviert")
    old_ids = {p.uid for p in start.me.pieces if p.kind == "form"}
    new = [p for p in s.me.pieces if p.kind == "form" and p.tier == "core" and p.uid not in old_ids]
    if len(new) == 1:
        items.append(f"Angriff Sp. {new[0].col + 1} (in {new[0].ct})")
    elif new:
        items.append(f"{len(new)} Angriffe (Sp. {'/'.join(str(p.col + 1) for p in new)})")
    dealt = sum(after["dealt"]) - sum(base["dealt"])
    taken = sum(after["taken"]) - sum(base["taken"])
    if dealt:
        items.append(f"Schaden am Gegner {dealt:+d}")
    if taken:
        items.append(f"Schaden an dir {taken:+d}")
    if plan.actions and plan.actions[-1][0] == "reinforce":
        items.append("dann nachrufen")
    if not items:
        return "Warum: Vorbereitung fuer den naechsten Zug (siehe Vorschau)"
    return f"Warum: {', '.join(items)}"
