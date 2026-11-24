from pathlib import Path

import pytest

from coh.stock import EMPTY, Slot, StockTracker

ROOT = Path(__file__).resolve().parent.parent


def test_tracker_only_decreases_and_keeps_unreadable():
    t = StockTracker()
    t.update({"me": [Slot(5, 5, "champion"), Slot(10, 10, "elite")], "enemy": [None, None]})
    t.update({"me": [Slot(4, 5, "champion"), None], "enemy": [None, None]})  # Engel verloren, Ritter unlesbar
    assert t.tiers("me") == {"elite": 10, "champion": 4}
    t.update({"me": [Slot(5, 5, "champion"), None], "enemy": [None, None]})  # Steigen = Lesefehler
    assert t.tiers("me")["champion"] == 4
    assert t.tiers("enemy") is None


def test_tracker_confirms_zero_and_new_battle():
    t = StockTracker()
    t.update({"me": [None, None], "enemy": [Slot(10, 10, "elite"), None]})
    t.update({"me": [None, None], "enemy": [Slot(0, 4, "elite"), None]})  # typischer Lesefehler
    assert t.tiers("enemy")["elite"] == 10
    t.update({"me": [None, None], "enemy": [Slot(3, 3, "champion"), None]})  # neuer Kampf ...
    assert t.tiers("enemy") == {"elite": 10, "champion": 0}
    t.update({"me": [None, None], "enemy": [Slot(3, 3, "champion"), None]})  # ... bestaetigt
    assert t.tiers("enemy") == {"elite": 0, "champion": 3}
    t.update({"me": [None, None], "enemy": [EMPTY, None]})
    assert t.tiers("enemy") is None


def test_tracker_warns_on_last_unit():
    t = StockTracker()
    t.update({"me": [Slot(1, 5, "champion"), None], "enemy": [None, None]})
    assert any("nur noch 1" in w for w in t.warnings())


@pytest.mark.parametrize("stem, me, enemy", [
    ("20261113_104601", [(5, 5, "champion"), (10, 10, "elite")], [EMPTY, (10, 10, "elite")]),
    ("20261113_004339", [(4, 5, "champion"), (10, 10, "elite")], [EMPTY, (9, 10, "elite")]),
    # Klinge des Schwertmeister-Icons ragt in die Zeile "3/3"
    ("20261124_125533", [(3, 3, "champion"), (5, 5, "champion")],
     [(5, 5, "champion"), (5, 5, "champion")]),
])
def test_read_stock_on_screenshot(stem, me, enemy):
    f = ROOT / "dataset" / "analysis" / f"{stem}.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.stock import read_stock
    r = read_stock(np.asarray(Image.open(f).convert("RGB")))
    norm = lambda rs: [s if s == EMPTY or s is None else (s.cur, s.max, s.tier) for s in rs]  # noqa: E731
    assert norm(r["me"]) == me
    assert norm(r["enemy"]) == enemy


@pytest.mark.parametrize("stem, cursor_col", [("20261113_110415", 1), ("20261113_110113", None)])
def test_champion_preview_under_cursor_is_idle_two_by_two(stem, cursor_col):
    """Cursor auf einem idle Champion: Das Spiel zeigt einen halb gefuellten Vorschau-Balken.
    Der Balken muss 2 Spalten breit erkannt werden (Fuellstandsmarke), das Piece bleibt idle."""
    f = ROOT / "dataset" / "analysis" / f"{stem}.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import Geometry, analyze, find_bars
    img = np.asarray(Image.open(f).convert("RGB"))
    bars = [(b.c0, b.c1, b.srow) for b in find_bars(img, Geometry(img.shape[1], img.shape[0]), "me")]
    assert (1, 2, 5) in bars
    if cursor_col is not None:
        st, _ = analyze(img, moves=3, cursor_col=cursor_col)
        champ = [p for p in st.me.pieces if p.kind == "unit" and p.tier == "champion"]
        assert champ and set(champ[0].cols()) == {1, 2}
        assert not any(p.kind == "form" and p.w == 2 for p in st.me.pieces)


def test_gap_in_front_of_champion_is_empty_not_blocker():
    """Champion haengt an der volleren Nachbarspalte; davor bleibt eine echte Luecke, in die seine
    Fluegel ragen. Sie darf kein unbekannter Blocker werden (sonst 'kann nicht nach vorn')."""
    f = ROOT / "dataset" / "analysis" / "20261123_001403.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.solver import activation_cost
    from coh.vision import analyze
    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=4, cursor_col=1)
    assert (4, 2) not in st.me.grid()
    champ = next(p for p in st.me.pieces if p.kind == "unit" and p.tier == "champion")
    assert activation_cost(st.me, champ) == 3  # blau loeschen + 2 weisse dahinter


def test_two_digit_toughness_at_cell_edge_is_champion():
    """Schwertmeister: '27' reicht ueber den Zahlenausschnitt hinaus und wurde als '2' (Core) gelesen."""
    f = ROOT / "dataset" / "analysis" / "20261123_002734.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze
    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=5)
    champ = [p for p in st.me.pieces if p.kind == "unit" and p.tier == "champion"]
    assert champ and set(champ[0].cols()) == {5, 6} and champ[0].row == 4


def test_cursor_column_from_cyan_cell_when_emblem_lags():
    """Das Zug-Emblem gleitet dem Cursor hinterher (gelesen: Spalte 1, Cursor: leeres Feld in Spalte 6).
    Ohne Gegenprobe wurde das Cursorfeld zum ladenden Balken und der Champion zu Hindernissen."""
    f = ROOT / "dataset" / "analysis" / "20261124_125533.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze
    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=0)
    champ = [p for p in st.me.pieces if p.kind == "unit" and p.tier == "champion"]
    assert champ and set(champ[0].cols()) == {5, 6} and champ[0].row == 2
    assert not any(p.kind in ("block", "form") and 5 in p.cols() and p.row >= 2 for p in st.me.pieces)
    assert (5, 4) not in st.me.grid()


def test_two_similar_core_colors_stay_separate():
    """Bogenschuetzen Blau und Weiss (Abstand ~0.54) wurden zu einer Klasse verschmolzen ->
    erfundene Formationen. Soll-Belegung von Hand aus dem Bild (b=blau, g=gold, w=weiss)."""
    f = ROOT / "dataset" / "analysis" / "20261124_134539.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze
    soll = {"b": [(0, 0), (1, 0), (3, 0), (4, 0), (1, 1), (2, 2), (6, 2), (7, 2), (0, 3), (0, 4), (1, 4)],
            "g": [(2, 0), (6, 0), (0, 1), (2, 1), (7, 1), (4, 2), (1, 3), (4, 3), (2, 4)],
            "w": [(5, 0), (3, 1), (4, 1), (6, 1), (0, 2), (1, 2), (3, 2), (2, 3)]}
    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=2, cursor_col=7)
    color = {(p.col, p.row): p.color for p in st.me.pieces if p.kind == "unit" and p.unit == "core"}
    groups = {k: {color.get(c) for c in cells} for k, cells in soll.items()}
    assert all(len(g) == 1 for g in groups.values()), groups
    assert len({next(iter(g)) for g in groups.values()}) == 3
