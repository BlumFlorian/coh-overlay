"""Spielfenster finden und aufnehmen (rein lesend, wie OBS)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from pathlib import Path

import numpy as np

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

DEFAULT_TITLE = "Clash of Heroes"
IGNORED_EXES = {"chrome.exe", "opera.exe", "firefox.exe", "msedge.exe", "explorer.exe", "code.exe", "steam.exe",
                "steamwebhelper.exe", "discord.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
                "conhost.exe", "claude.exe", "node.exe", "codium.exe", "python.exe", "pythonw.exe"}


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except OSError:
        user32.SetProcessDPIAware()


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


def find_window(title_part: str = DEFAULT_TITLE):
    """Sucht das Spielfenster per Titel; Browser, Terminals usw. mit gleichem Titel werden uebersprungen."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title_part.lower() in buf.value.lower():
                exe = process_name(hwnd)
                if exe.lower() not in IGNORED_EXES:
                    found.append((hwnd, f"{buf.value} [{exe}]"))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def client_rect(hwnd) -> dict | None:
    r = wt.RECT()
    if not hwnd or not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    if r.right <= 0 or r.bottom <= 0:
        return None
    return {"left": pt.x, "top": pt.y, "width": r.right, "height": r.bottom}


def new_grabber():
    import mss
    return mss.MSS() if hasattr(mss, "MSS") else mss.mss()


def grab_array(sct, region: dict) -> np.ndarray:
    """RGB-Array der Region."""
    img = sct.grab(region)
    return np.frombuffer(img.rgb, np.uint8).reshape(img.height, img.width, 3)
