"""Validation against the real compositor binaries.

* Hyprland: `Hyprland --verify-config -c FILE` parses and evaluates the Lua
  config, rejecting unknown keys, rule fields, dispatcher arguments and keys.
  It always exits 0, so the result text is parsed instead.
* Sway: `sway -C -c FILE` parses the config, but errors inside included files
  do not change the exit code, and the bodies of bindsym/for_window commands
  are not checked. SwayCommandChecker runs a throwaway headless Sway and asks
  it to execute such commands over IPC to close that gap.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _tmpdir() -> str:
    base = os.environ.get("WMLLM_TMP") or None
    return tempfile.mkdtemp(prefix="wmllm-", dir=base)


# --------------------------------------------------------------------------
# Hyprland
# --------------------------------------------------------------------------

def hyprland_errors_for_file(config: Path) -> list[str]:
    proc = subprocess.run(
        ["Hyprland", "--verify-config", "-c", str(config)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "HYPRLAND_NO_SD_NOTIFY": "1"},
    )
    out = ANSI.sub("", proc.stdout + proc.stderr)
    marker = "======== Config parsing result:"
    if marker not in out:
        return [f"validator produced no result (exit {proc.returncode}): {out[-300:]}"]
    result = out.split(marker, 1)[1].strip()
    if result.splitlines() and result.splitlines()[-1].strip() == "config ok":
        return []
    errors = []
    for line in result.splitlines():
        line = line.strip()
        if not line or line.startswith("stack traceback") or line.startswith("[C]") \
                or "in main chunk" in line or line.startswith("..."):
            if line.startswith("...") and ": " in line:
                errors.append(line.split("/")[-1])
            continue
        errors.append(line.replace(str(config.parent) + "/", ""))
    return errors or ["unknown validation failure"]


def validate_hyprland(main_text: str, managed: list[str], module: str = "ai") -> list[str]:
    """Validate a main config (which requires `module`) plus managed lines."""
    d = Path(_tmpdir())
    try:
        (d / "hyprland.lua").write_text(main_text)
        (d / f"{module}.lua").write_text("\n".join(managed) + ("\n" if managed else ""))
        return hyprland_errors_for_file(d / "hyprland.lua")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------
# Sway
# --------------------------------------------------------------------------

SWAY_NOISE = ("Proprietary Nvidia drivers", "Error(s) loading config", "Unable to connect",
              "--unsupported-gpu")


def sway_errors_for_file(config: Path, ignore_missing_files: bool = False) -> list[str]:
    proc = subprocess.run(["sway", "-C", "-c", str(config)], capture_output=True, text=True, timeout=30)
    errors = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if "[ERROR]" not in line and "Error on line" not in line:
            continue
        if any(n in line for n in SWAY_NOISE):
            continue
        if ignore_missing_files and "Unable to access background file" in line:
            continue
        line = re.sub(r"^\S+ \[ERROR\] \[[^\]]+\] ", "", line)
        errors.append(line.replace(str(config.parent) + "/", ""))
    # De-duplicate (background errors are reported twice)
    return list(dict.fromkeys(errors))


def validate_sway(main_text: str, managed: list[str], include_token: str = "@MANAGED@",
                  ignore_missing_files: bool = False) -> list[str]:
    """Validate a main config whose include line names `include_token`."""
    d = Path(_tmpdir())
    try:
        managed_path = d / "ai.conf"
        managed_path.write_text("\n".join(managed) + ("\n" if managed else ""))
        (d / "config").write_text(main_text.replace(include_token, str(managed_path)))
        return sway_errors_for_file(d / "config", ignore_missing_files)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# Errors that only mean "nothing to act on" in an empty headless session.
SWAY_CONTEXT_ERRORS = re.compile(
    r"empty workspace|Cannot resize nothing|no previous workspace|Scratchpad is empty|"
    r"There is no|nothing to|No (?:focused|window|container|output)|Can't|Cannot|"
    r"not (?:in|a) (?:floating|tiling|fullscreen)|Unable to find|No matching|"
    r"is not a (?:floating|tiled)|isn't|Only one|Only views|Only floating|No current container|Failed to find",
    re.I,
)


class SwayCommandChecker:
    """A throwaway headless Sway used to check command syntax over IPC."""

    def __init__(self):
        self.proc = None
        self.rundir = None
        self.sock = None

    def __enter__(self):
        # Socket paths are limited to ~108 bytes, so keep the runtime dir short.
        base = "/tmp/claude-1000" if Path("/tmp/claude-1000").is_dir() else None
        self.rundir = tempfile.mkdtemp(prefix="swv.", dir=base)
        os.chmod(self.rundir, 0o700)
        cfg = Path(self.rundir) / "config"
        cfg.write_text("set $mod Mod4\n")
        env = {**os.environ, "XDG_RUNTIME_DIR": self.rundir, "WLR_BACKENDS": "headless",
               "WLR_RENDERER": "pixman", "WLR_LIBINPUT_NO_DEVICES": "1"}
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("SWAYSOCK", None)
        self.proc = subprocess.Popen(["sway", "--unsupported-gpu", "-c", str(cfg)], env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            socks = list(Path(self.rundir).glob("sway-ipc.*"))
            if socks:
                self.sock = str(socks[0])
                break
            if self.proc.poll() is not None:
                raise RuntimeError("headless sway exited early")
            time.sleep(0.05)
        else:
            raise RuntimeError("headless sway did not start")
        return self

    def check(self, command: str) -> str | None:
        """Return an error message if Sway rejects the command's syntax."""
        proc = subprocess.run(["swaymsg", "-r", "-s", self.sock, "--", command],
                              capture_output=True, text=True, timeout=10)
        try:
            results = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return f"swaymsg failed: {proc.stderr.strip()[:200]}"
        for r in results:
            if not r.get("success", False):
                err = r.get("error", "unknown error")
                if SWAY_CONTEXT_ERRORS.search(err) and not re.search(r"Unknown|Invalid|Expected|Usage", err):
                    continue
                return err
        return None

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.rundir:
            shutil.rmtree(self.rundir, ignore_errors=True)


SWAY_BIND_RE = re.compile(r"^(?:mode \"[^\"]+\" )?bindsym\s+(?:--\S+\s+)*\S+\s+(.*)$")
SWAY_FOR_WINDOW_RE = re.compile(r"^for_window\s+\[[^\]]*\]\s+(.*)$")


def _split_commands(body: str) -> list[str]:
    """Split a Sway command list on ';' and ',' outside double quotes."""
    parts, buf, quoted = [], "", False
    for ch in body:
        if ch == '"':
            quoted = not quoted
        if ch in ";," and not quoted:
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return [p for p in parts if p]


def sway_runtime_commands(line: str) -> list[str]:
    """Commands inside a config line that `sway -C` does not check."""
    for rx in (SWAY_BIND_RE, SWAY_FOR_WINDOW_RE):
        m = rx.match(line)
        if m:
            body = m.group(1)
            return [c for c in _split_commands(body) if not c.startswith("exec")]
    return []
