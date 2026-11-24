from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_place_before_delete_gives_chain_move():
    """Nutzer (2026-11-24): Erst die passende Einheit hinter den Blocker stellen, dann den Blocker
    loeschen. Die Champion-Formation entsteht dann durch das Loeschen -> Chain, Extrazug und MP.
    Analyse 20261124_143157: goldener Greif Sp. 6-7, blaue Bogenschuetzen dahinter in Sp. 6."""
    f = ROOT / "dataset" / "analysis" / "20261124_143157.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.rules import apply_action
    from coh.solver import _reorder_variants, Plan
    from coh.vision import analyze

    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=7)
    g = st.me.grid()
    gold = g[(1, 3)].color  # goldener Speertraeger
    g[(5, 1)].color = gold  # Greif (Farbe kennt das Overlay aus frueheren Analysen)
    g[(5, 3)].color = g[(5, 4)].color = g[(4, 1)].color  # beide blau

    delete_first = [("delete", 5, 0), ("delete", 5, 3), ("move", 1, 5)]
    place_first = [("delete", 5, 0), ("move", 1, 5), ("delete", 5, 3)]
    s, extra = st, []
    for a in place_first:
        s, x = apply_action(s, a)
        extra.append(x)
    assert extra[-1] == 1  # Aktivierung durch Loeschen -> Extrazug

    s = st
    for a in delete_first:
        s, _ = apply_action(s, a)
    variants = [acts for acts, _ in _reorder_variants(st, [Plan(delete_first, 0.0, s)], set())]
    assert place_first in variants


def test_idle_champion_always_gets_nearest_color():
    """Analyse 20261124_144125: goldener Greif blieb 'Farbe unbekannt' -> Aktivierung nie geplant.
    Eine Armee hat nur 3 Farben: immer die aehnlichste nehmen (geschaetzt), hier Gold."""
    f = ROOT / "dataset" / "analysis" / "20261124_144125.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze

    st, meta = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=1)
    g = st.me.grid()
    champ = g[(5, 1)]
    assert champ.unit == "champion" and champ.color == g[(1, 3)].color  # goldener Speertraeger
    assert (5, 1) in meta["guessed"]


def test_split_blue_archers_and_bar_digit_in_charging_griffin():
    """Analyse 20261124_145258: (1) blaue Bogenschuetzen in zwei Klassen zerfallen -> blaue Mauern
    unsichtbar; (2) Balken-Ziffer des ladenden Greifs als 'Wand 5' gelesen und Ladezeit 4 als
    Ersatzwert 2 (Feder an der Ziffer)."""
    f = ROOT / "dataset" / "analysis" / "20261124_145258.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze

    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=7)
    g = st.me.grid()
    blue = [(7, 1), (7, 2), (1, 3), (1, 4), (4, 2), (5, 3), (3, 4), (5, 4), (4, 5)]
    assert len({g[c].color for c in blue}) == 1
    griffin = g[(5, 1)]
    assert griffin.kind == "form" and griffin.w == 2 and griffin.ct == 4
    assert not any(p.kind in ("wall", "block") and p.row > 0 for p in st.me.pieces)


@pytest.mark.parametrize("stem, enemy_hp", [("20261124_152341", 18), ("20261113_014323", 45), ("20261113_011301", 77),
                                             ("20261113_011834", 59), ("20261123_001349", 88)])
def test_enemy_hp_bar_any_color(stem, enemy_hp):
    """Lebensbalken wird bei wenig HP orange/rot; vorher nur Gruen gelesen -> 'Gegner 100' bei 18 HP."""
    f = ROOT / "dataset" / "analysis" / f"{stem}.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.ui import read_hp
    from coh.vision import Geometry
    assert read_hp(np.asarray(Image.open(f).convert("RGB")), Geometry(1920, 1080))[1] == enemy_hp


def test_unit_under_cursor_gets_color_from_head():
    """Analyse 20261124_152341: goldener Speertraeger unter dem Cursor (Sp. 6, R. 4) war 'unbekannt'."""
    f = ROOT / "dataset" / "analysis" / "20261124_152341.png"
    if not f.exists():
        pytest.skip("Aufnahme nicht vorhanden")
    import numpy as np
    from PIL import Image

    from coh.vision import analyze
    st, _ = analyze(np.asarray(Image.open(f).convert("RGB")), moves=3, cursor_col=5)
    g = st.me.grid()
    assert g[(5, 3)].color == g[(2, 0)].color  # beide goldene Speertraeger
