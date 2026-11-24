"""Zug-Berater-Overlay.

Bedienung im Spiel (Controller):
  L1 gedrueckt halten (~0,5 s)  -> Werte-Ansicht wird aufgenommen, analysiert, Vorschlag erscheint
  R1                            -> Overlay ein-/ausblenden
  (Tastatur: F8 = analysieren, F7 = ein-/ausblenden, wenn L1-Ansicht gerade offen ist)

Das Overlay ist ein eigenes, durchsichtiges, nicht anklickbares Fenster ueber dem Spiel.
Es liest nur Bildschirmpixel und sendet nichts ans Spiel.

  python tools/overlay.py [--nodes 3000] [--frames 3]
"""
from __future__ import annotations

import argparse
import ctypes
import os
import queue
import signal
import sys
import threading
import traceback
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coh.model import ROWS  # noqa: E402
from coh.rules import apply_action, backmost  # noqa: E402
from coh.screen import client_rect, find_window, grab_array, new_grabber, set_dpi_aware  # noqa: E402
from coh.solver import explain, solve  # noqa: E402
from coh.stock import StockTracker, read_stock  # noqa: E402
from coh.uncertain import close_call, uncertainties  # noqa: E402
from coh.assets import AssetLib  # noqa: E402
from coh.ui import read_ui  # noqa: E402
from coh.vision import Geometry, analyze, cell_crop, formation_feature  # noqa: E402

user32 = ctypes.windll.user32
VK_F7, VK_F8 = 0x76, 0x77
KEY = "#010203"  # Transparenzfarbe
STEP_COLORS = ["#30ff60", "#ffe030", "#ff9020", "#ff40ff", "#40e0ff", "#ffffff"]
OUT = ROOT / "dataset" / "analysis"


SPELL_NAMES = {"holy_shield": "Holy Shield"}

# --------------------------------------------------------------------------- Plan -> Zeichenbefehle

def plan_to_drawing(state, plan, geo: Geometry) -> tuple[list, list[str]]:
    """Rechnet die Aktionsfolge in Pfeile/Kreuze (Client-Pixel) und Textzeilen um."""
    shapes, lines = [], []
    s = state
    for i, a in enumerate(plan.actions, 1):
        kind, col, arg = a
        if kind == "reinforce":
            x, y = 1440 * geo.sx, 950 * geo.sy  # Reserve-Kasten rechts unten
            shapes.append(("reinforce", i, x, y))
            why = f", {s.me.reserve} in Reserve" + (" nach diesem Zug" if s.me.reserve > state.me.reserve else "")
            if "setup_expect" in plan.details:  # Erwartung ueber viele Wuerfe: was faellt hinter Elite/Champions
                d = plan.details["setup_expect"] - plan.details["setup_before"]
                if abs(d) >= 1:
                    why += f"; hinter Elite/Champions im Mittel {'passend' if d > 0 else 'verschuettet'} ({d:+.0f})"
            lines.append(f"{i}. Verstaerkung rufen (LT{why}) - danach L1 neu halten")
            break  # Ergebnis ist zufaellig -> danach neu analysieren
        if kind == "spell":
            x, y = 450 * geo.sx, 760 * geo.sy  # Heldenportraet links unten
            shapes.append(("spell", i, x, y))
            lines.append(f"{i}. Heldenzauber (Y): {SPELL_NAMES.get(s.me.hero.spell, s.me.hero.spell)}")
            s, _ = apply_action(s, a)
            continue
        if kind == "move":
            p = backmost(s.me, col)
            sx, sy = geo.cell_center("me", p.col + (p.w - 1) / 2, p.row + (p.h - 1) / 2)
            fill = s.me.fill(exclude=p)
            row = max(fill[c] for c in range(arg, arg + p.w))
            tx, ty = geo.cell_center("me", arg + (p.w - 1) / 2, min(row, ROWS - 1) + (p.h - 1) / 2)
            shapes.append(("arrow", i, sx, sy, tx, ty))
            what = {"elite": "Elite ", "champion": "Champion "}.get(p.unit, "")
            lines.append(f"{i}. {what}Spalte {col + 1} -> Spalte {arg + 1}")
        else:
            x, y = geo.cell_center("me", col, arg)
            shapes.append(("delete", i, x, y))
            lines.append(f"{i}. Loeschen (B): Spalte {col + 1}, Reihe {arg + 1}")
        reserve_before = s.me.reserve
        s, extra = apply_action(s, a)
        if extra:
            lines[-1] += f"   (Chain +{extra})"
        if s.me.reserve > reserve_before:  # Fusion gibt die Einheiten zurueck, Loeschen eine
            lines[-1] += f"   ({'Fusion, ' if kind == 'move' else ''}Reserve +{s.me.reserve - reserve_before})"
    ended_with_reinforce = bool(plan.actions) and plan.actions[-1][0] == "reinforce"
    if not ended_with_reinforce:
        forms = sum(p.kind == "form" for p in s.me.pieces) - sum(p.kind == "form" for p in state.me.pieces)
        walls = sum(p.kind == "wall" for p in s.me.pieces) - sum(p.kind == "wall" for p in state.me.pieces)
        if s.moves_left > 0:
            lines.append(f"{len(plan.actions) + 1}. Zug beenden (X): {s.moves_left} Zug/Zuege -> MP")
        lines.append(f"-> {max(forms, 0)} neue Formation(en), {max(walls, 0)} Wandsegment(e)")
    try:
        lines.append(explain(state, plan))
    except Exception:  # Begruendung ist nur Zusatz -- nie die Analyse daran scheitern lassen
        pass
    nxt = plan.details.get("next_actions")
    if nxt:  # Vorschau: bester eigener Folgezug, mit dem der Vorschlag bewertet wurde
        ns, parts = plan.details["next_state"], []
        for a in nxt:
            if a[0] == "reinforce":
                parts.append("Verstaerkung")
                break
            if a[0] == "move":
                p = backmost(ns.me, a[1])
                what = {"elite": "Elite ", "champion": "Champion "}.get(p.unit, "") if p else ""
                parts.append(f"{what}{a[1] + 1}->{a[2] + 1}")
            else:
                parts.append(f"loeschen {a[1] + 1}/{a[2] + 1}")
            ns, _ = apply_action(ns, a)
        champs = sum(p.kind == "form" and p.unit and p.tier == "champion" for p in ns.me.pieces)
        champs -= sum(p.kind == "form" and p.unit and p.tier == "champion" for p in plan.details["next_state"].me.pieces)
        tail = "  -> Champion aktiviert" if champs > 0 else ""
        lines.append(f"Naechster Zug (Vorschau): {', '.join(parts)}{tail}")
    return shapes, lines


def _step(line: str) -> tuple[str, str, str]:
    """'2. Loeschen (B): Spalte 6, Reihe 3   (Reserve +1)' -> ('2', 'Löschen  Spalte 6 · Reihe 3', 'Reserve +1')."""
    num, rest = line.split(". ", 1)
    parts = rest.split("   (")
    text, hints = parts[0], [h.rstrip(")") for h in parts[1:]]
    hints = [("Kette: " + h.replace("Chain ", "") + " Zug") if h.startswith("Chain") else h for h in hints
             if not (text.startswith("Loeschen") and h == "Reserve +1")]  # Loeschen gibt immer +1
    if text.startswith("Verstaerkung"):
        text, hints = "Verstärkung rufen (LT)", ["danach L1 neu halten"]
    elif text.startswith("Zug beenden"):
        text = "Zug beenden (X)"
    text = (text.replace("Loeschen (B):", "Löschen").replace(", Reihe", " · Reihe")
            .replace("Spalte ", "Sp. ").replace(" -> ", "  →  "))
    return num, text, ", ".join(hints)


def _round_rect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
           x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


# --------------------------------------------------------------------------- Overlay-Fenster

# Kleine Dauer-Hinweise oben rechts: Was beim L1-Halten der Erkennung hilft.
TIPS = [
    "Tipps für L1:",
    "- Cursor nicht auf Elite/Champion lassen (Vorschau verdeckt Herz und Farbe)",
    "- warten, bis der Vorschlag erscheint (~5-10 s), erst dann ziehen",
]


class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.visible = True
        self.region = None
        self.root.update_idletasks()
        self._click_through()

    def _click_through(self):
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x80000 | 0x20 | 0x80 | 0x08000000  # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        # Overlay aus Bildschirmaufnahmen ausnehmen (Win10 2004+), damit die eigene Analyse
        # nicht die Pfeile mitfotografiert. Folge: Auch OBS/Discord zeigen das Overlay nicht.
        user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE

    def place(self, region: dict):
        if region != self.region:
            self.region = region
            self.root.geometry(f"{region['width']}x{region['height']}+{region['left']}+{region['top']}")
            self.tips()

    def tips(self):
        """Hinweise klein und rechtsbuendig oben rechts (ueber dem gegnerischen Lebensbalken)."""
        self.canvas.delete("tips")
        if not self.region:
            return
        x = self.region["width"] - 16
        size = max(9, round(11 * self.region["height"] / 1080))
        for n, ln in enumerate(TIPS):
            self._text(x, 8 + n * (size + 9), ln, "#d8d8d8", tag="tips", size=size, anchor="ne", bold=False, outline=1)

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            self.root.deiconify()
            self._click_through()
        else:
            self.root.withdraw()

    def status(self, text: str, color: str = "#ffffff"):
        self.canvas.delete("status")
        k = (self.region or {"height": 1080})["height"] / 1080
        self._text(round(26 * k), round(22 * k), text, color, tag="status", size=round(12 * k), bold=False,
                   outline=1)

    def _text(self, x, y, text, color, tag="plan", size=16, anchor="nw", bold=True, outline=2):
        font = ("Segoe UI", size, "bold") if bold else ("Segoe UI", size)
        o = outline
        for dx, dy in ((-o, 0), (o, 0), (0, -o), (0, o), (-o, -o), (o, o), (-o, o), (o, -o)):
            self.canvas.create_text(x + dx, y + dy, text=text, fill="#000000", font=font, anchor=anchor, tags=tag)
        self.canvas.create_text(x, y, text=text, fill=color, font=font, anchor=anchor, tags=tag)

    def _card(self, lines):
        """Kompakte Karte oben links: nur die Schritte des aktuellen Zuges (plus Kontingent-Warnung).
        Alles Weitere (Vorschau, Unsicher, Knapp) steht in Konsole und Analyse-Datei."""
        steps = [_step(ln) for ln in lines if ln[:1].isdigit() and ". " in ln]
        warns = [ln.split(": ", 1)[1] for ln in lines if ln.startswith("ACHTUNG")]
        if not steps:
            return
        c = self.canvas
        k = (self.region or {"height": 1080})["height"] / 1080
        f_title = ("Segoe UI Semibold", round(11 * k))
        f_main = ("Segoe UI Semibold", round(15 * k))
        f_hint = ("Segoe UI", round(10 * k))
        x0, y0, w = round(24 * k), round(52 * k), round(300 * k)
        pad, badge = round(14 * k), round(13 * k)
        rows, y = [], y0 + round(38 * k)
        for st in steps:
            h = round(30 * k) + (round(16 * k) if st[2] else 0)
            rows.append((y, st))
            y += h
        for wn in warns:
            rows.append((y, ("!", wn, "")))
            y += round(26 * k)
        y1 = y + round(6 * k)
        _round_rect(c, x0, y0, x0 + w, y1, round(12 * k), fill="#15171d", outline="#3a3f4b", width=1, tags="plan")
        c.create_text(x0 + pad, y0 + round(18 * k), text="DEIN ZUG", fill="#8b93a7", font=f_title,
                      anchor="w", tags="plan")
        for y, (num, text, hint) in rows:
            cy = y + round(13 * k)
            if num == "!":
                c.create_text(x0 + pad, cy, text="! " + text, fill="#ff6b6b", font=f_hint, anchor="w",
                              tags="plan")
                continue
            col = STEP_COLORS[(int(num) - 1) % len(STEP_COLORS)]
            bx = x0 + pad + badge
            c.create_oval(bx - badge, cy - badge, bx + badge, cy + badge, fill=col, outline="", tags="plan")
            c.create_text(bx, cy, text=num, fill="#101010", font=("Segoe UI", round(11 * k), "bold"), tags="plan")
            c.create_text(bx + badge + round(10 * k), cy, text=text, fill="#f2f4f8", font=f_main, anchor="w",
                          tags="plan")
            if hint:
                c.create_text(bx + badge + round(10 * k), cy + round(19 * k), text=hint, fill="#8b93a7",
                              font=f_hint, anchor="w", tags="plan")

    def clear_plan(self):
        self.canvas.delete("plan")

    def show_plan(self, shapes, lines):
        c = self.canvas
        c.delete("plan")
        for sh in shapes:
            i = sh[1]
            col = STEP_COLORS[(i - 1) % len(STEP_COLORS)]
            if sh[0] == "arrow":
                _, _, sx, sy, tx, ty = sh
                c.create_line(sx, sy, tx, ty, fill="#000000", width=11, arrow="last", arrowshape=(26, 30, 11), tags="plan")
                c.create_line(sx, sy, tx, ty, fill=col, width=6, arrow="last", arrowshape=(24, 28, 9), tags="plan")
                # Nummer auch am Ziel: Mehrere Pfeile aus derselben Spalte sind sonst leicht zu verwechseln
                c.create_oval(tx - 13, ty - 13, tx + 13, ty + 13, fill=col, outline="#101010", width=2, tags="plan")
                c.create_text(tx, ty, text=str(i), fill="#101010", font=("Segoe UI", 12, "bold"), tags="plan")
                x, y = sx, sy
            elif sh[0] in ("reinforce", "spell"):
                _, _, x, y = sh
                c.create_oval(x - 46, y - 40, x + 46, y + 40, outline="#000000", width=9, tags="plan")
                c.create_oval(x - 46, y - 40, x + 46, y + 40, outline=col, width=5, tags="plan")
                x, y = x - 46, y - 40
            else:
                _, _, x, y = sh
                for w, cc in ((12, "#000000"), (7, "#ff3030")):
                    c.create_line(x - 22, y - 22, x + 22, y + 22, fill=cc, width=w, tags="plan")
                    c.create_line(x - 22, y + 22, x + 22, y - 22, fill=cc, width=w, tags="plan")
            c.create_oval(x - 17, y - 17, x + 17, y + 17, fill="#101010", outline=col, width=3, tags="plan")
            c.create_text(x, y, text=str(i), fill=col, font=("Segoe UI", 16, "bold"), tags="plan")
        self._card(lines)


# --------------------------------------------------------------------------- Worker (Controller + Analyse)

class Input:
    """Controller und Tastatur -- wird im Hauptthread (Tk-Schleife) abgefragt, denn SDL liefert
    Controller-Zustaende nur zuverlaessig in dem Thread, der es initialisiert hat."""

    def __init__(self, hold: float):
        import pygame
        from pygame._sdl2 import controller
        self.pg = pygame
        pygame.init()
        controller.init()
        self.pad = None
        for i in range(controller.get_count()):
            if controller.is_controller(i):
                self.pad = controller.Controller(i)
                break
        self.hold = hold
        self.l1_since, self.fired = None, False
        self.prev = {"r1": False, "f7": False, "f8": False}

    @property
    def name(self) -> str:
        return self.pad.name if self.pad else "keiner (nur F8/F7)"

    def poll(self) -> tuple[bool, bool]:
        """Rueckgabe: (analysieren?, ein/aus?)"""
        pg = self.pg
        pg.event.pump()
        btn = lambda b: bool(self.pad and self.pad.get_button(b))  # noqa: E731
        now = {"r1": btn(pg.CONTROLLER_BUTTON_RIGHTSHOULDER),
               "f7": bool(user32.GetAsyncKeyState(VK_F7) & 0x8000),
               "f8": bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)}
        edge = {k: now[k] and not self.prev[k] for k in now}
        self.prev = now
        trigger = edge["f8"]
        if btn(pg.CONTROLLER_BUTTON_LEFTSHOULDER):
            self.l1_since = self.l1_since or time.time()
            if not self.fired and time.time() - self.l1_since >= self.hold:
                trigger, self.fired = True, True
        else:
            self.l1_since, self.fired = None, False
        return trigger, edge["r1"] or edge["f7"]


class Learner:
    """Lokale Asset-Sammlung + Gedaechtnis der letzten Analyse, um ladende Formationen zu etikettieren:
    Entsteht eine Formation genau dort, wo der letzte Vorschlag sie vorhergesagt hat, ist ihre
    Klasse bekannt -> Aussehen als 'geladen' speichern."""

    def __init__(self):
        self.lib = AssetLib()
        self.prev = None  # (vorhergesagter Zustand, Kennungen je Klasse, Formationen vorher)

    @staticmethod
    def _form_keys(side):
        return {(p.col, p.row, p.w, p.h) for p in side.pieces if p.kind == "form"}

    def learn(self, state, meta, frame) -> int:
        if self.prev is None:
            return 0
        pred, uid_of, before = self.prev
        predicted = {(p.col, p.row, p.w, p.h): p for p in pred.me.pieces if p.kind == "form"}
        n = 0
        for p in state.me.pieces:
            key = (p.col, p.row, p.w, p.h)
            if p.kind != "form" or key in before or key not in predicted:
                continue
            q = predicted[key]
            uid = uid_of.get(q.color)
            if uid is None or q.unit != p.unit:
                continue
            scan = meta["scans"]["me"]
            self.lib.add(uid, "geladen", formation_feature(scan, p), cell_crop(frame, meta["geo"], "me", p.cells()))
            n += 1
        return n

    def remember(self, state, plan_state, meta):
        self.prev = (plan_state, dict(meta["uid_of"].get("me", {})), self._form_keys(state.me))


LEARNER: Learner | None = None
STOCK = StockTracker()  # Elite/Champion-Kontingent beider Seiten, ueber Analysen hinweg
HT_COLORS: dict = {}  # (Spalte, Reihe, Breite) -> zuletzt erkannte Farbe idle Elite/Champions


def remember_high_tier_colors(state) -> int:
    """Unter dem Cursor ist das Herz einer idle Elite/Champion ausgeblendet und ihre Farbe unbekannt.
    Steht sie noch auf demselben Platz wie bei der letzten Analyse, gilt die damalige Farbe."""
    restored = 0
    for p in state.me.pieces:
        if p.kind != "unit" or p.tier == "core":
            continue
        key = (p.col, p.row, p.w)
        if p.color.startswith("~"):
            if key in HT_COLORS:
                p.color = HT_COLORS[key]
                restored += 1
        else:
            HT_COLORS[key] = p.color
    return restored


def compute(frames, args):
    """UI lesen, Brett erkennen, Zug suchen. state=None, wenn der Gegner am Zug ist."""
    global LEARNER
    LEARNER = LEARNER or Learner()
    ui = read_ui(frames[0])
    if not ui.my_turn:
        return ui, None, None, [], []
    moves = ui.moves if ui.moves is not None else args.moves
    note = "" if ui.moves is not None else f"  (Zuganzeige nicht gelesen, nehme {moves} an)"
    state, meta = analyze(frames, moves=moves, cursor_col=ui.cursor_col, lib=LEARNER.lib)
    if not state.me.pieces:
        return ui, None, None, [], ["Keine Einheiten erkannt - L1 halten, bis das Raster mit Zahlen sichtbar ist"]
    learned = LEARNER.learn(state, meta, frames[0])
    STOCK.update(read_stock(frames[0]))  # nur im eigenen Zug: dann sind beide Kaesten sichtbar
    remember_high_tier_colors(state)
    state.me.stock = STOCK.tiers("me")
    state.enemy.stock = STOCK.tiers("enemy")
    if ui.my_reserve is not None:
        state.me.reserve = ui.my_reserve
    if ui.enemy_reserve is not None:
        state.enemy.reserve = ui.enemy_reserve
    if ui.my_hp is not None:
        state.me.hero.hp = ui.my_hp
    if ui.enemy_hp is not None:
        state.enemy.hero.hp = ui.enemy_hp
    state.me.hero.spell = args.spell or None
    if ui.my_mp is not None:
        # Ab 97 % gelesen = voll (Ablese-Toleranz); in der Simulation zaehlt nur die volle Leiste.
        state.me.hero.mp = state.me.hero.max_mp if ui.my_mp >= 0.97 else round(ui.my_mp * state.me.hero.max_mp)
    if ui.enemy_mp is not None:
        state.enemy.hero.mp = round(ui.enemy_mp * state.enemy.hero.max_mp)
    plans = solve(state, node_budget=args.nodes, beam=args.beam, top=2, lookahead=args.lookahead,
                  parallel=True)  # Vorausschau auf mehrere Kerne (Overlay hat den __main__-Schutz)
    shapes, lines = plan_to_drawing(state, plans[0], meta["geo"])
    gap = close_call(plans)
    if gap is not None:  # zwei Plaene fast gleich gut -> Spieler entscheidet
        _, alt = plan_to_drawing(state, plans[1], meta["geo"])
        steps = [ln.split(". ", 1)[1] for ln in alt if ln[:1].isdigit() and ". " in ln][:3]
        lines.append(f"Knapp (Abstand {gap:.1f}) - gleichwertige Alternative: {' | '.join(steps)}")
    unsure = [f"Farbe Elite/Champion Spalte {c + 1} nur geschaetzt (Farbton)" for c, _ in meta.get("guessed", [])]
    for u in (unsure + uncertainties(state, ui, STOCK))[:4]:
        lines.append("Unsicher: " + u)
    LEARNER.remember(state, plans[0].state, meta)
    LEARNER.lib.save()
    known = sum(1 for p in state.me.pieces if p.kind == "form" and not p.color.startswith("?"))
    spell = f"Zauber: ich {'BEREIT (Y)' if ui.my_spell_ready else f'{round((ui.my_mp or 0) * 100)} %'}"
    spell += f" | Gegner {'BEREIT - Vorsicht!' if ui.enemy_spell_ready else f'{round((ui.enemy_mp or 0) * 100)} %'}"
    if ui.my_spell_ready and not state.me.hero.spell:
        spell += "  (Zauber dieses Helden noch nicht simuliert)"
    elif ui.my_spell_ready and not any(a[0] == "spell" for a in plans[0].actions):
        spell += "  (Zauber lohnt sich jetzt nicht - aufheben)"
    lines.insert(0, spell)
    lines.insert(0, f"Kontingent: ich {STOCK.describe('me')} | Gegner {STOCK.describe('enemy')}")
    for warn in STOCK.warnings():
        lines.insert(0, "ACHTUNG: " + warn)
    lines.insert(0, f"Zuege: {moves}   Reserve: {state.me.reserve}   HP: ich {state.me.hero.hp} / Gegner {state.enemy.hero.hp}{note}")
    lines.append(f"Assets: {len(LEARNER.lib.units())} Klassen, +{learned} Formation(en) gelernt, "
                 f"{known} Formation(en) erkannt")
    return ui, state, meta, shapes, lines


def analysis_job(q: queue.Queue, region: dict, args):
    """Laeuft in einem eigenen Thread: Bilder holen, UI lesen, erkennen, Zug suchen."""
    try:
        sct = new_grabber()
        frames = []
        for _ in range(args.frames):  # mehrere Bilder gegen Idle-Animationen
            frames.append(grab_array(sct, region))
            time.sleep(0.07)
        t0 = time.time()
        ui, state, meta, shapes, lines = compute(frames, args)
        print(f"[{datetime.now():%H:%M:%S}] UI: {ui}", flush=True)
        if state is None:
            q.put(("status", lines[0] if lines else "Gegner ist am Zug - in deinem Zug L1 halten", "#ffb060"))
            return
        q.put(("plan", shapes, lines))
        q.put(("status", f"Vorschlag in {time.time() - t0:.1f} s  ·  nächste Runde wieder L1 halten", "#a0ffa0"))
        print(f"[{datetime.now():%H:%M:%S}] Vorschlag:\n  " + "\n  ".join(lines), flush=True)
        save_analysis(frames[0], state, meta, lines)
    except Exception as e:  # Overlay soll weiterlaufen
        traceback.print_exc()
        q.put(("status", f"Fehler: {e}", "#ff6060"))
    finally:
        q.put(("done",))


def save_analysis(img, state, meta, lines):
    from PIL import Image
    from analyze_image import draw_debug
    OUT.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    pil = Image.fromarray(img)
    pil.save(OUT / f"{stem}.png")
    draw_debug(pil, state, meta).save(OUT / f"{stem}_debug.png")
    (OUT / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")


def image_test(ov: Overlay, args):
    import numpy as np
    from PIL import Image
    img = np.asarray(Image.open(args.image).convert("RGB"))
    ov.place({"left": 0, "top": 0, "width": img.shape[1], "height": img.shape[0]})
    ui, state, meta, shapes, lines = compute([img], args)
    print(ui)
    ov.show_plan(shapes, lines or ["Gegner ist am Zug"])
    ov.status("Testbild: " + args.image.name)
    print("\n".join(lines))
    if args.snap:
        def snap():
            sct = new_grabber()
            Image.fromarray(grab_array(sct, {"left": 0, "top": 0, "width": img.shape[1], "height": img.shape[0]})).save(args.snap)
            ov.root.destroy()
        ov.root.after(3000, snap)
    ov.root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--moves", type=int, default=3, help="Zuege, falls die Zuganzeige nicht lesbar ist")
    ap.add_argument("--nodes", type=int, default=3000, help="Rechenbudget (bewertete Stellungen)")
    ap.add_argument("--frames", type=int, default=3, help="Bilder pro Analyse (gegen Animationen)")
    ap.add_argument("--beam", type=int, default=60)
    ap.add_argument("--lookahead", type=int, default=8,
                    help="So viele Kandidaten inkl. eigenem Folgezug bewerten (0 = aus, schneller)")
    ap.add_argument("--spell", default="holy_shield",
                    help="Simulierter Heldenzauber (holy_shield = Godric; leer = keinen einplanen)")
    ap.add_argument("--hold", type=float, default=0.5, help="Sekunden L1 halten bis zur Analyse")
    ap.add_argument("--image", type=Path, help="Test: Screenshot statt Live-Bild analysieren")
    ap.add_argument("--snap", type=Path, help="Test: nach 3 s Bildschirmfoto speichern und beenden")
    args = ap.parse_args()
    set_dpi_aware()
    ov = Overlay()
    signal.signal(signal.SIGINT, lambda *_: ov.root.destroy())
    if args.image:
        return image_test(ov, args)
    hwnd, title = find_window()
    region = client_rect(hwnd) or {"left": 0, "top": 0, "width": 1920, "height": 1080}
    ov.place(region)
    print(f"Spielfenster: {title or 'nicht gefunden (Overlay auf Hauptmonitor)'}")
    print("L1 halten = analysieren, R1 = Overlay ein/aus, Strg+C im Terminal = beenden")
    q: queue.Queue = queue.Queue()
    inp = Input(args.hold)
    print(f"Controller: {inp.name}")
    ov.status(f"Bereit. L1 halten = analysieren, R1 = ein/aus   (Controller: {inp.name})")
    state = {"busy": False, "hwnd": hwnd}

    def poll():
        trigger, toggle = inp.poll()
        if toggle:
            ov.toggle()
        if trigger and not state["busy"]:
            if not client_rect(state["hwnd"]):
                state["hwnd"] = find_window()[0]
            region = client_rect(state["hwnd"])
            if region is None:
                ov.status("Spielfenster nicht gefunden", "#ff6060")
            else:
                print(f"[{datetime.now():%H:%M:%S}] Analyse gestartet", flush=True)
                state["busy"] = True
                ov.place(region)
                ov.clear_plan()
                if not ov.visible:
                    ov.toggle()
                ov.status("Analysiere ...", "#ffff80")
                threading.Thread(target=analysis_job, args=(q, region, args), daemon=True).start()
        try:
            while True:
                msg = q.get_nowait()
                if msg[0] == "status":
                    ov.status(msg[1], *msg[2:])
                elif msg[0] == "plan":
                    ov.show_plan(msg[1], msg[2])
                elif msg[0] == "done":
                    state["busy"] = False
        except queue.Empty:
            pass
        ov.root.after(15, poll)

    ov.root.after(15, poll)
    try:
        ov.root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
