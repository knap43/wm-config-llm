"""MangoWC (mango 0.18) config helpers shared by the generator, validator and CLI.

Mango reads `key=value` lines and runs only the *first* key binding that
matches a combination, reporting every duplicate as a conflict. Options and
rules, on the other hand, are applied in order, so later lines win. There is
no unbind directive.

wmai therefore keeps the usual managed file (`~/.config/mango/ai.conf`,
sourced at the end of config.conf) and adds one pseudo-directive:

    wmai_disable=<an exact, normalised line of the main config>

It is stored in ai.conf as a comment (`#wmai_disable=...`), so mango never
sees it, and wmai comments the matching main-config line out with the marker
`#@wmai-unbound `. Whenever ai.conf is written, every marked line is first
restored and the current disables are applied again, which keeps the two
files consistent across edits and undo.

Standard library only.
"""

from __future__ import annotations

import re

DISABLE_KEY = "wmai_disable="
STORED_DISABLE = "#" + DISABLE_KEY
UNBOUND_PREFIX = "#@wmai-unbound "
MANAGED_SOURCE_RE = re.compile(r"^\s*source(?:_optional)?\s*=\s*\S*ai\.conf\s*$")


def strip_comment(line: str) -> str:
    """Mango treats `#` as a comment when it follows whitespace outside quotes."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and i > 0 and line[i - 1].isspace():
            return line[:i]
    return line


def normalise(raw: str) -> str | None:
    """One config line as `key=value`, or None for blanks and comments."""
    s = raw.strip()
    if s.startswith(UNBOUND_PREFIX):
        s = s[len(UNBOUND_PREFIX):].strip()
    if not s or s.startswith("#"):
        return None
    s = strip_comment(s).strip()
    if "=" not in s:
        return s or None
    key, value = s.split("=", 1)
    return f"{key.strip()}={value.strip()}"


def flatten_mango(text: str) -> list[str]:
    """Normalised lines of a config.conf, with wmai-disabled lines shown as live.

    The model always sees the main config as the user wrote it; whether a line
    is currently disabled is visible from the wmai_disable lines in ai.conf.
    """
    out = []
    for raw in text.splitlines():
        n = normalise(raw)
        if n is None or MANAGED_SOURCE_RE.match(n):
            continue
        out.append(n)
    return out


def restore_main(text: str) -> str:
    return "\n".join(l.replace(UNBOUND_PREFIX, "", 1) if l.lstrip().startswith(UNBOUND_PREFIX) else l
                     for l in text.split("\n"))


def disables(managed: list[str]) -> list[str]:
    return [l[len(DISABLE_KEY):] for l in managed if l.startswith(DISABLE_KEY)]


def apply_disables(main_text: str, managed: list[str]) -> tuple[str, list[str]]:
    """Return the main config with disabled lines commented out, plus unmatched targets."""
    targets = set(disables(managed))
    hit = set()
    out = []
    for raw in restore_main(main_text).split("\n"):
        n = normalise(raw)
        if n is not None and n in targets:
            indent = raw[: len(raw) - len(raw.lstrip())]
            out.append(indent + UNBOUND_PREFIX + raw.lstrip())
            hit.add(n)
        else:
            out.append(raw)
    return "\n".join(out), sorted(targets - hit)


def managed_text(managed: list[str], header: str = "") -> str:
    """The managed file as written to disk: disables become comments."""
    body = [STORED_DISABLE + l[len(DISABLE_KEY):] if l.startswith(DISABLE_KEY) else l for l in managed]
    return header + "\n".join(body) + ("\n" if body else "")


def read_managed(text: str) -> list[str]:
    out = []
    for l in text.splitlines():
        s = l.strip()
        if s.startswith(STORED_DISABLE):
            out.append(DISABLE_KEY + s[len(STORED_DISABLE):])
        elif s and not s.startswith("#"):
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Key combinations
# --------------------------------------------------------------------------

BIND_RE = re.compile(r"^(bind[a-z]*)=([^,]*),([^,]+),")
MOD_NAMES = {"super": "SUPER", "logo": "SUPER", "ctrl": "CTRL", "control": "CTRL", "alt": "ALT", "shift": "SHIFT",
             "none": None}


def combo_of_bind(line: str) -> tuple[frozenset, str] | None:
    m = BIND_RE.match(line)
    if not m:
        return None
    mods = set()
    for p in m.group(2).split("+"):
        p = p.strip().lower()
        if not p:
            continue
        v = MOD_NAMES.get(p, p.upper())
        if v:
            mods.add(v)
    key = m.group(3).strip().lower()
    return frozenset(mods), {"enter": "return", "esc": "escape"}.get(key, key)
