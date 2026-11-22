"""Sway 1.12 sample families.

Every directive form used here was checked with `sway -C`; bound commands are
additionally executed in a headless Sway at build time (see data/build.py).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from data.common import (APPS, COLORS, DIRECTIONS, FLOATY, FREE_KEYS, KIND_WORDS, LAUNCHERS, MOD_SPOKEN, THEMES,
                         VIM, Change, pick, vary)
from wmllm.context import combo_of_line, flatten_sway, sway_mod_value

DEFAULT_CONFIG = Path("/etc/sway/config")
WM = "sway"
INCLUDE_TOKEN = "@MANAGED@"

# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

SWAY_KEYNAMES = {"left": "Left", "right": "Right", "up": "Up", "down": "Down"}


def skey(mods: list[str], key: str, modv: str) -> str:
    """Render a combo as Sway writes it. mods are logical: SUPER/ALT/CTRL/SHIFT."""
    out = []
    if modv in mods:
        out.append("$mod")
    if "SUPER" in mods and modv != "SUPER":
        out.append("Mod4")
    if "ALT" in mods and modv != "ALT":
        out.append("Mod1")
    if "CTRL" in mods:
        out.append("Ctrl")
    if "SHIFT" in mods:
        out.append("Shift")
    k = key.lower() if len(key) == 1 else SWAY_KEYNAMES.get(key, key)
    return "+".join(out + [k])


def combo_id(mods: list[str], key: str) -> str:
    k = key.lower()
    k = {"enter": "return", "esc": "escape"}.get(k, k)
    return "+".join(sorted(mods)) + "+" + k


def combo_id_from_line(line: str, modv: str) -> str | None:
    c = combo_of_line(WM, line, modv)
    if c is None:
        return None
    mods, key = c
    return "+".join(sorted(mods)) + "+" + key


def spoken(rng: random.Random, mods: list[str], key_spoken: str, modv: str) -> str:
    words = []
    for m in mods:
        if m == modv and rng.random() < 0.6:
            words.append(rng.choice(["mod", "$mod", "Mod"]))
        else:
            words.append(rng.choice([w for w in MOD_SPOKEN[m] if w.lower() != "mod"]))
    k = key_spoken.upper() if len(key_spoken) == 1 and rng.random() < 0.4 else key_spoken
    sep = rng.choice(["+", "+", "+", " + ", "-"])
    return sep.join(words + [k])


# --------------------------------------------------------------------------
# Worlds
# --------------------------------------------------------------------------

TERMINAL_CMDS = [a.cmd for a in APPS if a.kind == "terminal"]
MENU_CMDS = ["wmenu-run"] + [c for _, c in LAUNCHERS]
AUTOSTART_POOL = ["waybar", "mako", "swaync", "nm-applet --indicator", "blueman-applet", "autotiling",
                  "wl-paste --watch cliphist store", "udiskie", "kanshi", "/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1",
                  "fcitx5 -d", "gammastep"]


@dataclass
class SwayWorld:
    text: str
    flat: list[str]
    modv: str          # "SUPER" or "ALT": what $mod means
    terminal: str
    menu: str

    def value_line(self, prefix: str, managed) -> tuple[str | None, bool]:
        """Last line starting with prefix (managed first)."""
        for e in reversed(managed):
            if e.line.startswith(prefix):
                return e.line, False
        for l in reversed(self.flat):
            if l.startswith(prefix):
                return l, True
        return None, True

    def main_bind(self, cid: str) -> str | None:
        for l in self.flat:
            if (l.startswith("bindsym ") or l.startswith("bindsym --")) and combo_id_from_line(l, self.modv) == cid:
                return l
        return None

    def main_binds_exec(self, cmd_or_var: str) -> list[str]:
        return [l for l in self.flat if l.startswith("bindsym") and re.search(rf"\bexec {re.escape(cmd_or_var)}$", l)]


def _mutate(rng: random.Random, base: str) -> tuple[str, dict]:
    t = base
    modv = "SUPER"
    if rng.random() < 0.1:
        t = t.replace("set $mod Mod4", "set $mod Mod1")
        modv = "ALT"
    term = rng.choice(TERMINAL_CMDS)
    menu = rng.choice(MENU_CMDS)
    t = t.replace("set $term foot", f"set $term {term}")
    t = t.replace("set $menu wmenu-run", f"set $menu {menu}")
    extra = []
    if rng.random() < 0.6:
        extra.append(f"gaps inner {rng.choice([0, 2, 4, 5, 6, 8, 10])}")
    if rng.random() < 0.4:
        extra.append(f"gaps outer {rng.choice([0, 2, 4, 5, 8])}")
    if rng.random() < 0.5:
        extra.append(f"default_border pixel {rng.choice([1, 2, 2, 3])}")
    if rng.random() < 0.3:
        extra.append("smart_gaps on")
    if rng.random() < 0.4:
        extra.append(f"font pango:{rng.choice(['monospace', 'Noto Sans', 'JetBrains Mono', 'Inter'])} {rng.choice([9, 10, 11, 12])}")
    if rng.random() < 0.5:
        extra.append("input type:touchpad {\n    tap enabled\n    natural_scroll " + rng.choice(["enabled", "disabled"]) + "\n    dwt enabled\n}")
    if rng.random() < 0.5:
        lay = rng.choice(["us", "us", "us", "de", "gb", "fr", "us,de", "pl"])
        extra.append(f'input type:keyboard {{\n    xkb_layout "{lay}"\n}}')
    if rng.random() < 0.3:
        extra.append(f"output eDP-1 scale {rng.choice(['1', '1.25', '1.5', '2'])}")
    for c in rng.sample(AUTOSTART_POOL, rng.choice([0, 0, 1, 2, 3])):
        extra.append(f"exec {c}")
    if rng.random() < 0.4:
        extra.append(f"bindsym $mod+b exec {rng.choice(['firefox', 'chromium', 'brave', 'librewolf'])}")
    if rng.random() < 0.25:
        extra.append('for_window [app_id="org.pulseaudio.pavucontrol"] floating enable')
    if rng.random() < 0.25:
        extra.append("focus_follows_mouse no")
    if rng.random() < 0.2:
        t = re.sub(r"\n\s*bindsym --locked XF86.*", "", t)
    if extra:
        t = t.replace("include /etc/sway/config.d/*", "\n".join(extra) + "\n\ninclude /etc/sway/config.d/*")
    return t, {"modv": modv, "terminal": term, "menu": menu}


MINIMAL = """# {comment}
set $mod {modsym}
set $term {term}
set $menu {menu}

output * bg #1e1e2e solid_color
gaps inner {gi}
default_border pixel {bs}
input type:keyboard xkb_layout {kb}

exec waybar

bindsym $mod+Return exec $term
bindsym $mod+d exec $menu
bindsym $mod+q kill
bindsym $mod+f fullscreen toggle
bindsym $mod+Shift+space floating toggle
bindsym $mod+Shift+r reload
bindsym $mod+h focus left
bindsym $mod+j focus down
bindsym $mod+k focus up
bindsym $mod+l focus right
bindsym $mod+1 workspace number 1
bindsym $mod+2 workspace number 2
bindsym $mod+3 workspace number 3
bindsym $mod+Shift+1 move container to workspace number 1
bindsym $mod+Shift+2 move container to workspace number 2
bindsym $mod+Shift+3 move container to workspace number 3
floating_modifier $mod normal

bar {{
    swaybar_command waybar
}}
"""


def build_worlds(n: int, seed: int = 1) -> list[SwayWorld]:
    rng = random.Random(seed)
    base = DEFAULT_CONFIG.read_text()
    worlds = []
    for _ in range(n):
        if rng.random() < 0.15:
            modv = "SUPER"
            term, menu = rng.choice(TERMINAL_CMDS), rng.choice(MENU_CMDS)
            text = MINIMAL.format(comment=rng.choice(["sway config", "my minimal sway setup"]), modsym="Mod4", term=term,
                                  menu=menu, gi=rng.choice([0, 4, 6, 8]), bs=rng.choice([1, 2, 3]), kb=rng.choice(["us", "de", "gb"]))
            params = {"modv": modv, "terminal": term, "menu": menu}
        else:
            text, params = _mutate(rng, base)
        text = text.rstrip() + f"\n\n# Managed by wmai (keep this last)\ninclude {INCLUDE_TOKEN}\n"
        flat = [l for l in flatten_sway(text) if INCLUDE_TOKEN not in l]
        worlds.append(SwayWorld(text, flat, **params))
    return worlds


# --------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------

def _num_from(line: str | None, rx: str):
    if not line:
        return None
    m = re.search(rx, line)
    return int(m.group(1)) if m else None


NUMS = [
    # slot, line template, regex for current value, names, lo, hi, step
    ("gaps:inner", "gaps inner {v}", r"^gaps inner (\d+)$", ["inner gaps", "the gaps between windows", "the inner gap"], 0, 30, 3),
    ("gaps:outer", "gaps outer {v}", r"^gaps outer (\d+)$", ["outer gaps", "the gaps at the screen edges", "the outer gap"], 0, 40, 4),
    ("border:default", "default_border pixel {v}", r"^default_border pixel (\d+)$", ["the border width", "border size", "window border thickness"], 0, 8, 1),
    ("border:floating", "default_floating_border pixel {v}", r"^default_floating_border pixel (\d+)$", ["the floating window border width"], 0, 8, 1),
    ("input:keyboard:repeat_rate", "input type:keyboard repeat_rate {v}", r"repeat_rate (\d+)$", ["the key repeat rate", "keyboard repeat rate"], 15, 80, 10),
    ("input:keyboard:repeat_delay", "input type:keyboard repeat_delay {v}", r"repeat_delay (\d+)$", ["the key repeat delay", "the delay before keys repeat"], 150, 800, 100),
    ("seat:hide_cursor", "seat * hide_cursor {v}", r"^seat \* hide_cursor (\d+)$", ["the cursor hide timeout in ms", "how long before the cursor hides (ms)"], 1000, 10000, 1000),
    ("titlebar_padding", "titlebar_padding {v}", r"^titlebar_padding (\d+)", ["titlebar padding"], 1, 12, 2),
]


def fam_num(rng, W: SwayWorld, managed):
    slot, tmpl, rx, names, lo, hi, step = rng.choice(NUMS)
    name = rng.choice(names)
    prefix = tmpl.split("{v}")[0]
    line, from_main = W.value_line(prefix, managed)
    cur = _num_from(line, rx)
    ev = []
    if cur is not None and rng.random() < 0.45:
        up = rng.random() < 0.5
        if (up and cur >= hi) or (not up and cur <= lo):
            up = not up
        mult = 2 if rng.random() < 0.25 else 1
        new = min(hi, max(lo, cur + (step if up else -step) * mult))
        if new == cur:
            return None
        if mult == 2:
            req = pick(rng, ["make {n} a lot bigger", "increase {n} a lot", "{n} is way too small"] if up else
                       ["make {n} a lot smaller", "decrease {n} a lot", "{n} is way too big"], n=name)
        else:
            req = pick(rng, ["make {n} bigger", "increase {n}", "bump up {n}", "{n} is too small", "more {n}"] if up else
                       ["make {n} smaller", "decrease {n}", "reduce {n}", "{n} is too big", "less {n}"], n=name)
        summary = f"{'Increase' if up else 'Decrease'} {prefix.strip()} from {cur} to {new}"
        if from_main:
            ev = [line]
    else:
        new = rng.randrange(lo, hi + 1, step if step > 1 and lo % step == 0 else 1)
        req = pick(rng, ["set {n} to {v}", "change {n} to {v}", "{n} {v}", "make {n} {v}", "use {v} for {n}"], n=name, v=new)
        summary = f"Set {prefix.strip()} to {new}"
    return vary(rng, req), Change(summary, [(slot, tmpl.format(v=new))], ref=f"the {name} change", evidence=ev)


TOGGLES = [
    # slot, [(line, [phrases], summary)]
    ("smart_gaps", [("smart_gaps on", ["enable smart gaps", "no gaps when there's only one window"], "Enable smart gaps"),
                    ("smart_gaps off", ["disable smart gaps", "always show gaps, even with one window"], "Disable smart gaps")]),
    ("smart_borders", [("smart_borders on", ["hide borders when there's only one window", "enable smart borders",
                                             "no outline when only one window is on screen", "remove the window border when a window is alone"], "Enable smart borders"),
                       ("smart_borders off", ["disable smart borders"], "Disable smart borders")]),
    ("hide_edge_borders", [("hide_edge_borders smart", ["hide borders at the screen edges when there's one window"], "Hide edge borders when only one window is visible"),
                           ("hide_edge_borders none", ["show borders at the screen edges"], "Show edge borders")]),
    ("focus_follows_mouse", [("focus_follows_mouse no", ["disable focus follows mouse", "don't change focus when the mouse moves", "focus only on click"], "Disable focus-follows-mouse"),
                             ("focus_follows_mouse yes", ["enable focus follows mouse", "focus the window under the mouse"], "Enable focus-follows-mouse"),
                             ("focus_follows_mouse always", ["focus should always follow the mouse, even across workspaces"], "Always focus the window under the mouse")]),
    ("mouse_warping", [("mouse_warping none", ["don't move the mouse when focus changes", "disable mouse warping"], "Disable mouse warping"),
                       ("mouse_warping container", ["move the mouse to the focused window", "warp the cursor to the focused container"], "Warp the cursor to the focused container")]),
    ("workspace_auto_back_and_forth", [("workspace_auto_back_and_forth yes", ["pressing the current workspace's number should go back to the previous workspace", "enable workspace back and forth"], "Enable workspace back-and-forth"),
                                       ("workspace_auto_back_and_forth no", ["disable workspace back and forth"], "Disable workspace back-and-forth")]),
    ("focus_wrapping", [("focus_wrapping no", ["don't wrap focus around at the edges", "disable focus wrapping"], "Disable focus wrapping"),
                        ("focus_wrapping yes", ["wrap focus around at the edge of the workspace"], "Enable focus wrapping")]),
    ("xwayland", [("xwayland disable", ["disable xwayland", "i don't need x11 apps, turn off xwayland"], "Disable XWayland (takes effect after restarting Sway)"),
                  ("xwayland enable", ["enable xwayland", "i need x11 apps, turn xwayland back on"], "Enable XWayland (takes effect after restarting Sway)")]),
    ("focus_on_window_activation", [("focus_on_window_activation focus", ["let apps take focus when they request it"], "Focus windows that request activation"),
                                    ("focus_on_window_activation urgent", ["don't let apps steal focus, just mark them urgent"], "Mark activating windows urgent instead of focusing them")]),
    ("workspace_layout", [("workspace_layout tabbed", ["make new workspaces tabbed by default", "default to the tabbed layout"], "Use the tabbed layout for new workspaces"),
                          ("workspace_layout stacking", ["default to the stacking layout"], "Use the stacking layout for new workspaces"),
                          ("workspace_layout default", ["use normal split layout for new workspaces"], "Use the default split layout for new workspaces")]),
    ("default_orientation", [("default_orientation vertical", ["split new workspaces vertically by default"], "Default to vertical orientation"),
                             ("default_orientation horizontal", ["split new workspaces horizontally by default"], "Default to horizontal orientation")]),
    ("popup_during_fullscreen", [("popup_during_fullscreen smart", ["show popups from the fullscreen app only"], "Show popups during fullscreen only from the fullscreen app"),
                                 ("popup_during_fullscreen leave_fullscreen", ["leave fullscreen when a popup appears"], "Leave fullscreen when a popup appears")]),
    ("seat:hide_cursor_typing", [("seat * hide_cursor when-typing enable", ["hide the cursor while typing", "hide the mouse pointer when i type"], "Hide the cursor while typing"),
                                 ("seat * hide_cursor when-typing disable", ["don't hide the cursor while typing"], "Stop hiding the cursor while typing")]),
    ("input:touchpad:tap", [("input type:touchpad tap enabled", ["enable tap to click", "let me tap the touchpad to click"], "Enable tap-to-click on touchpads"),
                            ("input type:touchpad tap disabled", ["disable tap to click", "stop touchpad taps from clicking"], "Disable tap-to-click on touchpads")]),
    ("input:touchpad:natural_scroll", [("input type:touchpad natural_scroll enabled", ["enable natural scrolling on the touchpad", "reverse touchpad scrolling like a mac"], "Enable natural scrolling on touchpads"),
                                       ("input type:touchpad natural_scroll disabled", ["disable natural scrolling on the touchpad", "normal touchpad scroll direction"], "Disable natural scrolling on touchpads")]),
    ("input:touchpad:dwt", [("input type:touchpad dwt enabled", ["disable the touchpad while typing", "ignore the touchpad while i type"], "Disable the touchpad while typing"),
                            ("input type:touchpad dwt disabled", ["keep the touchpad working while typing"], "Keep the touchpad active while typing")]),
    ("input:touchpad:middle_emulation", [("input type:touchpad middle_emulation enabled", ["emulate a middle click with two-button press on the touchpad"], "Enable middle-click emulation on touchpads")]),
    ("input:touchpad:click_method", [("input type:touchpad click_method clickfinger", ["two finger click for right click", "use clickfinger instead of button areas"], "Use clickfinger click method on touchpads")]),
    ("input:pointer:natural_scroll", [("input type:pointer natural_scroll enabled", ["invert the mouse wheel", "natural scrolling for the mouse"], "Enable natural scrolling for mice"),
                                      ("input type:pointer natural_scroll disabled", ["normal mouse wheel direction"], "Disable natural scrolling for mice")]),
    ("input:pointer:accel_profile", [("input type:pointer accel_profile flat", ["disable mouse acceleration", "raw mouse input, no accel"], "Disable mouse acceleration (flat profile)"),
                                     ("input type:pointer accel_profile adaptive", ["enable mouse acceleration"], "Enable mouse acceleration (adaptive profile)")]),
    ("input:pointer:left_handed", [("input type:pointer left_handed enabled", ["left handed mouse", "swap mouse buttons for a lefty"], "Enable left-handed mode for mice")]),
    ("input:keyboard:xkb_numlock", [("input type:keyboard xkb_numlock enabled", ["turn numlock on at startup", "enable numlock by default"], "Enable numlock at startup")]),
]


def fam_toggle(rng, W: SwayWorld, managed):
    slot, choices = rng.choice(TOGGLES)
    line, phrases, summary = rng.choice(choices)
    if line in W.flat:
        if rng.random() < 0.5:
            return vary(rng, rng.choice(phrases)), Change(f"Your config already has '{line}'; nothing to change.", evidence=[line])
        return None
    return vary(rng, rng.choice(phrases)), Change(summary, [(slot, line)], ref=f"the {slot.split(':')[-1].replace('_', ' ')} setting")


def fam_titlebars(rng, W: SwayWorld, managed):
    n = rng.choice([1, 2, 2, 3])
    if rng.random() < 0.7:
        req = rng.choice(["remove the title bars", "hide window titlebars", "no title bars, just a thin border",
                          f"get rid of titlebars and use {n}px borders"])
        return vary(rng, req), Change(f"Hide title bars ({n}px pixel borders for tiled and floating windows)",
                                      [("border:default", f"default_border pixel {n}"), ("border:floating", f"default_floating_border pixel {n}")],
                                      ref="the titlebar removal")
    req = rng.choice(["bring back the title bars", "show window titlebars again"])
    return vary(rng, req), Change("Show title bars again", [("border:default", "default_border normal 2"),
                                                            ("border:floating", "default_floating_border normal 2")], ref="the titlebars")


def fam_font(rng, W: SwayWorld, managed):
    fonts = ["monospace", "Noto Sans", "JetBrains Mono", "Inter", "Fira Code", "Cantarell", "Iosevka", "Hack"]
    cur, from_main = W.value_line("font pango:", managed)
    r = rng.random()
    m = re.match(r"^font pango:(.+) (\d+)$", cur or "")
    if m and r < 0.4:
        fam, size = m.group(1), int(m.group(2))
        up = rng.random() < 0.5
        new = size + (2 if up else -1)
        req = rng.choice(["make the titlebar font bigger", "increase the font size", "bigger font"] if up else
                         ["make the font smaller", "decrease the titlebar font size"])
        return vary(rng, req), Change(f"Change the font size from {size} to {new}", [("font", f"font pango:{fam} {new}")],
                                      ref="the font change", evidence=[cur] if from_main else [])
    fam = rng.choice(fonts)
    size = rng.choice([9, 10, 11, 12, 13])
    req = pick(rng, ["set the font to {f} {s}", "use {f} at size {s} for titlebars", "change the sway font to {f}, size {s}"], f=fam, s=size)
    return vary(rng, req), Change(f"Use {fam} {size} as the font", [("font", f"font pango:{fam} {size}")], ref="the font change")


KB_LAYOUTS = {"us": "US English", "de": "German", "fr": "French", "gb": "British", "es": "Spanish", "it": "Italian",
              "ru": "Russian", "pl": "Polish", "se": "Swedish", "ua": "Ukrainian", "pt": "Portuguese", "cz": "Czech",
              "tr": "Turkish", "fi": "Finnish", "dk": "Danish", "ch": "Swiss"}
KB_OPTIONS = [("caps:escape", ["make caps lock act as escape", "caps lock should be escape"]),
              ("ctrl:nocaps", ["make caps lock another ctrl", "turn caps lock into control"]),
              ("caps:swapescape", ["swap caps lock and escape"]),
              ("compose:ralt", ["use right alt as the compose key"]),
              ("altwin:swap_alt_win", ["swap alt and super"])]


def fam_keyboard(rng, W: SwayWorld, managed):
    cur_line, from_main = W.value_line("input type:keyboard xkb_layout", managed)
    cur = cur_line.split()[-1].strip('"') if cur_line else "us"
    r = rng.random()
    if r < 0.45:
        code, lang = rng.choice(list(KB_LAYOUTS.items()))
        if code == cur:
            return None
        req = pick(rng, ["set my keyboard layout to {l}", "use the {l} keyboard layout", "switch the keyboard to {c}", "i have a {l} keyboard"], l=lang, c=code)
        return vary(rng, req), Change(f"Set the keyboard layout to {code}", [("input:keyboard:xkb_layout", f"input type:keyboard xkb_layout {code}")],
                                      ref="the keyboard layout change")
    if r < 0.7:
        code, lang = rng.choice([(c, l) for c, l in KB_LAYOUTS.items() if c not in cur.split(",")])
        opt, sp = rng.choice([("grp:alt_shift_toggle", "alt+shift"), ("grp:win_space_toggle", "super+space"), ("grp:caps_toggle", "caps lock")])
        req = pick(rng, ["add a {l} layout and let me switch with {k}", "add {c} as a second layout, toggle with {k}"], l=lang, c=code, k=sp)
        opt_line, opt_main = W.value_line("input type:keyboard xkb_options", managed)
        opts = [o for o in (opt_line.split()[-1] if opt_line else "").split(",") if o and not o.startswith("grp:")]
        ev = ([cur_line] if (cur_line and from_main) else []) + ([opt_line] if (opt_line and opt_main and opts) else [])
        return vary(rng, req), Change(f"Add the {code} layout and switch with {sp}",
                                      [("input:keyboard:xkb_layout", f"input type:keyboard xkb_layout {cur},{code}"),
                                       ("input:keyboard:xkb_options", f"input type:keyboard xkb_options {','.join(opts + [opt])}")],
                                      ref=f"the {lang} layout", evidence=ev)
    opt, phrases = rng.choice(KB_OPTIONS)
    opt_line, opt_main = W.value_line("input type:keyboard xkb_options", managed)
    opts = [o for o in (opt_line.split()[-1] if opt_line else "").split(",") if o]
    if opt in opts:
        return None
    opts = [o for o in opts if o.split(":")[0] != opt.split(":")[0]]
    return vary(rng, rng.choice(phrases)), Change(f"Add {opt} to the keyboard options",
                                                  [("input:keyboard:xkb_options", f"input type:keyboard xkb_options {','.join(opts + [opt])}")],
                                                  ref=f"the {opt} option", evidence=[opt_line] if (opt_line and opt_main and opts) else [])


def _text_on(hexv: str) -> str:
    r, g, b = int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)
    return "#1e1e2e" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


def fam_colors(rng, W: SwayWorld, managed):
    r = rng.random()
    if r < 0.6:
        if rng.random() < 0.3:
            hexv = "".join(rng.choice("0123456789abcdef") for _ in range(6))
            sp = rng.choice([f"#{hexv}", hexv])
        else:
            sp = rng.choice(list(COLORS))
            hexv = COLORS[sp]
        which = rng.choice(["focused", "unfocused"])
        what = {"focused": ["the focused window border", "the active border", "the focused window color"],
                "unfocused": ["unfocused window borders", "the inactive border color"]}[which]
        req = pick(rng, ["make {w} {c}", "set {w} to {c}", "change {w} color to {c}", "{c} {w}"], w=rng.choice(what), c=sp)
        bg = f"#{hexv}" if which == "focused" else "#1e1e2e"
        txt = _text_on(hexv) if which == "focused" else "#cdd6f4"
        line = f"client.{which} #{hexv} {bg} {txt} #{hexv} #{hexv}"
        return vary(rng, req), Change(f"Set the {which} window colors to #{hexv}", [(f"client:{which}", line)], ref=f"the {which} border color")
    theme = rng.choice(list(THEMES))
    act, ina = THEMES[theme]
    req = pick(rng, ["use {t} colors for the window borders", "make sway's window colors {t}", "theme my borders {t}"], t=theme)
    return vary(rng, req), Change(f"Use {theme} window colors", [
        ("client:focused", f"client.focused #{act} #{act} {_text_on(act)} #{act} #{act}"),
        ("client:unfocused", f"client.unfocused #{ina} #1e1e2e #cdd6f4 #{ina} #{ina}")], ref=f"the {theme} colors")


# ---------------------------------------------------------------- binds

def _mod_sets(modv):
    sets = [(["M"], 5), (["M", "SHIFT"], 3), (["M", "CTRL"], 1.5), (["M", "ALT"], 1), (["CTRL", "ALT"], 0.7)]
    out = []
    for mods, w in sets:
        ms = [modv if m == "M" else m for m in mods]
        if len(set(ms)) != len(ms):
            continue
        out.append((ms, w))
    return out


def _pick_combo(rng, W: SwayWorld, prefer_bound=0.3):
    if rng.random() < prefer_bound:
        cands = [l for l in W.flat if re.match(r"^bindsym \$mod\+(Shift\+)?[a-z0-9]\s", l)]
        if cands:
            l = rng.choice(cands)
            k = re.match(r"^bindsym (\S+)", l).group(1)
            parts = k.split("+")
            mods = [W.modv] + (["SHIFT"] if "Shift" in parts else [])
            return mods, parts[-1], parts[-1]
    sets = _mod_sets(W.modv)
    x = rng.random() * sum(w for _, w in sets)
    for mods, w in sets:
        x -= w
        if x <= 0:
            break
    sp, key = rng.choice(FREE_KEYS)
    return list(mods), key, sp


def make_bind(W: SwayWorld, mods, key, command, flags=""):
    k = skey(mods, key, W.modv)
    cid = combo_id(mods, key)
    line = f"bindsym {flags}{k} {command}"
    main = W.main_bind(cid)
    if main == line:
        return None
    return [(f"bind:{cid}", line)], ([main] if main else []), main


def _repl(main):
    if not main:
        return ""
    return f" (overrides '{main.split(' ', 2)[-1]}')"


APP_REQ = ["bind {k} to open {a}", "{k} should launch {a}", "make {k} open {a}", "add a shortcut {k} for {a}", "open {a} with {k}",
           "{k} -> {a}", "launch {a} when i press {k}", "i want {k} to start {a}", "keybind {k} {a}"]


def fam_bind_app(rng, W: SwayWorld, managed):
    mods, key, ks = _pick_combo(rng, W)
    r = rng.random()
    ev_extra = []
    if r < 0.7:
        app = rng.choice([a for a in APPS if a.kind != "tui"])
        cmd, name = app.cmd, app.name
    elif r < 0.85:
        name, cmd = rng.choice(LAUNCHERS)
    else:
        app = rng.choice([a for a in APPS if a.kind == "tui"])
        cmd, name = f"$term -e {app.cmd}", f"{app.name} in my terminal"
        ev_extra = [l for l in W.flat if l.startswith("set $term ")]
    got = make_bind(W, mods, key, f"exec {cmd}")
    if got is None:
        return None
    adds, ev, main = got
    req = pick(rng, APP_REQ, k=spoken(rng, mods, ks, W.modv), a=name)
    return vary(rng, req), Change(f"Bind {skey(mods, key, W.modv)} to launch {cmd}{_repl(main)}", adds, ref=f"the {name} shortcut",
                                  evidence=ev + ev_extra)


def fam_swap_app(rng, W: SwayWorld, managed):
    kind = rng.choice(["terminal", "launcher"])
    var, old = ("$term", W.terminal) if kind == "terminal" else ("$menu", W.menu)
    setline = next((l for l in W.flat if l.startswith(f"set {var} ")), None)
    if not setline:
        return None
    if kind == "launcher":
        newname, new = rng.choice([(n, c) for n, c in LAUNCHERS if c != old])
    else:
        app = rng.choice([a for a in APPS if a.kind == "terminal" and a.cmd != old])
        newname, new = app.name, app.cmd
    req = pick(rng, ["use {n} as my {k} instead of {o}", "switch my {k} to {n}", "replace {o} with {n}", "make {n} my {k}"],
               n=newname, k=rng.choice(KIND_WORDS[kind]), o=old.split()[0])
    # `set` is evaluated in order, so redefining the variable in the managed file would be too late for binds
    # that already expanded it. Rebinding the keys that use it is what actually works.
    binds = W.main_binds_exec(var)
    if not binds:
        return None
    adds = []
    for b in binds:
        adds.append((f"bind:{combo_id_from_line(b, W.modv)}", b.replace(f"exec {var}", f"exec {new}")))
    return vary(rng, req), Change(f"Launch {new} instead of {old} on {', '.join(b.split()[1] for b in binds)}", adds,
                                  ref=f"the switch to {newname}", evidence=[setline] + binds)


SWAY_ACTIONS = [
    (["close the focused window", "kill the window", "close windows"], "kill", "close the window"),
    (["toggle fullscreen", "make the window fullscreen"], "fullscreen toggle", "toggle fullscreen"),
    (["toggle floating", "float or tile the window"], "floating toggle", "toggle floating"),
    (["make the window sticky", "pin the floating window to all workspaces", "toggle sticky"], "sticky toggle", "toggle sticky"),
    (["switch focus between floating and tiled windows"], "focus mode_toggle", "toggle focus between tiling and floating"),
    (["focus the parent container"], "focus parent", "focus the parent container"),
    (["focus the child container"], "focus child", "focus the child container"),
    (["switch to tabbed layout", "make the container tabbed"], "layout tabbed", "use the tabbed layout"),
    (["switch to stacking layout"], "layout stacking", "use the stacking layout"),
    (["toggle the split direction", "toggle split layout"], "layout toggle split", "toggle the split layout"),
    (["cycle through all layouts"], "layout toggle all", "cycle through layouts"),
    (["split horizontally"], "splith", "split horizontally"),
    (["split vertically"], "splitv", "split vertically"),
    (["send the window to the scratchpad", "move the window to the scratchpad"], "move scratchpad", "move the window to the scratchpad"),
    (["show the scratchpad", "toggle the scratchpad"], "scratchpad show", "show the scratchpad"),
    (["go back to the previous workspace", "switch to the last workspace"], "workspace back_and_forth", "go to the previous workspace"),
    (["go to the next workspace", "switch to the next workspace"], "workspace next_on_output", "go to the next workspace on this output"),
    (["go to the previous workspace in order"], "workspace prev_on_output", "go to the previous workspace on this output"),
    (["move the workspace to the right monitor", "send this workspace to the other output"], "move workspace to output right", "move the workspace to the output on the right"),
    (["move the window to the other monitor", "send the window to the next output"], "move container to output right", "move the window to the output on the right"),
    (["focus the other monitor", "switch focus to the right output"], "focus output right", "focus the output on the right"),
    (["center the floating window"], "move position center", "center the floating window"),
    (["toggle the window border", "cycle border styles"], "border toggle", "cycle border styles"),
    (["reload the config", "reload sway"], "reload", "reload the config"),
]

SWAY_ACTION_REQ = ["bind {k} to {a}", "{k} should {a}", "make {k} {a}", "add a keybind to {a} on {k}", "i want to {a} with {k}",
                   "set {k} to {a}", "use {k} to {a}"]


def fam_bind_action(rng, W: SwayWorld, managed):
    mods, key, ks = _pick_combo(rng, W)
    r = rng.random()
    if r < 0.6:
        phrases, cmd, desc = rng.choice(SWAY_ACTIONS)
        phrase = rng.choice(phrases)
    elif r < 0.8:
        n = rng.randint(1, 10)
        c = rng.random()
        if c < 0.4:
            phrase, cmd, desc = rng.choice([f"switch to workspace {n}", f"go to workspace {n}"]), f"workspace number {n}", f"go to workspace {n}"
        elif c < 0.75:
            phrase, cmd, desc = f"move the window to workspace {n}", f"move container to workspace number {n}", f"move the window to workspace {n}"
        else:
            phrase = f"move the window to workspace {n} and follow it"
            cmd, desc = f"move container to workspace number {n}, workspace number {n}", f"move the window to workspace {n} and follow it"
    else:
        d = rng.choice(DIRECTIONS)
        kind = rng.choice(["focus", "move"])
        phrase = {"focus": f"focus the window to the {d}", "move": f"move the window {d}"}[kind]
        cmd, desc = f"{kind} {d}", phrase
    got = make_bind(W, mods, key, cmd)
    if got is None:
        return None
    adds, ev, main = got
    req = pick(rng, SWAY_ACTION_REQ, k=spoken(rng, mods, ks, W.modv), a=phrase)
    return vary(rng, req), Change(f"Bind {skey(mods, key, W.modv)} to {desc}{_repl(main)}", adds,
                                  ref=f"the {skey(mods, key, W.modv)} shortcut", evidence=ev)


def fam_bind_bulk(rng, W: SwayWorld, managed):
    r = rng.random()
    if r < 0.5:
        shift = rng.random() < 0.4
        mods = [W.modv] + (["SHIFT"] if shift else [])
        adds, ev = [], []
        for d in DIRECTIONS:
            got = make_bind(W, mods, VIM[d], f"{'move' if shift else 'focus'} {d}")
            if got is None:
                return None
            adds += got[0]
            ev += got[1]
        req = rng.choice(["move windows with vim keys", "mod+shift+hjkl should move windows"] if shift else
                         ["use vim keys to move focus", "hjkl focus navigation", "focus with mod+h/j/k/l"])
        return vary(rng, req), Change(f"Bind {skey(mods, 'hjkl', W.modv)} to {'move windows' if shift else 'move focus'}", adds,
                                      ref="the vim-key binds", evidence=ev)
    step = rng.choice([20, 30, 40, 50])
    if rng.random() < 0.5:
        adds = []
        for key, cmd in [("Left", "shrink width"), ("Right", "grow width"), ("Up", "shrink height"), ("Down", "grow height")]:
            adds.append((f"mode:resize:{key.lower()}", f'mode "resize" bindsym {key} resize {cmd} {step}px'))
        mainmode = [l for l in W.flat if l.startswith('mode "resize" bindsym Left')]
        if not mainmode:
            return None
        req = rng.choice([f"make the resize mode step {step}px", f"resize mode should resize by {step} pixels", f"bigger resize steps in resize mode, {step}px"])
        return vary(rng, req), Change(f"Make resize mode arrow keys resize by {step}px", adds, ref="the resize step change", evidence=mainmode[:1])
    mods = [W.modv, "CTRL"]
    adds, ev = [], []
    for key, cmd in [("Left", "shrink width"), ("Right", "grow width"), ("Up", "shrink height"), ("Down", "grow height")]:
        got = make_bind(W, mods, key, f"resize {cmd} {step}px")
        if got is None:
            return None
        adds += got[0]
        ev += got[1]
    if rng.random() < 0.5:
        req = rng.choice([f"let me resize from the keyboard with ctrl+mod+arrows, {step}px steps",
                          f"resize windows with {spoken(rng, mods, 'arrows', W.modv)} by {step}px"])
    else:
        step = 30
        req = rng.choice([f"resize windows with {spoken(rng, mods, 'arrows', W.modv)}", "let me resize windows from the keyboard with ctrl+mod+arrows"])
        adds = [(slot, re.sub(r"\d+px$", "30px", line)) for slot, line in adds]
    return vary(rng, req), Change(f"Bind {skey(mods, 'arrows', W.modv)} to resize by {step}px", adds, ref="the resize binds", evidence=ev)


SWAY_MEDIA = [
    (["take a screenshot of a region and copy it", "region screenshot to the clipboard"], 'grim -g "$(slurp)" - | wl-copy', "Print"),
    (["take a full screenshot and save it to ~/Pictures", "save a screenshot of the whole screen"], "grim ~/Pictures/screenshot-$(date +%F-%H%M%S).png", "Print"),
    (["lock the screen", "lock my session with swaylock"], "swaylock -f -c 000000", "Escape"),
    (["open the clipboard history"], "cliphist list | wofi --dmenu | cliphist decode | wl-copy", "v"),
    (["toggle the notification center", "open swaync"], "swaync-client -t -sw", "n"),
    (["open the power menu", "show wlogout"], "wlogout", "x"),
    (["dismiss notifications", "clear mako notifications"], "makoctl dismiss --all", "n"),
]


def fam_media(rng, W: SwayWorld, managed):
    if rng.random() < 0.4:
        what = rng.choice(["volume", "brightness"])
        vague = rng.random() < 0.3
        s = 5 if vague else rng.choice([1, 2, 3, 5, 10])
        keys = ([("XF86AudioRaiseVolume", f"exec wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ {s}%+"),
                 ("XF86AudioLowerVolume", f"exec wpctl set-volume @DEFAULT_AUDIO_SINK@ {s}%-")] if what == "volume" else
                [("XF86MonBrightnessUp", f"exec brightnessctl set {s}%+"), ("XF86MonBrightnessDown", f"exec brightnessctl set {s}%-")])
        req = (rng.choice([f"set up my {what} keys", f"make the {what} keys work"]) if vague else
               rng.choice([f"make the {what} keys change {what} by {s}%", f"{what} keys in {s}% steps"]))
        existing = [W.main_bind(combo_id([], k)) for k, _ in keys]
        if vague and all(existing):
            return vary(rng, req), Change(f"The {what} keys are already bound in your config; nothing to change.", evidence=existing)
        adds, ev = [], []
        for k, cmd in keys:
            got = make_bind(W, [], k, cmd, "--locked ")
            if got is None:
                return None
            adds += got[0]
            ev += got[1]
        return vary(rng, req), Change(f"Bind the {what} keys with {s}% steps", adds, ref=f"the {what} keys", evidence=ev)
    phrases, cmd, dk = rng.choice(SWAY_MEDIA)
    if dk == "Print" and rng.random() < 0.6:
        mods, key, ks = ([], "Print", "print screen") if rng.random() < 0.5 else (["SHIFT"], "Print", "print")
    elif rng.random() < 0.5:
        mods, key, ks = [W.modv] + (["SHIFT"] if dk in "vnx" else []), dk, dk.lower()
    else:
        mods, key, ks = _pick_combo(rng, W)
    got = make_bind(W, mods, key, f"exec {cmd}")
    if got is None:
        return None
    adds, ev, main = got
    req = pick(rng, SWAY_ACTION_REQ, k=spoken(rng, mods, ks, W.modv) if mods else rng.choice(["print screen", "the print key", "Print"]),
               a=rng.choice(phrases))
    return vary(rng, req), Change(f"Bind {skey(mods, key, W.modv)} to run {cmd}{_repl(main)}", adds,
                                  ref=f"the {skey(mods, key, W.modv)} shortcut", evidence=ev)


def fam_unbind(rng, W: SwayWorld, managed):
    mine = [e for e in managed if e.slot.startswith("bind:")]
    if mine and rng.random() < 0.4:
        e = rng.choice(mine)
        k = e.line.split()[1] if not e.line.startswith("bindsym --") else e.line.split()[2]
        main = W.main_bind(e.slot[5:])
        adds = []
        if main:
            flags = "".join(t + " " for t in main.split()[1:] if t.startswith("--"))
            adds = [(f"unbind:{e.slot[5:]}", f"unbindsym {flags}{k}")]
        req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "{k} shouldn't do anything", "delete the {k} keybind"], k=k)
        return vary(rng, req), Change(f"Remove the {k} binding", adds, dels_lines=[e.line], ref=f"the {k} removal", evidence=[main] if main else [])
    cands = [l for l in W.flat if l.startswith("bindsym ") and not l.startswith("bindsym --")]
    l = rng.choice(cands)
    k = l.split()[1]
    cid = combo_id_from_line(l, W.modv)
    if any(e.slot == f"unbind:{cid}" for e in managed):
        return None
    req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "disable {k}", "i keep pressing {k} by accident, disable it"],
               k=k if rng.random() < 0.6 else k.replace("$mod", "mod"))
    return vary(rng, req), Change(f"Unbind {k}", [(f"unbind:{cid}", f"unbindsym {k}")], ref=f"the {k} unbind", evidence=[l])


# ---------------------------------------------------------------- rules, outputs, misc

def _crit(app) -> str:
    return f'[class="{app.app_id}"]' if app.x11 else f'[app_id="{app.app_id}"]'


def fam_window_rule(rng, W: SwayWorld, managed):
    app = rng.choice([a for a in APPS if a.kind != "tui"])
    n, c = app.name, _crit(app)
    r = rng.random()
    if r < 0.25 or (r < 0.35 and n in FLOATY):
        line = f"for_window {c} floating enable"
        req = pick(rng, ["make {a} float", "{a} should always open floating", "float {a} windows"], a=n)
        summary, key = f"Float {app.app_id} windows", "float"
    elif r < 0.4:
        w, h = rng.choice([(800, 600), (900, 600), (1000, 700), (1200, 800), (960, 540)])
        line = f"for_window {c} floating enable, resize set {w} {h}, move position center"
        req = pick(rng, ["open {a} floating at {w}x{h} in the center", "{a} should float, {w} by {h}, centered"], a=n, w=w, h=h)
        summary, key = f"Float {app.app_id} at {w}x{h}, centered", "float"
    elif r < 0.6:
        ws = rng.randint(1, 9)
        line = f"assign {c} workspace number {ws}"
        req = pick(rng, ["always open {a} on workspace {w}", "{a} should go to workspace {w}", "assign {a} to workspace {w}"], a=n, w=ws)
        summary, key = f"Assign {app.app_id} to workspace {ws}", "assign"
    elif r < 0.7:
        if rng.random() < 0.3:
            a = 0.9
            req = pick(rng, ["make {a} slightly transparent", "{a} a little see-through"], a=n)
        else:
            a = rng.choice([0.7, 0.75, 0.8, 0.85, 0.9, 0.95])
            req = pick(rng, ["set {a} opacity to {o}", "{a} at {p}% opacity", "make {a} {p} percent opaque"], a=n, o=a, p=int(round(a * 100)))
        line = f"for_window {c} opacity {a}"
        summary, key = f"Set {app.app_id} opacity to {a}", "opacity"
    elif r < 0.78:
        line = f"for_window {c} inhibit_idle fullscreen"
        req = pick(rng, ["don't let the screen sleep while {a} is fullscreen", "inhibit idle when {a} is fullscreen"], a=n)
        summary, key = f"Inhibit idle while {app.app_id} is fullscreen", "idle"
    elif r < 0.85:
        line = f"for_window {c} border pixel 0"
        req = pick(rng, ["remove the border from {a}", "no border on {a} windows"], a=n)
        summary, key = f"Remove the border from {app.app_id}", "border"
    elif r < 0.9:
        line = f"for_window {c} fullscreen enable"
        req = pick(rng, ["always open {a} fullscreen", "{a} should start fullscreen"], a=n)
        summary, key = f"Open {app.app_id} fullscreen", "fullscreen"
    elif r < 0.95:
        line = 'for_window [app_id="firefox" title="^Picture-in-Picture$"] floating enable, sticky enable, resize set 640 360'
        req = rng.choice(["make firefox picture-in-picture float and stay on all workspaces", "pip videos should float and be sticky"])
        return vary(rng, req), Change("Float firefox picture-in-picture windows, sticky, 640x360", [("rule:firefox-pip", line)], ref="the picture-in-picture rule")
    else:
        line = f"for_window {c} floating enable, sticky enable"
        req = pick(rng, ["make {a} float and follow me to every workspace", "{a} should be floating and sticky"], a=n)
        summary, key = f"Float {app.app_id} and make it sticky", "float"
    return vary(rng, req), Change(summary, [(f"rule:{app.app_id}:{key}", line)], ref=f"the {n} window rule")


OUTPUTS = ["eDP-1", "DP-1", "DP-2", "HDMI-A-1"]


def fam_output(rng, W: SwayWorld, managed):
    out = rng.choice(OUTPUTS)
    sp = "my laptop screen" if out == "eDP-1" and rng.random() < 0.5 else out
    r = rng.random()
    if r < 0.25:
        res = rng.choice(["1920x1080", "2560x1440", "3840x2160", "1366x768", "3440x1440"])
        hz = rng.choice([60, 75, 120, 144, 165])
        line, prop = f"output {out} mode {res}@{hz}Hz", "mode"
        req = pick(rng, ["set {o} to {r} at {h}hz", "{o} should run at {r}@{h}"], o=sp, r=res, h=hz)
        summary = f"Set {out} to {res}@{hz}Hz"
    elif r < 0.45:
        s = rng.choice(["1", "1.25", "1.5", "1.75", "2"])
        line, prop = f"output {out} scale {s}", "scale"
        req = pick(rng, ["set the scale of {o} to {s}", "scale {o} {s}x", "{o} scaling {s}"], o=sp, s=s)
        summary = f"Set the scale of {out} to {s}"
    elif r < 0.58:
        w = rng.choice([1920, 2560, 1366, 3840])
        other = rng.choice([o for o in OUTPUTS if o != out])
        line, prop = f"output {out} position {w} 0", "position"
        req = pick(rng, ["put {o} to the right of {l} (which is {w} pixels wide)", "{o} sits right of my {w}px wide {l}"], o=out, l=other, w=w)
        summary = f"Position {out} at {w},0"
    elif r < 0.66:
        line, prop = f"output {out} disable", "power"
        req = pick(rng, ["disable {o}", "turn off {o} completely"], o=sp)
        summary = f"Disable {out}"
    elif r < 0.74:
        deg = rng.choice([90, 180, 270])
        line, prop = f"output {out} transform {deg}", "transform"
        req = pick(rng, ["rotate {o} {d} degrees", "{o} is mounted vertically, rotate it {d}°"], o=sp, d=deg)
        summary = f"Rotate {out} by {deg} degrees"
    elif r < 0.8:
        line, prop = f"output {out} adaptive_sync on", "adaptive_sync"
        req = pick(rng, ["enable adaptive sync on {o}", "turn on vrr/freesync for {o}"], o=sp)
        summary = f"Enable adaptive sync on {out}"
    elif r < 0.92:
        path = rng.choice(["~/Pictures/wallpaper.jpg", "~/Pictures/wall.png", "~/.config/sway/bg.png", "/usr/share/backgrounds/sway/Sway_Wallpaper_Blue_1920x1080.png"])
        mode = rng.choice(["fill", "fill", "fit", "center", "stretch"])
        line, prop, out = f"output * bg {path} {mode}", "bg", "*"
        if rng.random() < 0.5:  # an unstated mode means the default, fill
            mode = "fill"
            req = pick(rng, ["set my wallpaper to {p}", "wallpaper {p}"], p=path)
        else:
            req = pick(rng, ["use {p} as the background ({m})", "set my wallpaper to {p}, {m} mode"], p=path, m=mode)
        summary = f"Set the wallpaper to {path} ({mode})"
    else:
        col = rng.choice(list(COLORS))
        line, prop, out = f"output * bg #{COLORS[col]} solid_color", "bg", "*"
        req = pick(rng, ["use a solid {c} background", "set the background to plain {c}"], c=col)
        summary = f"Use a solid #{COLORS[col]} background"
    return vary(rng, req), Change(summary, [(f"output:{out}:{prop}", line)], ref=f"the {out} {prop} setting")


def fam_workspace(rng, W: SwayWorld, managed):
    ws = rng.randint(1, 9)
    out = rng.choice(OUTPUTS)
    line = f"workspace number {ws} output {out}"
    req = pick(rng, ["put workspace {w} on {o}", "workspace {w} should live on {o}", "bind workspace {w} to monitor {o}"], w=ws, o=out)
    return vary(rng, req), Change(f"Put workspace {ws} on {out}", [(f"wsout:{ws}", line)], ref=f"the workspace {ws} output")


def fam_autostart(rng, W: SwayWorld, managed):
    mine = [e for e in managed if e.slot.startswith("exec:")]
    if mine and rng.random() < 0.15:
        e = rng.choice(mine)
        c = e.slot[5:]
        return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore"], c=c)), \
            Change(f"Stop starting {c} at login", dels_lines=[e.line], ref="")
    mains = [l for l in W.flat if l.startswith("exec ") and not l.startswith("exec swaynag")]
    if mains and rng.random() < 0.1:
        l = rng.choice(mains)
        c = l[5:]
        return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore"], c=c)), \
            Change(f"{c} is started by your main config, which this tool does not edit; remove the '{l}' line from it.", evidence=[l])
    c = rng.choice(AUTOSTART_POOL + ["firefox", "discord", "steam -silent", "spotify", "syncthing serve --no-browser"])
    always = c in ("autotiling", "kanshi") or rng.random() < 0.1
    line = f"exec{'_always' if always else ''} {c}"
    if f"exec {c}" in W.flat:
        return vary(rng, f"start {c} at login"), Change(f"{c} is already started by your config; nothing to change.", evidence=[f"exec {c}"])
    req = pick(rng, ["start {c} on login", "autostart {c}", "run {c} when sway starts", "launch {c} at startup"] +
               (["run {c} on every reload too"] if always else []), c=c)
    return vary(rng, req), Change(f"Start {c} {'on startup and every reload' if always else 'when Sway starts'}", [(f"exec:{c}", line)],
                                  ref=f"the {c} autostart")


def fam_bar(rng, W: SwayWorld, managed):
    has_bar = any(l.startswith("bar ") for l in W.flat)
    if not has_bar:
        return None
    ev = [next(l for l in W.flat if l.startswith("bar "))]
    r = rng.random()
    if r < 0.35:
        if any(l == "bar swaybar_command waybar" for l in W.flat):
            return None
        req = rng.choice(["use waybar instead of swaybar", "replace swaybar with waybar", "switch the bar to waybar"])
        return vary(rng, req), Change("Run waybar for bar-0 instead of swaybar", [("bar:command", "bar bar-0 swaybar_command waybar")], ref="the waybar switch", evidence=ev)
    if r < 0.6:
        pos = rng.choice(["top", "bottom"])
        req = pick(rng, ["move the bar to the {p}", "put the bar at the {p}", "bar on {p}"], p=pos)
        return vary(rng, req), Change(f"Move the bar to the {pos}", [("bar:position", f"bar bar-0 position {pos}")], ref="the bar position", evidence=ev)
    if r < 0.85:
        mode = rng.choice(["hide", "invisible"])
        req = rng.choice(["only show the bar while holding mod", "hide the bar until i press mod"] if mode == "hide" else
                         ["hide the bar completely", "get rid of the bar"])
        return vary(rng, req), Change(f"Set the bar mode to {mode}", [("bar:mode", f"bar bar-0 mode {mode}")], ref="the bar mode", evidence=ev)
    req = rng.choice(["show the bar again", "bring the bar back"])
    return vary(rng, req), Change("Set the bar mode to dock", [("bar:mode", "bar bar-0 mode dock")], ref="the bar mode", evidence=ev)


def fam_idle(rng, W: SwayWorld, managed):
    t1 = rng.choice([180, 300, 600, 900])
    t2 = t1 + rng.choice([60, 120, 300])
    line = (f"exec swayidle -w timeout {t1} 'swaylock -f -c 000000' timeout {t2} 'swaymsg \"output * power off\"' "
            f"resume 'swaymsg \"output * power on\"' before-sleep 'swaylock -f -c 000000'")
    req = pick(rng, ["lock the screen after {a} minutes and turn displays off after {b}", "set up swayidle: lock at {a} min, screen off at {b} min",
                     "auto lock after {a} minutes of inactivity, screens off at {b}"], a=t1 // 60 if t1 >= 60 else t1, b=t2 // 60)
    return vary(rng, req), Change(f"Lock after {t1}s and power displays off after {t2}s with swayidle (also locks before sleep)",
                                  [("exec:swayidle", line)], ref="the idle/lock setup")


def fam_gesture(rng, W: SwayWorld, managed):
    opts = [
        ([("swipe:3:left", "workspace next_on_output"), ("swipe:3:right", "workspace prev_on_output")],
         ["switch workspaces with a three finger swipe", "3 finger swipe left/right changes workspace"], "Switch workspaces with 3-finger horizontal swipes"),
        ([("swipe:4:left", "workspace next_on_output"), ("swipe:4:right", "workspace prev_on_output")],
         ["switch workspaces with four fingers"], "Switch workspaces with 4-finger horizontal swipes"),
        ([("swipe:3:up", "floating toggle")], ["three finger swipe up toggles floating"], "Toggle floating with a 3-finger swipe up"),
        ([("swipe:3:down", "kill")], ["swipe down with three fingers to close the window"], "Close the window with a 3-finger swipe down"),
        ([("swipe:4:up", "exec $menu")], ["four finger swipe up opens the app launcher"], "Open the launcher with a 4-finger swipe up"),
        ([("swipe:3:up", "fullscreen toggle")], ["3 finger swipe up for fullscreen"], "Toggle fullscreen with a 3-finger swipe up"),
    ]
    pairs, reqs, summary = rng.choice(opts)
    adds = [(f"gesture:{g}", f"bindgesture {g} {c}") for g, c in pairs]
    ev = [l for l in W.flat if l.startswith("set $menu ")] if any("$menu" in c for _, c in pairs) else []
    return vary(rng, rng.choice(reqs)), Change(summary, adds, ref="the gesture binds", evidence=ev)


def fam_cursor(rng, W: SwayWorld, managed):
    theme = rng.choice(["Adwaita", "Bibata-Modern-Ice", "Breeze", "phinger-cursors-dark"])
    size = rng.choice([24, 32, 36, 48])
    r = rng.random()
    if r < 0.5:
        req = pick(rng, ["set the cursor theme to {t} at size {s}", "use the {t} cursor, size {s}"], t=theme, s=size)
        return vary(rng, req), Change(f"Use the {theme} cursor theme at size {size}", [("seat:xcursor", f"seat seat0 xcursor_theme {theme} {size}")], ref="the cursor theme")
    req = pick(rng, ["make the cursor bigger, size {s}", "cursor size {s}"], s=size)
    return vary(rng, req), Change(f"Set the cursor size to {size} (Adwaita theme)", [("seat:xcursor", f"seat seat0 xcursor_theme Adwaita {size}")], ref="the cursor size")


def fam_lid(rng, W: SwayWorld, managed):
    req = rng.choice(["turn off the laptop screen when i close the lid", "disable eDP-1 when the lid is closed (i use an external monitor)",
                      "clamshell mode: lid closed should disable the internal display"])
    return vary(rng, req), Change("Disable eDP-1 while the lid is closed and re-enable it when opened", [
        ("switch:lid:on", "bindswitch --reload --locked lid:on output eDP-1 disable"),
        ("switch:lid:off", "bindswitch --reload --locked lid:off output eDP-1 enable")], ref="the lid switch binds")


def fam_remove(rng, W: SwayWorld, managed):
    if not managed:
        return None
    cids = sorted({e.cid for e in managed})
    r = rng.random()
    if r < 0.6:
        cid = rng.choice(cids)
        group = [e for e in managed if e.cid == cid]
        ref = group[0].ref
        if not ref:
            return None
        req = pick(rng, ["remove {r}", "undo {r}", "get rid of {r}", "revert {r}", "i don't want {r} anymore"], r=ref)
        return vary(rng, req), Change(f"Remove {ref}", dels_lines=[e.line for e in group])
    if r < 0.8:
        group = [e for e in managed if e.cid == cids[-1]]
        return vary(rng, rng.choice(["undo the last change", "revert your last edit", "undo that"])), \
            Change(f"Undo the last change ({group[0].ref})", dels_lines=[e.line for e in group])
    return vary(rng, rng.choice(["remove everything you added", "reset all your changes", "clear the managed config"])), \
        Change("Remove all managed changes", dels_lines=[e.line for e in managed])


NOOP = [
    ("what's the weather tomorrow", "This is not a Sway configuration request."),
    ("write me a poem", "This is not a Sway configuration request."),
    ("install waybar", "Installing software is not a config change; use your package manager (e.g. pacman -S waybar)."),
    ("open firefox", "That asks to run something now, not to change the config; ask for a keybind or autostart instead."),
    ("fix my bluetooth", "Bluetooth setup is not part of the Sway config."),
    ("configure my fish prompt", "Shell configuration is not part of the Sway config."),
    ("add blur behind windows", "Sway has no blur; SwayFX (a Sway fork) adds blur, rounded corners and shadows."),
    ("make the corners rounded", "Sway has no rounded corners; SwayFX (a Sway fork) adds corner_radius."),
    ("add window shadows", "Sway has no shadows; SwayFX (a Sway fork) adds them."),
    ("add animations", "Sway has no animations; consider Hyprland or SwayFX-based setups."),
    ("set GTK_THEME to Adwaita:dark", "Sway's config cannot set environment variables; put GTK_THEME=Adwaita:dark in ~/.config/environment.d/*.conf."),
    ("set the cursor size env variable", "Sway's config cannot set environment variables; use seat seat0 xcursor_theme <theme> <size> or environment.d."),
    ("use the hyprland layout", "This tool is set up for Sway, not Hyprland."),
]


def fam_noop(rng, W: SwayWorld, managed):
    req, summary = rng.choice(NOOP)
    return vary(rng, req), Change(summary)


FAMILIES = [
    (9, "num", fam_num), (9, "toggle", fam_toggle), (2, "titlebars", fam_titlebars), (2, "font", fam_font),
    (5, "keyboard", fam_keyboard), (4, "colors", fam_colors), (12, "bind_app", fam_bind_app), (2.5, "swap_app", fam_swap_app),
    (12, "bind_action", fam_bind_action), (3, "bind_bulk", fam_bind_bulk), (5, "media", fam_media), (4, "unbind", fam_unbind),
    (9, "window_rule", fam_window_rule), (6, "output", fam_output), (2, "workspace", fam_workspace), (4, "autostart", fam_autostart),
    (3, "bar", fam_bar), (1.5, "idle", fam_idle), (2, "gesture", fam_gesture), (1.5, "cursor", fam_cursor), (1, "lid", fam_lid),
    (6, "remove", fam_remove), (2.5, "noop", fam_noop),
]

PRIOR_FAMILIES = [fam_num, fam_toggle, fam_titlebars, fam_font, fam_keyboard, fam_colors, fam_bind_app, fam_bind_action,
                  fam_media, fam_window_rule, fam_output, fam_workspace, fam_autostart, fam_bar, fam_gesture, fam_cursor]
