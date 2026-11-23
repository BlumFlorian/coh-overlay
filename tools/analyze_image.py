"""Erkennung auf einem gespeicherten L1-Screenshot testen und ein Debug-Bild schreiben.

  python tools/analyze_image.py dataset/<Datum>/<stem>_info.png [--out debug.png] [--solve]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coh.model import COLS, ROWS, render_state  # noqa: E402
from coh.vision import analyze  # noqa: E402

COLORS = ["#ff4040", "#40ff40", "#4080ff", "#ffff40", "#ff40ff", "#40ffff", "#ff9040", "#a0a0ff", "#ffffff"]


def draw_debug(img: Image.Image, state, meta) -> Image.Image:
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arialbd.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    geo = meta["geo"]
    for who, side in (("me", state.me), ("enemy", state.enemy)):
        for p in side.pieces:
            boxes = [geo.cell_box(who, c, r) for c, r in p.cells()]
            x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
            x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
            if p.kind == "unit":
                col = COLORS["abcdefghi".index(p.color) % len(COLORS)] if p.color in "abcdefghi" else "#ffffff"
                label = p.color.upper()
            elif p.kind == "wall":
                col, label = "#00e0ff", "W"
            else:
                col, label = ("#ff8000", "F") if p.merged else ("#c0c0c0", "X")
            d.rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], outline=col, width=3)
            d.text((x1 - 26, y0 + 6), label, fill=col, font=font, stroke_width=2, stroke_fill="black")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--solve", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    img = Image.open(args.image)
    state, meta = analyze(np.asarray(img.convert("RGB")))
    print(render_state(state, compact=True))
    out = args.out or args.image.with_name(args.image.stem + "_debug.png")
    draw_debug(img, state, meta).save(out)
    print(f"Debug-Bild: {out}")
    if args.solve:
        from coh.rules import apply_action
        from coh.solver import describe, solve
        plans = solve(state, time_limit=8)
        s = state
        for a in plans[0].actions:
            print("  " + describe(a, s))
            s, _ = apply_action(s, a)


if __name__ == "__main__":
    main()
