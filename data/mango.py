"""MangoWC 0.18 sample families.

Every directive form used here was checked with `mango -p`, and every sample
is validated with it at build time (see data/build.py). Mango runs only the
first matching binding and has no unbind, so a rebind of a key, gesture or
switch that the main config binds disables that main line with
`wmai_disable=<line>` (see wmllm/mango.py).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from data.common import (APPS, COLORS, DIRECTIONS, FLOATY, FREE_KEYS, KIND_WORDS, LAUNCHERS, MOD_SPOKEN, THEMES, VIM,
                         Change, pick, vary)
from wmllm.mango import DISABLE_KEY, combo_of_bind, flatten_mango

DEFAULT_CONFIG = Path("/etc/mango/config.conf")
WM = "mango"
SOURCE_TOKEN = "@MANAGED@"
FOOTER = f"\n\n# Managed by wmai (keep this last so its settings win)\nkey_mode=default\nsource={SOURCE_TOKEN}\n"

# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

MOD_ORDER = ["SUPER", "CTRL", "ALT", "SHIFT"]


def mmods(mods) -> str:
    return "+".join(m for m in MOD_ORDER if m in mods) or "NONE"


def mkey(key: str) -> str:
    return key.lower() if len(key) == 1 else key


def combo_id(mods, key: str) -> str:
    k = key.lower()
    k = {"enter": "return", "esc": "escape"}.get(k, k)
    return "+".join(sorted(mods)) + "+" + k


def combo_id_from_line(line: str) -> str | None:
    c = combo_of_bind(line)
    if c is None:
        return None
    return "+".join(sorted(c[0])) + "+" + c[1]


def shown(mods, key: str) -> str:
    """How a combo is named in a summary."""
    return "+".join([m for m in MOD_ORDER if m in mods] + [mkey(key)])


def spoken(rng: random.Random, mods, key_spoken: str) -> str:
    words = [rng.choice([w for w in MOD_SPOKEN[m] if w.lower() != "mod"]) for m in mods]
    k = key_spoken.upper() if len(key_spoken) == 1 and rng.random() < 0.4 else key_spoken
    sep = rng.choice(["+", "+", "+", " + ", "-"])
    return sep.join(words + [k])


# --------------------------------------------------------------------------
# Worlds
# --------------------------------------------------------------------------

TERMINAL_CMDS = [a.cmd for a in APPS if a.kind == "terminal"]
MENU_CMDS = [c for _, c in LAUNCHERS]
AUTOSTART_POOL = ["waybar", "mako", "swaync", "nm-applet --indicator", "blueman-applet", "wl-paste --watch cliphist store",
                  "udiskie", "kanshi", "/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1", "fcitx5 -d", "gammastep",
                  "swaybg -i ~/Pictures/wallpaper.jpg -m fill"]


@dataclass
class MangoWorld:
    text: str
    flat: list[str]
    terminal: str
    menu: str

    def value(self, key: str, managed) -> tuple[str | None, str | None, bool]:
        """(value, line, from_main) of the last assignment of key (managed first)."""
        for e in reversed(managed):
            if e.line.startswith(key + "="):
                return e.line.split("=", 1)[1], e.line, False
        for l in reversed(self.flat):
            if l.startswith(key + "="):
                return l.split("=", 1)[1], l, True
        return None, None, True

    def main_binds(self, cid: str, kinds=("bind",)) -> list[str]:
        return [l for l in self.flat if l.split("=", 1)[0].startswith(kinds) and l.split("=", 1)[0] not in ("mousebind", "axisbind",
                "gesturebind", "switchbind") and combo_id_from_line(l) == cid]

    def main_spawns(self, cmd: str) -> list[str]:
        return [l for l in self.flat if re.match(r"^bind[a-z]*=", l) and re.search(rf",spawn(?:_shell)?,{re.escape(cmd)}$", l)]


def _set(text: str, key: str, value) -> str:
    return re.sub(rf"(?m)^{re.escape(key)}\s*=.*$", f"{key}={value}", text)


def _mutate(rng: random.Random, base: str) -> tuple[str, dict]:
    t = base
    term = rng.choice(TERMINAL_CMDS)
    menu = rng.choice(MENU_CMDS)
    t = t.replace("bind=Alt,Return,spawn,foot", f"bind=Alt,Return,spawn,{term}")
    t = t.replace("bind=Alt,space,spawn,rofi -show drun", f"bind=Alt,space,spawn,{menu}")
    if rng.random() < 0.5:
        g = rng.choice([0, 2, 4, 5, 6, 8, 10])
        t = _set(_set(t, "gap_inner_horizontal", g), "gap_inner_vertical", g)
    if rng.random() < 0.4:
        g = rng.choice([0, 4, 6, 8, 10, 12, 16])
        t = _set(_set(t, "gap_outer_horizontal", g), "gap_outer_vertical", g)
    if rng.random() < 0.5:
        t = _set(t, "border_px", rng.choice([1, 2, 2, 3, 4]))
    if rng.random() < 0.4:
        t = _set(t, "border_radius", rng.choice([0, 4, 8, 10, 12]))
    for key, p in (("blur", 0.3), ("shadows", 0.3), ("animations", 0.1), ("sloppy_focus", 0.2), ("trackpad_natural_scrolling", 0.3)):
        if rng.random() < p:
            t = _set(t, key, 1 - int(re.search(rf"(?m)^{key}\s*=\s*(\d)", t).group(1)))
    if rng.random() < 0.4:
        t = _set(t, "xkb_rules_layout", rng.choice(["us", "de", "gb", "fr", "us,de", "pl"]))
    if rng.random() < 0.3:
        lay = rng.choice(["scroller", "scroller", "dwindle", "monocle", "grid"])
        t = t.replace("layout_name:tile", f"layout_name:{lay}")
    extra = []
    for c in rng.sample(AUTOSTART_POOL, rng.choice([0, 0, 1, 2, 3])):
        extra.append(f"exec_once={c}")
    if rng.random() < 0.4:
        extra.append(f"bind=SUPER,b,spawn,{rng.choice(['firefox', 'chromium', 'brave', 'librewolf'])}")
    if rng.random() < 0.25:
        extra.append("window_rule=is_floating:1,app_id:org.pulseaudio.pavucontrol")
    if rng.random() < 0.25:
        extra.append(f"monitor_rule=name:^eDP-1$,scale:{rng.choice(['1', '1.25', '1.5', '2'])}")
    if rng.random() < 0.2:
        extra.append("env=QT_QPA_PLATFORMTHEME,qt6ct")
    if rng.random() < 0.2:
        t = re.sub(r"(?m)^gesturebind=.*\n", "", t)
    if extra:
        t = t.rstrip() + "\n\n# my additions\n" + "\n".join(extra) + "\n"
    return t, {"terminal": term, "menu": menu}


MINIMAL = """# {comment}
border_px={bs}
gap_inner_horizontal={gi}
gap_inner_vertical={gi}
gap_outer_horizontal={go}
gap_outer_vertical={go}
focus_color=0x{fc}ff
border_color=0x585b70ff
xkb_rules_layout={kb}
repeat_rate=25
repeat_delay=600
tap_to_click=1
trackpad_natural_scrolling=1
sloppy_focus=1

exec_once=waybar

bind=SUPER,Return,spawn,{term}
bind=SUPER,d,spawn,{menu}
bind=SUPER,q,killclient
bind=SUPER,f,togglefullscreen
bind=SUPER+SHIFT,space,togglefloating
bind=SUPER+SHIFT,r,reload_config
bind=SUPER+SHIFT,e,quit
bind=SUPER,h,focusdir,left
bind=SUPER,j,focusdir,down
bind=SUPER,k,focusdir,up
bind=SUPER,l,focusdir,right
bind=SUPER,1,view,1,0
bind=SUPER,2,view,2,0
bind=SUPER,3,view,3,0
bind=SUPER+SHIFT,1,tag,1,0
bind=SUPER+SHIFT,2,tag,2,0
bind=SUPER+SHIFT,3,tag,3,0
mousebind=SUPER,btn_left,moveresize,curmove
mousebind=SUPER,btn_right,moveresize,curresize

tag_rule=id:*,layout_name:{layout}
"""


def build_worlds(n: int, seed: int = 1) -> list[MangoWorld]:
    """Synthetic configs. Ones the checker already rejects are skipped: some layouts
    (e.g. de) map two of the stock bindings to the same keycode."""
    from wmllm.validate import validate_mango
    rng = random.Random(seed)
    base = DEFAULT_CONFIG.read_text()
    worlds = []
    while len(worlds) < n:
        if rng.random() < 0.2:
            term, menu = rng.choice(TERMINAL_CMDS), rng.choice(MENU_CMDS)
            text = MINIMAL.format(comment=rng.choice(["mango config", "my minimal mango setup"]), bs=rng.choice([1, 2, 3]),
                                  gi=rng.choice([0, 4, 6, 8]), go=rng.choice([0, 8, 10]), fc=rng.choice(list(COLORS.values())),
                                  kb=rng.choice(["us", "de", "gb"]), term=term, menu=menu,
                                  layout=rng.choice(["tile", "scroller", "dwindle"]))
            params = {"terminal": term, "menu": menu}
        else:
            text, params = _mutate(rng, base)
        text = text.rstrip() + FOOTER
        if validate_mango(text, []):
            continue
        worlds.append(MangoWorld(text, flatten_mango(text.replace(f"source={SOURCE_TOKEN}", "")), **params))
    return worlds


# --------------------------------------------------------------------------
# Helpers for families
# --------------------------------------------------------------------------

def disabled(managed) -> set[str]:
    return {e.line[len(DISABLE_KEY):] for e in managed if e.line.startswith(DISABLE_KEY)}


def take_over(W: MangoWorld, managed, mains: list[str]):
    """Disable the main-config lines a new binding would collide with."""
    off = disabled(managed)
    adds = [(f"disable:{m}", DISABLE_KEY + m) for m in mains if m not in off]
    return adds, list(mains)


def make_bind(W: MangoWorld, managed, mods, key, action: str, kind="bind"):
    cid = combo_id(mods, key)
    line = f"{kind}={mmods(mods)},{mkey(key)},{action}"
    mains = W.main_binds(cid)
    if line in mains:
        return None
    adds, ev = take_over(W, managed, mains)
    return adds + [(f"bind:{cid}", line)], ev, (mains[0] if mains else None)


def _repl(main):
    if not main:
        return ""
    return f" (replaces '{main.split(',', 2)[-1].rstrip(',')}')"


# --------------------------------------------------------------------------
# Families: options
# --------------------------------------------------------------------------

NUMS = [
    # keys, names, lo, hi, step
    (["gap_inner_horizontal", "gap_inner_vertical"], ["the gaps between windows", "inner gaps", "the inner gap"], 0, 30, 3),
    (["gap_outer_horizontal", "gap_outer_vertical"], ["outer gaps", "the gaps at the screen edges", "the outer gap"], 0, 40, 4),
    (["border_px"], ["the border width", "border size", "window border thickness"], 0, 8, 1),
    (["border_radius"], ["the corner radius", "corner rounding", "how rounded the corners are"], 0, 20, 2),
    (["repeat_rate"], ["the key repeat rate", "keyboard repeat rate"], 15, 80, 10),
    (["repeat_delay"], ["the key repeat delay", "the delay before keys repeat"], 150, 800, 100),
    (["shadows_size"], ["the shadow size", "how big the shadows are"], 5, 40, 5),
    (["blur_params_radius"], ["the blur radius", "blur strength"], 2, 20, 2),
    (["animation_duration_open"], ["the open animation duration in ms", "how long the window open animation takes (ms)"], 100, 800, 100),
    (["animation_duration_close"], ["the close animation duration in ms"], 100, 800, 100),
    (["snap_distance"], ["the floating snap distance"], 10, 60, 10),
    (["cursor_size"], ["the cursor size", "mouse pointer size"], 16, 64, 8),
]


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fam_num(rng, W: MangoWorld, managed):
    keys, names, lo, hi, step = rng.choice(NUMS)
    name = rng.choice(names)
    cur, line, from_main = W.value(keys[0], managed)
    cur = _int(cur)
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
        summary = f"{'Increase' if up else 'Decrease'} {' and '.join(keys)} from {cur} to {new}"
        if from_main:
            ev = [line]
    else:
        new = rng.randrange(lo, hi + 1, step if lo % step == 0 else 1)
        if new == cur:
            return None
        req = pick(rng, ["set {n} to {v}", "change {n} to {v}", "{n} {v}", "make {n} {v}", "use {v} for {n}"], n=name, v=new)
        summary = f"Set {' and '.join(keys)} to {new}"
    return vary(rng, req), Change(summary, [(f"opt:{k}", f"{k}={new}") for k in keys], ref=f"the {name} change", evidence=ev)


TOGGLES = [
    # key, phrases for 1, phrases for 0, what
    ("blur", ["enable blur", "turn on blur behind windows", "frosted glass windows"], ["disable blur", "turn off the blur"], "blur"),
    ("blur_layer", ["blur layer surfaces like waybar and rofi", "blur behind the bar and launcher"], ["don't blur layer surfaces"], "layer blur"),
    ("shadows", ["enable window shadows", "add drop shadows"], ["disable shadows", "remove the window shadows"], "shadows"),
    ("shadow_only_floating", ["only floating windows should have shadows"], ["shadows on all windows, not just floating ones"], "floating-only shadows"),
    ("animations", ["enable animations", "turn animations on"], ["disable animations", "turn off all animations", "no animations please"], "animations"),
    ("smart_gaps", ["no gaps when there's only one window", "enable smart gaps"], ["always show gaps, even with one window", "disable smart gaps"], "smart gaps"),
    ("no_border_when_single", ["hide the border when there's only one window"], ["show the border even with a single window"], "single-window border"),
    ("no_radius_when_single", ["square corners when only one window is open"], ["keep rounded corners with a single window"], "single-window corners"),
    ("sloppy_focus", ["enable focus follows mouse", "focus the window under the mouse"], ["disable focus follows mouse", "focus only on click"], "focus follows mouse"),
    ("warp_cursor", ["move the mouse to the focused window", "warp the cursor on focus change"], ["don't move the mouse when focus changes", "disable cursor warping"], "cursor warping"),
    ("tap_to_click", ["enable tap to click", "let me tap the touchpad to click"], ["disable tap to click", "stop touchpad taps from clicking"], "tap to click"),
    ("trackpad_natural_scrolling", ["enable natural scrolling on the touchpad", "reverse touchpad scrolling like a mac"],
     ["disable natural scrolling on the touchpad", "normal touchpad scroll direction"], "touchpad natural scrolling"),
    ("mouse_natural_scrolling", ["invert the mouse wheel", "natural scrolling for the mouse"], ["normal mouse wheel direction"], "mouse natural scrolling"),
    ("trackpad_disable_while_typing", ["disable the touchpad while typing", "ignore the touchpad while i type"],
     ["keep the touchpad working while typing"], "disable-while-typing"),
    ("disable_trackpad", ["turn the trackpad off completely"], ["turn the trackpad back on"], "trackpad"),
    ("mouse_left_handed", ["left handed mouse", "swap the mouse buttons for a lefty"], ["right handed mouse buttons again"], "left-handed mouse"),
    ("numlock_on", ["turn numlock on at startup", "enable numlock by default"], ["don't turn numlock on at startup"], "numlock"),
    ("focus_on_activate", ["let apps take focus when they request it"], ["don't let apps steal focus"], "focus on activation"),
    ("enable_hotarea", ["enable the hot corner that opens the overview"], ["disable the hot corner"], "hot corner"),
    ("dim_enable", ["dim unfocused windows"], ["stop dimming unfocused windows"], "dimming"),
    ("idle_inhibit_when_fullscreen", ["don't let the screen sleep while something is fullscreen"], ["allow idle even when a window is fullscreen"], "fullscreen idle inhibit"),
    ("enable_floating_snap", ["snap floating windows to edges and other windows"], ["disable floating window snapping"], "floating snap"),
    ("new_is_master", ["new windows should become the master"], ["new windows should go to the stack, not the master"], "new-is-master"),
    ("scroller_focus_center", ["keep the focused window centered in the scroller layout"], ["don't center the focused window in scroller"], "scroller centering"),
    ("focus_cross_monitor", ["let directional focus move to other monitors"], ["keep directional focus on the current monitor"], "cross-monitor focus"),
]


def fam_toggle(rng, W: MangoWorld, managed):
    key, on, off, what = rng.choice(TOGGLES)
    v = rng.choice([1, 0])
    phrases = on if v else off
    cur, line, from_main = W.value(key, managed)
    if cur == str(v):
        if from_main and rng.random() < 0.5:
            return vary(rng, rng.choice(phrases)), Change(f"Your config already has '{line}'; nothing to change.", evidence=[line])
        return None
    return vary(rng, rng.choice(phrases)), Change(f"{'Enable' if v else 'Disable'} {what} ({key}={v})", [(f"opt:{key}", f"{key}={v}")],
                                                  ref=f"the {what} setting")


ANIM_TYPES = {"slide": ["slide in", "slide"], "zoom": ["zoom in", "zoom"], "fade": ["fade in", "fade"], "none": ["not animate", "have no animation"]}


def fam_enum(rng, W: MangoWorld, managed):
    r = rng.random()
    if r < 0.5:
        which = rng.choice(["open", "close"])
        t = rng.choice(list(ANIM_TYPES))
        verb = rng.choice(ANIM_TYPES[t])
        verb = verb.replace(" in", " out") if which == "close" else verb
        req = pick(rng, ["windows should {v} when they {w}", "make windows {v} on {w}", "use the {t} animation for {w}ing windows",
                         "{w} animation: {t}"], v=verb, w=which, t=t)
        key = f"animation_type_{which}"
        return vary(rng, req), Change(f"Use the {t} animation when windows {which}", [(f"opt:{key}", f"{key}={t}")], ref=f"the {which} animation")
    if r < 0.65:
        v = rng.choice([0, 1])
        req = rng.choice(["switch tags with a vertical animation", "tag animation should go up and down"] if v == 0 else
                         ["switch tags with a horizontal animation", "tag animation should slide sideways"])
        return vary(rng, req), Change(f"Animate tag switches {'vertically' if v == 0 else 'horizontally'}",
                                      [("opt:tag_animation_direction", f"tag_animation_direction={v}")], ref="the tag animation direction")
    if r < 0.85:
        flat = rng.random() < 0.6
        req = rng.choice(["disable mouse acceleration", "raw mouse input, no accel", "flat mouse acceleration profile"] if flat else
                         ["enable mouse acceleration", "use the adaptive mouse acceleration profile"])
        return vary(rng, req), Change(f"Use the {'flat' if flat else 'adaptive'} mouse acceleration profile",
                                      [("opt:mouse_accel_profile", f"mouse_accel_profile={1 if flat else 2}")], ref="the mouse acceleration change")
    s = rng.choice(["-0.5", "-0.3", "0.2", "0.3", "0.5"])
    dev = rng.choice(["mouse", "trackpad"])
    req = pick(rng, ["set the {d} speed to {s}", "{d} sensitivity {s}", "{d} pointer speed {s} (libinput, -1 to 1)"], d=dev, s=s)
    return vary(rng, req), Change(f"Set the {dev} acceleration speed to {s}", [(f"opt:{dev}_accel_speed", f"{dev}_accel_speed={s}")],
                                  ref=f"the {dev} speed")


def fam_opacity(rng, W: MangoWorld, managed):
    which = rng.choice(["unfocused", "unfocused", "focused"])
    if rng.random() < 0.35:
        v = "0.9"
        req = rng.choice([f"make {which} windows slightly transparent", f"{which} windows a little see-through"])
    else:
        v = rng.choice(["0.6", "0.7", "0.75", "0.8", "0.85", "0.9", "0.95", "1.0"])
        req = pick(rng, ["set {w} window opacity to {v}", "{w} windows at {p}% opacity", "make {w} windows {p} percent opaque"],
                   w=which, v=v, p=int(round(float(v) * 100)))
    key = f"{which}_opacity"
    return vary(rng, req), Change(f"Set {key} to {v}", [(f"opt:{key}", f"{key}={v}")], ref=f"the {which} opacity")


KB_LAYOUTS = {"us": "US English", "de": "German", "fr": "French", "gb": "British", "es": "Spanish", "it": "Italian",
              "ru": "Russian", "pl": "Polish", "se": "Swedish", "ua": "Ukrainian", "pt": "Portuguese", "cz": "Czech",
              "tr": "Turkish", "fi": "Finnish", "dk": "Danish", "ch": "Swiss"}
KB_OPTIONS = [("caps:escape", ["make caps lock act as escape", "caps lock should be escape"]),
              ("ctrl:nocaps", ["make caps lock another ctrl", "turn caps lock into control"]),
              ("caps:swapescape", ["swap caps lock and escape"]),
              ("compose:ralt", ["use right alt as the compose key"]),
              ("altwin:swap_alt_win", ["swap alt and super"])]


def fam_keyboard(rng, W: MangoWorld, managed):
    cur, cur_line, from_main = W.value("xkb_rules_layout", managed)
    cur = cur or "us"
    r = rng.random()
    if r < 0.45:
        code, lang = rng.choice(list(KB_LAYOUTS.items()))
        if code == cur:
            return None
        req = pick(rng, ["set my keyboard layout to {l}", "use the {l} keyboard layout", "switch the keyboard to {c}", "i have a {l} keyboard"],
                   l=lang, c=code)
        return vary(rng, req), Change(f"Set the keyboard layout to {code}", [("opt:xkb_rules_layout", f"xkb_rules_layout={code}")],
                                      ref="the keyboard layout change")
    opt_v, opt_line, opt_main = W.value("xkb_rules_options", managed)
    if r < 0.7:
        code, lang = rng.choice([(c, l) for c, l in KB_LAYOUTS.items() if c not in cur.split(",")])
        opt, sp = rng.choice([("grp:alt_shift_toggle", "alt+shift"), ("grp:win_space_toggle", "super+space"), ("grp:caps_toggle", "caps lock")])
        req = pick(rng, ["add a {l} layout and let me switch with {k}", "add {c} as a second layout, toggle with {k}"], l=lang, c=code, k=sp)
        opts = [o for o in (opt_v or "").split(",") if o and not o.startswith("grp:")]
        ev = ([cur_line] if (cur_line and from_main) else []) + ([opt_line] if (opt_line and opt_main and opts) else [])
        return vary(rng, req), Change(f"Add the {code} layout and switch with {sp}",
                                      [("opt:xkb_rules_layout", f"xkb_rules_layout={cur},{code}"),
                                       ("opt:xkb_rules_options", f"xkb_rules_options={','.join(opts + [opt])}")],
                                      ref=f"the {lang} layout", evidence=ev)
    opt, phrases = rng.choice(KB_OPTIONS)
    opts = [o for o in (opt_v or "").split(",") if o]
    if opt in opts:
        return None
    opts = [o for o in opts if o.split(":")[0] != opt.split(":")[0]]
    return vary(rng, rng.choice(phrases)), Change(f"Add {opt} to the keyboard options",
                                                  [("opt:xkb_rules_options", f"xkb_rules_options={','.join(opts + [opt])}")],
                                                  ref=f"the {opt} option", evidence=[opt_line] if (opt_line and opt_main and opts) else [])


COLOR_KEYS = {
    "focus_color": ["the focused window border", "the active border", "the focused border color"],
    "border_color": ["unfocused window borders", "the inactive border color", "normal window borders"],
    "root_color": ["the background color", "the root window color", "the desktop background"],
    "urgent_color": ["the urgent window border", "urgent windows"],
}


def fam_colors(rng, W: MangoWorld, managed):
    if rng.random() < 0.7:
        if rng.random() < 0.3:
            hexv = "".join(rng.choice("0123456789abcdef") for _ in range(6))
            sp = rng.choice([f"#{hexv}", hexv])
        else:
            sp = rng.choice(list(COLORS))
            hexv = COLORS[sp]
        key = rng.choice(list(COLOR_KEYS))
        req = pick(rng, ["make {w} {c}", "set {w} to {c}", "change {w} color to {c}", "{c} {w}"], w=rng.choice(COLOR_KEYS[key]), c=sp)
        return vary(rng, req), Change(f"Set {key} to 0x{hexv}ff", [(f"opt:{key}", f"{key}=0x{hexv}ff")], ref=f"the {key.replace('_', ' ')}")
    theme = rng.choice(list(THEMES))
    act, ina = THEMES[theme]
    req = pick(rng, ["use {t} colors for the window borders", "make mango's border colors {t}", "theme my borders {t}"], t=theme)
    return vary(rng, req), Change(f"Use {theme} border colors", [("opt:focus_color", f"focus_color=0x{act}ff"),
                                                                 ("opt:border_color", f"border_color=0x{ina}ff")], ref=f"the {theme} colors")


def fam_cursor(rng, W: MangoWorld, managed):
    theme = rng.choice(["Adwaita", "Bibata-Modern-Ice", "Breeze", "phinger-cursors-dark"])
    size = rng.choice([24, 32, 36, 48])
    if rng.random() < 0.5:
        req = pick(rng, ["set the cursor theme to {t} at size {s}", "use the {t} cursor, size {s}"], t=theme, s=size)
        return vary(rng, req), Change(f"Use the {theme} cursor theme at size {size}",
                                      [("opt:cursor_theme", f"cursor_theme={theme}"), ("opt:cursor_size", f"cursor_size={size}")], ref="the cursor theme")
    req = pick(rng, ["set the cursor theme to {t}", "use the {t} cursor theme"], t=theme)
    return vary(rng, req), Change(f"Use the {theme} cursor theme", [("opt:cursor_theme", f"cursor_theme={theme}")], ref="the cursor theme")


# --------------------------------------------------------------------------
# Families: bindings
# --------------------------------------------------------------------------

MOD_SETS = [(["SUPER"], 5), (["SUPER", "SHIFT"], 3), (["SUPER", "CTRL"], 1.5), (["SUPER", "ALT"], 1), (["ALT"], 1.2),
            (["CTRL", "ALT"], 0.7), (["ALT", "SHIFT"], 0.6)]


def _pick_combo(rng, W: MangoWorld, prefer_bound=0.35):
    if rng.random() < prefer_bound:
        cands = [l for l in W.flat if re.match(r"^bind=[A-Za-z+]+,[A-Za-z0-9],", l) and not l.startswith("bind=NONE")]
        if cands:
            l = rng.choice(cands)
            mods, key = combo_of_bind(l)
            return sorted(mods, key=MOD_ORDER.index), key, key
    x = rng.random() * sum(w for _, w in MOD_SETS)
    for mods, w in MOD_SETS:
        x -= w
        if x <= 0:
            break
    sp, key = rng.choice(FREE_KEYS)
    return list(mods), key, sp


APP_REQ = ["bind {k} to open {a}", "{k} should launch {a}", "make {k} open {a}", "add a shortcut {k} for {a}", "open {a} with {k}",
           "{k} -> {a}", "launch {a} when i press {k}", "i want {k} to start {a}", "keybind {k} {a}"]


def fam_bind_app(rng, W: MangoWorld, managed):
    mods, key, ks = _pick_combo(rng, W)
    r = rng.random()
    if r < 0.7:
        app = rng.choice([a for a in APPS if a.kind != "tui"])
        cmd, name = app.cmd, app.name
    elif r < 0.85:
        name, cmd = rng.choice(LAUNCHERS)
    else:
        app = rng.choice([a for a in APPS if a.kind == "tui"])
        cmd, name = f"{W.terminal} -e {app.cmd}", f"{app.name} in {W.terminal}"
    got = make_bind(W, managed, mods, key, f"spawn,{cmd}")
    if got is None:
        return None
    adds, ev, main = got
    req = pick(rng, APP_REQ, k=spoken(rng, mods, ks), a=name)
    return vary(rng, req), Change(f"Bind {shown(mods, key)} to launch {cmd}{_repl(main)}", adds, ref=f"the {name} shortcut", evidence=ev)


def fam_swap_app(rng, W: MangoWorld, managed):
    kind = rng.choice(["terminal", "launcher"])
    old = W.terminal if kind == "terminal" else W.menu
    binds = W.main_spawns(old)
    if not binds:
        return None
    if kind == "launcher":
        newname, new = rng.choice([(n, c) for n, c in LAUNCHERS if c != old])
    else:
        app = rng.choice([a for a in APPS if a.kind == "terminal" and a.cmd != old])
        newname, new = app.name, app.cmd
    req = pick(rng, ["use {n} as my {k} instead of {o}", "switch my {k} to {n}", "replace {o} with {n}", "make {n} my {k}"],
               n=newname, k=rng.choice(KIND_WORDS[kind]), o=old.split()[0])
    adds, ev = take_over(W, managed, binds)
    for b in binds:
        adds.append((f"bind:{combo_id_from_line(b)}", b[: -len(old)] + new))
    keys = ", ".join("+".join(b.split("=", 1)[1].split(",")[:2]) for b in binds)
    return vary(rng, req), Change(f"Launch {new} instead of {old} on {keys}", adds, ref=f"the switch to {newname}", evidence=ev)


ACTIONS = [
    (["close the focused window", "kill the window", "close windows"], "killclient", "close the window"),
    (["toggle fullscreen", "make the window fullscreen"], "togglefullscreen", "toggle fullscreen"),
    (["maximize the window", "toggle maximize"], "togglemaximizescreen", "toggle maximize"),
    (["toggle floating", "float or tile the window"], "togglefloating", "toggle floating"),
    (["make the window sticky", "show the window on all tags", "toggle sticky"], "toggleglobal", "toggle sticky (global)"),
    (["keep the window on top", "toggle always on top"], "toggleoverlay", "toggle always-on-top (overlay)"),
    (["minimize the window", "hide the window"], "minimized", "minimize the window"),
    (["restore minimized windows", "bring back the minimized window"], "restore_minimized", "restore a minimized window"),
    (["toggle the scratchpad", "show the scratchpad"], "toggle_scratchpad", "toggle the scratchpad"),
    (["open the overview", "show all windows", "toggle overview"], "toggleoverview", "toggle the overview"),
    (["center the floating window"], "centerwin", "center the window"),
    (["switch to the tiling layout", "use the master stack layout"], "setlayout,tile", "use the tile layout"),
    (["switch to the scroller layout", "scrolling layout like niri"], "setlayout,scroller", "use the scroller layout"),
    (["switch to the monocle layout", "show one window at a time"], "setlayout,monocle", "use the monocle layout"),
    (["switch to the grid layout"], "setlayout,grid", "use the grid layout"),
    (["switch to the deck layout"], "setlayout,deck", "use the deck layout"),
    (["switch to the centered master layout"], "setlayout,center_tile", "use the center_tile layout"),
    (["cycle through layouts", "switch to the next layout"], "switch_layout", "cycle layouts"),
    (["go back to the previous window", "focus the last window"], "focuslast", "focus the previous window"),
    (["focus the next window", "cycle focus"], "focusstack,next", "focus the next window"),
    (["focus the previous window in the stack"], "focusstack,prev", "focus the previous window in the stack"),
    (["swap the window with the master", "zoom the window into the master area"], "zoom", "swap with the master"),
    (["add a window to the master area", "more master windows"], "incnmaster,+1", "add a master window"),
    (["remove a window from the master area", "fewer master windows"], "incnmaster,-1", "remove a master window"),
    (["grow the master area", "make the master bigger"], "setmfact,+0.05", "grow the master area"),
    (["shrink the master area", "make the master smaller"], "setmfact,-0.05", "shrink the master area"),
    (["increase the gaps", "bigger gaps"], "incgaps,1", "increase the gaps"),
    (["decrease the gaps", "smaller gaps"], "incgaps,-1", "decrease the gaps"),
    (["toggle gaps", "turn gaps on and off"], "togglegaps", "toggle gaps"),
    (["switch the keyboard layout", "cycle keyboard layouts"], "switch_keyboard_layout", "switch the keyboard layout"),
    (["focus the monitor to the right", "switch focus to the other monitor"], "focusmon,right", "focus the monitor to the right"),
    (["move the window to the other monitor", "send the window to the next monitor"], "tagmon,right", "move the window to the monitor on the right"),
    (["go to the next tag", "switch to the tag on the right"], "viewtoright", "go to the next tag"),
    (["go to the previous tag", "switch to the tag on the left"], "viewtoleft", "go to the previous tag"),
    (["go back to the last tag", "switch to the previously viewed tag"], "view,-1", "go back to the previous tag"),
    (["show all tags at once"], "view,00", "view all tags"),
    (["reload the config", "reload mango"], "reload_config", "reload the config"),
    (["exit mango", "log out", "quit the compositor"], "quit", "quit mango"),
]

ACTION_REQ = ["bind {k} to {a}", "{k} should {a}", "make {k} {a}", "add a keybind to {a} on {k}", "i want to {a} with {k}",
              "set {k} to {a}", "use {k} to {a}"]


def fam_bind_action(rng, W: MangoWorld, managed):
    mods, key, ks = _pick_combo(rng, W)
    r = rng.random()
    if r < 0.6:
        phrases, action, desc = rng.choice(ACTIONS)
        phrase = rng.choice(phrases)
    elif r < 0.8:
        n = rng.randint(1, 9)
        c = rng.random()
        if c < 0.4:
            phrase, action, desc = rng.choice([f"switch to tag {n}", f"go to tag {n}", f"go to workspace {n}"]), f"view,{n},0", f"view tag {n}"
        elif c < 0.75:
            phrase = rng.choice([f"move the window to tag {n}", f"send the window to workspace {n}"])
            action, desc = f"tag,{n},0", f"move the window to tag {n}"
        else:
            phrase = rng.choice([f"move the window to tag {n} without following it", f"silently send the window to workspace {n}"])
            action, desc = f"tagsilent,{n}", f"move the window to tag {n} silently"
    else:
        d = rng.choice(DIRECTIONS)
        kind = rng.choice(["focus", "move", "swap"])
        phrase = {"focus": f"focus the window to the {d}", "move": f"move the window {d}", "swap": f"swap the window with the one {d}"}[kind]
        action = {"focus": "focusdir", "move": "move_client", "swap": "exchange_client"}[kind] + f",{d}"
        desc = phrase
    got = make_bind(W, managed, mods, key, action)
    if got is None:
        return None
    adds, ev, main = got
    req = pick(rng, ACTION_REQ, k=spoken(rng, mods, ks), a=phrase)
    return vary(rng, req), Change(f"Bind {shown(mods, key)} to {desc}{_repl(main)}", adds, ref=f"the {shown(mods, key)} shortcut", evidence=ev)


def _bulk(W, managed, items):
    adds, ev = [], []
    for mods, key, action in items:
        got = make_bind(W, managed, mods, key, action)
        if got is None:
            return None
        adds += got[0]
        ev += got[1]
    return adds, ev


def fam_bind_bulk(rng, W: MangoWorld, managed):
    r = rng.random()
    if r < 0.35:
        shift = rng.random() < 0.4
        mods = ["SUPER"] + (["SHIFT"] if shift else [])
        got = _bulk(W, managed, [(mods, VIM[d], f"{'move_client' if shift else 'focusdir'},{d}") for d in DIRECTIONS])
        if got is None:
            return None
        req = rng.choice(["move windows with vim keys", "super+shift+hjkl should move windows"] if shift else
                         ["use vim keys to move focus", "hjkl focus navigation", "focus with super+h/j/k/l"])
        return vary(rng, req), Change(f"Bind {shown(mods, 'hjkl')} to {'move windows' if shift else 'move focus'}", got[0],
                                      ref="the vim-key binds", evidence=got[1])
    if r < 0.65:
        shift = rng.random() < 0.5
        n = rng.choice([4, 5, 9, 9])
        mods = ["SUPER"] + (["SHIFT"] if shift else [])
        got = _bulk(W, managed, [(mods, str(i), f"tag,{i},0" if shift else f"view,{i},0") for i in range(1, n + 1)])
        if got is None:
            return None
        req = (rng.choice([f"super+shift+1-{n} should move the window to that tag", f"move windows to tags 1-{n} with super+shift+number"])
               if shift else rng.choice([f"switch tags 1-{n} with super+number", f"super+1 to super+{n} should switch workspaces"]))
        return vary(rng, req), Change(f"Bind {shown(mods, f'1-{n}')} to {'move the window to' if shift else 'view'} tags 1-{n}", got[0],
                                      ref="the tag binds", evidence=got[1])
    mods = ["SUPER", "CTRL"]
    if rng.random() < 0.5:
        step = rng.choice([20, 30, 40, 50])
        req = rng.choice([f"let me resize from the keyboard with ctrl+super+arrows, {step}px steps",
                          f"resize windows with {spoken(rng, mods, 'arrows')} by {step}px"])
    else:
        step = 30
        req = rng.choice([f"resize windows with {spoken(rng, mods, 'arrows')}", "let me resize windows from the keyboard with ctrl+super+arrows"])
    deltas = {"Left": f"-{step},+0", "Right": f"+{step},+0", "Up": f"+0,-{step}", "Down": f"+0,+{step}"}
    got = _bulk(W, managed, [(mods, k, f"resizewin,{d}") for k, d in deltas.items()])
    if got is None:
        return None
    return vary(rng, req), Change(f"Bind {shown(mods, 'arrows')} to resize by {step}px", got[0], ref="the resize binds", evidence=got[1])


MEDIA = [
    (["take a screenshot of a region and copy it", "region screenshot to the clipboard"], 'spawn_shell,grim -g "$(slurp)" - | wl-copy', "Print"),
    (["take a full screenshot and save it to ~/Pictures", "save a screenshot of the whole screen"],
     "spawn_shell,grim ~/Pictures/screenshot-$(date +%F-%H%M%S).png", "Print"),
    (["lock the screen", "lock my session with swaylock"], "spawn,swaylock -f", "Escape"),
    (["open the clipboard history"], "spawn_shell,cliphist list | wofi --dmenu | cliphist decode | wl-copy", "v"),
    (["toggle the notification center", "open swaync"], "spawn,swaync-client -t -sw", "n"),
    (["open the power menu", "show wlogout"], "spawn,wlogout", "x"),
    (["dismiss notifications", "clear mako notifications"], "spawn,makoctl dismiss --all", "n"),
    (["play or pause music", "toggle media playback"], "spawn,playerctl play-pause", "p"),
]


def fam_media(rng, W: MangoWorld, managed):
    if rng.random() < 0.45:
        what = rng.choice(["volume", "brightness", "mute"])
        vague = rng.random() < 0.3
        s = 5 if vague else rng.choice([1, 2, 3, 5, 10])
        if what == "volume":
            keys = [("XF86AudioRaiseVolume", f"spawn,wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ {s}%+"),
                    ("XF86AudioLowerVolume", f"spawn,wpctl set-volume @DEFAULT_AUDIO_SINK@ {s}%-")]
        elif what == "brightness":
            keys = [("XF86MonBrightnessUp", f"spawn,brightnessctl set {s}%+"), ("XF86MonBrightnessDown", f"spawn,brightnessctl set {s}%-")]
        else:
            vague = True
            keys = [("XF86AudioMute", "spawn,wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")]
        req = (rng.choice([f"set up my {what} keys", f"make the {what} keys work", f"the {what} keys don't do anything"]) if vague else
               rng.choice([f"make the {what} keys change {what} by {s}%", f"{what} keys in {s}% steps"]))
        got = _bulk(W, managed, [([], k, a) for k, a in keys])
        if got is None:
            return None
        adds = [(slot, line.replace("bind=", "bindl=", 1) if line.startswith("bind=") else line) for slot, line in got[0]]
        return vary(rng, req), Change(f"Bind the {what} keys{'' if what == 'mute' else f' with {s}% steps'} (also while locked)", adds,
                                      ref=f"the {what} keys", evidence=got[1])
    phrases, action, dk = rng.choice(MEDIA)
    if dk == "Print" and rng.random() < 0.6:
        mods, key, ks = ([], "Print", "print screen") if rng.random() < 0.5 else (["SHIFT"], "Print", "print")
    elif rng.random() < 0.5:
        mods, key, ks = ["SUPER"] + (["SHIFT"] if dk in "vnxp" else []), dk, dk.lower()
    else:
        mods, key, ks = _pick_combo(rng, W)
    got = make_bind(W, managed, mods, key, action)
    if got is None:
        return None
    adds, ev, main = got
    k = spoken(rng, mods, ks) if mods else rng.choice(["print screen", "the print key", "Print"])
    req = pick(rng, ACTION_REQ, k=k, a=rng.choice(phrases))
    return vary(rng, req), Change(f"Bind {shown(mods, key)} to run {action.split(',', 1)[1]}{_repl(main)}", adds,
                                  ref=f"the {shown(mods, key)} shortcut", evidence=ev)


def fam_unbind(rng, W: MangoWorld, managed):
    mine = [e for e in managed if e.slot.startswith("bind:")]
    if mine and rng.random() < 0.4:
        e = rng.choice(mine)
        k = "+".join(e.line.split("=", 1)[1].split(",")[:2])
        req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "{k} shouldn't do anything", "delete the {k} keybind"], k=k)
        mains = W.main_binds(e.slot[5:])
        note = " (the main-config binding stays disabled)" if mains else ""
        return vary(rng, req), Change(f"Remove the {k} binding{note}", dels_lines=[e.line], ref=f"the {k} removal")
    cands = [l for l in W.flat if l.startswith("bind=") and l not in disabled(managed)]
    if not cands:
        return None
    l = rng.choice(cands)
    k = "+".join(l.split("=", 1)[1].split(",")[:2])
    sp = k if rng.random() < 0.6 else k.lower()
    req = pick(rng, ["remove the {k} shortcut", "unbind {k}", "disable {k}", "i keep pressing {k} by accident, disable it"], k=sp)
    return vary(rng, req), Change(f"Disable the {k} binding from the main config", [(f"disable:{l}", DISABLE_KEY + l)],
                                  ref=f"the {k} unbind", evidence=[l])


def fam_submap(rng, W: MangoWorld, managed):
    mods, key, ks = (["SUPER"], "r", "r") if rng.random() < 0.5 else _pick_combo(rng, W, 0)
    step = 20 if rng.random() < 0.6 else rng.choice([10, 30, 40, 50])
    trig = make_bind(W, managed, mods, key, "setkeymode,resize")
    if trig is None or any(e.slot.startswith("mode:resize") for e in managed):
        return None
    sp = spoken(rng, mods, ks)
    req = (pick(rng, ["add a resize mode on {k}: arrows resize, escape exits", "{k} should enter a resize mode like in i3"], k=sp) if step == 20 else
           pick(rng, ["add a resize mode on {k} where arrows resize by {s}px", "{k} enters resize mode, {s} pixel steps"], k=sp, s=step))
    adds = trig[0] + [("mode:resize:enter", "key_mode=resize")]
    for k, d in {"Left": f"-{step},+0", "Right": f"+{step},+0", "Up": f"+0,-{step}", "Down": f"+0,+{step}"}.items():
        adds.append((f"mode:resize:{k.lower()}", f"bind=NONE,{k},resizewin,{d}"))
    adds += [("mode:resize:escape", "bind=NONE,Escape,setkeymode,default"), ("mode:resize:return", "bind=NONE,Return,setkeymode,default"),
             ("mode:resize:exit", "key_mode=default")]
    return vary(rng, req), Change(f"Add a resize key mode on {shown(mods, key)} (arrows resize by {step}px, Escape/Return leave){_repl(trig[2])}",
                                  adds, ref="the resize mode", evidence=trig[1])


GESTURES = [
    ([("left", 3, "viewtoright_have_client"), ("right", 3, "viewtoleft_have_client")],
     ["switch tags with a three finger swipe", "3 finger swipe left/right changes workspace"], "Switch tags with 3-finger horizontal swipes"),
    ([("left", 4, "viewtoright_have_client"), ("right", 4, "viewtoleft_have_client")],
     ["switch tags with four fingers", "4 finger swipe changes workspace"], "Switch tags with 4-finger horizontal swipes"),
    ([("up", 3, "toggleoverview")], ["three finger swipe up opens the overview"], "Toggle the overview with a 3-finger swipe up"),
    ([("up", 4, "toggleoverview")], ["four finger swipe up shows all windows"], "Toggle the overview with a 4-finger swipe up"),
    ([("down", 3, "killclient")], ["swipe down with three fingers to close the window"], "Close the window with a 3-finger swipe down"),
    ([("up", 3, "togglefullscreen")], ["3 finger swipe up for fullscreen"], "Toggle fullscreen with a 3-finger swipe up"),
    ([("down", 4, "togglefloating")], ["four finger swipe down toggles floating"], "Toggle floating with a 4-finger swipe down"),
]


def fam_gesture(rng, W: MangoWorld, managed):
    items, reqs, summary = rng.choice(GESTURES)
    adds, ev = [], []
    for d, f, action in items:
        line = f"gesturebind=none,{d},{f},{action}"
        mains = [l for l in W.flat if re.match(rf"^gesturebind=none,{d},{f},", l, re.I)]
        if line in mains:
            return None
        a, e = take_over(W, managed, mains)
        adds += a + [(f"gesture:{d}:{f}", line)]
        ev += e
    return vary(rng, rng.choice(reqs)), Change(summary, adds, ref="the gesture binds", evidence=ev)


def fam_lid(rng, W: MangoWorld, managed):
    req = rng.choice(["turn off the laptop screen when i close the lid", "disable eDP-1 when the lid is closed (i use an external monitor)",
                      "clamshell mode: lid closed should disable the internal display"])
    return vary(rng, req), Change("Disable eDP-1 while the lid is closed and re-enable it when opened", [
        ("switch:lid_on", "switchbind=lid_on,disable_monitor,eDP-1"), ("switch:lid_off", "switchbind=lid_off,enable_monitor,eDP-1")],
        ref="the lid switch binds")


# --------------------------------------------------------------------------
# Families: rules, monitors, startup
# --------------------------------------------------------------------------

def fam_window_rule(rng, W: MangoWorld, managed):
    app = rng.choice([a for a in APPS if a.kind != "tui"])
    n, aid = app.name, app.app_id
    r = rng.random()
    if r < 0.22 or (r < 0.32 and n in FLOATY):
        props, req = "is_floating:1", pick(rng, ["make {a} float", "{a} should always open floating", "float {a} windows"], a=n)
        summary, key = f"Float {aid} windows", "float"
    elif r < 0.37:
        w, h = rng.choice([(800, 600), (900, 600), (1000, 700), (1200, 800), (960, 540)])
        props = f"is_floating:1,width:{w},height:{h}"
        req = pick(rng, ["open {a} floating at {w}x{h}", "{a} should float, {w} by {h}"], a=n, w=w, h=h)
        summary, key = f"Float {aid} at {w}x{h}", "float"
    elif r < 0.55:
        t = rng.randint(1, 9)
        silent = rng.random() < 0.3
        props = f"tags:{t}" + (",is_open_silent:1" if silent else "")
        req = (pick(rng, ["open {a} on tag {t} in the background", "{a} should go to workspace {t} without switching to it"], a=n, t=t) if silent else
               pick(rng, ["always open {a} on tag {t}", "{a} should go to workspace {t}", "put {a} on tag {t}"], a=n, t=t))
        summary, key = f"Open {aid} on tag {t}{' without focusing it' if silent else ''}", "tag"
    elif r < 0.67:
        if rng.random() < 0.3:
            a = "0.9"
            req = pick(rng, ["make {a} slightly transparent", "{a} a little see-through"], a=n)
        else:
            a = rng.choice(["0.7", "0.75", "0.8", "0.85", "0.9", "0.95"])
            req = pick(rng, ["set {a} opacity to {o}", "{a} at {p}% opacity", "make {a} {p} percent opaque"], a=n, o=a, p=int(round(float(a) * 100)))
        props = f"focused_opacity:{a},unfocused_opacity:{a}"
        summary, key = f"Set {aid} opacity to {a}", "opacity"
    elif r < 0.74:
        props, req = "no_border:1", pick(rng, ["remove the border from {a}", "no border on {a} windows"], a=n)
        summary, key = f"Remove the border from {aid}", "border"
    elif r < 0.8:
        props, req = "is_fullscreen:1", pick(rng, ["always open {a} fullscreen", "{a} should start fullscreen"], a=n)
        summary, key = f"Open {aid} fullscreen", "fullscreen"
    elif r < 0.85:
        mon = rng.choice(["HDMI-A-1", "DP-1", "DP-2", "eDP-1"])
        props, req = f"monitor:{mon}", pick(rng, ["open {a} on {m}", "{a} should always go to monitor {m}"], a=n, m=mon)
        summary, key = f"Open {aid} on {mon}", "monitor"
    elif r < 0.9:
        props, req = "no_shadow:1", pick(rng, ["no shadow on {a}", "remove the shadow from {a} windows"], a=n)
        summary, key = f"Remove the shadow from {aid}", "shadow"
    elif r < 0.95:
        line = "window_rule=is_floating:1,is_global:1,width:640,height:360,app_id:firefox,title:^Picture-in-Picture$"
        req = rng.choice(["make firefox picture-in-picture float and stay on all tags", "pip videos should float and be sticky"])
        return vary(rng, req), Change("Float firefox picture-in-picture windows on all tags at 640x360", [("rule:firefox-pip", line)],
                                      ref="the picture-in-picture rule")
    else:
        props = "is_floating:1,is_global:1"
        req = pick(rng, ["make {a} float and follow me to every tag", "{a} should be floating and sticky"], a=n)
        summary, key = f"Float {aid} and show it on all tags", "float"
    return vary(rng, req), Change(summary, [(f"rule:{aid}:{key}", f"window_rule={props},app_id:{aid}")], ref=f"the {n} window rule")


LAYOUTS = {"tile": ["tiling", "master-stack", "tile"], "scroller": ["scroller", "scrolling"], "monocle": ["monocle"], "grid": ["grid"],
           "deck": ["deck"], "dwindle": ["dwindle", "spiral"], "center_tile": ["centered master"], "vertical_tile": ["vertical tiling"]}


def fam_tag_rule(rng, W: MangoWorld, managed):
    lay = rng.choice(list(LAYOUTS))
    name = rng.choice(LAYOUTS[lay])
    ev = [l for l in W.flat if l.startswith("tag_rule=")][:1]
    if rng.random() < 0.45:
        req = pick(rng, ["use the {n} layout everywhere", "make {n} the default layout", "all tags should use {n}"], n=name)
        return vary(rng, req), Change(f"Use the {lay} layout on all tags", [("tag:*:layout", f"tag_rule=id:*,layout_name:{lay}")],
                                      ref="the default layout", evidence=ev)
    t = rng.randint(1, 9)
    req = pick(rng, ["use the {n} layout on tag {t}", "tag {t} should be {n}", "workspace {t} with the {n} layout"], n=name, t=t)
    return vary(rng, req), Change(f"Use the {lay} layout on tag {t}", [(f"tag:{t}:layout", f"tag_rule=id:{t},layout_name:{lay}")],
                                  ref=f"the tag {t} layout", evidence=ev)


OUTPUTS = ["eDP-1", "DP-1", "DP-2", "HDMI-A-1"]


def fam_monitor(rng, W: MangoWorld, managed):
    out = rng.choice(OUTPUTS)
    sp = "my laptop screen" if out == "eDP-1" and rng.random() < 0.5 else out
    r = rng.random()
    if r < 0.3:
        w, h = rng.choice([(1920, 1080), (2560, 1440), (3840, 2160), (1366, 768), (3440, 1440)])
        hz = rng.choice([60, 75, 120, 144, 165])
        props = f"width:{w},height:{h},refresh:{hz}"
        req = pick(rng, ["set {o} to {w}x{h} at {r}hz", "{o} should run at {w}x{h}@{r}"], o=sp, w=w, h=h, r=hz)
        summary = f"Set {out} to {w}x{h}@{hz}Hz"
    elif r < 0.55:
        s = rng.choice(["1", "1.25", "1.5", "1.75", "2"])
        props = f"scale:{s}"
        req = pick(rng, ["set the scale of {o} to {s}", "scale {o} {s}x", "{o} scaling {s}"], o=sp, s=s)
        summary = f"Set the scale of {out} to {s}"
    elif r < 0.7:
        x = rng.choice([1920, 2560, 1366, 3840])
        other = rng.choice([o for o in OUTPUTS if o != out])
        props = f"x:{x},y:0"
        req = pick(rng, ["put {o} to the right of {l} (which is {w} pixels wide)", "{o} sits right of my {w}px wide {l}"], o=out, l=other, w=x)
        summary = f"Position {out} at {x},0"
    elif r < 0.8:
        props = "disable:1"
        req = pick(rng, ["disable {o}", "turn off {o} completely"], o=sp)
        summary = f"Disable {out}"
    elif r < 0.9:
        deg = rng.choice([90, 180, 270])
        props = f"rr:{deg // 90}"
        req = pick(rng, ["rotate {o} {d} degrees", "{o} is mounted vertically, rotate it {d}°"], o=sp, d=deg)
        summary = f"Rotate {out} by {deg} degrees"
    else:
        props = "vrr:1"
        req = pick(rng, ["enable adaptive sync on {o}", "turn on vrr/freesync for {o}"], o=sp)
        summary = f"Enable adaptive sync on {out}"
    prop = props.split(":")[0]
    return vary(rng, req), Change(summary, [(f"monitor:{out}:{prop}", f"monitor_rule=name:^{out}$,{props}")], ref=f"the {out} {prop} setting")


def fam_autostart(rng, W: MangoWorld, managed):
    mine = [e for e in managed if e.slot.startswith("exec:")]
    if mine and rng.random() < 0.15:
        e = rng.choice(mine)
        c = e.slot[5:]
        return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore"], c=c)), \
            Change(f"Stop starting {c} at login", dels_lines=[e.line], ref="")
    mains = [l for l in W.flat if l.startswith("exec_once=")]
    if mains and rng.random() < 0.12:
        l = rng.choice(mains)
        if l in disabled(managed):
            return None
        c = l.split("=", 1)[1]
        return vary(rng, pick(rng, ["stop starting {c} at login", "don't autostart {c} anymore"], c=c)), \
            Change(f"Stop starting {c} (disables '{l}' in your main config)", [(f"disable:{l}", DISABLE_KEY + l)], ref=f"the {c} removal",
                   evidence=[l])
    c = rng.choice(AUTOSTART_POOL + ["firefox", "discord", "steam -silent", "spotify", "syncthing serve --no-browser"])
    always = c in ("kanshi",) or rng.random() < 0.1
    line = f"{'exec' if always else 'exec_once'}={c}"
    if f"exec_once={c}" in W.flat:
        return vary(rng, f"start {c} at login"), Change(f"{c} is already started by your config; nothing to change.", evidence=[f"exec_once={c}"])
    req = pick(rng, ["start {c} on login", "autostart {c}", "run {c} when mango starts", "launch {c} at startup"] +
               (["run {c} on every config reload too"] if always else []), c=c)
    return vary(rng, req), Change(f"Start {c} {'on startup and every reload' if always else 'when mango starts'}", [(f"exec:{c}", line)],
                                  ref=f"the {c} autostart")


def fam_wallpaper(rng, W: MangoWorld, managed):
    path = rng.choice(["~/Pictures/wallpaper.jpg", "~/Pictures/wall.png", "~/.config/mango/bg.png", "~/Pictures/backgrounds/forest.jpg"])
    mode = rng.choice(["fill", "fill", "fit", "center", "stretch"])
    mains = [l for l in W.flat if l.startswith("exec_once=swaybg")]
    adds, ev = take_over(W, managed, mains)
    req = pick(rng, ["set my wallpaper to {p}", "use {p} as the background ({m})", "wallpaper {p}"], p=path, m=mode)
    return vary(rng, req), Change(f"Start swaybg with {path} ({mode}) as the wallpaper", adds + [("exec:swaybg", f"exec_once=swaybg -i {path} -m {mode}")],
                                  ref="the wallpaper", evidence=ev)


ENVS = [
    ("QT_QPA_PLATFORMTHEME", "qt6ct", ["use qt6ct for qt app theming", "set QT_QPA_PLATFORMTHEME to qt6ct"]),
    ("GTK_THEME", "Adwaita:dark", ["force the dark Adwaita theme for gtk apps", "set GTK_THEME=Adwaita:dark"]),
    ("XCURSOR_SIZE", "32", ["set the XCURSOR_SIZE env variable to 32"]),
    ("MOZ_ENABLE_WAYLAND", "1", ["make firefox use wayland natively"]),
    ("ELECTRON_OZONE_PLATFORM_HINT", "auto", ["make electron apps run on wayland", "fix blurry electron apps"]),
    ("QT_QPA_PLATFORM", "wayland;xcb", ["make qt apps use wayland with an x11 fallback"]),
    ("SDL_VIDEODRIVER", "wayland", ["make sdl games use wayland"]),
]


def fam_env(rng, W: MangoWorld, managed):
    name, value, reqs = rng.choice(ENVS)
    return vary(rng, rng.choice(reqs)), Change(f"Set {name}={value} for programs started by mango", [(f"env:{name}", f"env={name},{value}")],
                                               ref=f"the {name} variable")


def fam_layer_rule(rng, W: MangoWorld, managed):
    layer = rng.choice(["waybar", "rofi", "wofi", "fuzzel", "swaync-control-center", "notifications"])
    r = rng.random()
    if r < 0.4:
        props, req, summary = "no_blur:1", pick(rng, ["don't blur behind {l}", "no blur on {l}"], l=layer), f"Disable blur behind {layer}"
    elif r < 0.7:
        props, req, summary = "no_shadow:1", pick(rng, ["remove the shadow from {l}"], l=layer), f"Remove the shadow from {layer}"
    else:
        t = rng.choice(["zoom", "slide", "fade"])
        props, req, summary = f"animation_type_open:{t}", pick(rng, ["make {l} {t} in when it opens", "{l} should open with a {t} animation"], l=layer, t=t), \
            f"Open {layer} with the {t} animation"
    key = props.split(":")[0]
    return vary(rng, req), Change(summary, [(f"layer:{layer}:{key}", f"layer_rule=layer_name:{layer},{props}")], ref=f"the {layer} layer rule")


def fam_remove(rng, W: MangoWorld, managed):
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
    ("what's the weather tomorrow", "This is not a MangoWC configuration request."),
    ("write me a poem", "This is not a MangoWC configuration request."),
    ("install waybar", "Installing software is not a config change; use your package manager (e.g. pacman -S waybar)."),
    ("open firefox", "That asks to run something now, not to change the config; ask for a keybind or autostart instead."),
    ("fix my bluetooth", "Bluetooth setup is not part of the MangoWC config."),
    ("configure my fish prompt", "Shell configuration is not part of the MangoWC config."),
    ("make waybar show the battery", "Waybar is configured in ~/.config/waybar/config.jsonc, not in the MangoWC config."),
    ("use the hyprland config syntax", "This tool is set up for MangoWC, not Hyprland."),
    ("convert my config to toml", "This tool edits config.conf only; mango reads config.conf before config.toml."),
]


def fam_noop(rng, W: MangoWorld, managed):
    req, summary = rng.choice(NOOP)
    return vary(rng, req), Change(summary)


FAMILIES = [
    (9, "num", fam_num), (10, "toggle", fam_toggle), (3, "enum", fam_enum), (2.5, "opacity", fam_opacity), (5, "keyboard", fam_keyboard),
    (4, "colors", fam_colors), (1.5, "cursor", fam_cursor), (12, "bind_app", fam_bind_app), (2.5, "swap_app", fam_swap_app),
    (12, "bind_action", fam_bind_action), (3, "bind_bulk", fam_bind_bulk), (5, "media", fam_media), (4, "unbind", fam_unbind),
    (1.5, "submap", fam_submap), (2, "gesture", fam_gesture), (1, "lid", fam_lid), (9, "window_rule", fam_window_rule),
    (2.5, "tag_rule", fam_tag_rule), (5, "monitor", fam_monitor), (4, "autostart", fam_autostart), (1.5, "wallpaper", fam_wallpaper),
    (2, "env", fam_env), (1.5, "layer_rule", fam_layer_rule), (6, "remove", fam_remove), (2.5, "noop", fam_noop),
]

PRIOR_FAMILIES = [fam_num, fam_toggle, fam_enum, fam_opacity, fam_keyboard, fam_colors, fam_bind_app, fam_bind_action, fam_media,
                  fam_window_rule, fam_tag_rule, fam_monitor, fam_autostart, fam_gesture, fam_cursor, fam_unbind, fam_env]
