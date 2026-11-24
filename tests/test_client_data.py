"""Datenformat zwischen Overlay und Client, Meldungen und Trainings-Auswertung (ohne Fenster)."""
import json

from coh import boardio, training
from coh.model import Hero, Piece, Side, State


def _state():
    me = Side(Hero(hp=90, mp=40))
    me.pieces = [Piece("unit", 0, 0, unit="spearman", color="a", uid=1),
                 Piece("unit", 1, 0, unit="archer", color="b", uid=2),
                 Piece("unit", 2, 0, unit="archer", color="b", uid=3),
                 Piece("wall", 3, 0, hp=7, uid=4),
                 Piece("form", 4, 0, 1, 3, unit="spearman", color="a", max_power=10, start_power=5, ct=2, ct_total=3,
                       uid=5)]
    en = Side(Hero(hp=18))
    en.pieces = [Piece("unit", 0, 0, unit="core", color="a", uid=1)]
    me.reserve, en.reserve = 4, 14
    return State(me, en, 3)


def test_record_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(boardio, "ANALYSIS", tmp_path)
    st = _state()
    rec = boardio.analysis_record("20261124_160000", st, lines=["1. Spalte 1 -> Spalte 2"],
                                  stock_text=("C 5/5", "E 8/10"))
    boardio.write_analysis("20261124_160000", rec)
    back = boardio.load_analysis("20261124_160000")
    assert back["format"] == boardio.FORMAT and back["kopf"]["hp_gegner"] == 18 and back["kopf"]["reserve_gegner"] == 14
    assert back["klassen"]["ich"] == {"a": [0, 0], "b": [1, 0]}
    st2 = boardio.record_to_state(back)
    assert [p.sig() for p in st2.me.pieces] == [p.sig() for p in st.me.pieces]
    assert st2.moves_left == 3 and st2.me.reserve == 4


def test_save_correction_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(boardio, "ANALYSIS", tmp_path / "analysis")
    monkeypatch.setattr(boardio, "CORRECTIONS", tmp_path / "corrections")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "S.png").write_bytes(b"png")
    rec = boardio.analysis_record("S", _state())
    out = boardio.save_correction("S", rec, korrigiert={"kopf": {}, "ich": [], "gegner": []}, notiz="Test")
    assert sorted(p.name for p in out.iterdir()) == ["erkannt.json", "korrigiert.json", "notiz.txt", "screenshot.png"]
    out2 = boardio.save_correction("S", rec, zug={"bewertung": "schlecht", "besser": [["move", 1, 5]]})
    assert json.loads((out2 / "zug.json").read_text(encoding="utf-8"))["besser"] == [["move", 1, 5]]
    assert boardio.corrected_stems() == {"S"}


def test_compare_maps_letters_to_real_colors():
    rec = boardio.analysis_record("S", _state())
    corr = json.loads(json.dumps(rec))
    for p in corr["ich"] + corr["gegner"]:
        p["color"] = {"a": "Gold", "b": "Blau"}.get(p["color"], p["color"])
    r = training.compare(rec, corr)
    assert r.kind_ok == r.cells and r.color_ok == r.color_n and not r.diffs
    # Ein Bogenschuetze in Wahrheit Gold -> genau ein Farbfehler
    next(p for p in corr["ich"] if p["col"] == 2)["color"] = "Gold"
    corr["kopf"]["hp_gegner"] = 20
    r = training.compare(rec, corr)
    assert r.color_ok == r.color_n - 1
    assert ("kopf", "hp_gegner", "", 18, 20) in r.diffs
    s = training.summary([r])
    assert s["Korrekturen"] == 1 and s["Art %"] == 100.0
