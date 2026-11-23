"""Lokale Asset-Sammlung: wie sehen Einheiten idle / als ladende Formation aus?

Ablage (alles einfache Dateien):
  dataset/assets/index.json          Kennungen, Herz-Zahl, Merkmale, optional Name
  dataset/assets/<id>/<zustand>_*.png Bildausschnitte (Zustand: idle, geladen)

Jede Einheitenklasse (Typ + Farbe) bekommt eine dauerhafte Kennung (u001, ...), wiedererkannt
ueber das Farbhistogramm des Rumpfs und die Herz-Zahl. Gespeichert wird nur bei sicherer Zuordnung.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent / "dataset" / "assets"
MATCH = 0.62  # gleiche Schwelle wie beim Clustering
MAX_FEATS = 60  # gespeicherte Merkmalsvektoren je Kennung und Zustand
MAX_PNGS = 40  # gespeicherte Bilder je Kennung und Zustand


class AssetLib:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.file = root / "index.json"
        self.data: dict = {"units": {}}
        if self.file.exists():
            try:
                self.data = json.loads(self.file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        # Von Hand gepflegte Einheitentypen (eigene Datei: index.json schreibt das Overlay laufend neu)
        self.names: dict = {}
        try:
            self.names = {k: v for k, v in json.loads((root / "names.json").read_text(encoding="utf-8")).items()
                          if not k.startswith("_")}
        except (OSError, json.JSONDecodeError):
            pass

    # ------------------------------------------------------------------ Zugriff
    def units(self) -> dict:
        return self.data.setdefault("units", {})

    def _feats(self, uid: str, state: str) -> np.ndarray | None:
        f = self.units()[uid].get("feats", {}).get(state)
        return np.array(f, np.float32) if f else None

    def name(self, uid: str) -> str:
        return self.names.get(uid) or self.units().get(uid, {}).get("name") or uid

    def match(self, feat: np.ndarray, tough: int | None, state: str = "idle") -> tuple[str | None, float]:
        """Naechste Kennung (mittlere Distanz zu den gespeicherten Merkmalen dieses Zustands)."""
        best, bd = None, 9.0
        for uid, u in self.units().items():
            if state == "idle" and tough is not None and u.get("tough") not in (None, tough):
                continue
            F = self._feats(uid, state)
            if F is None:
                continue
            ds = np.sort(np.abs(F - feat).sum(1))
            d = float(np.median(ds[:5]))  # naechste Beispiele zaehlen (Animationen, Leuchten variieren)
            if d < bd:
                best, bd = uid, d
        return best, bd

    def match_or_create(self, feat: np.ndarray, tough: int | None, tier: str = "core",
                        exclude: set = frozenset(), create: bool = True) -> str | None:
        best, bd = None, 9.0
        for uid in self.units():
            if uid in exclude:
                continue
            u = self.units()[uid]
            if tough is not None and u.get("tough") not in (None, tough):
                continue
            F = self._feats(uid, "idle")
            if F is None:
                continue
            d = float(np.median(np.sort(np.abs(F - feat).sum(1))[:5]))
            if d < bd:
                best, bd = uid, d
        if best is not None and bd < MATCH:
            return best
        if not create:
            return None
        uid = f"u{len(self.units()) + 1:03d}"
        self.units()[uid] = {"tough": tough, "tier": tier, "name": None, "feats": {}, "count": {}}
        return uid

    # ------------------------------------------------------------------ Schreiben
    def add(self, uid: str, state: str, feat: np.ndarray, crop: np.ndarray | None = None) -> None:
        u = self.units()[uid]
        feats = u.setdefault("feats", {}).setdefault(state, [])
        feats.append([round(float(x), 4) for x in feat])
        del feats[:-MAX_FEATS]
        cnt = u.setdefault("count", {})
        cnt[state] = cnt.get(state, 0) + 1
        if crop is not None and cnt[state] <= MAX_PNGS:
            d = self.root / uid
            d.mkdir(parents=True, exist_ok=True)
            Image.fromarray(crop.astype(np.uint8)).save(d / f"{state}_{datetime.now():%Y%m%d_%H%M%S_%f}.png")

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        tmp.replace(self.file)
