#!/usr/bin/env python3
"""wmai: edit your Sway or Hyprland config in plain language with a local model.

    wmai init                    add the managed include/require to your config
    wmai "make the gaps bigger"  propose an edit, validate it, ask, apply, reload
    wmai undo                    restore the managed file to its previous state
    wmai show                    print the managed file
    wmai serve                   start llama-server with the model

The model only ever writes to a managed file (~/.config/sway/ai.conf or
~/.config/hypr/ai.lua) that your main config loads last. Every proposal is
checked with the real compositor (`sway -C` / `Hyprland --verify-config`)
before you are asked to apply it.

Standard library only. Talks to llama-server over HTTP (default
http://127.0.0.1:8089, override with WMAI_SERVER).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
for cand in (HERE.parent, HERE):
    if (cand / "wmllm" / "context.py").exists():
        sys.path.insert(0, str(cand))
        break

from wmllm.context import (SYSTEM_PROMPTS, ParseError, apply_edit, flatten_hyprland, flatten_sway,  # noqa: E402
                           parse_answer, render_user, select_context)

SERVER = os.environ.get("WMAI_SERVER", "http://127.0.0.1:8089")
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "wmai"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "wmai"

GRAMMAR = r'''root ::= "summary: " line ( "\n" op )*
op ::= ( "add: " | "del: " ) line
line ::= [^\n]+
'''

HYPR_REQUIRE = 'require("ai")'


class WM:
    def __init__(self, name: str):
        self.name = name
        if name == "sway":
            self.dir = CONFIG_HOME / "sway"
            self.main = self.dir / "config"
            self.managed = self.dir / "ai.conf"
        else:
            self.dir = CONFIG_HOME / "hypr"
            self.main = self.dir / "hyprland.lua"
            self.managed = self.dir / "ai.lua"

    # ---------------------------------------------------------------- reading
    def managed_lines(self) -> list[str]:
        if not self.managed.exists():
            return []
        return [l for l in self.managed.read_text().splitlines() if l.strip() and not l.startswith(("#", "--"))]

    def flat(self) -> list[str]:
        if self.name == "sway":
            return flatten_sway(self.main.read_text())
        if not shutil.which("lua"):
            sys.exit("wmai needs a standalone Lua interpreter to read hyprland.lua (pacman -S lua)")
        return flatten_hyprland(self.main, "ai")

    def is_initialised(self) -> bool:
        if not self.main.exists():
            return False
        text = self.main.read_text()
        if self.name == "sway":
            return any(re.match(r"^\s*include\s+\S*ai\.conf\s*$", l) for l in text.splitlines())
        return HYPR_REQUIRE in text or "require('ai')" in text

    # ---------------------------------------------------------------- checking
    def validate(self, lines: list[str]) -> list[str]:
        header = "# Managed by wmai\n" if self.name == "sway" else "-- Managed by wmai\n"
        body = header + "\n".join(lines) + ("\n" if lines else "")
        if self.name == "sway":
            cand = self.dir / ".wmai-check-ai.conf"
            main = self.dir / ".wmai-check-config"
            text = self.main.read_text()
            new_text, n = re.subn(r"(?m)^(\s*include\s+)\S*ai\.conf\s*$", lambda m: m.group(1) + str(cand), text)
            if n == 0:
                return ["the main config does not include ai.conf; run `wmai init`"]
            try:
                cand.write_text(body)
                main.write_text(new_text)
                proc = subprocess.run(["sway", "-C", "-c", str(main)], capture_output=True, text=True, timeout=30)
            finally:
                cand.unlink(missing_ok=True)
                main.unlink(missing_ok=True)
            errs = [re.sub(r"^\S+ \[ERROR\] \[[^\]]+\] ", "", l) for l in (proc.stdout + proc.stderr).splitlines()
                    if ("[ERROR]" in l or "Error on line" in l) and "Error(s) loading" not in l and "Nvidia" not in l]
            return list(dict.fromkeys(errs))
        cand = self.dir / "wmai_check_ai.lua"
        main = self.dir / ".wmai-check.lua"
        text = self.main.read_text()
        new_text = text.replace(HYPR_REQUIRE, 'require("wmai_check_ai")').replace("require('ai')", 'require("wmai_check_ai")')
        try:
            cand.write_text(body)
            main.write_text(new_text)
            proc = subprocess.run(["Hyprland", "--verify-config", "-c", str(main)], capture_output=True, text=True, timeout=30)
        finally:
            cand.unlink(missing_ok=True)
            main.unlink(missing_ok=True)
        out = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout + proc.stderr)
        result = out.split("======== Config parsing result:", 1)[-1].strip()
        if result.splitlines() and result.splitlines()[-1].strip() == "config ok":
            return []
        return [l.replace(str(self.dir) + "/", "") for l in result.splitlines()
                if l.strip() and not l.strip().startswith(("stack traceback", "[C]")) and "in main chunk" not in l] or [result[-300:]]

    # ---------------------------------------------------------------- writing
    def write_managed(self, lines: list[str]):
        STATE_HOME.mkdir(parents=True, exist_ok=True)
        hist = STATE_HOME / "history" / self.name
        hist.mkdir(parents=True, exist_ok=True)
        if self.managed.exists():
            shutil.copy2(self.managed, hist / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6:06d}{self.managed.suffix}")
        header = ("# Managed by wmai. Edit freely; one directive per line.\n" if self.name == "sway"
                  else "-- Managed by wmai. Edit freely; one statement per line.\n")
        self.managed.write_text(header + "\n".join(lines) + ("\n" if lines else ""))

    def reload(self):
        cmd = ["swaymsg", "reload"] if self.name == "sway" else ["hyprctl", "reload"]
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True, timeout=15)


def detect_wm(explicit: str | None) -> WM:
    if explicit:
        return WM(explicit)
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return WM("hyprland")
    if os.environ.get("SWAYSOCK"):
        return WM("sway")
    have = [n for n, p in (("hyprland", CONFIG_HOME / "hypr" / "hyprland.lua"), ("sway", CONFIG_HOME / "sway" / "config")) if p.exists()]
    if len(have) == 1:
        return WM(have[0])
    sys.exit("could not tell whether to edit Sway or Hyprland; pass --wm sway|hyprland")


# ---------------------------------------------------------------- model

def chatml(wm: str, user: str) -> str:
    # Mirrors the MiniCPM5 chat template with add_generation_prompt and no thinking block.
    return (f"<s><|im_start|>system\n{SYSTEM_PROMPTS[wm]}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def complete(prompt: str, temperature: float, seed: int) -> str:
    body = {"prompt": prompt, "n_predict": 600, "temperature": temperature, "top_p": 0.95, "seed": seed,
            "grammar": GRAMMAR, "stop": ["<|im_end|>"], "cache_prompt": True}
    req = urllib.request.Request(f"{SERVER}/completion", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["content"]
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach llama-server at {SERVER} ({e.reason}). Start it with `wmai serve`.")


def propose(wm: WM, request: str, attempts: int, verbose: bool):
    flat = wm.flat()
    context = select_context(wm.name, request, flat)
    managed = wm.managed_lines()
    user = render_user(wm.name, request, context, managed)
    if verbose:
        print("----- prompt\n" + user + "\n-----", file=sys.stderr)
    last_err = None
    for i in range(attempts):
        t0 = time.time()
        text = complete(chatml(wm.name, user), 0.0 if i == 0 else 0.5, seed=i)
        if verbose:
            print(f"----- answer ({time.time() - t0:.1f}s)\n{text}\n-----", file=sys.stderr)
        try:
            edit = parse_answer(text)
            new = apply_edit(managed, edit)
        except ParseError as e:
            last_err = [str(e)]
            continue
        if edit.is_noop:
            return edit, managed, managed, []
        errs = wm.validate(new)
        if not errs:
            return edit, managed, new, []
        last_err = errs
        if verbose:
            print("validation failed: " + "; ".join(errs), file=sys.stderr)
    return None, managed, None, last_err or ["no answer"]


# ---------------------------------------------------------------- commands

def cmd_init(wm: WM):
    if not wm.main.exists():
        sys.exit(f"{wm.main} does not exist; create your config first")
    if wm.is_initialised():
        print(f"{wm.main} already loads {wm.managed.name}")
    else:
        backup = wm.main.with_name(wm.main.name + ".wmai-backup")
        shutil.copy2(wm.main, backup)
        home = str(Path.home())
        managed = str(wm.managed)
        managed = "~" + managed[len(home):] if managed.startswith(home + "/") else managed
        line = f"include {managed}" if wm.name == "sway" else HYPR_REQUIRE
        comment = "#" if wm.name == "sway" else "--"
        with wm.main.open("a") as f:
            f.write(f"\n{comment} Managed by wmai (keep this last so its settings win)\n{line}\n")
        print(f"appended `{line}` to {wm.main} (backup: {backup})")
    if not wm.managed.exists():
        wm.write_managed([])
        print(f"created {wm.managed}")
    errs = wm.validate(wm.managed_lines())
    print("config check: " + ("ok" if not errs else "; ".join(errs)))


def cmd_edit(wm: WM, request: str, yes: bool, dry_run: bool, attempts: int, verbose: bool):
    if not wm.is_initialised():
        sys.exit(f"{wm.main} does not load {wm.managed.name} yet; run `wmai init` first")
    edit, old, new, errs = propose(wm, request, attempts, verbose)
    if edit is None:
        print("The model did not produce a valid edit:", file=sys.stderr)
        for e in errs:
            print("  " + e, file=sys.stderr)
        sys.exit(1)
    print(edit.summary)
    if edit.is_noop:
        return
    diff = difflib.unified_diff(old, new, fromfile=f"{wm.managed.name} (now)", tofile=f"{wm.managed.name} (proposed)", lineterm="", n=1)
    for line in diff:
        colour = "\x1b[32m" if line.startswith("+") and not line.startswith("+++") else (
            "\x1b[31m" if line.startswith("-") and not line.startswith("---") else "")
        print(f"{colour}{line}\x1b[0m" if colour and sys.stdout.isatty() else line)
    print("validated with " + ("sway -C" if wm.name == "sway" else "Hyprland --verify-config") + ": ok")
    if dry_run:
        return
    if not yes:
        try:
            ans = input("Apply and reload? [Y/n] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("", "y", "yes"):
            print("not applied")
            return
    wm.write_managed(new)
    wm.reload()
    print(f"applied to {wm.managed} and reloaded")


def cmd_undo(wm: WM):
    hist = STATE_HOME / "history" / wm.name
    snaps = sorted(hist.glob("*")) if hist.exists() else []
    if not snaps:
        sys.exit("nothing to undo")
    last = snaps[-1]
    shutil.copy2(last, wm.managed)
    last.unlink()
    wm.reload()
    print(f"restored {wm.managed} from {last.name} and reloaded")


def cmd_serve(model: str | None, threads: int | None):
    model = model or os.environ.get("WMAI_MODEL") or str(DATA_HOME / "wmcfg-Q4_K_M.gguf")
    if not Path(model).exists():
        sys.exit(f"model not found: {model} (set WMAI_MODEL or pass --model)")
    port = SERVER.rsplit(":", 1)[-1].split("/")[0]
    args = ["llama-server", "-m", model, "--port", port, "--host", "127.0.0.1", "-c", "4096", "-np", "1",
            "--no-webui", "--cache-reuse", "256"]
    if threads:
        args += ["-t", str(threads)]
    os.execvp(args[0], args)


def main():
    ap = argparse.ArgumentParser(prog="wmai", description="Edit Sway/Hyprland config in plain language with a local model.")
    ap.add_argument("--wm", choices=["sway", "hyprland"])
    ap.add_argument("-y", "--yes", action="store_true", help="apply without asking")
    ap.add_argument("-n", "--dry-run", action="store_true", help="show the proposal only")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the prompt and raw answers")
    ap.add_argument("--attempts", type=int, default=3, help="samples to try until one validates")
    ap.add_argument("--model", help="GGUF path for `wmai serve`")
    ap.add_argument("--threads", type=int, help="CPU threads for `wmai serve`")
    ap.add_argument("words", nargs="+", help="init | undo | show | serve | your request")
    a = ap.parse_args()
    first = a.words[0]
    if len(a.words) == 1 and first == "serve":
        return cmd_serve(a.model, a.threads)
    wm = detect_wm(a.wm)
    if len(a.words) == 1 and first == "init":
        return cmd_init(wm)
    if len(a.words) == 1 and first == "undo":
        return cmd_undo(wm)
    if len(a.words) == 1 and first == "show":
        print("\n".join(wm.managed_lines()) or "(empty)")
        return
    cmd_edit(wm, " ".join(a.words), a.yes, a.dry_run, a.attempts, a.verbose)


if __name__ == "__main__":
    main()
