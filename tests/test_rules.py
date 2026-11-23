from coh.model import Hero, Piece, Side, State, make_formation, parse_state
from coh.rules import apply_action, legal_moves, link_bonus, settle, start_turn

EMPTY = ". . . . . . . ."


def board(me_rows, en_rows=None, me_extra="", en_extra=""):
    en_rows = en_rows or [EMPTY] * 6
    me_rows = me_rows + [EMPTY] * (6 - len(me_rows))
    return parse_state(
        f"[me]\nfaction = haven\nlevel = 10\n{me_extra}\n[enemy]\nfaction = necropolis\nlevel = 10\n{en_extra}\n"
        "[board]\n" + "\n".join(en_rows) + "\n----\n" + "\n".join(me_rows))


def forms(side):
    return [p for p in side.pieces if p.kind == "form"]


def test_vertical_core_formation_on_move():
    s = board(["swb arg . . . . . .", "swb . . . . . . .", ". . . . . . . .", ". swb . . . . . ."])
    # Spalte 2 hat arg + swb (hinten). swb nach Spalte 1 -> 3 Swordsman blau senkrecht.
    s2, extra = apply_action(s, ("move", 1, 0))
    f = forms(s2.me)
    assert len(f) == 1 and f[0].unit == "swordsman" and f[0].col == 0 and f[0].row == 0
    assert f[0].max_power == 11 and f[0].power == 6 and f[0].ct == 3
    assert extra == 0 and s2.moves_left == 2


def test_wall_and_chain_delete():
    # Reihe 1: drei gruene nebeneinander, getrennt durch einen weissen Archer in Spalte 3.
    s = board(["arg swg arw spg arg . . .", ". . swg . . . . ."])
    s2, extra = apply_action(s, ("delete", 2, 0))
    walls = [p for p in s2.me.pieces if p.kind == "wall"]
    assert len(walls) >= 3
    assert extra >= 1 and s2.moves_left == s.moves_left - 1 + extra


def test_walls_move_to_front_and_formation_behind():
    s = board(["swb spb arw arg . . . .", "arg arg . . . . . ."])
    # arg aus Spalte 4 hinter arw in Spalte 3 -> Reihe 2: arg arg arg -> Wand, die nach vorn rueckt.
    s2, _ = apply_action(s, ("move", 3, 2))
    walls = sorted((p.col, p.row) for p in s2.me.pieces if p.kind == "wall")
    assert walls == [(0, 0), (1, 0), (2, 0)]
    assert any(p.unit == "archer" and p.color == "w" and (p.col, p.row) == (2, 1) for p in s2.me.pieces)


def test_elite_formation_needs_two_same_color_cores_behind():
    s = board(["knb . . . . . . .", "knb . . . . . . .", "swb . . . . . . .", ". arb . . . . . ."])
    s2, _ = apply_action(s, ("move", 1, 0))
    f = forms(s2.me)
    assert len(f) == 1 and f[0].unit == "knight" and f[0].h == 2


def test_fusion_doubles_power():
    s = board(["F:swb:3:6 . . . . . . .", "F:swb:3:6 . . . . . . .", "F:swb:3:6 . . . . . . .",
               "swb swb . . . . . .", ". swb . . . . . ."])
    # Spalte 1 hat noch ein swb in Reihe 4; zwei weitere aus Spalte 2 -> zweite Formation dahinter -> Fusion.
    s2, _ = apply_action(s, ("move", 1, 0))
    s3, _ = apply_action(s2, ("move", 1, 0))
    f = forms(s3.me)
    assert len(f) == 1 and f[0].fused == 2 and f[0].max_power == 22


def test_attack_through_blockers():
    en = [EMPTY] * 3 + ["zob . . . . . . .", "zob . . . . . . .", "W6 . . . . . . ."]
    s = board(["F:swb:1:11 . . . . . . .", "F:swb:1:11 . . . . . . .", "F:swb:1:11 . . . . . . ."], en)
    s.enemy.hero.hp = 100
    rep = start_turn(s, "me")
    # 11 - Wand 6 - Zombie 2 - Zombie 2 = 1
    assert rep.hero_damage == 1 and s.enemy.hero.hp == 99


def test_link_bonus_formula():
    side = Side(Hero())
    a = Piece("form", 0, 0, unit="swordsman", color="b")
    b = Piece("form", 1, 0, unit="archer", color="b")
    c = Piece("form", 2, 0, w=2, unit="angel", color="b")
    lb = link_bonus([a, b, c], side)
    assert abs(lb[id(a)] - 0.65) < 1e-9 and abs(lb[id(c)] - 0.30) < 1e-9


def test_legal_moves_only_backmost_idle():
    s = board(["F:swb:2:7 arg . . . . . .", "F:swb:2:7 . . . . . . .", "F:swb:2:7 . . . . . . ."])
    srcs = {m[1] for m in legal_moves(s)}
    assert srcs == {1}


def test_combo_move_creates_formation_and_wall_gives_extra_move():
    # Spalte 1: swb swb; Reihe 3 hat in Spalte 2+3 zwei blaue -> swb nach Spalte 1 Reihe 3
    # ergibt gleichzeitig Formation (senkrecht) und Wand (waagerecht) -> 1 Zug zurueck.
    s = board(["swb arg arw swb . . . .", "swb arw arg . . . . .", ". spb spb . . . . ."])
    s2, extra = apply_action(s, ("move", 3, 0))
    kinds = sorted(p.kind for p in s2.me.pieces if p.kind in ("form", "wall"))
    assert "form" in kinds and "wall" in kinds
    assert extra == 1 and s2.moves_left == s.moves_left


# --------------------------------------------------------------------------- Elite/Champions

def test_high_tier_units_are_never_deleted():
    from coh.rules import legal_deletes
    s = board(["anb anb swg swg swg . . .", "anb anb . . . . . .", "swb swb . . . . . ."])
    targets = {(c, r) for _, c, r in legal_deletes(s)}
    assert (0, 0) not in targets and (1, 0) not in targets
    assert (0, 2) in targets  # Core darf weiterhin geloescht werden


def test_setup_bonus_counts_matching_cores_behind_champion():
    from coh.solver import Weights, _high_tier_setup
    w = Weights()
    none = board(["anb anb . . . . . .", "anb anb . . . . . ."])
    half = board(["anb anb . . . . . .", "anb anb . . . . . .", "swb swb . . . . . ."])
    wrong = board(["anb anb . . . . . .", "anb anb . . . . . .", "swg swg . . . . . ."])
    assert _high_tier_setup(none, w) == 0
    assert _high_tier_setup(wrong, w) == -2 * w.bury_champion  # fremde Farbe verschuettet
    assert _high_tier_setup(half, w) == w.setup_champion / 2


def test_solver_activates_champion_instead_of_sacrificing_it():
    from coh.solver import solve
    # Angel blau vorn, 3 blaue Swordsman dahinter, der vierte steht in Spalte 4.
    s = board(["anb anb . . . . . .", "anb anb . . . . . .", "swb swb . swb . . . .", "swb . . . . . . ."])
    best = solve(s, node_budget=400)[0]
    assert any(p.kind == "form" and p.tier == "champion" for p in best.state.me.pieces)
    assert not any(a[0] == "delete" and (a[1], a[2]) in {(0, 0), (1, 0), (0, 1), (1, 1)} for a in best.actions)


def test_losing_last_champion_costs_more_than_a_spare_one():
    from coh.solver import Weights, evaluate
    # Gegnerischer Ritter (Elite, CT 1, 30 PWR) trifft Spalte 1, dort steht mein idle Engel.
    en = [EMPTY] * 4 + ["F:knr:1:30 . . . . . . .", "F:knr:1:30 . . . . . . ."]
    s = board(["anb anb . . . . . .", "anb anb . . . . . ."], en)
    w = Weights()
    s.me.stock = {"elite": 0, "champion": 5}
    spare, det = evaluate(s, w, horizon=1)
    assert det["ht_lost"]["champion"] == 1
    s.me.stock = {"elite": 0, "champion": 1}
    last, _ = evaluate(s, w, horizon=1)
    assert last < spare - w.ht_last_champion


def test_attacking_with_elite_is_not_a_loss():
    from coh.solver import Weights, evaluate
    en = [EMPTY] * 4 + ["F:knr:1:30 . . . . . . .", "F:knr:1:30 . . . . . . ."]
    s = board([". . . swb . . . ."], en)  # Spalte 1 frei -> Ritter greift an und verschwindet
    _, det = evaluate(s, Weights(), horizon=1)
    assert sum(det["ht_killed"].values()) == 0 and sum(det["ht_lost"].values()) == 0


def test_lookahead_plans_champion_activation_over_two_turns():
    from coh.solver import solve
    # Angel blau vorn; die vier blauen Swordsman stehen einzeln -> 4 Zuege noetig, nur 3 pro Zug.
    s = board(["anb anb . swb arg swb arg .", "anb anb . . swb . swb ."])
    best = solve(s, node_budget=300, lookahead=4, lookahead_budget=200)[0]
    ns = best.details["next_state"]
    for a in best.details["next_actions"]:
        ns, _ = apply_action(ns, a)
    assert any(p.kind == "form" and p.tier == "champion" for p in ns.me.pieces)


def test_far_future_win_does_not_hide_other_terms():
    from coh.solver import Weights, evaluate
    # Eigene starke Formation trifft den Gegner (10 HP) erst in Runde 2: Sieg ist nur weich gewertet.
    s = board(["F:swb:2:11 . . . . . . .", "F:swb:2:11 . . . . . . .", "F:swb:2:11 . . . . . . ."],
              en_extra="hp = 10")
    sc, det = evaluate(s, Weights(), horizon=3)
    assert det.get("end", (None,))[0] == "win" and sc < 10_000


def test_win_next_turn_outweighs_losing_champions_and_elite():
    from coh.solver import Weights, evaluate
    # Gegner hat 1 HP. Mein Swordsman-Angriff (CT 1) trifft eine leere Spalte -> Sieg im naechsten Zug.
    # Vorher greifen zwei gegnerische Ritter meine beiden idle Engel an (beide sterben, letzte im Kontingent).
    en = [EMPTY] * 4 + ["F:knr:1:30 . F:knr:1:30 . . . . .", "F:knr:1:30 . F:knr:1:30 . . . . ."]
    me_win = ["anb anb anw anw . F:swg:1:11 . .", "anb anb anw anw . F:swg:1:11 . .", ". . . . . F:swg:1:11 . ."]
    w = Weights()
    win = board(me_win, en, en_extra="hp = 1")
    win.me.stock = {"elite": 0, "champion": 2}
    safe = board([". . . . anb anb . .", ". . . . anb anb . ."], en, en_extra="hp = 1")
    safe.me.stock = {"elite": 0, "champion": 2}
    sw, dw = evaluate(win, w, horizon=3)
    ss, _ = evaluate(safe, w, horizon=3)
    assert dw["end"] == ("win", 0) and dw["ht_lost"]["champion"] == 2
    assert sw > ss


def test_burying_a_champion_costs():
    from coh.solver import Weights, _high_tier_setup
    w = Weights()
    free = board(["anb anb . . . . . .", "anb anb . . . . . ."])
    buried = board(["anb anb . . . . . .", "anb anb . . . . . .", "arg swg . . . . . .", "arg swg . . . . . ."])
    assert _high_tier_setup(buried, w) == _high_tier_setup(free, w) - 4 * w.bury_champion


def test_reinforce_expects_burial_behind_champion():
    from coh.solver import Plan, Weights, _add_reinforce
    # Viele Blaue und Gruene auf dem Feld -> in der Reserve ueberwiegt die dritte Farbe, die faellt
    # meist hinter den blauen Engel und verschuettet ihn.
    s = board(["anb anb swb arg swb arg swb arg", "anb anb arg swb arg swb arg swb"], me_extra="reserve = 9")
    p = _add_reinforce([Plan([], 0.0, s, {})], Weights(), horizon=2, samples=2)[0]
    assert p.details["setup_expect"] < p.details["setup_before"] == 0


# --------------------------------------------------------------------------- Verstaerkung mit Elite/Champions

def _filled(rows_filled, extra_rows=()):
    """Raster ohne Dreierreihen: Farbe wechselt diagonal (b, g, w)."""
    rows = [" ".join(f"sw{'bgw'[(r + c) % 3]}" for c in range(8)) for r in range(rows_filled)]
    return rows + list(extra_rows)


def _ht_drops(s, seeds=200):
    import random
    from coh.rules import apply_reinforce
    n = {"elite": 0, "champion": 0}
    for seed in range(seeds):
        s2 = apply_reinforce(s, random.Random(seed))
        new = [p for p in s2.me.pieces if p.kind == "unit" and p.tier != "core"
               and p.uid >= s.me.next_uid]
        for p in new:
            n[p.tier] += 1
            assert p.row + p.h <= 6  # passt ins Raster
    return n


def test_no_high_tier_drop_without_room():
    s = board(_filled(5), me_extra="reserve = 8")  # nur noch 1 freie Reihe: weder 1x2 noch 2x2 passt
    s.me.stock = {"elite": 10, "champion": 5}
    assert _ht_drops(s) == {"elite": 0, "champion": 0}


def test_no_champion_without_free_two_by_two():
    # Spalten abwechselnd 4 und 5 belegt: Elites passen (2 frei), Champions nie (Nachbar hat nur 1 frei)
    rows = _filled(4) + [" ".join("swb" if c % 2 else "." for c in range(8))]
    s = board(rows, me_extra="reserve = 8")
    s.me.stock = {"elite": 10, "champion": 5}
    n = _ht_drops(s)
    assert n["champion"] == 0 and n["elite"] > 0


def test_high_tier_drops_respect_stock_cap_and_space():
    empty = board([". . . . . . . ."], me_extra="reserve = 8")
    empty.me.stock = {"elite": 10, "champion": 5}
    half = board(_filled(3), me_extra="reserve = 8")
    half.me.stock = {"elite": 10, "champion": 5}
    none = board([". . . . . . . ."], me_extra="reserve = 8")
    none.me.stock = {"elite": 0, "champion": 0}
    capped = board(["anb anb anw anw . . . .", "anb anb anw anw . . . ."], me_extra="reserve = 8")
    capped.me.stock = {"elite": 10, "champion": 5}
    n_empty, n_half = _ht_drops(empty), _ht_drops(half)
    assert sum(n_empty.values()) > sum(n_half.values()) > 0  # mehr Platz -> mehr High-Tier
    assert _ht_drops(none) == {"elite": 0, "champion": 0}  # Kontingent leer
    assert _ht_drops(capped) == {"elite": 0, "champion": 0}  # 2 Champions = Cap voll


def test_uncertainties_name_blocks_unknown_champion_and_enemy_links():
    from coh.model import Piece
    from coh.uncertain import uncertainties
    en = [EMPTY] * 3 + ["F:knr:2:20 . F:knr:2:20 . . . . .", "F:knr:2:20 . F:knr:2:20 . . . . .", EMPTY]
    s = board(["anb anb . . . . . .", "anb anb . . . . . ."], en)
    s.me.pieces.append(Piece("block", 4, 0, hp=3))
    for p in s.me.pieces:
        if p.kind == "unit" and p.tier == "champion":
            p.color = "~05"
    u = " | ".join(uncertainties(s))
    assert "Spalte 5 nicht erkannt" in u and "Farbe Champion Spalte 1" in u and "Spalte 1, 3 greifen zusammen" in u


# --------------------------------------------------------------------------- Champion-Vorbereitung

# Angel blau steht zu weit hinten; Unterstuetzer gemischt (Spearman/Swordsman), damit keine
# Core-Formation aus Versehen entsteht.
CHAMP_BACK = ["arg arg . swb . spb . .", "spg arw . . . . . .", "arw spg . . . . . .",
              "anb anb . . . . . .", "anb anb . . . . . .", "swb spb . . . . . ."]


def test_activation_cost_counts_front_deletes_and_supply():
    from coh.solver import activation_cost
    s = board(CHAMP_BACK)
    angel = next(p for p in s.me.pieces if p.unit == "angel")
    # je Spalte 1 Loeschung davor (Champion steht zu weit hinten) + 2 blaue aus Spalte 4/5 holen
    assert activation_cost(s.me, angel) == 4
    s2, _ = apply_action(s, ("delete", 0, 1))
    s2, _ = apply_action(s2, ("delete", 1, 1))
    assert activation_cost(s2.me, next(p for p in s2.me.pieces if p.unit == "angel")) == 2


def test_solver_deletes_in_front_of_champion_and_activates_next_turn():
    from coh.solver import solve
    s = board(CHAMP_BACK)
    best = solve(s, node_budget=600, lookahead=4, lookahead_budget=200)[0]
    ns = best.details["next_state"]
    for a in best.details["next_actions"]:
        ns, _ = apply_action(ns, a)
    champ_active = lambda st: any(p.kind == "form" and p.tier == "champion" for p in st.me.pieces)  # noqa: E731
    assert champ_active(best.state) or champ_active(ns)
    # Vorbereitung durch mehrere reine Loeschungen muss moeglich sein
    assert sum(1 for a in best.actions if a[0] == "delete") >= 1


def test_mp_from_combo_and_linked_attack():
    s = board(["swb arg arw swb . . . .", "swb arw arg . . . . .", ". spb spb . . . . ."])
    s2, extra = apply_action(s, ("move", 3, 0))
    assert extra == 1 and s2.me.hero.mp > s.me.hero.mp
    linked = board(["F:swb:1:11 F:arb:1:8 . . . . . .", "F:swb:1:11 F:arb:1:8 . . . . . .",
                    "F:swb:1:11 F:arb:1:8 . . . . . ."])
    single = board(["F:swb:1:11 F:arg:1:8 . . . . . .", "F:swb:1:11 F:arg:1:8 . . . . . .",
                    "F:swb:1:11 F:arg:1:8 . . . . . ."])
    for st in (linked, single):
        st.enemy.hero.hp = 200
        st.me.hero.mp = 0
    start_turn(linked, "me")
    start_turn(single, "me")
    assert linked.me.hero.mp > single.me.hero.mp  # Link: mehr Schaden und Extra-Magie


# --------------------------------------------------------------------------- Heldenzauber

def test_holy_shield_absorbs_then_fires_back_double():
    from coh.rules import cast_spell
    en = [EMPTY] * 3 + ["F:swg:1:11 . . . . . . ."] * 3
    s = board([EMPTY], en)
    s.me.hero.spell, s.me.hero.mp = "holy_shield", 100
    s2, extra = apply_action(s, ("spell", 0, 0))
    assert extra == 0 and s2.moves_left == s.moves_left and s2.me.hero.mp == 0
    assert s2.me.hero.shield == 50
    start_turn(s2, "enemy")  # 11 Schaden gehen in den Schild, nicht auf die HP
    assert s2.me.hero.hp == 100 and s2.me.hero.shield == 39
    s2.enemy.hero.hp = 200
    start_turn(s2, "me")  # Rest 39 x 2 = 78, auf leere Spalten verteilt -> voll auf den Helden
    assert s2.enemy.hero.hp == 200 - 78 and s2.me.hero.shield == -1


def test_solver_casts_holy_shield_against_lethal_attack():
    from coh.solver import solve
    en = [EMPTY] * 3 + ["F:swg:1:11 F:swr:1:11 F:swb:1:11 . . . . ."] * 3
    s = board(["arg . . . . . . ."], en)
    s.me.hero.hp, s.me.hero.spell, s.me.hero.mp = 30, "holy_shield", 100
    best = solve(s, node_budget=200, lookahead=0)[0]
    assert ("spell", 0, 0) in best.actions  # 33 Schaden waeren toedlich, der Schild faengt 50


def test_ending_turn_with_unused_moves_gives_mp():
    from coh.rules import end_turn_mp
    s = board([EMPTY])
    s.me.hero.mp, s.moves_left = 10, 2
    assert end_turn_mp(s) == 16  # 2 ungenutzte Zuege x 3 %
    s.me.hero.mp = 98
    assert end_turn_mp(s) == 100  # Ueberlauf verfaellt


# --------------------------------------------------------------------------- Im Spiel nachgeprueft

def test_delete_two_walls_at_once_matches_game_2026_11_23():
    """Analyse 20261123_111246 -> S8/R1 geloescht -> 20261123_121043 (Spielbild).
    Zwei Waende gleichzeitig (weiss Reihe 3, gold Reihe 4), Elite NICHT aktiviert, Waende 14,
    Zuege 2 -> 3, Reserve 0 -> 4."""
    s = board(["swa swa arc spb swa spb arc spb",
               "arc arc swa spb swa arc swa knb",
               ". swa arc swa arc swa swa knb",
               ". swa . swa . spb spb swa",
               ". . . arc . spb knc spb",
               ". . . . . . knc spb"])
    s.moves_left, s.me.reserve = 2, 0
    s2, extra = apply_action(s, ("delete", 7, 0))
    walls = sorted((p.col, p.row, p.hp) for p in s2.me.pieces if p.kind == "wall")
    assert walls == [(5, 0, 14), (6, 0, 14), (7, 0, 14)]
    assert extra == 2 and s2.moves_left == 3
    assert s2.me.reserve == 4
    g = s2.me.grid()
    assert g[(7, 1)].kind == "unit" and g[(7, 1)].tier == "elite"  # Reiter nicht aktiviert
    assert g[(7, 3)].unit == "spearman" and (7, 4) not in g


def test_missed_link_penalty_same_color_core_before_champion():
    """Nutzer (2026-11-23): Blaue Bogen-Formation (CT 2) vor blauem Champion (CT 5) verschenkt
    den spaeteren gebundenen Angriff -> Abzug; andere Farbe oder gleiche Restladezeit -> keiner."""
    from coh.solver import _missed_links
    champ = ["F:chb:5:60 F:chb:5:60 . . . . . .", "F:chb:5:60 F:chb:5:60 . . . . . ."]
    early = board(champ + ["F:arb:2:6 . . . . . . .", "F:arb:2:6 . . . . . . .", "F:arb:2:6 . . . . . . ."])
    other = board(champ + ["F:arw:2:6 . . . . . . .", "F:arw:2:6 . . . . . . .", "F:arw:2:6 . . . . . . ."])
    assert _missed_links(early) > 0
    assert _missed_links(other) == 0
