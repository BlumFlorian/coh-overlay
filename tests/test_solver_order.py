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
