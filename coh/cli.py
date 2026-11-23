"""Kommandozeile:  python -m coh.cli <brett.txt> [--beam 80] [--time 20] [--top 3] [--steps]"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .model import parse_state, render_state
from .rules import apply_action
from .solver import describe, solve


def main(argv=None):
    ap = argparse.ArgumentParser(description="Clash of Heroes Zug-Berater (Simulator + Solver)")
    ap.add_argument("board", type=Path)
    ap.add_argument("--beam", type=int, default=80)
    ap.add_argument("--time", type=float, default=20.0)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--horizon", type=int, default=5, help="Runden Vorausschau")
    ap.add_argument("--steps", action="store_true", help="Brett nach jedem Schritt zeigen")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    state = parse_state(args.board.read_text(encoding="utf-8"))
    print(render_state(state, compact=True))
    t0 = time.time()
    plans = solve(state, beam=args.beam, time_limit=args.time, top=args.top, horizon=args.horizon)
    print(f"\nSuche: {time.time() - t0:.1f}s\n")
    for i, plan in enumerate(plans, 1):
        dealt = plan.details.get("dealt", [])
        taken = plan.details.get("taken", [])
        print(f"=== Vorschlag {i}  (Score {plan.score:.1f}) | Schaden je Runde {dealt} | erlitten {taken}")
        s = state
        for a in plan.actions:
            print("  " + describe(a, s))
            s, extra = apply_action(s, a)
            if extra:
                print(f"    -> Chain! +{extra} Zug")
            if args.steps:
                print(render_state(s, compact=True))
        if not plan.actions:
            print("  (keine Aktion besser als Passen)")
        if not args.steps and i == 1:
            print("\nBrett danach:")
            print(render_state(plan.state, compact=True))
        print()


if __name__ == "__main__":
    main()
