"""Shared prompt format, used identically by the data generator and the CLI.

Standard library only, so the CLI runs on any machine with Python 3.9+.

Prompt layout (user turn):

    wm: hyprland
    request: make the gaps bigger
    config:
    hl.config({ general = { gaps_in = 5 } })
    managed:
    (empty)

Answer layout (assistant turn):

    summary: Increase the inner gaps to 8
    add: hl.config({ general = { gaps_in = 8 } })

`del:` lines remove an exact line from the managed file; `add:` lines append
one. The model never edits the user's main config: it writes only to the
managed file (ai.conf / ai.lua), which the main config includes last, so its
settings take precedence.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLATTEN_LUA = HERE / "flatten_hypr.lua"

MAX_CONTEXT_LINES = 14

SYSTEM_PROMPTS = {
    "sway": (
        "You edit Sway 1.12 configuration. You write only to a managed file that "
        "is included at the end of the user's config, so its lines override "
        "earlier ones. Answer with one 'summary:' line, then 'del:' lines that "
        "remove exact lines from the managed file and 'add:' lines that append "
        "new ones. One directive per line. If the request is not about Sway "
        "configuration, answer with a summary line only."
    ),
    "hyprland": (
        "You edit Hyprland 0.57 configuration written in Lua (hyprland.lua). You "
        "write only to a managed module that is required at the end of the "
        "user's config, so its calls override earlier ones. Main-config locals "
        "are not visible there: always write literal values. Answer with one "
        "'summary:' line, then 'del:' lines that remove exact lines from the "
        "managed module and 'add:' lines that append new ones. One statement "
        "per line, one config key per hl.config call. Before rebinding a key "
        "that is already bound, add hl.unbind for it. If the request is not "
        "about Hyprland configuration, answer with a summary line only."
    ),
}


# --------------------------------------------------------------------------
# Flattening the user's main config into one-line statements
# --------------------------------------------------------------------------

def flatten_sway(text: str) -> list[str]:
    """Flatten a Sway config: join continuations, drop comments, inline blocks.

    `input type:touchpad { tap enabled }` becomes `input type:touchpad tap enabled`.
    """
    joined: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        joined.append(buf + line)
        buf = ""
    if buf:
        joined.append(buf)

    out: list[str] = []
    stack: list[str] = []
    for line in joined:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # A block may open and close on one line: `bar { swaybar_command waybar }`
        if s.endswith("{") or ("{" in s and s.endswith("}")):
            head, _, rest = s.partition("{")
            head = head.strip()
            rest = rest.strip()
            if rest.endswith("}"):
                inner = rest[:-1].strip()
                prefix = " ".join(stack + [head])
                for part in [p.strip() for p in inner.split(";") if p.strip()]:
                    out.append(f"{prefix} {part}")
                continue
            stack.append(head)
            continue
        if s == "}":
            if stack:
                stack.pop()
            continue
        out.append(" ".join(stack + [s]) if stack else s)
    return [re.sub(r"\s+", " ", l) for l in out]


def flatten_hyprland(config_path: str | Path, managed_module: str = "ai") -> list[str]:
    """Flatten a Hyprland Lua config by evaluating it against a recording stub."""
    proc = subprocess.run(
        ["lua", str(FLATTEN_LUA), str(config_path), managed_module],
        capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(proc.stderr.strip() or "lua flattener failed")
    return [l for l in proc.stdout.splitlines() if l.strip()]


def is_managed_include(wm: str, line: str) -> bool:
    if wm == "sway":
        return bool(re.match(r"^include\s+\S*ai\.conf\s*$", line))
    return False


# --------------------------------------------------------------------------
# Choosing the lines relevant to a request
# --------------------------------------------------------------------------

STOPWORDS = set("""
a an the to of in on for and or but with my me i you it is are be can could
would should please make set change want like let lets use using into from by
at as this that these those so too very more less bit little some any all
also just now then than when what which how do does did not no yes hey hi
thanks thank its it's im i'm get got put give have has had will shall
window windows key keys shortcut shortcuts bind binding binds config
then type thanks thx pls plz instead only always never every one two
start starts open opens add new mine they them there here want need
mod super alt ctrl control shift win logo meta mainmod
""".split())

# (request pattern, line pattern). If the request matches, lines matching the
# second pattern become candidates.
TOPICS: list[tuple[str, str]] = [
    (r"gap|spacing|space between|padding|margin", r"gaps|smart_gaps"),
    (r"border|outline|frame", r"border|client\.|default_border|default_floating_border|hide_edge"),
    (r"colou?r|theme|accent|red|blue|green|purple|pink|orange|yellow|catppuccin|nord|gruvbox|dracula",
     r"col\b|col\.|color|colou?r|client\.|border"),
    (r"round|corner", r"rounding|corner_radius"),
    (r"opacity|transparen|translucent|see.?through|opaque", r"opacity|opaque"),
    (r"blur|frosted|glass|acrylic", r"blur"),
    (r"shadow|drop.?shadow", r"shadow"),
    (r"anim|transition|motion|bezier|spring|smooth|snappy|speed up|slow down", r"animation|curve|anim"),
    (r"keyboard|layout|xkb|kb_|qwerty|azerty|dvorak|colemak|caps|compose|repeat",
     r"kb_|xkb|repeat|type:keyboard|input \*"),
    (r"touchpad|trackpad|tap|natural|scroll|two.?finger|palm", r"touchpad|natural_scroll|tap|scroll|dwt|disable_while_typing"),
    (r"mouse|cursor|pointer|sensitiv|accel", r"sensitivity|accel|cursor|follow_mouse|focus_follows_mouse|mouse_warping|seat"),
    (r"focus follows|follow.?mouse|hover", r"follow_mouse|focus_follows_mouse"),
    (r"monitor|display|screen|output|resolution|refresh|hz|scale|hidpi|dpi|external|laptop screen|edp|hdmi|\bdp\b",
     r"hl\.monitor|^output|monitor"),
    (r"wallpaper|background|bg\b", r"wallpaper|swaybg|hyprpaper|\bbg\b|logo"),
    (r"autostart|startup|start up|on login|launch at|run at|exec.?once|boot",
     r"hyprland\.start|^exec|exec_always"),
    (r"bar|waybar|panel|status", r"waybar|^bar|swaybar|status"),
    (r"terminal|term\b|console|shell",
     r"kitty|foot|alacritty|wezterm|ghostty|konsole|gnome-terminal|xterm|\$term|ptyxis|st\b"),
    (r"browser|firefox|chrom|brave|web", r"firefox|chrom|brave|librewolf|zen-browser|qutebrowser|\$browser"),
    (r"file manager|files|explorer|nautilus|dolphin|thunar|nemo|yazi|ranger",
     r"dolphin|nautilus|thunar|nemo|pcmanfm|yazi|ranger|\$files|\$filemanager"),
    (r"launcher|menu|rofi|wofi|fuzzel|tofi|dmenu|bemenu|run dialog|app finder|spotlight",
     r"rofi|wofi|fuzzel|tofi|dmenu|bemenu|hyprlauncher|anyrun|walker|\$menu"),
    (r"close|kill|quit window", r"close|kill"),
    (r"fullscreen|full screen|maximi", r"fullscreen|maximize"),
    (r"float|tiling|tile", r"float|tile|floating"),
    (r"workspace|desktop|virtual", r"workspace"),
    (r"scratchpad|special|magic|hidden", r"special|scratchpad"),
    (r"volume|audio|sound|mute|speaker|mic", r"Audio|volume|wpctl|pactl|pamixer"),
    (r"bright|backlight", r"Brightness|brightnessctl|light\b"),
    (r"media|music|play|pause|next track|previous track|spotify", r"playerctl|Audio(Play|Pause|Next|Prev)"),
    (r"screenshot|screen shot|capture|grim|slurp|print", r"grim|slurp|Print|hyprshot|grimblast|screenshot"),
    (r"lock|idle|sleep|suspend|swayidle|hypridle|dpms", r"lock|idle|dpms|suspend"),
    (r"exit|logout|log out|quit (sway|hyprland)|power", r"exit|hyprshutdown|swaynag|wlogout"),
    (r"reload|restart", r"reload"),
    (r"resize|size", r"resize|size"),
    (r"focus|move focus|vim|hjkl|arrow", r"focus|left|right|up|down|\bh\b|\bj\b|\bk\b|\bl\b"),
    (r"move|swap", r"move|swap"),
    (r"split|layout|dwindle|master|scrolling|tabbed|stack", r"layout|split|dwindle|master|scrolling|tabbed|stacking"),
    (r"gesture|swipe", r"gesture"),
    (r"env|environment|variable|cursor size|gtk|qt|theme", r"hl\.env|^env|XCURSOR|GTK|QT_"),
    (r"font|title ?bar|titlebar", r"font|title"),
    (r"rule|always|every time|whenever|open on|opens on|pavucontrol|picture.in.picture|pip",
     r"window_rule|for_window|assign|no_focus"),
    (r"group|tab", r"group|tab"),
    (r"submap|mode|resize mode", r"submap|^mode"),
    (r"modifier|mod key|main key|super key", r"^set \$mod|floating_modifier"),
    (r"logo|anime|mascot|splash", r"logo|wallpaper|splash"),
    (r"tearing|vrr|adaptive|freesync|gsync|game", r"tearing|vrr|immediate|adaptive_sync"),
    (r"xwayland|x11", r"xwayland"),
]

_MODS = {
    "super": "SUPER", "mod": "MOD", "mod4": "SUPER", "win": "SUPER", "windows": "SUPER",
    "logo": "SUPER", "meta": "SUPER", "cmd": "SUPER", "command": "SUPER", "$mod": "MOD",
    "mainmod": "MOD",
    "alt": "ALT", "mod1": "ALT", "ctrl": "CTRL", "control": "CTRL", "shift": "SHIFT",
}
_MOD_RE = r"(?:super|\$?mod4?|mod1|win(?:dows)?|logo|meta|cmd|command|alt|ctrl|control|shift|mainmod)"
_COMBO_RE = re.compile(
    rf"(?<![\w$])((?:{_MOD_RE}\s*[+\-]\s*)+)([a-z0-9]+|f\d+|return|enter|space|tab|escape|esc|"
    rf"left|right|up|down|print|delete|backspace|minus|equal|comma|period|slash)\b",
    re.I,
)

_KEY_ALIASES = {"enter": "return", "esc": "escape"}


def _norm_combo(mods: str, key: str, mod_value: str = "SUPER") -> tuple[frozenset, str]:
    ms = set()
    for m in re.split(r"\s*[+\-]\s*", mods.strip(" +-")):
        m = m.strip().lower()
        if not m:
            continue
        v = _MODS.get(m, m.upper())
        if v == "MOD":
            v = mod_value
        ms.add(v)
    key = key.lower()
    return frozenset(ms), _KEY_ALIASES.get(key, key)


def combos_in_request(request: str, mod_value: str = "SUPER") -> set[tuple[frozenset, str]]:
    return {_norm_combo(m.group(1), m.group(2), mod_value) for m in _COMBO_RE.finditer(request)}


def combo_of_line(wm: str, line: str, mod_value: str = "SUPER") -> tuple[frozenset, str] | None:
    if wm == "hyprland":
        m = re.match(r'^hl\.(?:un)?bind\("([^"]+)"', line)
        if not m:
            return None
        parts = [p.strip() for p in m.group(1).split("+")]
        mods = {_MODS.get(p.lower(), p.upper()) for p in parts[:-1]}
        mods = {mod_value if p == "MOD" else p for p in mods}
        key = parts[-1].lower()
        return frozenset(mods), _KEY_ALIASES.get(key, key)
    m = re.match(r"^(?:mode \S+ )?(?:un)?bindsym\s+(?:--\S+\s+)*(\S+)", line)
    if not m:
        return None
    parts = m.group(1).split("+")
    mods = set()
    for p in parts[:-1]:
        pl = p.lower()
        if pl in ("$mod", "mod4", "super", "logo"):
            mods.add(mod_value if pl == "$mod" else "SUPER")
        else:
            mods.add(_MODS.get(pl, p.upper()))
    key = parts[-1].lower()
    return frozenset(mods), _KEY_ALIASES.get(key, key)


def sway_mod_value(lines: list[str]) -> str:
    for l in lines:
        m = re.match(r"^set \$mod (\S+)", l)
        if m:
            return {"mod4": "SUPER", "mod1": "ALT"}.get(m.group(1).lower(), "SUPER")
    return "SUPER"


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9_\-]{2,}", s.lower()) if w not in STOPWORDS}


def select_context(wm: str, request: str, lines: list[str], k: int = MAX_CONTEXT_LINES) -> list[str]:
    """Pick the main-config lines most relevant to the request, in file order."""
    lines = [l for l in lines if not is_managed_include(wm, l)]
    mod_value = sway_mod_value(lines) if wm == "sway" else "SUPER"
    req = request.lower()
    combos = combos_in_request(request, mod_value)
    active = [lp for rp, lp in TOPICS if re.search(rp, req)]
    rwords = _words(req)

    scores: dict[int, float] = {}
    for i, line in enumerate(lines):
        low = line.lower()
        score = 0.0
        if combos:
            c = combo_of_line(wm, line, mod_value)
            if c is not None and c in combos:
                score += 10
        for lp in active:
            if re.search(lp, line, re.I):
                score += 3
        lwords = _words(low)
        score += 1.5 * len(rwords & lwords)
        if score > 0:
            # Shorter lines are cheaper context; break ties towards them.
            scores[i] = score - len(line) / 1000.0

    chosen = sorted(scores, key=lambda i: -scores[i])[:k]
    if wm == "sway":
        # Variables are always useful and cheap.
        sets = [i for i, l in enumerate(lines) if l.startswith("set $")][:8]
        chosen = list(dict.fromkeys(sets + chosen))[: k + len(sets)]
    return [lines[i] for i in sorted(chosen)]


# --------------------------------------------------------------------------
# Prompt rendering and answer parsing
# --------------------------------------------------------------------------

def render_user(wm: str, request: str, context: list[str], managed: list[str]) -> str:
    parts = [f"wm: {wm}", f"request: {request.strip()}", "config:"]
    parts += context if context else ["(none)"]
    parts.append("managed:")
    parts += managed if managed else ["(empty)"]
    return "\n".join(parts)


def messages(wm: str, request: str, context: list[str], managed: list[str]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[wm]},
        {"role": "user", "content": render_user(wm, request, context, managed)},
    ]


@dataclass
class Edit:
    summary: str
    dels: list[str] = field(default_factory=list)
    adds: list[str] = field(default_factory=list)

    def render(self) -> str:
        out = [f"summary: {self.summary}"]
        out += [f"del: {d}" for d in self.dels]
        out += [f"add: {a}" for a in self.adds]
        return "\n".join(out)

    @property
    def is_noop(self) -> bool:
        return not self.dels and not self.adds


class ParseError(ValueError):
    pass


def parse_answer(text: str) -> Edit:
    summary = None
    dels: list[str] = []
    adds: list[str] = []
    for raw in text.strip().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("summary:"):
            if summary is not None:
                raise ParseError("more than one summary line")
            summary = line[len("summary:"):].strip()
        elif line.startswith("del: "):
            dels.append(line[5:])
        elif line.startswith("add: "):
            adds.append(line[5:])
        else:
            raise ParseError(f"unexpected line: {line!r}")
    if summary is None:
        raise ParseError("missing summary line")
    return Edit(summary, dels, adds)


def apply_edit(managed: list[str], edit: Edit) -> list[str]:
    result = list(managed)
    for d in edit.dels:
        if d not in result:
            raise ParseError(f"del line not present in managed file: {d!r}")
        result.remove(d)
    result += edit.adds
    return result
