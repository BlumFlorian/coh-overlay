"""Datensammler: Speichert Screenshots des Spielfensters, wenn L1 (Controller) oder F9 gedrueckt wird.

Rein passiv: liest nur Bildschirmpixel (wie OBS) und den Controller-Zustand (wie Steam/DS4Windows).
Kein Zugriff auf den Spielprozess, keine Eingaben ans Spiel.

Pro Ausloesung entstehen zwei Bilder:
  *_board.png  -- unmittelbar beim Druecken (normales Brett)
  *_info.png   -- nach --delay Sekunden (Werte-Ansicht, die L1 im Spiel einblendet)
So entstehen Paare "Brett ohne / mit Zahlen" fuer Kalibrierung und Erkennung.

  python tools/capture.py                 # normaler Betrieb
  python tools/capture.py --learn         # zeigt gedrueckte Controller-Tasten (Button-Index finden)
  python tools/capture.py --test          # ein Testbild (Spielfenster oder Hauptmonitor)
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")  # Controller auch ohne Fokus lesen
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import mss  # noqa: E402
import mss.tools  # noqa: E402
import pygame  # noqa: E402

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # echte Pixel statt skalierter Koordinaten
except OSError:
    user32.SetProcessDPIAware()

VK_F9 = 0x78
DEFAULT_TITLE = "Clash of Heroes"
OUT = Path(__file__).resolve().parent.parent / "dataset"


kernel32 = ctypes.windll.kernel32


def process_name(hwnd) -> str:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return "?"
    buf = ctypes.create_unicode_buffer(260)
    size = wt.DWORD(260)
    kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    kernel32.CloseHandle(h)
    return Path(buf.value).name


BROWSERS = {"chrome.exe", "opera.exe", "firefox.exe", "msedge.exe", "explorer.exe", "code.exe", "steam.exe",
            "steamwebhelper.exe", "discord.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
            "conhost.exe", "claude.exe", "node.exe", "codium.exe"}


def find_window(title_part: str):
    """Sucht das Spielfenster per Titel; Browser-Tabs u. ae. mit gleichem Titel werden uebersprungen."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title_part.lower() in buf.value.lower() and process_name(hwnd).lower() not in BROWSERS:
                found.append((hwnd, f"{buf.value} [{process_name(hwnd)}]"))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def client_rect(hwnd) -> dict | None:
    r = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    if r.right <= 0 or r.bottom <= 0:
        return None
    return {"left": pt.x, "top": pt.y, "width": r.right, "height": r.bottom}


def grab(sct, region: dict, path: Path):
    img = sct.grab(region)
    mss.tools.to_png(img.rgb, img.size, output=str(path))


def open_controller():
    pygame.init()
    from pygame._sdl2 import controller
    controller.init()
    for i in range(controller.get_count()):
        if controller.is_controller(i):
            c = controller.Controller(i)
            return c, c.name
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default=DEFAULT_TITLE, help="Teil des Fenstertitels")
    ap.add_argument("--delay", type=float, default=0.6, help="Sekunden bis zum Info-Bild")
    ap.add_argument("--learn", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    hwnd, title = find_window(args.title)
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    with (mss.MSS() if hasattr(mss, "MSS") else mss.mss()) as sct:
        if args.test:
            region = client_rect(hwnd) if hwnd else sct.monitors[1]
            OUT.mkdir(parents=True, exist_ok=True)
            p = OUT / "test.png"
            grab(sct, region, p)
            print(f"Fenster: {title or '(nicht gefunden, Hauptmonitor)'}  Region: {region}\nGespeichert: {p}")
            return

        pad, name = open_controller()
        print(f"Controller: {name or 'keiner gefunden (nur F9)'}")
        print(f"Spielfenster: {title or 'noch nicht gefunden'}")
        if args.learn:
            print("Druecke Tasten am Controller (Strg+C beendet) ...")
        else:
            print(f"L1 oder F9 -> Screenshot-Paar nach {OUT}   (Strg+C beendet)")

        prev_l1 = prev_f9 = False
        prev_buttons: set[int] = set()
        count = 0
        while True:
            pygame.event.pump()
            l1 = bool(pad and pad.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER))
            f9 = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
            if args.learn and pad:
                now = {b for b in range(21) if pad.get_button(b)}
                for b in now - prev_buttons:
                    print(f"Taste gedrueckt: SDL-Controller-Button {b}"
                          f"{'  (= L1)' if b == pygame.CONTROLLER_BUTTON_LEFTSHOULDER else ''}")
                prev_buttons = now
            elif (l1 and not prev_l1) or (f9 and not prev_f9):
                if not hwnd:
                    hwnd, title = find_window(args.title)
                region = client_rect(hwnd) if hwnd else None
                if region is None:
                    print("Spielfenster nicht gefunden -- laeuft das Spiel (borderless)?")
                else:
                    day = OUT / datetime.now().strftime("%Y-%m-%d")
                    day.mkdir(parents=True, exist_ok=True)
                    stem = datetime.now().strftime("%H%M%S_%f")[:-3]
                    grab(sct, region, day / f"{stem}_board.png")
                    # Die Werte-Ansicht erscheint nur, solange L1 gehalten wird.
                    t_end = time.time() + args.delay
                    held = True
                    while time.time() < t_end:
                        pygame.event.pump()
                        if l1 and not pad.get_button(pygame.CONTROLLER_BUTTON_LEFTSHOULDER):
                            held = False
                            break
                        time.sleep(0.01)
                    if not held:
                        print("  L1 zu kurz gedrueckt -- bitte ca. 1 Sekunde halten. Nur Brett gespeichert.")
                    else:
                        grab(sct, region, day / f"{stem}_info.png")
                    (day / f"{stem}.json").write_text(json.dumps(
                        {"trigger": "L1" if l1 else "F9", "region": region, "window": title,
                         "time": datetime.now().isoformat()}, indent=1), encoding="utf-8")
                    count += 1
                    print(f"[{count}] gespeichert: {day.name}/{stem}_*.png")
            prev_l1, prev_f9 = l1, f9
            time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
