"""Hyprland 0.57 (Lua config) sample families.

Every statement written here was checked against `Hyprland --verify-config`
and, for dispatcher arguments (which the validator only partly checks), against
the v0.57.2 source (src/config/lua/bindings/LuaBindingsDispatchers.cpp).
"""

from __future__ import annotations

import random
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from data.common import (APPS, COLORS, DIRECTIONS, FLOATY, FREE_KEYS, KIND_WORDS, LAUNCHERS, THEMES,
                         VIM, Change, pick, spoken_combo, vary)
from wmllm.context import combo_of_line, flatten_hyprland

DEFAULT_CONFIG = Path("/usr/share/hypr/hyprland.lua")
WM = "hyprland"

# --------------------------------------------------------------------------
# Lua rendering helpers (must match flatten_hypr.lua's serialiser)
# --------------------------------------------------------------------------


def lstr(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lval(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{round(v, 3):g}"
        return s
    if isinstance(v, str):
        return lstr(v)
    raise TypeError(v)


def cfg_line(path: str, value_lua: str) -> str:
    s = value_lua
    for seg in reversed(path.split(".")):
        s = "{ " + seg + " = " + s + " }"
    return f"hl.config({s})"


def cfg_prefix_suffix(path: str) -> tuple[str, str]:
    segs = path.split(".")
    prefix = "hl.config(" + "".join("{ " + s + " = " for s in segs)
    suffix = " }" * len(segs) + ")"
    return prefix, suffix


MOD_ORDER = ["SUPER", "CTRL", "ALT", "SHIFT"]


def hkey(mods: list[str], key: str) -> str:
    ms = [m for m in MOD_ORDER if m in mods]
    k = key.upper() if len(key) == 1 and key.isalpha() else key
    return " + ".join(ms + [k])


def combo_id(mods: list[str], key: str) -> str:
    k = key.lower()
    return "+".join(sorted(mods)) + "+" + k


def combo_id_from_line(line: str) -> str | None:
    c = combo_of_line(WM, line)
    if c is None:
        return None
    mods, key = c
    return "+".join(sorted(mods)) + "+" + key


def bind_line(keystr: str, dsp: str, opts: str | None = None) -> str:
    return f"hl.bind({lstr(keystr)}, {dsp}" + (f", {opts}" if opts else "") + ")"


# --------------------------------------------------------------------------
# Synthetic main configs
# --------------------------------------------------------------------------

AUTOSTART_POOL = ["waybar", "mako", "swaync", "nm-applet --indicator", "blueman-applet", "hyprpaper",
                  "hypridle", "wl-paste --watch cliphist store", "udiskie", "swww-daemon",
                  "/usr/lib/polkit-kde-authentication-agent-1", "fcitx5 -d"]

TERMINAL_CMDS = [a.cmd for a in APPS if a.kind == "terminal"]
FILES_CMDS = [a.cmd for a in APPS if a.kind == "files"]
MENU_CMDS = ["hyprlauncher"] + [c for _, c in LAUNCHERS]


@dataclass
class HyprWorld:
    text: str
    flat: list[str]
    terminal: str
    files: str
    menu: str

    def cfg(self, path: str, managed) -> tuple[str | None, str | None, bool]:
        """Current value of an option: (lua value, line, from_main)."""
        pre, suf = cfg_prefix_suffix(path)
        for e in reversed(managed):
            if e.line.startswith(pre) and e.line.endswith(suf):
                return e.line[len(pre):-len(suf)], e.line, False
        for line in reversed(self.flat):
            if line.startswith(pre) and line.endswith(suf):
                return line[len(pre):-len(suf)], line, True
        return None, None, True

    def main_bind(self, cid: str) -> tuple[str, str] | None:
        """(line, exact key string) of the main-config bind for this combo."""
        for line in self.flat:
            if line.startswith("hl.bind(") and "-- submap" not in line and combo_id_from_line(line) == cid:
                key = re.match(r'^hl\.bind\("([^"]+)"', line).group(1)
                return line, key
        return None

    def main_binds_exec(self, cmd: str) -> list[tuple[str, str]]:
        out = []
        needle = f"hl.dsp.exec_cmd({lstr(cmd)})"
        for line in self.flat:
            if line.startswith("hl.bind(") and needle in line and "-- submap" not in line:
                out.append((line, re.match(r'^hl\.bind\("([^"]+)"', line).group(1)))
        return out


def _mutate_default(rng: random.Random, base: str) -> tuple[str, dict]:
    t = base
    term = rng.choice(TERMINAL_CMDS)
    files = rng.choice(FILES_CMDS)
    menu = rng.choice(MENU_CMDS)
    t = t.replace('local terminal    = "kitty"', f'local terminal    = {lstr(term)}')
    t = t.replace('local fileManager = "dolphin"', f'local fileManager = {lstr(files)}')
    t = t.replace('local menu        = "hyprlauncher"', f'local menu        = {lstr(menu)}')
    t = re.sub(r"gaps_in  = 5", f"gaps_in  = {rng.choice([0, 2, 3, 4, 5, 5, 5, 6, 8, 10])}", t)
    t = re.sub(r"gaps_out = 20", f"gaps_out = {rng.choice([0, 5, 8, 10, 12, 15, 20, 20, 20, 25])}", t)
    t = re.sub(r"border_size = 2", f"border_size = {rng.choice([1, 2, 2, 2, 3, 4])}", t)
    t = re.sub(r"rounding       = 10", f"rounding       = {rng.choice([0, 4, 6, 8, 10, 10, 12, 16])}", t)
    t = t.replace('kb_layout  = "us"', f'kb_layout  = {lstr(rng.choice(["us"] * 6 + ["de", "gb", "fr", "us,de", "es", "pl", "se"]))}')
    if rng.random() < 0.3:
        t = t.replace("natural_scroll = false", "natural_scroll = true")
    if rng.random() < 0.25:
        t = t.replace("enabled   = true,\n            size", "enabled   = false,\n            size")
    if rng.random() < 0.6:
        cmds = rng.sample(AUTOSTART_POOL, rng.randint(1, 4))
        body = "\n".join(f"    hl.exec_cmd({lstr(c)})" for c in cmds)
        t = t.replace('-- hl.on("hyprland.start", function () \n--   hl.exec_cmd(terminal)\n--   hl.exec_cmd("nm-applet")\n--   hl.exec_cmd("waybar & hyprpaper & firefox")\n-- end)',
                      f'hl.on("hyprland.start", function()\n{body}\nend)')
    if rng.random() < 0.2:
        # Drop the multimedia block
        t = re.sub(r"-- Laptop multimedia keys.*?-- Requires playerctl\n(hl\.bind\(\"XF86.*\n)+", "", t, flags=re.S)
    extra = []
    if rng.random() < 0.5:
        extra.append(f'hl.bind(mainMod .. " + B", hl.dsp.exec_cmd({lstr(rng.choice(["firefox", "chromium", "brave", "librewolf"]))}))')
    if rng.random() < 0.3:
        extra.append('hl.bind("Print", hl.dsp.exec_cmd("grim -g \\"$(slurp)\\" - | wl-copy"))')
    if rng.random() < 0.3:
        extra.append('hl.bind(mainMod .. " + L", hl.dsp.exec_cmd("hyprlock"))')
    if rng.random() < 0.3:
        extra.append('hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen())')
    if rng.random() < 0.25:
        extra.append('hl.window_rule({ match = { class = "org.pulseaudio.pavucontrol" }, float = true })')
    if rng.random() < 0.2:
        extra.append('hl.layer_rule({ match = { namespace = "waybar" }, blur = true })')
    if rng.random() < 0.15:
        extra.append('hl.monitor({ output = "eDP-1", mode = "1920x1080@60", position = "0x0", scale = 1.25 })')
    if extra:
        t = t.rstrip() + "\n\n-- my additions\n" + "\n".join(extra) + "\n"
    return t, {"terminal": term, "files": files, "menu": menu}


MINIMAL_TEMPLATE = """-- {comment}
local mod = "{mod}"

hl.config({{
    general = {{ gaps_in = {gi}, gaps_out = {go}, border_size = {bs}, layout = "{layout}" }},
    decoration = {{ rounding = {rd} }},
    input = {{ kb_layout = "{kb}", follow_mouse = 1 }},
}})
hl.config({{ ["decoration.blur.enabled"] = {blur} }})

hl.on("hyprland.start", function()
    hl.exec_cmd("{bar}")
end)

hl.bind(mod .. " + Return", hl.dsp.exec_cmd("{term}"))
hl.bind(mod .. " + D", hl.dsp.exec_cmd("{menu}"))
hl.bind(mod .. " + Q", hl.dsp.window.close())
hl.bind(mod .. " + F", hl.dsp.window.fullscreen())
hl.bind(mod .. " + SHIFT + SPACE", hl.dsp.window.float({{ action = "toggle" }}))
for _, d in ipairs({{ "left", "right", "up", "down" }}) do
    hl.bind(mod .. " + " .. d, hl.dsp.focus({{ direction = d }}))
end
for i = 1, 9 do
    hl.bind(mod .. " + " .. i, hl.dsp.focus({{ workspace = i }}))
    hl.bind(mod .. " + SHIFT + " .. i, hl.dsp.window.move({{ workspace = i }}))
end
hl.bind(mod .. " + mouse:272", hl.dsp.window.drag(), {{ mouse = true }})
hl.bind(mod .. " + mouse:273", hl.dsp.window.resize(), {{ mouse = true }})
"""


def _minimal(rng: random.Random) -> tuple[str, dict]:
    term = rng.choice(TERMINAL_CMDS)
    menu = rng.choice(MENU_CMDS)
    t = MINIMAL_TEMPLATE.format(
        comment=rng.choice(["my hyprland config", "minimal setup", "hyprland.lua"]),
        mod="SUPER", gi=rng.choice([2, 4, 5, 6]), go=rng.choice([4, 8, 10, 12]), bs=rng.choice([1, 2, 3]),
        layout=rng.choice(["dwindle", "dwindle", "master", "scrolling"]), rd=rng.choice([0, 6, 8, 12]),
        kb=rng.choice(["us", "us", "de", "gb", "us,ru"]), blur=rng.choice(["true", "false"]),
        bar=rng.choice(["waybar", "waybar", "ashell", "hyprpanel"]), term=term, menu=menu,
    )
    return t, {"terminal": term, "files": "", "menu": menu}


def build_worlds(n: int, seed: int = 1) -> list[HyprWorld]:
    rng = random.Random(seed)
    base = DEFAULT_CONFIG.read_text()
    worlds = []
    with tempfile.TemporaryDirectory(prefix="wmllm-hw-") as d:
        p = Path(d) / "hyprland.lua"
        (Path(d) / "ai.lua").write_text("")
        for _ in range(n):
            text, params = _minimal(rng) if rng.random() < 0.15 else _mutate_default(rng, base)
            text = text.rstrip() + '\n\n-- Managed by wmai (keep this last)\nrequire("ai")\n'
            p.write_text(text)
            worlds.append(HyprWorld(text, flatten_hyprland(p, "ai"), **params))
    return worlds


# --------------------------------------------------------------------------
# Option tables (keys checked against the stub's HL.ConfigValueTypes at build)
# --------------------------------------------------------------------------

NUM_OPTS = [
    # path, names, lo, hi, step, is_float, unit
    ("general.gaps_in", ["inner gaps", "the gaps between windows", "the inner gap", "gaps_in"], 0, 30, 3, False, "px"),
    ("general.gaps_out", ["outer gaps", "the gaps at the screen edges", "the outer gap", "gaps_out"], 0, 60, 5, False, "px"),
    ("general.border_size", ["border size", "the border width", "border thickness", "the window border"], 0, 8, 1, False, "px"),
    ("decoration.rounding", ["corner rounding", "the corner radius", "window rounding", "rounded corners"], 0, 24, 4, False, "px"),
    ("decoration.active_opacity", ["the opacity of the focused window", "active window opacity"], 0.6, 1.0, 0.05, True, ""),
    ("decoration.inactive_opacity", ["the opacity of unfocused windows", "inactive window opacity"], 0.5, 1.0, 0.05, True, ""),
    ("decoration.blur.size", ["blur size", "the blur radius", "blur strength"], 1, 15, 2, False, ""),
    ("decoration.blur.passes", ["blur passes", "the number of blur passes"], 1, 6, 1, False, ""),
    ("decoration.shadow.range", ["shadow range", "the shadow size"], 0, 40, 5, False, "px"),
    ("decoration.dim_strength", ["dim strength", "how much unfocused windows are dimmed"], 0.05, 0.8, 0.05, True, ""),
    ("input.sensitivity", ["mouse sensitivity", "pointer speed", "mouse speed"], -1.0, 1.0, 0.2, True, ""),
    ("input.repeat_rate", ["the key repeat rate", "keyboard repeat rate"], 15, 80, 10, False, ""),
    ("input.repeat_delay", ["the key repeat delay", "keyboard repeat delay", "the delay before keys repeat"], 150, 800, 100, False, "ms"),
    ("input.touchpad.scroll_factor", ["touchpad scroll speed", "the touchpad scroll factor", "trackpad scrolling speed"], 0.2, 2.0, 0.2, True, ""),
    ("master.mfact", ["the master area size", "the master split ratio"], 0.3, 0.8, 0.05, True, ""),
    ("cursor.inactive_timeout", ["the cursor hide timeout", "how many seconds until the cursor hides"], 1, 30, 2, False, "s"),
]

BOOL_OPTS = [
    # path, phrases that mean "true", phrases that mean "false", what it is
    ("animations.enabled", ["enable animations", "turn on animations", "bring the animations back"],
     ["disable animations", "turn off all animations", "no animations", "kill the animations, they're slow"], "animations"),
    ("decoration.blur.enabled", ["enable blur", "turn blur on", "blur the background of transparent windows"],
     ["disable blur", "turn off blur", "no blur, it's slow on my laptop"], "blur"),
    ("decoration.shadow.enabled", ["enable window shadows", "turn on drop shadows"],
     ["disable shadows", "remove the window shadows", "no drop shadows"], "shadows"),
    ("decoration.dim_inactive", ["dim unfocused windows", "dim inactive windows"],
     ["stop dimming inactive windows", "don't dim unfocused windows"], "dimming of inactive windows"),
    ("input.touchpad.natural_scroll", ["enable natural scrolling on the touchpad", "reverse touchpad scrolling like on a mac"],
     ["disable natural scrolling on the touchpad", "use normal touchpad scrolling direction"], "natural touchpad scrolling"),
    ("input.natural_scroll", ["enable natural scrolling for the mouse", "invert the mouse wheel"],
     ["disable natural scrolling for the mouse", "make the mouse wheel scroll normally again"], "natural mouse scrolling"),
    ("input.touchpad.tap_to_click", ["enable tap to click", "let me tap the touchpad to click"],
     ["disable tap to click", "stop touchpad taps from clicking"], "tap to click"),
    ("input.touchpad.disable_while_typing", ["disable the touchpad while typing", "ignore the touchpad while i type"],
     ["keep the touchpad working while typing"], "disable-while-typing"),
    ("input.numlock_by_default", ["turn numlock on at startup", "enable numlock by default"],
     ["don't turn numlock on at startup"], "numlock at startup"),
    ("input.left_handed", ["switch the mouse to left-handed mode", "swap the mouse buttons for a lefty"],
     ["switch the mouse back to right-handed"], "left-handed mode"),
    ("misc.disable_hyprland_logo", ["hide the hyprland logo", "disable the hyprland logo"],
     ["show the hyprland logo again"], "the Hyprland logo"),
    ("misc.disable_splash_rendering", ["disable the splash text", "hide the splash message on the wallpaper"],
     ["show the splash text again"], "the splash text"),
    ("misc.focus_on_activate", ["focus windows that request activation", "let apps grab focus when they ask"],
     ["don't let apps steal focus", "stop windows from stealing focus"], "focus on activate"),
    ("misc.enable_swallow", ["enable window swallowing", "let the terminal swallow windows it launches"],
     ["disable window swallowing"], "window swallowing"),
    ("misc.middle_click_paste", ["enable middle click paste"],
     ["disable middle click paste", "stop middle click from pasting"], "middle-click paste"),
    ("general.resize_on_border", ["let me resize windows by dragging their borders", "enable resize on border"],
     ["disable resizing by dragging borders"], "resizing by dragging borders"),
    ("general.allow_tearing", ["allow screen tearing", "enable tearing for lower latency"],
     ["disable tearing"], "tearing"),
    ("dwindle.preserve_split", ["preserve the split direction in dwindle", "keep my dwindle split direction"],
     ["don't preserve the dwindle split direction"], "preserve split"),
    ("dwindle.smart_split", ["enable smart split", "split windows based on where the cursor is"],
     ["disable smart split"], "smart split"),
    ("master.new_on_top", ["put new windows on top of the master stack"],
     ["put new windows at the bottom of the stack"], "new windows on top"),
    ("binds.workspace_back_and_forth", ["enable workspace back and forth", "pressing the current workspace's number should take me back to the previous one"],
     ["disable workspace back and forth"], "workspace back and forth"),
    ("cursor.no_hardware_cursors", ["disable hardware cursors", "fix the invisible cursor on nvidia", "use software cursors"],
     ["enable hardware cursors again"], "software cursors"),
    ("cursor.hide_on_key_press", ["hide the cursor while typing", "hide the mouse pointer when i press a key"],
     ["don't hide the cursor when typing"], "hiding the cursor while typing"),
    ("xwayland.force_zero_scaling", ["fix blurry xwayland apps on my hidpi screen", "stop scaling xwayland apps"],
     ["let xwayland apps be scaled again"], "zero scaling for XWayland"),
    ("ecosystem.no_update_news", ["disable the update news popup", "stop showing the update news"],
     ["show the update news again"], "the update news popup"),
    ("ecosystem.no_donation_nag", ["disable the donation popup", "stop the donation nag"],
     ["show the donation reminder again"], "the donation reminder"),
    ("general.snap.enabled", ["make floating windows snap to each other", "enable window snapping"],
     ["disable window snapping"], "snapping of floating windows"),
    ("gestures.workspace_swipe_invert", ["invert the workspace swipe direction"],
     ["don't invert workspace swipes"], "inverted workspace swipes"),
    ("gestures.workspace_swipe_create_new", ["create a new workspace when i swipe past the last one"],
     ["don't create new workspaces when swiping"], "creating workspaces by swiping"),
]

# Options whose "true" value means turning something OFF.
INVERTED_BOOL = {"misc.disable_hyprland_logo", "misc.disable_splash_rendering", "cursor.no_hardware_cursors",
                 "ecosystem.no_update_news", "ecosystem.no_donation_nag", "input.touchpad.disable_while_typing",
                 "xwayland.force_zero_scaling"}

ENUM_OPTS = [
    # path, [(value, [phrases], summary)]
    ("general.layout", [
        ("dwindle", ["switch to the dwindle layout", "use dwindle tiling", "go back to the default dwindle layout"], "Use the dwindle layout"),
        ("master", ["switch to the master layout", "use the master-stack layout", "i want a master and stack layout"], "Use the master layout"),
        ("scrolling", ["switch to the scrolling layout", "use the scrollable/niri-like layout", "i want windows in scrolling columns like niri"], "Use the scrolling layout"),
    ]),
    ("input.accel_profile", [
        ("flat", ["disable mouse acceleration", "turn off pointer acceleration", "i want raw mouse input, no accel"], "Disable mouse acceleration (flat profile)"),
        ("adaptive", ["enable mouse acceleration", "turn pointer acceleration back on"], "Enable mouse acceleration (adaptive profile)"),
    ]),
    ("input.follow_mouse", [
        (0, ["disable focus follows mouse", "don't change focus when i move the mouse", "focus should only change on click"], "Disable focus-follows-mouse"),
        (1, ["enable focus follows mouse", "focus the window under the cursor"], "Enable focus-follows-mouse"),
    ]),
    ("master.orientation", [
        ("left", ["put the master window on the left"], "Put the master area on the left"),
        ("right", ["put the master window on the right", "master area on the right side"], "Put the master area on the right"),
        ("top", ["put the master window at the top"], "Put the master area at the top"),
        ("center", ["center the master window", "master in the middle with stacks on both sides"], "Center the master area"),
    ]),
    ("master.new_status", [
        ("master", ["new windows should become the master", "open new windows as master"], "Open new windows as master"),
        ("slave", ["new windows should go to the stack", "don't make new windows master"], "Open new windows in the stack"),
    ]),
    ("misc.vrr", [
        (0, ["disable variable refresh rate", "turn off vrr", "disable freesync"], "Disable variable refresh rate"),
        (1, ["enable variable refresh rate", "turn on vrr", "enable freesync/adaptive sync"], "Enable variable refresh rate"),
        (2, ["enable vrr only for fullscreen apps", "adaptive sync only in fullscreen games"], "Enable variable refresh rate for fullscreen only"),
    ]),
    ("dwindle.force_split", [
        (0, ["split new windows based on the mouse position"], "Split new windows towards the cursor"),
        (2, ["always split new windows to the right or bottom", "new windows always go right/below"], "Always split new windows to the right/bottom"),
        (1, ["always split new windows to the left or top"], "Always split new windows to the left/top"),
    ]),
]

KB_LAYOUTS = {"us": "US English", "de": "German", "fr": "French", "gb": "British", "es": "Spanish", "it": "Italian",
              "ru": "Russian", "pl": "Polish", "se": "Swedish", "no": "Norwegian", "ua": "Ukrainian", "pt": "Portuguese",
              "cz": "Czech", "tr": "Turkish", "jp": "Japanese", "fi": "Finnish", "dk": "Danish", "ch": "Swiss"}
KB_OPTIONS = [
    ("caps:escape", ["make caps lock act as escape", "remap caps lock to escape", "caps lock should be escape"]),
    ("ctrl:nocaps", ["make caps lock another ctrl", "turn caps lock into control"]),
    ("caps:swapescape", ["swap caps lock and escape"]),
    ("compose:ralt", ["use right alt as the compose key", "set the compose key to right alt"]),
    ("altwin:swap_alt_win", ["swap alt and super", "swap the alt and windows keys"]),
    ("caps:backspace", ["make caps lock a backspace"]),
]
KB_VARIANTS = [("us", "dvorak", ["use dvorak", "switch to the dvorak layout"]), ("us", "colemak", ["use colemak", "switch to colemak"]),
               ("us", "intl", ["use US international", "us international with dead keys"]), ("us", "altgr-intl", ["us altgr-intl so i can type accents"])]


def _fmt_num(v: float, is_float: bool):
    return round(v, 2) if is_float else int(round(v))


def _parse_num(s: str | None):
    if s is None:
        return None
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------


def fam_num(rng, W: HyprWorld, managed):
    path, names, lo, hi, step, is_float, unit = rng.choice(NUM_OPTS)
    name = rng.choice(names)
    cur_s, cur_line, from_main = W.cfg(path, managed)
    cur = _parse_num(cur_s)
    evidence = []
    if cur is not None and rng.random() < 0.4:
        up = rng.random() < 0.5
        if (up and cur >= hi) or (not up and cur <= lo):
            up = not up
        mult = 2 if (not is_float and rng.random() < 0.25) else 1
        new = _fmt_num(min(hi, max(lo, cur + (step * mult if up else -step * mult))), is_float)
        if new == cur:
            return None
        if path.endswith("opacity"):
            req = pick(rng, ["make {n} less transparent", "increase {n}"] if up else
                       ["make {n} more transparent", "decrease {n}", "lower {n} a bit"], n=name)
        else:
            if mult == 2:
                req = pick(rng, ["make {n} a lot bigger", "increase {n} a lot", "much bigger {n}", "{n} is way too small"] if up else
                           ["make {n} a lot smaller", "decrease {n} a lot", "much smaller {n}", "{n} is way too big"], n=name)
            else:
                req = pick(rng, ["make {n} bigger", "increase {n}", "bump up {n} a bit", "more {n}", "{n} is too small", "raise {n}"] if up else
                           ["make {n} smaller", "decrease {n}", "reduce {n}", "less {n}", "{n} is too big", "lower {n}"], n=name)
        summary = f"{'Increase' if up else 'Decrease'} {path} from {cur_s} to {lval(new)}"
        if from_main:
            evidence = [cur_line]
    else:
        new = _fmt_num(rng.uniform(lo, hi) if is_float else rng.randint(int(lo), int(hi)), is_float)
        if is_float:
            new = round(round(new / step) * step, 2)
        u = unit if (unit and rng.random() < 0.4) else ""
        req = pick(rng, ["set {n} to {v}{u}", "change {n} to {v}{u}", "{n} {v}{u}", "make {n} {v}{u}", "i want {n} at {v}{u}",
                         "use {v}{u} for {n}", "{n} = {v}"], n=name, v=lval(new), u=u)
        summary = f"Set {path} to {lval(new)}"
    line = cfg_line(path, lval(new))
    ch = Change(summary, [(f"cfg:{path}", line)], ref=f"the {name} change", evidence=evidence)
    return vary(rng, req), ch


def fam_bool(rng, W: HyprWorld, managed):
    path, on, off, what = rng.choice(BOOL_OPTS)
    target_phrase_true = rng.random() < 0.5
    phrase = rng.choice(on if target_phrase_true else off)
    value = target_phrase_true
    cur_s, cur_line, from_main = W.cfg(path, managed)
    if cur_s == lval(value):
        if from_main and rng.random() < 0.5:
            state = "already " + ("set" if path in INVERTED_BOOL else ("enabled" if value else "disabled"))
            note = ""
            if path == "decoration.blur.enabled" and value and _fully_opaque(W, managed):
                note = " Blur only shows behind transparent windows, and yours are fully opaque; ask for transparent windows to see it."
            return vary(rng, phrase), Change(f"{path} is {state} ({lval(value)}) in your config; nothing to change.{note}",
                                             evidence=[cur_line])
        return None
    verb = "Enable" if value else "Disable"
    summary = f"Set {path} to {lval(value)}" if path in INVERTED_BOOL else f"{verb} {what} ({path} = {lval(value)})"
    ch = Change(summary, [(f"cfg:{path}", cfg_line(path, lval(value)))], ref=f"the {what} setting")
    return vary(rng, phrase), ch


def fam_enum(rng, W: HyprWorld, managed):
    path, choices = rng.choice(ENUM_OPTS)
    value, phrases, summary = rng.choice(choices)
    cur_s, cur_line, from_main = W.cfg(path, managed)
    if cur_s == lval(value):
        if from_main:
            return vary(rng, rng.choice(phrases)), Change(f"{path} is already {lval(value)}; nothing to change.",
                                                          evidence=[cur_line])
        return None
    return vary(rng, rng.choice(phrases)), Change(f"{summary} ({path} = {lval(value)})",
                                                  [(f"cfg:{path}", cfg_line(path, lval(value)))], ref=f"the {path} setting")


def fam_keyboard(rng, W: HyprWorld, managed):
    r = rng.random()
    cur_s, cur_line, from_main = W.cfg("input.kb_layout", managed)
    cur = cur_s.strip('"') if cur_s else "us"
    if r < 0.4:
        code, lang = rng.choice(list(KB_LAYOUTS.items()))
        if code == cur:
            return None
        req = pick(rng, ["set my keyboard layout to {l}", "use the {l} keyboard layout", "switch the keyboard to {c}",
                         "change kb layout to {c}", "i have a {l} keyboard"], l=lang, c=code)
        return vary(rng, req), Change(f"Set the keyboard layout to {code}",
                                      [("cfg:input.kb_layout", cfg_line("input.kb_layout", lstr(code)))], ref="the keyboard layout change")
    if r < 0.65:
        code, lang = rng.choice([(c, l) for c, l in KB_LAYOUTS.items() if c not in cur.split(",")])
        new = f"{cur},{code}"
        grp_opts = [("grp:alt_shift_toggle", "alt+shift"), ("grp:win_space_toggle", "super+space"),
                    ("grp:caps_toggle", "caps lock"), ("grp:ctrl_shift_toggle", "ctrl+shift")]
        opt, spoken = rng.choice(grp_opts)
        cur_opt, opt_line, opt_main = W.cfg("input.kb_options", managed)
        opts = [o for o in (cur_opt or '""').strip('"').split(",") if o and not o.startswith("grp:")]
        req = pick(rng, ["add a {l} layout and let me switch with {k}", "i also want {l}, toggle layouts with {k}",
                         "add {c} as a second layout, switch using {k}"], l=lang, c=code, k=spoken)
        ev = [cur_line] if from_main and cur_line else []
        if opt_main and opt_line and opts:
            ev.append(opt_line)
        return vary(rng, req), Change(
            f"Add the {code} layout ({new}) and switch layouts with {spoken}",
            [("cfg:input.kb_layout", cfg_line("input.kb_layout", lstr(new))),
             ("cfg:input.kb_options", cfg_line("input.kb_options", lstr(",".join(opts + [opt]))))],
            ref=f"the {lang} layout", evidence=ev)
    if r < 0.85:
        opt, phrases = rng.choice(KB_OPTIONS)
        cur_opt, opt_line, opt_main = W.cfg("input.kb_options", managed)
        opts = [o for o in (cur_opt or '""').strip('"').split(",") if o]
        if opt in opts:
            return None
        group = opt.split(":")[0]
        opts = [o for o in opts if o.split(":")[0] != group]
        ev = [opt_line] if (opt_main and opt_line and opts) else []
        return vary(rng, rng.choice(phrases)), Change(
            f"Add {opt} to the keyboard options",
            [("cfg:input.kb_options", cfg_line("input.kb_options", lstr(",".join(opts + [opt]))))],
            ref=f"the {opt} keyboard option", evidence=ev)
    layout, variant, phrases = rng.choice(KB_VARIANTS)
    return vary(rng, rng.choice(phrases)), Change(
        f"Use the {layout} {variant} keyboard variant",
        [("cfg:input.kb_layout", cfg_line("input.kb_layout", lstr(layout))),
         ("cfg:input.kb_variant", cfg_line("input.kb_variant", lstr(variant)))], ref=f"the {variant} layout")


def _color_word(rng):
    if rng.random() < 0.3:
        hexv = "".join(rng.choice("0123456789abcdef") for _ in range(6))
        spoken = rng.choice([f"#{hexv}", f"#{hexv.upper()}", hexv])
        return spoken, hexv
    name = rng.choice(list(COLORS))
    return name, COLORS[name]


def fam_colors(rng, W: HyprWorld, managed):
    r = rng.random()
    if r < 0.45:
        which = rng.choice(["active", "inactive"])
        spoken, hexv = _color_word(rng)
        what = {"active": ["the active border", "the focused window border", "the border of the active window"],
                "inactive": ["the inactive border", "unfocused window borders", "the border of inactive windows"]}[which]
        req = pick(rng, ["make {w} {c}", "set {w} color to {c}", "change {w} to {c}", "i want {w} {c}", "{c} {w}"],
                   w=rng.choice(what), c=spoken)
        path = f"general.col.{which}_border"
        return vary(rng, req), Change(f"Set the {which} border color to rgb({hexv})",
                                      [(f"cfg:{path}", cfg_line(path, lstr(f"rgb({hexv})")))], ref=f"the {which} border color")
    if r < 0.75:
        a, b = rng.sample(list(COLORS), 2)
        if rng.random() < 0.35:
            angle = rng.choice([0, 90, 135, 180, 270])
            req = pick(rng, ["active border: gradient {a} → {b}, {ang} degrees", "gradient from {a} to {b} at {ang}° for the active border",
                             "make the focused border a {a}/{b} gradient angled {ang} degrees"], a=a, b=b, ang=angle)
        else:
            angle = 45
            req = pick(rng, ["make the active border a gradient from {a} to {b}", "gradient border {a} to {b}",
                             "use a {a}-to-{b} gradient for the focused border"], a=a, b=b)
        val = f'{{ angle = {angle}, colors = {{ "rgb({COLORS[a]})", "rgb({COLORS[b]})" }} }}'
        return vary(rng, req), Change(f"Set the active border to a {a}-to-{b} gradient at {angle} degrees",
                                      [("cfg:general.col.active_border", cfg_line("general.col.active_border", val))],
                                      ref="the gradient border")
    theme = rng.choice(list(THEMES))
    act, ina = THEMES[theme]
    req = pick(rng, ["use {t} colors for the borders", "make the borders match the {t} theme", "{t} border colors",
                     "theme my window borders {t}"], t=theme)
    return vary(rng, req), Change(
        f"Use {theme} border colors",
        [("cfg:general.col.active_border", cfg_line("general.col.active_border", lstr(f"rgb({act})"))),
         ("cfg:general.col.inactive_border", cfg_line("general.col.inactive_border", lstr(f"rgb({ina})")))],
        ref=f"the {theme} border colors")


def fam_presets(rng, W: HyprWorld, managed):
    presets = [
        (["remove all gaps", "no gaps at all", "i don't want any gaps between windows", "gaps 0"],
         [("general.gaps_in", "0"), ("general.gaps_out", "0")], "Remove all gaps"),
        (["remove the window borders", "no borders", "hide window borders"], [("general.border_size", "0")], "Remove window borders"),
        (["no rounded corners", "make corners square", "disable rounding"], [("decoration.rounding", "0")], "Disable rounded corners"),
        (["make everything flat: no rounding, no shadows, no blur", "flat minimal look, no blur or shadows or rounding"],
         [("decoration.rounding", "0"), ("decoration.shadow.enabled", "false"), ("decoration.blur.enabled", "false")],
         "Flat look: no rounding, shadows or blur"),
        (["disable the anime wallpaper", "get rid of the default anime wallpaper and logo", "remove the hyprland mascot wallpaper"],
         [("misc.force_default_wallpaper", "0"), ("misc.disable_hyprland_logo", "true")], "Disable the default wallpaper and logo"),
        (["make hyprland faster on my old laptop", "optimise for a weak gpu", "make it lighter, my laptop is slow"],
         [("animations.enabled", "false"), ("decoration.blur.enabled", "false"), ("decoration.shadow.enabled", "false")],
         "Disable animations, blur and shadows for performance"),
        (["make unfocused windows slightly transparent", "inactive windows a bit see-through"],
         [("decoration.inactive_opacity", "0.9")], "Make unfocused windows 90% opaque"),
    ]
    g = rng.randrange(len(presets) + 1)
    if g == len(presets):
        n = rng.choice([2, 4, 5, 6, 8, 10, 12, 15, 20])
        req = pick(rng, ["set gaps to {n}", "gaps {n}px", "make all gaps {n}", "use {n} pixel gaps everywhere"], n=n)
        adds = [("general.gaps_in", str(n)), ("general.gaps_out", str(n))]
        summary = f"Set inner and outer gaps to {n}"
    else:
        reqs, adds, summary = presets[g]
        req = rng.choice(reqs)
    return vary(rng, req), Change(summary, [(f"cfg:{p}", cfg_line(p, v)) for p, v in adds], ref=f"the '{summary.lower()}' change")


# ---------------------------------------------------------------- binds

MOD_SETS = [(["SUPER"], 5), (["SUPER", "SHIFT"], 3), (["SUPER", "CTRL"], 1.5), (["SUPER", "ALT"], 1),
            (["ALT"], 0.7), (["CTRL", "ALT"], 0.7), (["SUPER", "CTRL", "SHIFT"], 0.3)]


def _pick_combo(rng, W: HyprWorld, prefer_bound: float = 0.3):
    if rng.random() < prefer_bound:
        cands = [l for l in W.flat if l.startswith("hl.bind(") and "mouse" not in l and "XF86" not in l and "-- submap" not in l]
        if cands:
            line = rng.choice(cands)
            key = re.match(r'^hl\.bind\("([^"]+)"', line).group(1)
            parts = [p.strip() for p in key.split("+")]
            mods, k = [p.upper() for p in parts[:-1]], parts[-1]
            if all(m in MOD_ORDER for m in mods) and re.fullmatch(r"[A-Za-z0-9]|Return|space|Tab|left|right|up|down|Escape", k):
                spoken = {"Return": "enter", "space": "space", "Tab": "tab"}.get(k, k.lower())
                return mods, k if len(k) > 1 else k.upper(), spoken
    total = sum(w for _, w in MOD_SETS)
    x = rng.random() * total
    for mods, w in MOD_SETS:
        x -= w
        if x <= 0:
            break
    spoken, key = rng.choice(FREE_KEYS)
    return list(mods), key, spoken


def make_bind(W: HyprWorld, managed, mods, key, dsp, opts=None):
    """Return (adds, evidence, replaced_line) for binding a combo, unbinding the main bind first."""
    keystr = hkey(mods, key)
    cid = combo_id(mods, key)
    line = bind_line(keystr, dsp, opts)
    adds, evidence, replaced = [], [], None
    main = W.main_bind(cid)
    if main:
        mline, mkey = main
        if mline == line:
            return None
        replaced = mline
        evidence.append(mline)
        if not any(e.slot == f"unbind:{cid}" for e in managed):
            adds.append((f"unbind:{cid}", f"hl.unbind({lstr(mkey)})"))
    adds.append((f"bind:{cid}", line))
    return adds, evidence, replaced


def _desc_replaced(replaced: str | None) -> str:
    if not replaced:
        return ""
    m = re.search(r"hl\.dsp\.(.*)\)$", replaced)
    return f" (replacing its existing binding)" if not m else f" (replacing hl.dsp.{m.group(1)})"


APP_BIND_REQ = ["bind {k} to open {a}", "{k} should launch {a}", "make {k} open {a}", "add a shortcut {k} for {a}",
                "open {a} with {k}", "{k} -> {a}", "launch {a} when i press {k}", "i want {k} to start {a}",
                "keybind {k} {a}", "set {k} to run {a}"]


def fam_bind_app(rng, W: HyprWorld, managed):
    mods, key, kspoken = _pick_combo(rng, W)
    combo = spoken_combo(rng, mods, kspoken)
    r = rng.random()
    if r < 0.7:
        app = rng.choice([a for a in APPS if a.kind != "tui"])
        cmd, name = app.cmd, app.name
    elif r < 0.85:
        lname, cmd = rng.choice(LAUNCHERS)
        name = lname
    else:
        app = rng.choice([a for a in APPS if a.kind == "tui"])
        term = W.terminal
        cmd, name = f"{term} -e {app.cmd}", f"{app.name} in a terminal"
        tl = W.main_binds_exec(term)
        if not tl:
            return None
    got = make_bind(W, managed, mods, key, f"hl.dsp.exec_cmd({lstr(cmd)})")
    if got is None:
        return None
    adds, ev, replaced = got
    if r >= 0.85:
        ev = ev + [W.main_binds_exec(W.terminal)[0][0]]
    req = pick(rng, APP_BIND_REQ, k=combo, a=name)
    return vary(rng, req), Change(f"Bind {hkey(mods, key)} to launch {cmd}{_desc_replaced(replaced)}", adds,
                                  ref=f"the {name} shortcut", evidence=ev)


def fam_swap_app(rng, W: HyprWorld, managed):
    """'use foot instead of kitty' — rebind every key that launches the old app."""
    kind = rng.choice(["terminal", "files", "launcher"])
    old = {"terminal": W.terminal, "files": W.files, "launcher": W.menu}[kind]
    if not old:
        return None
    binds = W.main_binds_exec(old)
    if not binds:
        return None
    if kind == "launcher":
        lname, new = rng.choice([(n, c) for n, c in LAUNCHERS if c != old])
        newname = lname
    else:
        app = rng.choice([a for a in APPS if a.kind == kind and a.cmd != old])
        new, newname = app.cmd, app.name
    adds, ev = [], []
    for line, key in binds:
        parts = [p.strip() for p in key.split("+")]
        mods, k = [p.upper() for p in parts[:-1]], parts[-1]
        got = make_bind(W, managed, mods, k, line[len(f"hl.bind({lstr(key)}, "):-1].replace(lstr(old), lstr(new), 1))
        if got is None:
            return None
        a, e, _ = got
        adds += a
        ev += e
    kw = rng.choice(KIND_WORDS[kind])
    req = pick(rng, ["use {n} as my {k} instead of {o}", "switch my {k} to {n}", "replace {o} with {n}",
                     "i want {n} as {k}", "change the {k} from {o} to {n}", "make {n} my default {k}"],
               n=newname, k=kw, o=old.split()[0])
    return vary(rng, req), Change(f"Launch {new} instead of {old} on {', '.join(k for _, k in binds)}", adds,
                                  ref=f"the switch to {newname}", evidence=ev)


def fam_move_app_bind(rng, W: HyprWorld, managed):
    """'change the terminal shortcut to super+t' — move an existing launcher bind."""
    kind = rng.choice(["terminal", "files", "launcher"])
    old = {"terminal": W.terminal, "files": W.files, "launcher": W.menu}[kind]
    binds = W.main_binds_exec(old) if old else []
    if not binds:
        return None
    oline, okey = binds[0]
    mods, key, kspoken = _pick_combo(rng, W, prefer_bound=0.15)
    if hkey(mods, key) == okey:
        return None
    got = make_bind(W, managed, mods, key, f"hl.dsp.exec_cmd({lstr(old)})")
    if got is None:
        return None
    adds, ev, _ = got
    ocid = combo_id_from_line(oline)
    if not any(e.slot == f"unbind:{ocid}" for e in managed):
        adds = [(f"unbind:{ocid}", f"hl.unbind({lstr(okey)})")] + adds
    kw = rng.choice(KIND_WORDS[kind])
    req = pick(rng, ["change the {k} shortcut to {c}", "move the {k} keybind to {c}", "open the {k} with {c} instead",
                     "i want {c} for the {k}, not {o}"], k=kw, c=spoken_combo(rng, mods, kspoken),
               o=okey.lower().replace(" ", ""))
    return vary(rng, req), Change(f"Move {old} from {okey} to {hkey(mods, key)}", adds,
                                  ref=f"the new {kw} shortcut", evidence=list(dict.fromkeys(ev + [oline])))


ACTIONS = [
    (["close the focused window", "close windows", "close the active window", "kill the window"], "hl.dsp.window.close()", "close the window"),
    (["force kill the window", "force-kill the focused app"], "hl.dsp.window.kill()", "force-kill the window"),
    (["toggle fullscreen", "make the window fullscreen", "fullscreen the focused window"], "hl.dsp.window.fullscreen()", "toggle fullscreen"),
    (["maximize the window", "toggle maximize", "maximize without going fullscreen"], 'hl.dsp.window.fullscreen({ mode = "maximized" })', "toggle maximize"),
    (["toggle floating", "float or tile the window", "switch the window between floating and tiled"], 'hl.dsp.window.float({ action = "toggle" })', "toggle floating"),
    (["pin the window", "pin a floating window on all workspaces", "toggle pin"], "hl.dsp.window.pin()", "toggle pin"),
    (["center the floating window", "center the window"], "hl.dsp.window.center()", "center the window"),
    (["toggle pseudotiling", "pseudo-tile the window"], "hl.dsp.window.pseudo()", "toggle pseudotiling"),
    (["toggle the split direction", "switch the split orientation"], 'hl.dsp.layout("togglesplit")', "toggle the split"),
    (["swap the two halves of the split", "swap split"], 'hl.dsp.layout("swapsplit")', "swap the split"),
    (["toggle window grouping", "make a tabbed group", "group windows into tabs"], "hl.dsp.group.toggle()", "toggle a group"),
    (["switch to the next window in the group", "go to the next tab in the group"], "hl.dsp.group.next()", "focus the next window in the group"),
    (["switch to the previous window in the group"], "hl.dsp.group.prev()", "focus the previous window in the group"),
    (["cycle through windows", "switch to the next window like alt-tab", "alt-tab between windows"], "hl.dsp.window.cycle_next()", "cycle to the next window"),
    (["cycle backwards through windows", "go to the previous window in the cycle"], "hl.dsp.window.cycle_next({ next = false })", "cycle to the previous window"),
    (["go back to the previous workspace", "switch to the last workspace i was on", "jump back to the previous workspace"], 'hl.dsp.focus({ workspace = "previous" })', "go to the previous workspace"),
    (["go to the next workspace", "switch to the next workspace"], 'hl.dsp.focus({ workspace = "e+1" })', "go to the next workspace"),
    (["go to the previous workspace in order", "switch one workspace to the left"], 'hl.dsp.focus({ workspace = "e-1" })', "go to the previous numbered workspace"),
    (["jump to an empty workspace", "open the first empty workspace"], 'hl.dsp.focus({ workspace = "empty" })', "go to an empty workspace"),
    (["focus the next monitor", "switch focus to the other monitor"], 'hl.dsp.focus({ monitor = "+1" })', "focus the next monitor"),
    (["move the current workspace to the other monitor", "send this workspace to the next monitor"], 'hl.dsp.workspace.move({ monitor = "+1" })', "move the workspace to the next monitor"),
    (["move the window to the other monitor", "send the window to the next monitor"], 'hl.dsp.window.move({ monitor = "+1" })', "move the window to the next monitor"),
    (["focus the urgent window", "jump to the window that wants attention"], "hl.dsp.focus({ urgent_or_last = true })", "focus the urgent or last window"),
    (["exit hyprland", "log out of hyprland", "quit hyprland"], "hl.dsp.exit()", "exit Hyprland"),
    (["reload the config", "reload hyprland"], "hl.dsp.reload_config()", "reload the config"),
    (["turn the screens off and on", "toggle the displays (dpms)"], 'hl.dsp.dpms({ action = "toggle" })', "toggle DPMS"),
    (["toggle the scratchpad", "show the special workspace", "toggle the magic workspace"], 'hl.dsp.workspace.toggle_special("magic")', "toggle the special workspace"),
    (["send the window to the scratchpad", "move the window to the special workspace"], 'hl.dsp.window.move({ workspace = "special:magic" })', "move the window to the special workspace"),
]

ACTION_REQ = ["bind {k} to {a}", "{k} should {a}", "make {k} {a}", "add a keybind to {a} on {k}", "i want to {a} with {k}",
              "set {k} to {a}", "{a} with {k}", "use {k} to {a}"]


def fam_bind_action(rng, W: HyprWorld, managed):
    mods, key, kspoken = _pick_combo(rng, W)
    r = rng.random()
    if r < 0.6:
        phrases, dsp, desc = rng.choice(ACTIONS)
        phrase = rng.choice(phrases)
    elif r < 0.75:
        n = rng.randint(1, 10)
        if rng.random() < 0.5:
            phrase = rng.choice([f"switch to workspace {n}", f"go to workspace {n}"])
            dsp, desc = f"hl.dsp.focus({{ workspace = {n} }})", f"focus workspace {n}"
        elif rng.random() < 0.5:
            phrase = rng.choice([f"move the window to workspace {n}", f"send the window to workspace {n}"])
            dsp, desc = f"hl.dsp.window.move({{ workspace = {n} }})", f"move the window to workspace {n}"
        else:
            phrase = rng.choice([f"move the window to workspace {n} without following it",
                                 f"silently send the window to workspace {n}"])
            dsp, desc = f"hl.dsp.window.move({{ workspace = {n}, follow = false }})", f"move the window to workspace {n} silently"
    else:
        d = rng.choice(DIRECTIONS)
        kind = rng.choice(["focus", "move", "swap"])
        phrase = {"focus": f"focus the window to the {d}", "move": f"move the window {d}",
                  "swap": f"swap the window with the one to the {d}"}[kind]
        dsp = {"focus": f'hl.dsp.focus({{ direction = "{d}" }})', "move": f'hl.dsp.window.move({{ direction = "{d}" }})',
               "swap": f'hl.dsp.window.swap({{ direction = "{d}" }})'}[kind]
        desc = phrase
    got = make_bind(W, managed, mods, key, dsp)
    if got is None:
        return None
    adds, ev, replaced = got
    req = pick(rng, ACTION_REQ, k=spoken_combo(rng, mods, kspoken), a=phrase)
    return vary(rng, req), Change(f"Bind {hkey(mods, key)} to {desc}{_desc_replaced(replaced)}", adds,
                                  ref=f"the {hkey(mods, key)} shortcut", evidence=ev)


def fam_bind_bulk(rng, W: HyprWorld, managed):
    r = rng.random()
    if r < 0.35:
        mods = rng.choice([["SUPER"], ["SUPER", "SHIFT"], ["SUPER", "CTRL"]])
        kind = {("SUPER",): "focus", ("SUPER", "SHIFT"): "move", ("SUPER", "CTRL"): "swap"}[tuple(mods)]
        adds, ev = [], []
        for d in DIRECTIONS:
            dsp = {"focus": f'hl.dsp.focus({{ direction = "{d}" }})', "move": f'hl.dsp.window.move({{ direction = "{d}" }})',
                   "swap": f'hl.dsp.window.swap({{ direction = "{d}" }})'}[kind]
            got = make_bind(W, managed, mods, VIM[d].upper(), dsp)
            if got is None:
                return None
            adds += got[0]
            ev += got[1]
        mod_sp = spoken_combo(rng, mods, "hjkl")
        req = {"focus": ["use vim keys to move focus", f"{mod_sp} to focus windows like vim", "hjkl focus navigation"],
               "move": [f"move windows with {mod_sp}", "vim keys with shift to move windows"],
               "swap": [f"swap windows with {mod_sp}"]}[kind]
        return vary(rng, rng.choice(req)), Change(f"Bind {hkey(mods, 'hjkl')} (vim keys) to {kind} in each direction",
                                                   adds, ref="the vim-key binds", evidence=ev)
    if r < 0.6:
        mods = rng.choice([["SUPER", "CTRL"], ["SUPER", "ALT"]])
        stated = rng.random() < 0.5
        step = rng.choice([10, 20, 40, 50]) if stated else 30
        deltas = {"left": (-step, 0), "right": (step, 0), "up": (0, -step), "down": (0, step)}
        adds, ev = [], []
        for d, (x, y) in deltas.items():
            got = make_bind(W, managed, mods, d, f"hl.dsp.window.resize({{ x = {x}, y = {y}, relative = true }})",
                            "{ repeating = true }")
            if got is None:
                return None
            adds += got[0]
            ev += got[1]
        sp = spoken_combo(rng, mods, "arrows")
        req = (rng.choice([f"{sp} should resize the active window by {step}px", f"resize windows with {sp} in {step}px steps"]) if stated else
               rng.choice([f"resize windows with {sp}", f"let me resize windows from the keyboard using {sp}"]))
        return vary(rng, req), Change(f"Bind {hkey(mods, 'arrows')} to resize the window by {step}px (repeating)",
                                      adds, ref="the resize binds", evidence=ev)
    if r < 0.8:
        silent = rng.random() < 0.5
        first = W.main_bind(combo_id(["SUPER", "SHIFT"], "1"))
        if not first:
            return None
        mline, mkey = first
        if silent:
            line = ('for i = 1, 10 do hl.unbind("SUPER + SHIFT + " .. i % 10) '
                    'hl.bind("SUPER + SHIFT + " .. i % 10, hl.dsp.window.move({ workspace = i, follow = false })) end')
            req = rng.choice(["make super+shift+number move windows without following them",
                              "moving a window to another workspace shouldn't switch me there",
                              "make the move-to-workspace binds silent"])
            return vary(rng, req), Change("Make SUPER + SHIFT + 0-9 move windows silently (follow = false)",
                                          [("bulk:silentmove", line)], ref="the silent move binds", evidence=[mline])
        return None
    mod = rng.choice(["ALT", "CTRL"])
    line = (f'for i = 1, 10 do hl.bind("{mod} + " .. i % 10, hl.dsp.focus({{ workspace = i }})) '
            f'hl.bind("{mod} + SHIFT + " .. i % 10, hl.dsp.window.move({{ workspace = i }})) end')
    req = rng.choice([f"also let me switch workspaces with {mod.lower()}+number",
                      f"use {mod.lower()} + 1-0 for workspaces too, and {mod.lower()}+shift to move windows"])
    return vary(rng, req), Change(f"Bind {mod} + 0-9 to switch workspaces and {mod} + SHIFT + 0-9 to move windows",
                                  [(f"bulk:ws:{mod}", line)], ref=f"the {mod.lower()} workspace binds")


MEDIA = [
    ("volume", [("XF86AudioRaiseVolume", "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ {s}%+"),
                ("XF86AudioLowerVolume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ {s}%-")],
     ["make the volume keys change the volume by {s}%", "volume keys should step by {s} percent", "set up the volume keys with {s}% steps"]),
    ("brightness", [("XF86MonBrightnessUp", "brightnessctl set {s}%+"), ("XF86MonBrightnessDown", "brightnessctl set {s}%-")],
     ["make the brightness keys change brightness by {s}%", "brightness keys in {s}% steps"]),
]


def fam_media(rng, W: HyprWorld, managed):
    r = rng.random()
    if r < 0.4:
        what, keys, reqs = rng.choice(MEDIA)
        vague = rng.random() < 0.3
        s = 5 if vague else rng.choice([1, 2, 3, 5, 10])
        req = (rng.choice([f"set up my {what} keys", f"make the {what} keys work", f"add {what} key bindings"]) if vague
               else rng.choice([t for t in reqs if "{s}" in t]).format(s=s))
        existing = [W.main_bind(combo_id([], k)) for k, _ in keys]
        if vague and all(existing):
            return vary(rng, req), Change(f"The {what} keys are already bound in your config; nothing to change.",
                                          evidence=[e[0] for e in existing])
        adds, ev = [], []
        for key, cmd in keys:
            got = make_bind(W, managed, [], key, f"hl.dsp.exec_cmd({lstr(cmd.format(s=s))})", "{ locked = true, repeating = true }")
            if got is None:
                return None
            adds += got[0]
            ev += got[1]
        return vary(rng, req), Change(f"Bind the {what} keys with {s}% steps", adds,
                                      ref=f"the {what} key change", evidence=ev)
    items = [
        (["take a screenshot of a region and copy it", "screenshot a selected area to the clipboard", "region screenshot to clipboard"],
         'grim -g "$(slurp)" - | wl-copy', "Print"),
        (["take a full screenshot and save it to ~/Pictures", "save a screenshot of the whole screen"],
         "grim ~/Pictures/screenshot-$(date +%F-%H%M%S).png", "Print"),
        (["screenshot a region with hyprshot", "use hyprshot for region screenshots"], "hyprshot -m region", "Print"),
        (["screenshot the active window with hyprshot"], "hyprshot -m window", "Print"),
        (["lock the screen", "lock my session with hyprlock"], "hyprlock", "L"),
        (["pick a color from the screen", "open the color picker"], "hyprpicker -a", "C"),
        (["open the clipboard history", "show my clipboard history with cliphist and wofi"], "cliphist list | wofi --dmenu | cliphist decode | wl-copy", "V"),
        (["toggle the notification center", "open swaync"], "swaync-client -t -sw", "N"),
        (["open the power menu", "show wlogout"], "wlogout", "Escape"),
        (["play/pause music", "toggle media playback"], "playerctl play-pause", "P"),
    ]
    phrases, cmd, default_key = rng.choice(items)
    if default_key == "Print" and rng.random() < 0.6:
        mods, key, kspoken = ([], "Print", "print screen") if rng.random() < 0.5 else (["SHIFT"], "Print", "print")
    elif rng.random() < 0.6:
        mods, key = ["SUPER"] if default_key not in "CV" else ["SUPER", "SHIFT"], default_key
        kspoken = {"Escape": "escape"}.get(key, key.lower())
    else:
        mods, key, kspoken = _pick_combo(rng, W)
    got = make_bind(W, managed, mods, key, f"hl.dsp.exec_cmd({lstr(cmd)})")
    if got is None:
        return None
    adds, ev, replaced = got
    combo = "the print screen key" if (not mods and key == "Print" and rng.random() < 0.5) else spoken_combo(rng, mods, kspoken)
    req = pick(rng, ACTION_REQ, k=combo, a=rng.choice(phrases))
    return vary(rng, req), Change(f"Bind {hkey(mods, key)} to run {cmd}{_desc_replaced(replaced)}", adds,
                                  ref=f"the {hkey(mods, key)} shortcut", evidence=ev)


def fam_unbind(rng, W: HyprWorld, managed):
    mbinds = [e for e in managed if e.slot.startswith("bind:")]
    if mbinds and rng.random() < 0.4:
        e = rng.choice(mbinds)
        key = re.match(r'^hl\.bind\("([^"]+)"', e.line).group(1)
        cid = e.slot[5:]
        main = W.main_bind(cid)
        req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "{k} shouldn't do anything", "get rid of the {k} keybind",
                         "delete the binding on {k}"], k=key.lower().replace(" ", "") if rng.random() < 0.5 else key)
        # If the main config also binds it, the unbind stays so the key really does nothing.
        dels = [e.line]
        adds = []
        if main and not any(x.slot == f"unbind:{cid}" for x in managed):
            adds = [(f"unbind:{cid}", f"hl.unbind({lstr(main[1])})")]
        return vary(rng, req), Change(f"Remove the {key} binding", adds, dels_lines=dels, ref=f"the {key} removal",
                                      evidence=[main[0]] if main else [])
    cands = [l for l in W.flat if l.startswith("hl.bind(") and "-- submap" not in l]
    line = rng.choice(cands)
    key = re.match(r'^hl\.bind\("([^"]+)"', line).group(1)
    cid = combo_id_from_line(line)
    if any(e.slot == f"unbind:{cid}" for e in managed):
        return None
    spoken = key.lower().replace(" ", "") if rng.random() < 0.5 else key
    req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "disable {k}", "{k} shouldn't do anything",
                     "i keep hitting {k} by accident, disable it", "get rid of the default {k} bind"], k=spoken)
    return vary(rng, req), Change(f"Unbind {key}", [(f"unbind:{cid}", f"hl.unbind({lstr(key)})")],
                                  ref=f"the {key} unbind", evidence=[line])


def fam_submap(rng, W: HyprWorld, managed):
    mods, key, kspoken = rng.choice([(["SUPER"], "R", "r"), (["SUPER", "SHIFT"], "R", "r"), (["SUPER", "ALT"], "R", "r"), (["ALT"], "R", "r")])
    stated = rng.random() < 0.4
    step = rng.choice([10, 30, 40, 50]) if stated else 20
    got = make_bind(W, managed, mods, key, 'hl.dsp.submap("resize")')
    if got is None:
        return None
    adds, ev, replaced = got
    vim = rng.random() < 0.4
    keys = [("h" if vim else "left", -step, 0), ("l" if vim else "right", step, 0), ("k" if vim else "up", 0, -step), ("j" if vim else "down", 0, step)]
    body = " ".join(f'hl.bind("{k}", hl.dsp.window.resize({{ x = {x}, y = {y}, relative = true }}), {{ repeating = true }})'
                    for k, x, y in keys)
    submap = f'hl.define_submap("resize", function() {body} hl.bind("Escape", hl.dsp.submap("reset")) hl.bind("Return", hl.dsp.submap("reset")) end)'
    adds = adds + [("submap:resize", submap)]
    req = pick(rng, ["create a resize submap on {k} where {d} resize by {s}px", "{k}: resize mode with {d}, {s} pixel steps"] if stated else
               ["add a resize mode on {k} using {d}", "{k} should enter a resize mode where {d} resize the window",
                "i want an i3-style resize mode bound to {k} ({d})"],
               k=spoken_combo(rng, mods, kspoken), d="hjkl" if vim else "the arrow keys", s=step)
    return vary(rng, req), Change(f"Add a resize submap on {hkey(mods, key)} ({'hjkl' if vim else 'arrows'}, {step}px; Escape/Return to leave){_desc_replaced(replaced)}",
                                  adds, ref="the resize mode", evidence=ev)


# ---------------------------------------------------------------- rules

def _match(app) -> str:
    return f"{{ class = {lstr(app.app_id)} }}"


def fam_window_rule(rng, W: HyprWorld, managed):
    app = rng.choice([a for a in APPS if a.kind != "tui"])
    n = app.name
    r = rng.random()
    if r < 0.2 or (r < 0.3 and n in FLOATY):
        effects = "float = true"
        req = pick(rng, ["make {a} float", "{a} should always open floating", "float {a} windows", "open {a} as a floating window",
                         "i want {a} to float"], a=n)
        summary, key = f"Float {app.app_id} windows", "float"
    elif r < 0.33:
        w, h = rng.choice([(800, 600), (900, 600), (1000, 700), (1200, 800), (640, 480), (960, 540)])
        effects = f'float = true, size = "{w} {h}", center = true'
        req = pick(rng, ["open {a} floating at {w}x{h} in the center", "{a} should float, be {w} by {h} and centered",
                         "make {a} a centered {w}x{h} floating window"], a=n, w=w, h=h)
        summary, key = f"Float {app.app_id} at {w}x{h}, centered", "float,size,center"
    elif r < 0.48:
        ws = rng.randint(1, 9)
        silent = rng.random() < 0.35
        effects = f'workspace = "{ws}{" silent" if silent else ""}"'
        if silent:
            req = pick(rng, ["open {a} on workspace {w} without switching to it", "{a} should go to workspace {w} silently",
                             "send {a} to workspace {w} in the background when it starts"], a=n, w=ws)
        else:
            req = pick(rng, ["always open {a} on workspace {w}", "{a} should go to workspace {w}", "put {a} on workspace {w} when it opens",
                             "assign {a} to workspace {w}"], a=n, w=ws)
        summary, key = f"Open {app.app_id} on workspace {ws}{' silently' if silent else ''}", "workspace"
    elif r < 0.58:
        if rng.random() < 0.5:
            if rng.random() < 0.3:
                a = 0.9
                req = pick(rng, ["make {a} slightly transparent", "{a} a little see-through"], a=n)
            else:
                a = rng.choice([0.7, 0.75, 0.8, 0.85, 0.9, 0.95])
                req = pick(rng, ["set {a} opacity to {o}", "{a} at {p}% opacity", "make {a} {p} percent opaque"], a=n, o=a, p=int(round(a * 100)))
            effects = f"opacity = {lval(a)}"
            summary = f"Set {app.app_id} opacity to {lval(a)}"
        else:
            a, b = rng.choice([(0.95, 0.85), (0.9, 0.8), (1.0, 0.85), (0.92, 0.75)])
            effects = f'opacity = "{lval(a)} {lval(b)}"'
            req = pick(rng, ["make {a} {x} opaque when focused and {y} when not", "{a}: opacity {x} active, {y} inactive"], a=n, x=a, y=b)
            summary = f"Set {app.app_id} opacity to {lval(a)} focused / {lval(b)} unfocused"
        key = "opacity"
    elif r < 0.64:
        effects = "opaque = true"
        req = pick(rng, ["make {a} always fully opaque", "never make {a} transparent", "{a} shouldn't be see-through"], a=n)
        summary, key = f"Keep {app.app_id} fully opaque", "opaque"
    elif r < 0.7:
        effects = 'idle_inhibit = "fullscreen"'
        req = pick(rng, ["don't let the screen sleep while {a} is fullscreen", "inhibit idle when {a} is fullscreen",
                         "keep the screen awake while watching stuff fullscreen in {a}"], a=n)
        summary, key = f"Inhibit idle while {app.app_id} is fullscreen", "idle"
    elif r < 0.76:
        which = rng.choice(["fullscreen", "maximize"])
        effects = f"{which} = true"
        req = pick(rng, ["always open {a} {w}", "{a} should start {w}"], a=n, w="fullscreen" if which == "fullscreen" else "maximized")
        summary, key = f"Open {app.app_id} {'fullscreen' if which == 'fullscreen' else 'maximized'}", which
    elif r < 0.8:
        effects = "tile = true"
        req = pick(rng, ["force {a} to tile", "{a} keeps opening floating, make it tile", "{a} should be tiled"], a=n)
        summary, key = f"Force {app.app_id} to tile", "tile"
    elif r < 0.86:
        which = rng.choice(["no_blur", "no_shadow", "no_anim", "no_initial_focus"])
        effects = f"{which} = true"
        what = {"no_blur": "blur", "no_shadow": "the shadow", "no_anim": "animations", "no_initial_focus": "focus when it opens"}[which]
        req = pick(rng, ["disable {w} for {a}", "{a} shouldn't get {w}", "no {w} on {a} windows"], a=n, w=what)
        summary, key = f"Disable {what} for {app.app_id}", which
    elif r < 0.9:
        mon = rng.choice(["DP-1", "DP-2", "HDMI-A-1", "eDP-1"])
        effects = f'monitor = "{mon}"'
        req = pick(rng, ["always open {a} on monitor {m}", "{a} should open on my {m} screen"], a=n, m=mon)
        summary, key = f"Open {app.app_id} on {mon}", "monitor"
    elif r < 0.94:
        effects = "border_size = 0, rounding = 0"
        req = pick(rng, ["no border or rounding for {a}", "remove borders and rounded corners from {a}"], a=n)
        summary, key = f"Remove border and rounding for {app.app_id}", "border,rounding"
    elif r < 0.97:
        line = ('hl.window_rule({ match = { class = "firefox", title = "Picture-in-Picture" }, float = true, pin = true, '
                'size = "640 360", move = "monitor_w-660 monitor_h-380" })')
        req = rng.choice(["make firefox picture-in-picture float and stay on all workspaces",
                          "pip videos from firefox should float, pin and sit in the bottom right corner"])
        return vary(rng, req), Change("Float and pin Firefox picture-in-picture windows in the bottom-right corner",
                                      [("wrule:firefox-pip", line)], ref="the picture-in-picture rule")
    else:
        req = rng.choice(["allow tearing for steam games", "enable tearing in games for lower input lag"])
        cur, cl, fm = W.cfg("general.allow_tearing", managed)
        adds = []
        if cur != "true":
            adds.append(("cfg:general.allow_tearing", cfg_line("general.allow_tearing", "true")))
        adds.append(("wrule:steam_app:immediate", 'hl.window_rule({ match = { class = "steam_app_.*" }, immediate = true })'))
        return vary(rng, req), Change("Allow tearing and enable it (immediate) for Steam games", adds, ref="the tearing rule for games")
    line = f"hl.window_rule({{ match = {_match(app)}, {effects} }})"
    return vary(rng, req), Change(summary, [(f"wrule:{app.app_id}:{key}", line)], ref=f"the {n} window rule")


def fam_workspace_rule(rng, W: HyprWorld, managed):
    r = rng.random()
    ws = rng.randint(1, 9)
    if r < 0.2:
        line = f'hl.workspace_rule({{ workspace = "{ws}", persistent = true }})'
        req = pick(rng, ["make workspace {w} persistent", "workspace {w} should always exist", "keep workspace {w} even when empty"], w=ws)
        return vary(rng, req), Change(f"Make workspace {ws} persistent", [(f"wsrule:{ws}:persistent", line)], ref=f"the workspace {ws} rule")
    if r < 0.45:
        mon = rng.choice(["DP-1", "DP-2", "HDMI-A-1", "eDP-1"])
        default = rng.random() < 0.4
        line = f'hl.workspace_rule({{ workspace = "{ws}", monitor = "{mon}"{", default = true" if default else ""} }})'
        req = pick(rng, ["put workspace {w} on {m}", "workspace {w} should live on monitor {m}", "bind workspace {w} to {m}"] if not default else
                   ["workspace {w} should be the default on {m}", "make {w} the default workspace of {m}"], w=ws, m=mon)
        return vary(rng, req), Change(f"Put workspace {ws} on {mon}{' as its default' if default else ''}",
                                      [(f"wsrule:{ws}:monitor", line)], ref=f"the workspace {ws} monitor rule")
    if r < 0.6:
        line = f'hl.workspace_rule({{ workspace = "{ws}", gaps_in = 0, gaps_out = 0 }})'
        req = pick(rng, ["no gaps on workspace {w}", "remove gaps only on workspace {w}", "workspace {w} without gaps"], w=ws)
        return vary(rng, req), Change(f"Remove gaps on workspace {ws}", [(f"wsrule:{ws}:gaps", line)], ref=f"the workspace {ws} gaps rule")
    if r < 0.72:
        layout = rng.choice(["master", "dwindle", "scrolling"])
        line = f'hl.workspace_rule({{ workspace = "{ws}", layout = "{layout}" }})'
        req = pick(rng, ["use the {l} layout on workspace {w}", "workspace {w} should use {l}"], w=ws, l=layout)
        return vary(rng, req), Change(f"Use the {layout} layout on workspace {ws}", [(f"wsrule:{ws}:layout", line)], ref=f"the workspace {ws} layout rule")
    if r < 0.85:
        app = rng.choice([a for a in APPS if a.kind in ("browser", "terminal", "other")])
        line = f'hl.workspace_rule({{ workspace = "{ws}", on_created_empty = {lstr(app.cmd)} }})'
        req = pick(rng, ["open {a} automatically when i go to an empty workspace {w}", "empty workspace {w} should launch {a}"], a=app.name, w=ws)
        return vary(rng, req), Change(f"Launch {app.cmd} when workspace {ws} is created empty", [(f"wsrule:{ws}:empty", line)], ref=f"the workspace {ws} autostart rule")
    lines = [
        ("wsrule:smartgaps:wtv1", 'hl.workspace_rule({ workspace = "w[tv1]", gaps_out = 0, gaps_in = 0 })'),
        ("wsrule:smartgaps:f1", 'hl.workspace_rule({ workspace = "f[1]", gaps_out = 0, gaps_in = 0 })'),
        ("wrule:smartgaps:wtv1", 'hl.window_rule({ match = { float = false, workspace = "w[tv1]" }, border_size = 0, rounding = 0 })'),
        ("wrule:smartgaps:f1", 'hl.window_rule({ match = { float = false, workspace = "f[1]" }, border_size = 0, rounding = 0 })'),
    ]
    req = rng.choice(["enable smart gaps", "remove gaps and borders when a window is alone",
                      "smart gaps like in sway"])
    return vary(rng, req), Change("Smart gaps: no gaps, border or rounding when a workspace has a single window", lines, ref="smart gaps")


LAYERS = [("waybar", "waybar"), ("rofi", "rofi"), ("wofi", "wofi"), ("fuzzel", "launcher"), ("mako notifications", "notifications"),
          ("swaync", "swaync-control-center"), ("wlogout", "logout_dialog")]


def fam_layer_rule(rng, W: HyprWorld, managed):
    name, ns = rng.choice(LAYERS)
    r = rng.random()
    if r < 0.5:
        effects, req, summary, key = "blur = true", pick(rng, ["blur {n}", "add blur behind {n}", "make {n} blurred", "i want {n} to have a blurred background"], n=name), f"Blur the {ns} layer", "blur"
    elif r < 0.7:
        if rng.random() < 0.4:
            a = rng.choice([0.1, 0.2, 0.5, 0.6])
            req = pick(rng, ["blur {n}, ignoring alpha below {a}", "blur {n} with ignore_alpha {a}"], n=name, a=a)
        else:
            a = 0.3
            req = pick(rng, ["blur {n} but not its transparent edges", "blur {n} and ignore fully transparent pixels"], n=name)
        effects = f"blur = true, ignore_alpha = {lval(a)}"
        summary, key = f"Blur the {ns} layer, ignoring alpha below {lval(a)}", "blur"
    elif r < 0.85:
        effects, req, summary, key = "no_anim = true", pick(rng, ["disable animations for {n}", "{n} shouldn't animate"], n=name), f"Disable animations for the {ns} layer", "anim"
    else:
        effects, req, summary, key = "dim_around = true", pick(rng, ["dim everything behind {n}", "darken the background when {n} is open"], n=name), f"Dim behind the {ns} layer", "dim"
    line = f'hl.layer_rule({{ match = {{ namespace = "{ns}" }}, {effects} }})'
    return vary(rng, req), Change(summary, [(f"lrule:{ns}:{key}", line)], ref=f"the {name} layer rule")


def _start_line(cmd: str) -> str:
    return f'hl.on("hyprland.start", function() hl.exec_cmd({lstr(cmd)}) end)'


def fam_autostart(rng, W: HyprWorld, managed):
    r = rng.random()
    if r < 0.8:
        k = 1 if rng.random() < 0.7 else 2
        cmds = rng.sample(AUTOSTART_POOL + ["firefox", "discord", "steam -silent", "spotify", "kdeconnect-indicator", "syncthing serve --no-browser"], k)
        adds, ev = [], []
        for c in cmds:
            line = _start_line(c)
            if line in W.flat:
                if k == 1 and rng.random() < 0.6:
                    return vary(rng, f"start {c} at login"), Change(f"{c} is already started by your config; nothing to change.", evidence=[line])
                return None
            adds.append((f"start:{c}", line))
        names = " and ".join(cmds)
        req = pick(rng, ["start {c} on login", "autostart {c}", "run {c} when hyprland starts", "launch {c} at startup",
                         "exec-once {c}", "make {c} start automatically"], c=names)
        return vary(rng, req), Change(f"Start {names} when Hyprland starts", adds, ref=f"the {names} autostart")
    started = [l for l in W.flat if l.startswith('hl.on("hyprland.start", function() hl.exec_cmd(')]
    mine = [e for e in managed if e.slot.startswith("start:")]
    if mine and rng.random() < 0.6:
        e = rng.choice(mine)
        c = e.slot[6:]
        return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore", "remove {c} from autostart"], c=c)), \
            Change(f"Stop starting {c} at login", dels_lines=[e.line], ref=f"the {c} autostart removal")
    if not started:
        return None
    line = rng.choice(started)
    c = re.search(r'exec_cmd\("((?:[^"\\]|\\.)*)"\)', line).group(1)
    return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore"], c=c)), \
        Change(f"{c} is started by your main config, which this tool does not edit; remove that hl.exec_cmd line from hyprland.lua.",
               evidence=[line])


ENVS = [
    (["set the cursor size to {v}", "make the cursor bigger, size {v}", "cursor size {v}"],
     [("XCURSOR_SIZE", "{v}"), ("HYPRCURSOR_SIZE", "{v}")], ["24", "32", "36", "48"], "Set the cursor size to {v}"),
    (["set the cursor theme to {v}", "use the {v} cursor theme"], [("XCURSOR_THEME", "{v}"), ("HYPRCURSOR_THEME", "{v}")],
     ["Bibata-Modern-Ice", "Adwaita", "Breeze", "phinger-cursors-dark"], "Use the {v} cursor theme"),
    (["force dark mode for gtk apps", "set the gtk theme to {v}"], [("GTK_THEME", "{v}")], ["Adwaita:dark"], "Set GTK_THEME to {v}"),
    (["make electron apps run natively on wayland", "fix blurry electron apps", "electron apps should use wayland"],
     [("ELECTRON_OZONE_PLATFORM_HINT", "auto")], [""], "Make Electron apps prefer Wayland"),
    (["make qt apps use wayland", "qt should run on wayland with an x11 fallback"], [("QT_QPA_PLATFORM", "wayland;xcb")], [""], "Make Qt apps use Wayland, falling back to X11"),
    (["use qt6ct to theme qt apps", "set the qt platform theme to qt6ct"], [("QT_QPA_PLATFORMTHEME", "qt6ct")], [""], "Use qt6ct for Qt theming"),
    (["set the nvidia environment variables", "i have an nvidia card, set the env vars"],
     [("LIBVA_DRIVER_NAME", "nvidia"), ("__GLX_VENDOR_LIBRARY_NAME", "nvidia")], [""], "Set the NVIDIA environment variables"),
    (["make firefox use wayland", "enable wayland in firefox"], [("MOZ_ENABLE_WAYLAND", "1")], [""], "Make Firefox use Wayland"),
]


def fam_env(rng, W: HyprWorld, managed):
    reqs, pairs, vals, summary = rng.choice(ENVS)
    v = rng.choice(vals)
    adds, ev = [], []
    for name, val in pairs:
        val = val.format(v=v)
        line = f"hl.env({lstr(name)}, {lstr(val)})"
        if line in W.flat:
            return None
        old = [l for l in W.flat if l.startswith(f"hl.env({lstr(name)},")]
        ev += old
        adds.append((f"env:{name}", line))
    return vary(rng, rng.choice(reqs).format(v=v)), Change(summary.format(v=v), adds, ref=f"the {pairs[0][0]} variable", evidence=ev)


OUTPUTS = ["eDP-1", "DP-1", "DP-2", "HDMI-A-1"]


def _mon_fields(managed, out):
    for e in managed:
        if e.slot == f"mon:{out}":
            return dict(re.findall(r'(\w+) = ("[^"]*"|[\w.]+)', e.line))
    return None


def _mon_line(fields: dict) -> str:
    order = ["output", "mode", "position", "scale", "transform", "mirror", "vrr", "disabled"]
    return "hl.monitor({ " + ", ".join(f"{k} = {fields[k]}" for k in order if k in fields) + " })"


def fam_monitor(rng, W: HyprWorld, managed):
    out = rng.choice(OUTPUTS)
    spoken = "my laptop screen" if out == "eDP-1" and rng.random() < 0.5 else out
    f = _mon_fields(managed, out) or {"output": f'"{out}"', "mode": '"preferred"', "position": '"auto"', "scale": "1"}
    f.pop("disabled", None)
    r = rng.random()
    if r < 0.3:
        res = rng.choice(["1920x1080", "2560x1440", "3840x2160", "1366x768", "2880x1800", "3440x1440"])
        hz = rng.choice([60, 75, 120, 144, 165, 240])
        f["mode"] = f'"{res}@{hz}"'
        req = pick(rng, ["set {o} to {r} at {h}hz", "{o} should run at {r}@{h}", "change the resolution of {o} to {r}, {h} Hz"], o=spoken, r=res, h=hz)
        summary = f"Set {out} to {res}@{hz}"
    elif r < 0.5:
        s = rng.choice([1, 1.25, 1.5, 1.6, 2])
        f["scale"] = lval(float(s)) if isinstance(s, float) else str(s)
        req = pick(rng, ["set the scale of {o} to {s}", "scale {o} {s}x", "{o} scaling {s}", "make {o} hidpi with scale {s}"], o=spoken, s=s)
        summary = f"Set the scale of {out} to {s}"
    elif r < 0.65:
        left = rng.choice([o for o in OUTPUTS if o != out])
        w = rng.choice([1920, 2560, 1366, 3840])
        side = rng.choice(["right", "left", "above"])
        f["position"] = {"right": f'"{w}x0"', "left": f'"-{rng.choice([1920, 2560])}x0"', "above": f'"0x-{rng.choice([1080, 1440])}"'}[side]
        if side == "right":
            req = pick(rng, ["put {o} to the right of {l} (which is {w} pixels wide)", "{o} is right of my {w}px wide {l}"], o=out, l=left, w=w)
        elif side == "left":
            width = int(f["position"].strip('"').split("x")[0][1:])
            req = pick(rng, ["{o} is {w}px wide and sits to the left of {l}", "put {o} ({w} wide) on the left of {l}"], o=out, l=left, w=width)
        else:
            hgt = int(f["position"].strip('"').split("x-")[1])
            req = pick(rng, ["{o} is above {l} and is {h}px tall", "put {o} ({h}px high) above {l}"], o=out, l=left, h=hgt)
        summary = f"Position {out} at {f['position'].strip(chr(34))}"
    elif r < 0.75:
        f = {"output": f'"{out}"', "disabled": "true"}
        req = pick(rng, ["disable {o}", "turn off {o} completely", "i don't use {o}, disable it"], o=spoken)
        summary = f"Disable {out}"
    elif r < 0.83:
        src = rng.choice([o for o in OUTPUTS if o != out])
        f["mirror"] = f'"{src}"'
        req = pick(rng, ["mirror {s} on {o}", "{o} should show the same as {s}", "duplicate {s} onto {o}"], s=src, o=out)
        summary = f"Mirror {src} on {out}"
    elif r < 0.92:
        deg, t = rng.choice([(90, 1), (180, 2), (270, 3)])
        f["transform"] = str(t)
        req = pick(rng, ["rotate {o} {d} degrees", "{o} is mounted vertically, rotate it {d}°", "flip {o} by {d} degrees"], o=spoken, d=deg)
        summary = f"Rotate {out} by {deg} degrees (transform {t})"
    else:
        f["vrr"] = "1"
        req = pick(rng, ["enable vrr on {o}", "turn on adaptive sync for {o}"], o=spoken)
        summary = f"Enable VRR on {out}"
    return vary(rng, req), Change(summary, [(f"mon:{out}", _mon_line(f))], ref=f"the {out} monitor settings")


GESTURES = [
    (3, "up", "special", ["swipe up with three fingers to toggle the special workspace", "3 finger swipe up for the scratchpad"], "toggle the special workspace"),
    (3, "down", "close", ["swipe down with three fingers to close the window", "three finger swipe down closes windows"], "close the window"),
    (4, "swipe", "move", ["drag windows around with four fingers", "4 finger swipe moves the window"], "move the window"),
    (4, "pinchout", "fullscreen", ["pinch out with four fingers to fullscreen", "4 finger pinch out toggles fullscreen"], "toggle fullscreen"),
    (4, "up", "float", ["four finger swipe up to toggle floating"], "toggle floating"),
    (4, "vertical", "workspace", ["switch workspaces with a vertical 4 finger swipe", "4 fingers up/down to change workspace"], "switch workspaces"),
    (4, "horizontal", "workspace", ["also switch workspaces with 4 fingers horizontally"], "switch workspaces"),
    (3, "pinchin", "close", ["pinch in with three fingers to close a window"], "close the window"),
]


def fam_gesture(rng, W: HyprWorld, managed):
    fingers, direction, action, reqs, desc = rng.choice(GESTURES)
    line = f'hl.gesture({{ fingers = {fingers}, direction = "{direction}", action = "{action}" }})'
    if any(l.startswith(f'hl.gesture({{ action = "{action}", direction = "{direction}", fingers = {fingers}') for l in W.flat):
        return None
    return vary(rng, rng.choice(reqs)), Change(f"Add a {fingers}-finger {direction} gesture to {desc}", [(f"gest:{fingers}:{direction}", line)],
                                              ref=f"the {fingers}-finger {direction} gesture")


ANIM_LEAVES = [("workspaces", ["workspace switching", "workspace animations", "switching workspaces"]),
               ("windows", ["window animations", "windows opening and moving"]),
               ("fade", ["fading", "fade animations"]), ("border", ["the border animation"]), ("layers", ["layer animations (bars, menus)"])]


def _anim_fields(line: str) -> dict:
    return dict(re.findall(r'(\w+) = ("[^"]*"|[\w.\-]+)', line))


def _anim_line(f: dict) -> str:
    order = ["leaf", "enabled", "speed", "bezier", "spring", "style"]
    return "hl.animation({ " + ", ".join(f"{k} = {f[k]}" for k in order if k in f) + " })"


def fam_animation(rng, W: HyprWorld, managed):
    leaf, names = rng.choice(ANIM_LEAVES)
    name = rng.choice(names)
    main = next((l for l in W.flat if l.startswith("hl.animation(") and f'leaf = "{leaf}"' in l), None)
    mine = next((e.line for e in managed if e.slot == f"anim:{leaf}"), None)
    base = mine or main
    r = rng.random()
    if r < 0.3:
        f = {"leaf": f'"{leaf}"', "enabled": "false"}
        req = pick(rng, ["disable {n}", "turn off {n}", "no {n}"], n=name)
        summary, ev = f"Disable the {leaf} animation", []
    elif r < 0.65 and base:
        f = _anim_fields(base)
        f["enabled"] = "true"
        cur = float(f.get("speed", "5"))
        faster = rng.random() < 0.6
        new = round(cur * (0.5 if faster else 1.8), 2)
        f["speed"] = f"{new:g}"
        req = pick(rng, ["make {n} faster", "speed up {n}", "{n} are too slow"] if faster else
                   ["make {n} slower", "slow down {n}", "{n} feel too fast"], n=name)
        summary = f"{'Speed up' if faster else 'Slow down'} the {leaf} animation (speed {cur:g} -> {new:g}; lower is faster)"
        ev = [main] if not mine else []
    elif leaf in ("workspaces", "windows"):
        styles = {"workspaces": [("slide", "slide"), ("slidevert", "slide vertically"), ("fade", "fade"), ("slidefade", "slide and fade")],
                  "windows": [("slide", "slide in"), ("popin 80%", "pop in")]}[leaf]
        style, sp = rng.choice(styles)
        f = _anim_fields(base) if base else {"leaf": f'"{leaf}"', "speed": "4", "bezier": '"default"'}
        f["enabled"] = "true"
        f["style"] = f'"{style}"'
        req = pick(rng, ["make {n} {s}", "{n} should {s}", "i want {n} to {s}"], n=name, s=sp)
        summary = f"Make the {leaf} animation use the {style} style"
        ev = [main] if (base and not mine) else []
    else:
        return None
    if f.get("enabled") == "true" and "bezier" not in f and "spring" not in f:
        f["bezier"] = '"default"'
    if f.get("enabled") == "true" and "speed" not in f:
        f["speed"] = "4"
    return vary(rng, req), Change(summary, [(f"anim:{leaf}", _anim_line(f))], ref=f"the {leaf} animation change", evidence=ev)


DEVICES = [("logitech-g502-hero-gaming-mouse", "mouse"), ("razer-razer-deathadder-v2", "mouse"), ("logitech-mx-master-3s", "mouse"),
           ("elan0670:00-04f3:3150-touchpad", "touchpad"), ("syna2ba6:00-06cb:ce44-touchpad", "touchpad"),
           ("keychron-keychron-k2", "keyboard"), ("at-translated-set-2-keyboard", "keyboard")]


def fam_device(rng, W: HyprWorld, managed):
    name, kind = rng.choice(DEVICES)
    existing = next((e.line for e in managed if e.slot == f"dev:{name}"), None)
    f = dict(re.findall(r'(\w+) = ("[^"]*"|[\w.\-]+)', existing)) if existing else {"name": lstr(name)}
    if kind == "mouse":
        if rng.random() < 0.6:
            v = rng.choice([-0.8, -0.5, -0.3, 0.2, 0.4])
            f["sensitivity"] = lval(v)
            req = pick(rng, ["set the sensitivity of {d} to {v}", "my {d} is too fast, set sensitivity {v}"], d=name, v=v)
            summary = f"Set {name} sensitivity to {v}"
        else:
            f["accel_profile"] = '"flat"'
            req = pick(rng, ["disable acceleration only for {d}", "flat accel profile for {d}"], d=name)
            summary = f"Use a flat acceleration profile for {name}"
    elif kind == "touchpad":
        f["natural_scroll"] = "true"
        req = pick(rng, ["natural scrolling only on {d}", "enable natural scroll for the device {d}"], d=name)
        summary = f"Enable natural scrolling on {name}"
    else:
        code, lang = rng.choice(list(KB_LAYOUTS.items()))
        f["kb_layout"] = lstr(code)
        req = pick(rng, ["use the {l} layout only on {d}", "my external keyboard {d} is {l}, set its layout"], d=name, l=lang)
        summary = f"Use the {code} layout on {name}"
    line = "hl.device({ " + ", ".join(f"{k} = {v}" for k, v in f.items()) + " })"
    return vary(rng, req), Change(summary, [(f"dev:{name}", line)], ref=f"the {name} device settings")


# ---------------------------------------------------------------- managed-file maintenance

def fam_remove(rng, W: HyprWorld, managed):
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
        req = pick(rng, ["remove {r}", "undo {r}", "get rid of {r}", "revert {r}", "i don't want {r} anymore", "delete {r}"], r=ref)
        return vary(rng, req), Change(f"Remove {ref}", dels_lines=[e.line for e in group], ref="")
    if r < 0.8:
        cid = cids[-1]
        group = [e for e in managed if e.cid == cid]
        req = rng.choice(["undo the last change", "revert your last edit", "undo that", "go back, undo the previous change"])
        return vary(rng, req), Change(f"Undo the last change ({group[0].ref})", dels_lines=[e.line for e in group])
    req = rng.choice(["remove everything you added", "reset all your changes", "undo all the changes in the managed file",
                      "clear all my customisations from the ai file", "start over, remove all managed settings"])
    return vary(rng, req), Change("Remove all managed changes", dels_lines=[e.line for e in managed])


OFF_TOPIC = [
    ("what's the weather like tomorrow", "This is not a Hyprland configuration request."),
    ("write me a haiku about tiling", "This is not a Hyprland configuration request."),
    ("install firefox", "Installing software is not a config change; use your package manager (e.g. pacman -S firefox)."),
    ("update my system", "Updating the system is not a config change; run your package manager."),
    ("how do i exit vim", "This is not a Hyprland configuration request."),
    ("tell me a joke", "This is not a Hyprland configuration request."),
    ("open firefox", "That asks to run something now, not to change the config; ask for a keybind or autostart instead."),
    ("close this window", "That is an action, not a config change; ask for a keybind if you want one."),
    ("fix my wifi", "Network setup is not part of the Hyprland config."),
    ("set up my printer", "Printer setup is not part of the Hyprland config."),
    ("change my gnome wallpaper", "GNOME settings are not part of the Hyprland config."),
    ("configure my zsh prompt", "Shell configuration is not part of the Hyprland config."),
    ("add titlebars to windows", "Hyprland has no built-in titlebars; a plugin such as hyprbars provides them."),
    ("make sway use blur", "This tool is set up for Hyprland, not Sway."),
]


def fam_noop(rng, W: HyprWorld, managed):
    req, summary = rng.choice(OFF_TOPIC)
    return vary(rng, req), Change(summary)

# ---------------------------------------------------------------- whole-look intents

def _fully_opaque(W: HyprWorld, managed) -> bool:
    vals = [_parse_num(W.cfg(f"decoration.{k}_opacity", managed)[0]) for k in ("active", "inactive")]
    return all(v is None or v >= 1 for v in vals)


TRANSPARENCY = {
    "default": ((0.9, 0.8), ["enable window transparency", "make windows transparent", "make my windows see-through",
                             "i want transparent windows", "turn on transparency", "add transparency to the windows"]),
    "slight": ((0.95, 0.9), ["make windows slightly transparent", "a little transparency on all windows",
                             "make the windows a bit see-through"]),
    "strong": ((0.85, 0.7), ["make windows very transparent", "lots of transparency please", "make windows really see-through"]),
}


def _transparency(rng, W: HyprWorld, managed):
    level = rng.choice(["default", "default", "slight", "strong"])
    (act, ina), reqs = TRANSPARENCY[level]
    want_blur = rng.random() < 0.4
    req = rng.choice(reqs)
    if want_blur:
        generic = ["frosted glass windows", "transparent blurred windows", "enable transparency and blur"] if level == "default" else []
        req = rng.choice([req + " with blur", req + " and blur what's behind them"] + generic)
    adds, ev = [], []
    for k, v in (("active", act), ("inactive", ina)):
        path = f"decoration.{k}_opacity"
        cur_s, cur_line, from_main = W.cfg(path, managed)
        if _parse_num(cur_s) == v:
            continue
        adds.append((f"cfg:{path}", cfg_line(path, lval(v))))
        if from_main and cur_line:
            ev.append(cur_line)
    blur_s, blur_line, blur_main = W.cfg("decoration.blur.enabled", managed)
    if want_blur and blur_s != "true":
        adds.append(("cfg:decoration.blur.enabled", cfg_line("decoration.blur.enabled", "true")))
    if not adds:
        return None
    if want_blur and blur_s == "true" and blur_main and blur_line:
        ev.append(blur_line)
    summary = f"Make focused windows {int(act * 100)}% and unfocused windows {int(ina * 100)}% opaque"
    if want_blur:
        summary += ", with blur behind them" + (" (already enabled)" if blur_s == "true" else "")
    return vary(rng, req), Change(summary, adds, ref="the transparency", evidence=ev)


ANIM_SPEED_REQS = [
    (0.5, ["make the animations faster", "speed up the animations", "animations are too slow", "make animations snappier",
           "make animations twice as fast", "2x faster animations", "animation speed 2x", "faster animations"]),
    (0.75, ["make the animations a bit faster", "slightly faster animations", "speed up animations a little"]),
    (0.33, ["make animations 3x faster", "make the animations much faster", "animations are way too slow"]),
    (2.0, ["slow down the animations", "make animations slower", "animations are too fast", "animations twice as slow",
           "make the animations half as fast", "slower animations"]),
    (1.5, ["make the animations a bit slower", "slow the animations down a little"]),
]


def _anim_speed(rng, W: HyprWorld, managed):
    """Scale every animation: each leaf with its own speed would otherwise ignore a global change."""
    factor, reqs = rng.choice(ANIM_SPEED_REQS)
    mine = {e.slot: e.line for e in managed if e.slot.startswith("anim:")}
    adds, ev, seen = [], [], set()
    for line in W.flat:
        if not line.startswith("hl.animation("):
            continue
        f = _anim_fields(line)
        leaf = f.get("leaf", "").strip('"')
        if not leaf or leaf in seen:
            continue
        seen.add(leaf)
        base = mine.get(f"anim:{leaf}", line)
        f = _anim_fields(base)
        if f.get("enabled") == "false" or "speed" not in f:
            continue
        new = max(0.1, round(float(f["speed"]) * factor, 2))
        f["speed"] = f"{new:g}"
        adds.append((f"anim:{leaf}", _anim_line(f)))
        if base == line:
            ev.append(line)
    if not adds:
        g = mine.get("anim:global")
        f = _anim_fields(g) if g else {"leaf": '"global"', "enabled": "true", "speed": "8", "bezier": '"default"'}
        f["speed"] = f"{max(0.1, round(float(f.get('speed', '8')) * factor, 2)):g}"
        adds.append(("anim:global", _anim_line(f)))
    verb = "Speed up" if factor < 1 else "Slow down"
    summary = f"{verb} all animations: every speed x{factor:g} (lower is faster)"
    return vary(rng, rng.choice(reqs)), Change(summary, adds, ref="the animation speed", evidence=ev)


SINGLE_RULES = [("wtv1", "w[tv1]"), ("f1", "f[1]")]


def _single_window(rng, W: HyprWorld, managed):
    what = rng.choice(["border", "border", "gaps"])
    if what == "border":
        word = rng.choice(["border", "outline", "frame", "window border"])
        req = pick(rng, ["remove the {w} when there's only one window", "no {w} when only one window is on screen",
                         "hide the {w} when a window is alone", "smart borders", "don't draw a {w} around a single window",
                         "only show the {w} when there are several windows"], w=word)
        adds = [(f"wrule:smartgaps:{s}", f'hl.window_rule({{ match = {{ float = false, workspace = "{ws}" }}, border_size = 0 }})')
                for s, ws in SINGLE_RULES]
        summary = "Hide the border of a tiled window when it is alone on its workspace"
    else:
        req = rng.choice(["no gaps when there's only one window", "remove the gaps around a lone window",
                          "a single window should fill the screen without gaps"])
        adds = [(f"wsrule:smartgaps:{s}", f'hl.workspace_rule({{ workspace = "{ws}", gaps_out = 0, gaps_in = 0 }})')
                for s, ws in SINGLE_RULES]
        summary = "Remove the gaps when a workspace has a single tiled window"
    return vary(rng, req), Change(summary, adds, ref="the single-window rule")


def fam_look(rng, W: HyprWorld, managed):
    r = rng.random()
    if r < 0.4:
        return _transparency(rng, W, managed)
    if r < 0.75:
        return _anim_speed(rng, W, managed)
    return _single_window(rng, W, managed)


FAMILIES = [
    (10, "num", fam_num), (7, "bool", fam_bool), (4, "enum", fam_enum), (5, "keyboard", fam_keyboard),
    (5, "colors", fam_colors), (3, "presets", fam_presets), (12, "bind_app", fam_bind_app), (3, "swap_app", fam_swap_app),
    (2.5, "move_app_bind", fam_move_app_bind), (12, "bind_action", fam_bind_action), (3, "bind_bulk", fam_bind_bulk),
    (5, "media", fam_media), (4, "unbind", fam_unbind), (1.5, "submap", fam_submap), (10, "window_rule", fam_window_rule),
    (4, "workspace_rule", fam_workspace_rule), (3, "layer_rule", fam_layer_rule), (4, "autostart", fam_autostart),
    (3, "env", fam_env), (5, "monitor", fam_monitor), (2, "gesture", fam_gesture), (3, "animation", fam_animation), (4, "look", fam_look),
    (1.5, "device", fam_device), (6, "remove", fam_remove), (2, "noop", fam_noop),
]

PRIOR_FAMILIES = [fam_num, fam_bool, fam_enum, fam_colors, fam_bind_app, fam_bind_action, fam_media, fam_window_rule,
                  fam_workspace_rule, fam_layer_rule, fam_autostart, fam_env, fam_monitor, fam_gesture, fam_animation, fam_look,
                  fam_keyboard, fam_device]


def known_config_keys() -> set[str]:
    s = Path("/usr/share/hypr/stubs/hl.meta.lua").read_text()
    return set(re.findall(r"---@field \['([^']+)'\]", s))


def check_tables():
    keys = known_config_keys()
    missing = [p for p, *_ in NUM_OPTS + BOOL_OPTS + ENUM_OPTS if p not in keys]
    for p in ["general.col.active_border", "general.col.inactive_border", "input.kb_layout", "input.kb_options",
              "input.kb_variant", "misc.force_default_wallpaper"]:
        if p not in keys:
            missing.append(p)
    return missing
