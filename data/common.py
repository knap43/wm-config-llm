"""Vocabulary and phrasing helpers shared by the Sway and Hyprland generators."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


@dataclass
class App:
    name: str          # how people say it
    cmd: str           # what to execute
    app_id: str        # Wayland app_id / Hyprland class (exact)
    kind: str          # terminal, browser, files, launcher, other
    x11: bool = False  # runs under XWayland (Sway matches on class, not app_id)


APPS = [
    App("kitty", "kitty", "kitty", "terminal"),
    App("foot", "foot", "foot", "terminal"),
    App("alacritty", "alacritty", "Alacritty", "terminal"),
    App("wezterm", "wezterm", "org.wezfurlong.wezterm", "terminal"),
    App("ghostty", "ghostty", "com.mitchellh.ghostty", "terminal"),
    App("gnome terminal", "gnome-terminal", "org.gnome.Terminal", "terminal"),
    App("konsole", "konsole", "org.kde.konsole", "terminal"),
    App("firefox", "firefox", "firefox", "browser"),
    App("chromium", "chromium", "chromium", "browser"),
    App("brave", "brave", "brave-browser", "browser"),
    App("librewolf", "librewolf", "librewolf", "browser"),
    App("nautilus", "nautilus", "org.gnome.Nautilus", "files"),
    App("thunar", "thunar", "thunar", "files"),
    App("dolphin", "dolphin", "org.kde.dolphin", "files"),
    App("nemo", "nemo", "nemo", "files"),
    App("pcmanfm", "pcmanfm", "pcmanfm", "files"),
    App("pavucontrol", "pavucontrol", "org.pulseaudio.pavucontrol", "other"),
    App("mpv", "mpv", "mpv", "other"),
    App("imv", "imv", "imv", "other"),
    App("steam", "steam", "steam", "other", True),
    App("spotify", "spotify", "Spotify", "other", True),
    App("thunderbird", "thunderbird", "thunderbird", "other"),
    App("obs", "obs", "com.obsproject.Studio", "other"),
    App("keepassxc", "keepassxc", "org.keepassxc.KeePassXC", "other"),
    App("vs code", "code", "code", "other"),
    App("gimp", "gimp", "gimp", "other"),
    App("gnome calculator", "gnome-calculator", "org.gnome.Calculator", "other"),
    App("blueman", "blueman-manager", "blueman-manager", "other"),
    App("network manager editor", "nm-connection-editor", "nm-connection-editor", "other"),
    App("telegram", "telegram-desktop", "org.telegram.desktop", "other"),
    App("vesktop", "vesktop", "vesktop", "other"),
    App("signal", "signal-desktop", "signal", "other"),
    App("zathura", "zathura", "org.pwmt.zathura", "other"),
    App("btop", "btop", "btop", "tui"),
]

LAUNCHERS = [
    ("rofi", "rofi -show drun"),
    ("wofi", "wofi --show drun"),
    ("fuzzel", "fuzzel"),
    ("tofi", "tofi-drun --drun-launch=true"),
    ("bemenu", "bemenu-run"),
    ("wmenu", "wmenu-run"),
]

KIND_WORDS = {
    "terminal": ["terminal", "terminal emulator", "term"],
    "browser": ["browser", "web browser"],
    "files": ["file manager", "files app", "file browser"],
    "launcher": ["app launcher", "launcher", "application menu", "run menu", "app menu"],
}

FLOATY = ["pavucontrol", "gnome calculator", "blueman", "network manager editor", "keepassxc", "imv", "mpv"]

COLORS = {
    "red": "f38ba8", "blue": "89b4fa", "green": "a6e3a1", "yellow": "f9e2af",
    "orange": "fab387", "purple": "cba6f7", "pink": "f5c2e7", "teal": "94e2d5",
    "cyan": "89dceb", "white": "ffffff", "black": "000000", "grey": "585b70",
    "gray": "585b70", "lavender": "b4befe",
}

THEMES = {
    "catppuccin": ("cba6f7", "585b70"),
    "nord": ("88c0d0", "4c566a"),
    "gruvbox": ("fe8019", "504945"),
    "dracula": ("bd93f9", "44475a"),
    "tokyo night": ("7aa2f7", "414868"),
    "everforest": ("a7c080", "475258"),
    "rose pine": ("ebbcba", "403d52"),
}

DIRECTIONS = ["left", "right", "up", "down"]
VIM = {"left": "h", "down": "j", "up": "k", "right": "l"}

# Keys a person may name, as (spoken form, canonical key name). The canonical
# name is lower case except for multi-letter keys, which use the X keysym spelling.
LETTERS = list("abcdefgimnopqrstuvwxyz")
FREE_KEYS = [(c, c) for c in LETTERS] + [
    ("enter", "Return"), ("return", "Return"), ("space", "space"), ("tab", "Tab"),
    ("escape", "Escape"), ("backspace", "BackSpace"), ("f1", "F1"), ("f2", "F2"),
    ("f5", "F5"), ("f12", "F12"), ("comma", "comma"), ("period", "period"),
    ("slash", "slash"), ("grave", "grave"), ("minus", "minus"), ("equal", "equal"),
]

MOD_SPOKEN = {
    "SUPER": ["super", "Super", "SUPER", "win", "the windows key", "mod", "Mod", "logo"],
    "ALT": ["alt", "Alt", "ALT"],
    "CTRL": ["ctrl", "Ctrl", "control", "CTRL"],
    "SHIFT": ["shift", "Shift", "SHIFT"],
}


def spoken_combo(rng: random.Random, mods: list[str], key_spoken: str) -> str:
    """Render a key combo the way a person would type it in a request."""
    words = [rng.choice(MOD_SPOKEN[m]) for m in mods]
    k = key_spoken
    if len(k) == 1 and rng.random() < 0.5:
        k = k.upper()
    style = rng.random()
    if style < 0.55:
        return "+".join(words + [k])
    if style < 0.75:
        return " + ".join(words + [k])
    if style < 0.9:
        return "-".join(words + [k])
    return " ".join(words + [k])


# --------------------------------------------------------------------------
# Natural-language variety
# --------------------------------------------------------------------------

PREFIXES = [
    "", "", "", "", "", "please ", "can you ", "could you ", "i want to ", "i'd like to ",
    "help me ", "hey, ", "pls ", "how do i ", "i want you to ", "go ahead and ", "quick one: ",
]
SUFFIXES = ["", "", "", "", "", " please", " thanks", " pls", "?", ".", " for me", "!"]


def _typo(rng: random.Random, s: str) -> str:
    words = s.split(" ")
    idx = [i for i, w in enumerate(words) if len(w) > 4 and w.isalpha()]
    if not idx:
        return s
    i = rng.choice(idx)
    w = words[i]
    j = rng.randrange(1, len(w) - 2)
    op = rng.random()
    if op < 0.4:
        w = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    elif op < 0.7:
        w = w[:j] + w[j + 1:]
    else:
        w = w[:j] + w[j] + w[j:]
    words[i] = w
    return " ".join(words)


def vary(rng: random.Random, text: str, allow_prefix: bool = True) -> str:
    """Add surface variation: politeness, casing, punctuation, the odd typo."""
    s = text.strip()
    if allow_prefix and not re.match(r"^(how|what|why|can|could|i |i'd)", s, re.I):
        s = rng.choice(PREFIXES) + s
    s += rng.choice(SUFFIXES)
    r = rng.random()
    if r < 0.12:
        s = s.lower()
    elif r < 0.5:
        s = s[0].upper() + s[1:]
    if rng.random() < 0.06:
        s = _typo(rng, s)
    return re.sub(r"\s+", " ", s).strip()


def pick(rng: random.Random, templates: list[str], **kw) -> str:
    return rng.choice(templates).format(**kw)


# --------------------------------------------------------------------------
# Example container
# --------------------------------------------------------------------------

@dataclass
class Change:
    """One logical edit: lines to add, with the slots they occupy.

    A slot identifies what a managed line controls (e.g. "cfg:general.gaps_in"
    or "bind:SUPER+T"). When a new change claims a slot, managed lines with the
    same slot are deleted first, which keeps the managed file free of stale
    duplicates.
    """
    summary: str
    adds: list[tuple[str, str]] = field(default_factory=list)   # (slot, line)
    dels_by_slot: list[str] = field(default_factory=list)       # slots to clear without re-adding
    dels_lines: list[str] = field(default_factory=list)         # exact managed lines to delete
    ref: str = ""                                               # how a later request refers to it
    evidence: list[str] = field(default_factory=list)           # main-config lines the answer relies on


@dataclass
class Sample:
    wm: str
    request: str
    change: Change
    family: str
