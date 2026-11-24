"""CoH-Berater – Client-Fenster (PySide6).

Zeigt das erkannte Brett der neuesten L1-Analyse neben dem Screenshot, den Plan und die Kopfwerte.
Startet/stoppt das Overlay (eigener Prozess) und nimmt Korrekturen ("Brett falsch") und
Zug-Feedback ("Vorschlag schlecht") auf. Meldungen landen in dataset/corrections/<Zeit>/.
Anforderungen: docs/CLIENT.md.

  .venv\\Scripts\\python tools\\client.py
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtCore import QObject, QProcess, QRectF, Qt, QThread, QTimer, Signal, QFileSystemWatcher  # noqa: E402
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
    QWidget,
)

from coh import boardio  # noqa: E402
from coh.boardio import ANALYSIS, COLOR_NAMES  # noqa: E402
from coh.model import COLS, ROWS, TIER, UNITS  # noqa: E402

PY = ROOT / ".venv" / "Scripts" / "python.exe"
SETTINGS = ROOT / "dataset" / "client_settings.json"
CLIENT_STATE = ROOT / "dataset" / "client_state.json"

REAL = {"Gold": "#e2b230", "Blau": "#3d7fd9", "Weiss": "#f0f0f0", "Rot": "#d9453d", "Gruen": "#4caf50",
        "Lila": "#9c5bd6", "Schwarz": "#3a3a3a", "Grau": "#9e9e9e", "?": "#b8b8b8"}
LETTER = ["#ff7070", "#70d070", "#7090ff", "#ffe070", "#ff70ff", "#70ffff", "#ffa040", "#b0b0ff"]
SIDES = {"ich": "me", "gegner": "enemy"}

KINDS = [("leer", None), ("Einheit (Core)", "core"), ("Elite", "elite"), ("Champion", "champion"),
         ("Wand", "wall"), ("Ladende Formation", "form"), ("Hindernis (unbekannt)", "block")]
FOOT = {"core": (1, 1), "elite": (1, 2), "champion": (2, 2)}
FORM_FOOT = {"core": (1, 3), "elite": (1, 2), "champion": (2, 2)}
ACTION_TYPES = [("Bewegen", "move"), ("Loeschen", "delete"), ("Verstaerkung", "reinforce"),
                ("Heldenzauber", "spell"), ("Zug beenden", "end")]

DEFAULT_SETTINGS = {"spell": "holy_shield", "nodes": 3000, "lookahead": 8, "hold": 0.5, "frames": 3}


# --------------------------------------------------------------------------- Hilfen

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(default)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def tier_of(p: dict) -> str | None:
    u = p.get("unit")
    return TIER.get(u) if u else None


def stem_label(stem: str) -> str:
    try:
        t = datetime.strptime(stem[:15], "%Y%m%d_%H%M%S")
        return t.strftime("%d.%m. %H:%M:%S")
    except ValueError:
        return stem


def class_features(img: np.ndarray, pieces: list[dict], letter: str, who: str) -> np.ndarray | None:
    """Mittleres Aussehen aller idle Einheiten einer Klasse (Rumpf + Kopf, wie die Erkennung)."""
    from coh.vision import Background, Geometry, _cursor_bg, _features, _rgb
    geo, nb, feats = Geometry(img.shape[1], img.shape[0]), Background([]), []
    for p in pieces:
        if p.get("color") != letter or p["kind"] != "unit" or tier_of(p) != "core":
            continue
        x0, y0, x1, y1 = geo.cell_box(who, p["col"], p["row"])
        w, h = x1 - x0, y1 - y0
        parts = []
        for a, b, c, d in ((0.50, 0.25, 0.65, 0.55), (0.30, 0.00, 0.80, 0.24)):
            px = _rgb(img, x0 + a * w, y0 + b * h, x0 + c * w, y0 + d * h).reshape(-1, 3)
            px = px[~_cursor_bg(px)]
            if len(px) < 20:
                break
            parts.append(_features(px.reshape(1, -1, 3), nb))
        if len(parts) == 2:
            feats.append(np.concatenate(parts))
    return np.mean(feats, 0) if feats else None


def suggest_names(feats: dict, refs: dict, limit: float = 1.2) -> dict:
    """Buchstabe -> Farbname nach den gelernten Vorlagen; jede Farbe hoechstens einmal (naechste zuerst)."""
    pairs = sorted((float(np.abs(np.array(ref["f"]) - f).sum()), letter, name)
                   for letter, f in feats.items() if f is not None for name, ref in refs.items())
    out, used = {}, set()
    for d, letter, name in pairs:
        if d > limit or letter in out or name in used:
            continue
        out[letter], _ = name, used.add(name)
    return out


# --------------------------------------------------------------------------- Hintergrund-Arbeit

class Job(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:  # noqa: BLE001 - im Fenster anzeigen
            import traceback
            if sys.stderr:  # unter pythonw gibt es keine Konsole
                traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


def load_record(stem: str) -> dict:
    """Analyse-Record laden; fuer aeltere Analysen ohne JSON aus dem Screenshot nacherkennen."""
    rec = boardio.load_analysis(stem)
    if rec is None:
        from coh.training import recognize_png
        rec = recognize_png(ANALYSIS / f"{stem}.png")
        txt = ANALYSIS / f"{stem}.txt"
        if txt.exists():
            rec["plan"]["zeilen"] = txt.read_text(encoding="utf-8").splitlines()
        boardio.write_analysis(stem, rec)
    return rec


# --------------------------------------------------------------------------- Overlay-Prozess

class OverlayProcess(QObject):
    line = Signal(str)
    running = Signal(bool)

    def __init__(self):
        super().__init__()
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.started.connect(lambda: self.running.emit(True))
        self.proc.finished.connect(lambda *_: self.running.emit(False))
        self._buf = ""
        if os.name == "nt":  # kein eigenes Konsolenfenster fuer das Overlay (Ausgabe kommt ins Log)
            try:
                def _no_window(args):
                    args.flags |= 0x08000000  # CREATE_NO_WINDOW
                self.proc.setCreateProcessArgumentsModifier(_no_window)
            except AttributeError:
                pass

    def is_running(self) -> bool:
        return self.proc.state() != QProcess.NotRunning

    def start(self, settings: dict):
        if self.is_running():
            return
        args = ["-u", str(ROOT / "tools" / "overlay.py"), "--nodes", str(settings["nodes"]),
                "--lookahead", str(settings["lookahead"]), "--hold", str(settings["hold"]),
                "--frames", str(settings["frames"]), "--spell", settings["spell"]]
        env = self.proc.processEnvironment()
        if env.isEmpty():
            from PySide6.QtCore import QProcessEnvironment
            env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.line.emit(f"> Overlay wird gestartet ({' '.join(args[2:])})")
        self.proc.start(str(PY if PY.exists() else sys.executable), args)

    def stop(self):
        if not self.is_running():
            return
        pid = self.proc.processId()
        self.proc.terminate()  # WM_CLOSE an das Overlay-Fenster
        if not self.proc.waitForFinished(2500):
            # Ganzen Prozessbaum beenden (Rechenprozesse des Solvers eingeschlossen)
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            self.proc.waitForFinished(2000)
        self.line.emit("> Overlay beendet")

    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for ln in lines:
            self.line.emit(ln.rstrip("\r"))


# --------------------------------------------------------------------------- Brett-Ansicht

class BoardWidget(QWidget):
    """Beide Seiten wie auf dem Bildschirm: Gegner oben (Front unten), ich unten (Front oben)."""
    cellClicked = Signal(str, int, int)  # Seite ("ich"/"gegner"), Spalte, Reihe (Modell, 0 = Front)

    def __init__(self):
        super().__init__()
        self.rec: dict | None = None
        self.names: dict = {"ich": {}, "gegner": {}}
        self.selected = None
        self.changed: set = set()
        self.editable = False
        self.setMinimumSize(360, 520)
        self.setMouseTracking(True)

    def set_record(self, rec, names):
        self.rec, self.names, self.selected, self.changed = rec, names, None, set()
        self.update()

    # Geometrie
    def _layout(self):
        gap = 14
        cs = min((self.width() - 8) / COLS, (self.height() - gap - 8) / (2 * ROWS))
        x0 = (self.width() - cs * COLS) / 2
        y0 = (self.height() - (2 * ROWS * cs + gap)) / 2
        return cs, x0, y0, gap

    def cell_rect(self, side, c, r) -> QRectF:
        cs, x0, y0, gap = self._layout()
        if side == "gegner":
            y = y0 + (ROWS - 1 - r) * cs
        else:
            y = y0 + ROWS * cs + gap + r * cs
        return QRectF(x0 + c * cs, y, cs, cs)

    def piece_rect(self, side, p) -> QRectF:
        rects = [self.cell_rect(side, c, r) for c in range(p["col"], p["col"] + p.get("w", 1))
                 for r in range(p["row"], p["row"] + p.get("h", 1)) if 0 <= c < COLS and 0 <= r < ROWS]
        if not rects:
            return QRectF()
        out = rects[0]
        for q in rects[1:]:
            out = out.united(q)
        return out

    def hit(self, x, y):
        for side in ("gegner", "ich"):
            for c in range(COLS):
                for r in range(ROWS):
                    if self.cell_rect(side, c, r).contains(x, y):
                        return side, c, r
        return None

    def mousePressEvent(self, ev):
        h = self.hit(ev.position().x(), ev.position().y())
        if h:
            self.selected = h
            self.update()
            self.cellClicked.emit(*h)

    # Zeichnen
    def color_of(self, side, color) -> QColor:
        if not color:
            return QColor(REAL["?"])
        if color in REAL:
            return QColor(REAL[color])
        name = self.names.get(side, {}).get(color)
        if name and name in REAL:
            return QColor(REAL[name])
        if color[0].isalpha():
            return QColor(LETTER[(ord(color[0]) - 97) % len(LETTER)])
        return QColor(REAL["?"])

    def label_color(self, side, color) -> str:
        if not color:
            return ""
        if color in REAL:
            return color
        name = self.names.get(side, {}).get(color)
        if name:
            return name
        return "?" if color[0] in "?~#" else color.upper()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.fillRect(self.rect(), QColor("#20232a"))
        cs, x0, y0, gap = self._layout()
        for side in ("gegner", "ich"):
            for c in range(COLS):
                for r in range(ROWS):
                    rc = self.cell_rect(side, c, r)
                    qp.fillRect(rc.adjusted(1, 1, -1, -1), QColor("#2c313a"))
        # Trennlinie
        ym = y0 + ROWS * cs + gap / 2
        qp.setPen(QPen(QColor("#7fd8ff"), 2))
        qp.drawLine(int(x0), int(ym), int(x0 + COLS * cs), int(ym))
        if not self.rec:
            qp.setPen(QColor("#aaaaaa"))
            qp.drawText(self.rect(), Qt.AlignCenter, "Noch keine Analyse")
            return
        guessed = {tuple(x) for x in self.rec.get("geschaetzt", [])}
        fsize = max(7, int(cs * 0.2))
        for side in ("gegner", "ich"):
            for p in self.rec.get(side, []):
                rect = self.piece_rect(side, p).adjusted(3, 3, -3, -3)
                kind = p["kind"]
                if kind == "wall":
                    fill, text = QColor("#5fb3c9"), f"W{p.get('hp')}"
                elif kind == "block":
                    fill, text = QColor("#606060"), "?"
                else:
                    fill = self.color_of(side, p.get("color"))
                    unit = p.get("unit") or "?"
                    code = UNITS.get(unit, {}).get("code", unit[:2]) if unit not in ("core", "elite", "champion") else ""
                    t = tier_of(p) or "?"
                    tl = {"core": "", "elite": "E", "champion": "C"}.get(t, "?")
                    text = f"{tl}{code}".strip() or "•"
                    text += f"\n{self.label_color(side, p.get('color'))}"
                    if kind == "form":
                        text = f"⚔{text}\n{p.get('ct')}R/{p.get('max_power')}"
                if kind == "form":
                    fill = QColor(fill)
                    fill.setAlpha(150)
                qp.setBrush(QBrush(fill))
                pen = QPen(QColor("#111111"), 1)
                if side == "ich" and (p["col"], p["row"]) in guessed:
                    pen = QPen(QColor("#ff9800"), 2, Qt.DashLine)
                if (side, p["col"], p["row"]) in self.changed:
                    pen = QPen(QColor("#ffeb3b"), 3)
                qp.setPen(pen)
                qp.drawRoundedRect(rect, 6, 6)
                light = fill.lightness() > 150
                qp.setPen(QColor("#111111" if light else "#ffffff"))
                qp.setFont(QFont("Segoe UI", fsize, QFont.Bold))
                qp.drawText(rect, Qt.AlignCenter, text)
        if self.selected:
            qp.setBrush(Qt.NoBrush)
            qp.setPen(QPen(QColor("#00e5ff"), 3))
            qp.drawRect(self.cell_rect(*self.selected).adjusted(1, 1, -1, -1))
        if self.editable:
            qp.setPen(QPen(QColor("#ffeb3b"), 3))
            qp.setBrush(Qt.NoBrush)
            qp.drawRect(self.rect().adjusted(1, 1, -2, -2))


# --------------------------------------------------------------------------- Screenshot-Ansicht

class ShotView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.pix = QGraphicsPixmapItem()
        self.scene_.addItem(self.pix)
        self.mark = QGraphicsRectItem()
        self.mark.setPen(QPen(QColor("#00e5ff"), 4))
        self.scene_.addItem(self.mark)
        self.mark.hide()
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#15171c"))
        self._fit = True

    def show_image(self, path: Path):
        pm = QPixmap(str(path)) if path.exists() else QPixmap()
        self.pix.setPixmap(pm)
        self.scene_.setSceneRect(QRectF(pm.rect()))
        self.mark.hide()
        if self._fit:
            self.fitInView(self.pix, Qt.KeepAspectRatio)

    def mark_cell(self, who: str, c: int, r: int):
        pm = self.pix.pixmap()
        if pm.isNull():
            return
        from coh.vision import Geometry
        x0, y0, x1, y1 = Geometry(pm.width(), pm.height()).cell_box(who, c, r)
        self.mark.setRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        self.mark.show()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._fit and not self.pix.pixmap().isNull():
            self.fitInView(self.pix, Qt.KeepAspectRatio)

    def wheelEvent(self, ev):
        self._fit = False
        f = 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
        self.scale(f, f)

    def mouseDoubleClickEvent(self, ev):
        self._fit = True
        self.fitInView(self.pix, Qt.KeepAspectRatio)


# --------------------------------------------------------------------------- Dialoge

class CellDialog(QDialog):
    """Korrektur eines Feldes: was steht dort wirklich?"""

    def __init__(self, parent, side: str, c: int, r: int, piece: dict | None, names: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Feld korrigieren – {'Ich' if side == 'ich' else 'Gegner'}, Spalte {c + 1}, Reihe {r + 1}")
        self.side, self.c, self.r, self.orig = side, c, r, piece
        f = QFormLayout(self)
        self.kind = QComboBox()
        for label, _ in KINDS:
            self.kind.addItem(label)
        self.unit = QComboBox()
        self.color = QComboBox()
        self.color.addItems(COLOR_NAMES)
        self.ct = QSpinBox()
        self.ct.setRange(0, 9)
        self.power = QSpinBox()
        self.power.setRange(0, 300)
        self.hp = QSpinBox()
        self.hp.setRange(1, 60)
        f.addRow("Art", self.kind)
        f.addRow("Einheit", self.unit)
        f.addRow("Farbe", self.color)
        f.addRow("Ladezeit (Runden)", self.ct)
        f.addRow("Angriffskraft", self.power)
        f.addRow("Wand-HP", self.hp)
        hint = QLabel("Groesse ergibt sich aus der Art (Elite 1x2, Champion 2x2, Kern-Formation 1x3).\n"
                      "Ueberlappende Pieces werden ersetzt.")
        hint.setStyleSheet("color: #888")
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self.kind.currentIndexChanged.connect(self._update)
        self._prefill(piece, names)
        self._update()

    def _units_for(self, tier):
        names = sorted(u for u, d in UNITS.items() if d["tier"] == tier and u not in ("core", "elite", "champion"))
        return [tier] + names

    def _prefill(self, p, names):
        if p is None:
            self.kind.setCurrentIndex(0)
            return
        kind, t = p["kind"], tier_of(p)
        idx = {"wall": 4, "form": 5, "block": 6}.get(kind, {"core": 1, "elite": 2, "champion": 3}.get(t, 1))
        self.kind.setCurrentIndex(idx)
        self._update()
        if p.get("unit"):
            i = self.unit.findText(p["unit"])
            if i >= 0:
                self.unit.setCurrentIndex(i)
        col = p.get("color") or "?"
        col = col if col in COLOR_NAMES else names.get(col, "?")
        self.color.setCurrentText(col if col in COLOR_NAMES else "?")
        self.ct.setValue(int(p.get("ct") or 0))
        self.power.setValue(int(p.get("max_power") or 0))
        self.hp.setValue(int(p.get("hp") or 7))

    def _update(self):
        key = KINDS[self.kind.currentIndex()][1]
        cur = self.unit.currentText()
        self.unit.clear()
        if key in ("core", "elite", "champion"):
            self.unit.addItems(self._units_for(key))
        elif key == "form":
            for t in ("core", "elite", "champion"):
                self.unit.addItems(self._units_for(t))
        i = self.unit.findText(cur)
        if i >= 0:
            self.unit.setCurrentIndex(i)
        for w, on in ((self.unit, key in ("core", "elite", "champion", "form")),
                      (self.color, key in ("core", "elite", "champion", "form")),
                      (self.ct, key == "form"), (self.power, key == "form"), (self.hp, key == "wall")):
            w.setEnabled(on)

    def result_piece(self) -> dict | None:
        """None = Feld leer."""
        key = KINDS[self.kind.currentIndex()][1]
        if key is None:
            return None
        anchor = (self.c, self.r)
        p = {k: 0 for k in boardio.PIECE_FIELDS}
        p.update(col=anchor[0], row=anchor[1], w=1, h=1, unit=None, color=None, merged=False, fused=1)
        if key == "wall":
            p.update(kind="wall", hp=self.hp.value())
        elif key == "block":
            p.update(kind="block", hp=3)
        else:
            unit = self.unit.currentText() or key
            t = TIER.get(unit, "core")
            w, h = (FORM_FOOT if key == "form" else FOOT)[t]
            p.update(kind="form" if key == "form" else "unit", unit=unit, color=self.color.currentText(), w=w, h=h)
            if key == "form":
                p.update(ct=self.ct.value(), ct_total=self.ct.value(), max_power=self.power.value(),
                         start_power=self.power.value())
        if self.orig and (self.orig.get("w", 1), self.orig.get("h", 1)) == (p["w"], p["h"]):
            p["col"], p["row"] = self.orig["col"], self.orig["row"]  # gleiche Groesse: Position behalten
        p["col"] = min(p["col"], COLS - p["w"])
        p["row"] = min(p["row"], ROWS - p["h"])
        return p


class MoveDialog(QDialog):
    """Zug-Feedback: Vorschlag schlecht, optional besserer Zug + Notiz."""

    def __init__(self, parent, rec: dict):
        super().__init__(parent)
        self.setWindowTitle("Vorschlag schlecht – was waere besser?")
        self.resize(560, 520)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("<b>Vorschlag des Tools</b>"))
        shown = QPlainTextEdit("\n".join(rec.get("plan", {}).get("zeilen", [])))
        shown.setReadOnly(True)
        shown.setMaximumHeight(150)
        v.addWidget(shown)
        v.addWidget(QLabel("<b>Besserer Zug</b> (optional, Spalten/Reihen wie im Spiel ab 1; Reihe 1 = vorn)"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Aktion", "Spalte (von)", "nach Spalte / Reihe"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.table)
        h = QHBoxLayout()
        add, rem = QPushButton("+ Aktion"), QPushButton("– entfernen")
        add.clicked.connect(self.add_row)
        rem.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        h.addWidget(add)
        h.addWidget(rem)
        h.addStretch()
        v.addLayout(h)
        v.addWidget(QLabel("<b>Notiz</b> (z. B. „erst platzieren, dann loeschen“)"))
        self.note = QPlainTextEdit()
        self.note.setMaximumHeight(90)
        v.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        typ = QComboBox()
        for label, _ in ACTION_TYPES:
            typ.addItem(label)
        a, b = QSpinBox(), QSpinBox()
        a.setRange(1, COLS)
        b.setRange(1, COLS)
        typ.currentIndexChanged.connect(lambda i, b=b: b.setRange(1, ROWS if ACTION_TYPES[i][1] == "delete" else COLS))
        self.table.setCellWidget(r, 0, typ)
        self.table.setCellWidget(r, 1, a)
        self.table.setCellWidget(r, 2, b)

    def feedback(self) -> dict:
        acts = []
        for r in range(self.table.rowCount()):
            key = ACTION_TYPES[self.table.cellWidget(r, 0).currentIndex()][1]
            a, b = self.table.cellWidget(r, 1).value(), self.table.cellWidget(r, 2).value()
            if key == "move":
                acts.append(["move", a - 1, b - 1])
            elif key == "delete":
                acts.append(["delete", a - 1, b - 1])
            else:
                acts.append([key, 0, 0])
        return {"bewertung": "schlecht", "besser": acts, "notiz": self.note.toPlainText().strip()}


class SettingsDialog(QDialog):
    def __init__(self, parent, s: dict):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        f = QFormLayout(self)
        self.spell = QComboBox()
        self.spell.addItem("Holy Shield (Godric)", "holy_shield")
        self.spell.addItem("keinen Zauber einplanen", "")
        self.spell.setCurrentIndex(0 if s["spell"] == "holy_shield" else 1)
        self.nodes = QSpinBox()
        self.nodes.setRange(500, 20000)
        self.nodes.setSingleStep(500)
        self.nodes.setValue(s["nodes"])
        self.look = QSpinBox()
        self.look.setRange(0, 30)
        self.look.setValue(s["lookahead"])
        self.hold = QDoubleSpinBox()
        self.hold.setRange(0.2, 2.0)
        self.hold.setSingleStep(0.1)
        self.hold.setValue(s["hold"])
        self.frames = QSpinBox()
        self.frames.setRange(1, 5)
        self.frames.setValue(s["frames"])
        f.addRow("Heldenzauber", self.spell)
        f.addRow("Rechenbudget (Stellungen)", self.nodes)
        f.addRow("Vorausschau-Kandidaten", self.look)
        f.addRow("L1 halten (Sekunden)", self.hold)
        f.addRow("Bilder je Analyse", self.frames)
        f.addRow(QLabel("Aenderungen gelten beim naechsten Start des Overlays."))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def values(self) -> dict:
        return {"spell": self.spell.currentData(), "nodes": self.nodes.value(), "lookahead": self.look.value(),
                "hold": round(self.hold.value(), 2), "frames": self.frames.value()}


class TrainingDialog(QDialog):
    """Trainings-Ansicht: alle Korrekturen gegen die aktuelle Erkennung."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Training – Erkennung gegen Korrekturen")
        self.resize(900, 600)
        v = QVBoxLayout(self)
        self.info = QLabel("Rechne ...")
        v.addWidget(self.info)
        self.sumtab = QTableWidget(0, 2)
        self.sumtab.setHorizontalHeaderLabels(["Merkmal", "Wert"])
        self.sumtab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sumtab.setMaximumHeight(240)
        v.addWidget(self.sumtab)
        v.addWidget(QLabel("<b>Abweichungen</b> (Erkennung → Korrektur)"))
        self.diff = QTableWidget(0, 6)
        self.diff.setHorizontalHeaderLabels(["Korrektur", "Seite", "Spalte", "Reihe", "erkannt", "richtig"])
        self.diff.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.diff)
        from coh import training
        self.job = Job(training.evaluate_all, training.recognize_png)
        self.job.done.connect(self.show_results)
        self.job.failed.connect(lambda e: self.info.setText(f"Fehler: {e}"))
        self.job.start()

    def show_results(self, results):
        from coh.training import summary
        if not results:
            self.info.setText("Noch keine Korrekturen mit korrigiertem Brett vorhanden.")
            return
        s = summary(results)
        self.info.setText(f"{len(results)} Korrektur(en) ausgewertet – aktuelle Erkennung gegen deine Soll-Werte.")
        self.sumtab.setRowCount(len(s))
        for i, (k, val) in enumerate(s.items()):
            self.sumtab.setItem(i, 0, QTableWidgetItem(k))
            self.sumtab.setItem(i, 1, QTableWidgetItem("–" if val is None else str(val)))
        rows = [(r.name, *d) for r in results for d in r.diffs]
        self.diff.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                self.diff.setItem(i, j, QTableWidgetItem(str(val)))


# --------------------------------------------------------------------------- Hauptfenster

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CoH-Berater")
        self.resize(1600, 900)
        self.settings = {**DEFAULT_SETTINGS, **load_json(SETTINGS, {})}
        self.cstate = load_json(CLIENT_STATE, {"farben": {}})
        self.rec: dict | None = None
        self.stem: str | None = None
        self.edit_rec: dict | None = None
        self.img_cache: tuple[str, np.ndarray] | None = None
        self.jobs: list = []

        # Overlay
        self.overlay = OverlayProcess()
        self.overlay.line.connect(self.on_log)
        self.overlay.running.connect(self.on_running)

        # Werkzeugleiste
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        self.act_start = QAction("▶ Overlay starten", self)
        self.act_start.triggered.connect(lambda: self.overlay.start(self.settings))
        self.act_stop = QAction("■ Overlay stoppen", self)
        self.act_stop.triggered.connect(self.overlay.stop)
        self.act_stop.setEnabled(False)
        tb.addAction(self.act_start)
        tb.addAction(self.act_stop)
        tb.addSeparator()
        self.act_wrong = QAction("✎ Brett falsch melden", self)
        self.act_wrong.triggered.connect(self.start_correction)
        self.act_bad = QAction("👎 Vorschlag schlecht", self)
        self.act_bad.triggered.connect(self.report_move)
        tb.addAction(self.act_wrong)
        tb.addAction(self.act_bad)
        tb.addSeparator()
        act_train = QAction("📊 Training", self)
        act_train.triggered.connect(lambda: TrainingDialog(self).exec())
        act_set = QAction("⚙ Einstellungen", self)
        act_set.triggered.connect(self.open_settings)
        act_folder = QAction("📁 Meldungen", self)
        act_folder.triggered.connect(lambda: os.startfile(str(boardio.CORRECTIONS)) if boardio.CORRECTIONS.exists()
                                     else QMessageBox.information(self, "Meldungen", "Noch keine Meldungen."))
        tb.addAction(act_train)
        tb.addAction(act_set)
        tb.addAction(act_folder)
        self.status = QLabel("Overlay aus")
        self.status.setStyleSheet("padding-left: 12px; font-weight: bold")
        tb.addWidget(self.status)

        # Links: Verlauf
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)
        lv.addWidget(QLabel("<b>Verlauf</b>"))
        self.follow = QCheckBox("neueste live anzeigen")
        self.follow.setChecked(True)
        lv.addWidget(self.follow)
        self.history = QListWidget()
        self.history.currentItemChanged.connect(self.on_pick)
        lv.addWidget(self.history)

        # Mitte: Brett + Screenshot
        self.board = BoardWidget()
        self.board.cellClicked.connect(self.on_cell)
        shot_box = QWidget()
        sv = QVBoxLayout(shot_box)
        sv.setContentsMargins(0, 0, 0, 0)
        self.debug_img = QCheckBox("Debug-Bild (Erkennung eingezeichnet)")
        self.debug_img.toggled.connect(self.show_shot)
        sv.addWidget(self.debug_img)
        self.shot = ShotView()
        sv.addWidget(self.shot)
        center = QSplitter(Qt.Horizontal)
        center.addWidget(self.board)
        center.addWidget(shot_box)
        center.setSizes([520, 760])

        # Rechts: Kopfwerte, Farben, Plan
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)
        kg = QGroupBox("Kopfwerte")
        kf = QFormLayout(kg)
        self.kopf: dict = {}
        for key, label, hi in (("zuege", "Zuege", 9), ("reserve_ich", "Reserve ich", 40),
                               ("reserve_gegner", "Reserve Gegner", 40), ("hp_ich", "HP ich", 200),
                               ("hp_gegner", "HP Gegner", 200), ("mp_ich", "Magie ich %", 100),
                               ("mp_gegner", "Magie Gegner %", 100)):
            sp = QSpinBox()
            sp.setRange(0, hi)
            sp.setReadOnly(True)
            sp.setButtonSymbols(QSpinBox.NoButtons)
            kf.addRow(label, sp)
            self.kopf[key] = sp
        self.stock_me, self.stock_en = QLineEdit(), QLineEdit()
        for w in (self.stock_me, self.stock_en):
            w.setReadOnly(True)
        kf.addRow("Kontingent ich", self.stock_me)
        kf.addRow("Kontingent Gegner", self.stock_en)
        rv.addWidget(kg)
        self.legend_box = QGroupBox("Farben (Buchstabe → echte Farbe)")
        lb = QVBoxLayout(self.legend_box)
        lb.setContentsMargins(2, 2, 2, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.legend = QGridLayout(inner)
        scroll.setWidget(inner)
        lb.addWidget(scroll)
        rv.addWidget(self.legend_box, 1)
        pg = QGroupBox("Vorschlag")
        pv = QVBoxLayout(pg)
        self.plan = QPlainTextEdit()
        self.plan.setReadOnly(True)
        pv.addWidget(self.plan)
        rv.addWidget(pg, 1)
        # Korrekturleiste
        self.edit_bar = QGroupBox("Korrekturmodus: Felder im Brett anklicken, Kopfwerte aendern")
        self.edit_bar.setStyleSheet("QGroupBox { color: #ffeb3b; font-weight: bold }")
        ev = QVBoxLayout(self.edit_bar)
        self.edit_note = QPlainTextEdit()
        self.edit_note.setPlaceholderText("Notiz (optional)")
        self.edit_note.setMaximumHeight(70)
        ev.addWidget(self.edit_note)
        eh = QHBoxLayout()
        save, cancel = QPushButton("Speichern"), QPushButton("Abbrechen")
        save.clicked.connect(self.save_correction)
        cancel.clicked.connect(self.cancel_correction)
        eh.addWidget(save)
        eh.addWidget(cancel)
        ev.addLayout(eh)
        self.edit_bar.hide()
        rv.addWidget(self.edit_bar)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(center)
        split.addWidget(right)
        split.setSizes([200, 1080, 340])

        # Unten: Log
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFont(QFont("Consolas", 9))
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(split)
        vsplit.addWidget(self.log)
        vsplit.setSizes([720, 160])
        self.setCentralWidget(vsplit)

        # Ordner beobachten
        ANALYSIS.mkdir(parents=True, exist_ok=True)
        self.watch = QFileSystemWatcher([str(ANALYSIS)])
        self.debounce = QTimer(singleShot=True, interval=600)
        self.debounce.timeout.connect(self.refresh_history)
        self.watch.directoryChanged.connect(lambda _: self.debounce.start())
        self.refresh_history()

    # ---- Verlauf
    def refresh_history(self):
        stems = sorted({p.stem for p in ANALYSIS.glob("*.png") if not p.stem.endswith("_debug")}, reverse=True)
        done = boardio.corrected_stems()
        known = {self.history.item(i).data(Qt.UserRole) for i in range(self.history.count())}
        newest_with_json = next((s for s in stems if (ANALYSIS / f"{s}.json").exists()), None)
        self.history.blockSignals(True)
        cur = self.stem
        self.history.clear()
        for s in stems:
            mark = "✎ " if s in done else ""
            plain = "" if (ANALYSIS / f"{s}.json").exists() else "  ·"
            it = QListWidgetItem(f"{mark}{stem_label(s)}{plain}")
            it.setData(Qt.UserRole, s)
            self.history.addItem(it)
            if s == cur:
                self.history.setCurrentItem(it)
        self.history.blockSignals(False)
        new = [s for s in stems if s not in known]
        if self.follow.isChecked() and self.edit_rec is None and newest_with_json and newest_with_json in new \
                and newest_with_json != self.stem:
            self.select_stem(newest_with_json)
        elif self.stem is None and stems:
            self.select_stem(stems[0])

    def select_stem(self, stem):
        for i in range(self.history.count()):
            if self.history.item(i).data(Qt.UserRole) == stem:
                self.history.setCurrentRow(i)
                return

    def on_pick(self, item, _prev=None):
        if item is None:
            return
        if self.edit_rec is not None:
            if QMessageBox.question(self, "Korrektur verwerfen?", "Die laufende Korrektur verwerfen?") != QMessageBox.Yes:
                return
            self.cancel_correction()
        stem = item.data(Qt.UserRole)
        self.stem = stem
        self.plan.setPlainText("Lade ...")
        job = Job(load_record, stem)
        job.done.connect(lambda rec, s=stem: self.show_record(s, rec))
        job.failed.connect(lambda e: self.plan.setPlainText(f"Konnte die Analyse nicht laden: {e}"))
        self.jobs.append(job)
        job.finished.connect(lambda j=job: self.jobs.remove(j) if j in self.jobs else None)
        job.start()

    # ---- Anzeige
    def names_for(self, stem):
        return self.cstate.setdefault("farben", {}).setdefault(stem, {"ich": {}, "gegner": {}})

    def show_record(self, stem, rec):
        if stem != self.stem:
            return
        self.rec = rec
        self.board.set_record(rec, self.names_for(stem))
        self.show_shot()
        self.fill_kopf(rec["kopf"])
        lines = rec.get("plan", {}).get("zeilen", [])
        head = "(nachtraeglich erkannt – Vorschlag aus der damaligen Analyse)\n" if rec.get("nachtraeglich_erkannt") else ""
        self.plan.setPlainText(head + "\n".join(lines))
        self.fill_legend(stem, rec)

    def show_shot(self):
        if not self.stem:
            return
        dbg = ANALYSIS / f"{self.stem}_debug.png"
        self.shot.show_image(dbg if self.debug_img.isChecked() and dbg.exists() else ANALYSIS / f"{self.stem}.png")

    def fill_kopf(self, k):
        for key, sp in self.kopf.items():
            val = k.get(key)
            if key.startswith("mp_") and isinstance(val, (int, float)):
                val = round(val)  # Modell: 0..100 Punkte
            sp.setValue(int(val) if isinstance(val, (int, float)) else 0)
            sp.setSpecialValueText("")
        self.stock_me.setText(k.get("kontingent_ich") or "?")
        self.stock_en.setText(k.get("kontingent_gegner") or "?")

    def image(self) -> np.ndarray | None:
        if self.img_cache and self.img_cache[0] == self.stem:
            return self.img_cache[1]
        p = ANALYSIS / f"{self.stem}.png"
        if not p.exists():
            return None
        arr = np.asarray(Image.open(p).convert("RGB"))
        self.img_cache = (self.stem, arr)
        return arr

    def fill_legend(self, stem, rec):
        while self.legend.count():
            w = self.legend.takeAt(0).widget()
            if w:
                w.deleteLater()
        names = self.names_for(stem)
        img = self.image()
        self.class_feats = {}
        row = 0
        from coh.vision import Geometry
        for side in ("ich", "gegner"):
            classes = rec.get("klassen", {}).get(side, {})
            if not classes:
                continue
            feats = {L: class_features(img, rec[side], L, SIDES[side]) for L in classes} if img is not None else {}
            self.class_feats[side] = feats
            refs = self.cstate.setdefault("vorlagen", {}).setdefault(side, {})
            auto = suggest_names({L: f for L, f in feats.items() if L not in names[side]}, refs)
            names[side].update(auto)
            self.legend.addWidget(QLabel(f"<b>{'Ich' if side == 'ich' else 'Gegner'}</b>"), row, 0, 1, 3)
            row += 1
            for letter, (c, r) in sorted(classes.items()):
                thumb = QLabel()
                if img is not None:
                    geo = Geometry(img.shape[1], img.shape[0])
                    x0, y0, x1, y1 = (int(v) for v in geo.cell_box(SIDES[side], c, r))
                    crop = np.ascontiguousarray(img[y0:y1, x0:x1])
                    q = QImage(crop.data, crop.shape[1], crop.shape[0], crop.strides[0], QImage.Format_RGB888)
                    thumb.setPixmap(QPixmap.fromImage(q.copy()).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                combo = QComboBox()
                combo.addItems(COLOR_NAMES)
                combo.setCurrentText(names[side].get(letter, "?"))
                if letter in auto:
                    combo.setToolTip("automatisch zugeordnet (gelernte Vorlage) – bei Bedarf aendern")
                combo.currentTextChanged.connect(lambda t, s=side, L=letter: self.set_name(s, L, t))
                self.legend.addWidget(thumb, row, 0)
                self.legend.addWidget(QLabel(letter.upper() + (" (auto)" if letter in auto else "")), row, 1)
                self.legend.addWidget(combo, row, 2)
                row += 1
        self.save_cstate()
        self.board.update()

    def set_name(self, side, letter, name):
        if not self.stem:
            return
        self.names_for(self.stem)[side][letter] = name
        # Vorlage lernen: Aussehen dieser Klasse gehoert zu dieser Farbe (gleitender Mittelwert)
        f = getattr(self, "class_feats", {}).get(side, {}).get(letter)
        if f is not None and name != "?":
            refs = self.cstate.setdefault("vorlagen", {}).setdefault(side, {})
            ref = refs.get(name)
            if ref is None:
                refs[name] = {"f": f.tolist(), "n": 1}
            else:
                n = min(ref["n"], 19)
                refs[name] = {"f": ((np.array(ref["f"]) * n + f) / (n + 1)).tolist(), "n": ref["n"] + 1}
        self.save_cstate()
        self.board.update()

    def save_cstate(self):
        save_json(CLIENT_STATE, self.cstate)

    def on_cell(self, side, c, r):
        self.shot.mark_cell(SIDES[side], c, r)
        if self.edit_rec is None:
            return
        pieces = self.edit_rec[side]
        cur = next((p for p in pieces if p["col"] <= c < p["col"] + p.get("w", 1)
                    and p["row"] <= r < p["row"] + p.get("h", 1)), None)
        dlg = CellDialog(self, side, c, r, cur, self.names_for(self.stem)[side])
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.result_piece()
        if cur is not None:
            pieces.remove(cur)
        if new is not None:
            cells = {(x, y) for x in range(new["col"], new["col"] + new["w"]) for y in range(new["row"], new["row"] + new["h"])}
            for p in list(pieces):
                pc = {(x, y) for x in range(p["col"], p["col"] + p.get("w", 1)) for y in range(p["row"], p["row"] + p.get("h", 1))}
                if pc & cells:
                    pieces.remove(p)
            new["uid"] = 10_000 + len(self.board.changed)
            pieces.append(new)
            self.board.changed.add((side, new["col"], new["row"]))
        else:
            self.board.changed.add((side, c, r))
        self.board.update()

    # ---- Korrektur
    def start_correction(self):
        if self.rec is None:
            return
        if self.edit_rec is not None:
            return
        self.edit_rec = copy.deepcopy(self.rec)
        self.board.rec = self.edit_rec
        self.board.editable = True
        self.board.changed = set()
        for sp in self.kopf.values():
            sp.setReadOnly(False)
            sp.setButtonSymbols(QSpinBox.UpDownArrows)
        for w in (self.stock_me, self.stock_en):
            w.setReadOnly(False)
        self.edit_note.clear()
        self.edit_bar.show()
        self.board.update()

    def cancel_correction(self):
        self.edit_rec = None
        self.board.editable = False
        for sp in self.kopf.values():
            sp.setReadOnly(True)
            sp.setButtonSymbols(QSpinBox.NoButtons)
        for w in (self.stock_me, self.stock_en):
            w.setReadOnly(True)
        self.edit_bar.hide()
        if self.rec is not None:
            self.board.set_record(self.rec, self.names_for(self.stem))
            self.fill_kopf(self.rec["kopf"])

    def save_correction(self):
        if self.edit_rec is None:
            return
        names = self.names_for(self.stem)
        corrected = {"kopf": dict(self.edit_rec["kopf"])}
        for key, sp in self.kopf.items():
            corrected["kopf"][key] = sp.value()
        corrected["kopf"]["kontingent_ich"] = self.stock_me.text()
        corrected["kopf"]["kontingent_gegner"] = self.stock_en.text()
        for side in ("ich", "gegner"):
            out = []
            for p in self.edit_rec[side]:
                q = dict(p)
                col = q.get("color")
                if col and col not in COLOR_NAMES:
                    q["color"] = names[side].get(col, "?" + col.lstrip("?~#"))
                out.append(q)
            corrected[side] = out
        corrected["farben"] = names
        erkannt = dict(self.rec, farben=names)
        path = boardio.save_correction(self.stem, erkannt, korrigiert=corrected, notiz=self.edit_note.toPlainText())
        self.on_log(f"> Korrektur gespeichert: {path}")
        self.cancel_correction()
        self.refresh_history()

    def report_move(self):
        if self.rec is None:
            return
        dlg = MoveDialog(self, self.rec)
        if dlg.exec() != QDialog.Accepted:
            return
        zug = dlg.feedback()
        zug["vorschlag"] = self.rec.get("plan", {}).get("aktionen", [])
        zug["vorschlag_text"] = self.rec.get("plan", {}).get("zeilen", [])
        path = boardio.save_correction(self.stem, dict(self.rec, farben=self.names_for(self.stem)), zug=zug,
                                       notiz=zug.get("notiz", ""))
        self.on_log(f"> Zug-Feedback gespeichert: {path}")
        self.refresh_history()

    # ---- Overlay / Log / Einstellungen
    def on_log(self, text):
        self.log.appendPlainText(text)
        t = text.lower()
        if "spielfenster:" in t:
            self.status.setText("Overlay läuft – " + text.split(":", 1)[1].strip())
        elif "analyse gestartet" in t:
            self.status.setText("Analysiere ...")
        elif text.strip().startswith("[") and "vorschlag" in t:
            self.status.setText("Vorschlag fertig")
        elif "controller:" in t:
            self.status.setText(f"Bereit – {text.split(':', 1)[1].strip()}")

    def on_running(self, on):
        self.act_start.setEnabled(not on)
        self.act_stop.setEnabled(on)
        if not on:
            self.status.setText("Overlay aus")

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.values()
            save_json(SETTINGS, self.settings)
            if self.overlay.is_running():
                QMessageBox.information(self, "Einstellungen", "Gespeichert. Gilt nach Neustart des Overlays.")

    def closeEvent(self, ev):
        self.overlay.stop()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CoH-Berater")
    app.setStyle("Fusion")
    pal = app.palette()
    from PySide6.QtGui import QPalette
    for role, col in ((QPalette.Window, "#1e2026"), (QPalette.WindowText, "#e6e6e6"), (QPalette.Base, "#16181d"),
                      (QPalette.AlternateBase, "#22252c"), (QPalette.Text, "#e6e6e6"), (QPalette.Button, "#2a2e36"),
                      (QPalette.ButtonText, "#e6e6e6"), (QPalette.Highlight, "#3d7fd9"),
                      (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, "#2a2e36"),
                      (QPalette.ToolTipText, "#e6e6e6")):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    win = MainWindow()
    win.show()
    if "--start" in sys.argv:
        win.overlay.start(win.settings)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
