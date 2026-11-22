# wm-config-llm

A tiny local model that edits **Sway 1.12**, **Hyprland 0.57 (Lua config)** and
**MangoWC 0.18 (config.conf)**
from plain-language requests, small enough to run on CPU-only machines such as a
2011 MacBook Pro.

```
$ wmai "make the gaps bigger and use foot instead of kitty"
Increase general.gaps_in from 5 to 8; launch foot instead of kitty on SUPER + Q
+hl.config({ general = { gaps_in = 8 } })
+hl.unbind("SUPER + Q")
+hl.bind("SUPER + Q", hl.dsp.exec_cmd("foot"))
validated with Hyprland --verify-config: ok
Apply and reload? [Y/n]
```

## How it works

* **Managed file.** The model never rewrites your config. It only writes
  `~/.config/sway/ai.conf`, `~/.config/hypr/ai.lua` or `~/.config/mango/ai.conf`,
  which your main config loads last (`wmai init` adds the `include` / `require` /
  `source`). Its lines override earlier ones, `wmai undo` restores the previous
  version, and you can always edit or delete the file yourself.
* **Mango rebinds.** Mango runs only the *first* binding that matches a key and
  has no unbind, so a later binding cannot override one in your config. To
  rebind such a key the model adds `wmai_disable=<that exact line>`; wmai stores
  it in ai.conf as a comment and comments the line out of config.conf with the
  marker `#@wmai-unbound `. Removing the disable (or `wmai undo`) restores the
  line. These marked lines are the only change wmai ever makes to config.conf
  besides the `source=` line `wmai init` appends.
* **Small, structured answers.** The model replies with a `summary:` line and
  `add:` / `del:` lines, one directive per line. This is far easier for a
  1B-parameter model than writing diffs, and llama.cpp enforces it with a grammar.
* **Relevant context only.** Your main config is flattened to one-line
  statements (Hyprland's Lua is *evaluated* against a recording stub of `hl`,
  so locals, loops and concatenation are resolved) and only the ~14 lines
  relevant to the request are shown to the model. That keeps prompts short,
  which matters most on old CPUs.
* **Real validation.** Every proposal is checked with `sway -C`,
  `Hyprland --verify-config` or `mango -p` before you are asked to apply it;
  invalid proposals are resampled. For mango, a binding that collides with one
  in your config also counts as invalid.

The same code (`wmllm/context.py`) builds prompts for training and for the
CLI, so the model sees exactly the format it was trained on.

## Dataset

`data/` generates the training set programmatically from templated task
families (options, colours, keybinds, window/workspace/layer rules, monitors,
autostart, env, gestures, animations, devices, submaps, removals/undo,
off-topic refusals...). Every line the generator can produce is grounded in
the installed compositors: Hyprland's option names come from
`/usr/share/hypr/stubs/hl.meta.lua`, dispatcher arguments from the v0.57.2
source, and every sample is validated with the real binaries. Sway commands
inside `bindsym`/`for_window` (which `sway -C` does not check) are executed in
a throwaway headless Sway. Mango's option names, rule fields and dispatchers
were checked against the 0.18.6 source and `mango -p`.

```fish
python3 -m data.build --per-wm 9000 --test-per-wm 400   # ~27k samples, a few minutes
```

## Training (on a machine with an NVIDIA GPU)

```fish
uv sync --extra train --python 3.13
uv run python train/train.py --base openbmb/MiniCPM5-1B --out runs/minicpm5-1b
uv run python train/export.py --run runs/minicpm5-1b --quant Q4_K_M
```

The default base is MiniCPM5-1B (Apache-2.0, plain Llama architecture, so it
gets llama.cpp's fastest CPU kernels). Any chat model with a ChatML template
works with `--base`; `Qwen/Qwen3.5-2B` is the stronger, slower alternative.

Evaluate the exported GGUF on held-out configs:

```fish
llama-server -m runs/minicpm5-1b/wmcfg-Q4_K_M.gguf --port 8089 -c 4096 -np 4 &
python3 -m eval.eval --jobs 4
```

## Running it (e.g. on the MacBook)

Requirements: Python 3.9+, `llama-cpp` (Arch's package includes a Sandy Bridge
CPU backend, so no AVX2 is needed), `lua` for Hyprland, and the compositor
(`sway`, `hyprland` or `mangowm`).

A trained model is attached to the
[v4 release](https://github.com/knap43/wm-config-llm/releases/tag/v4), so you
need not train one yourself.

```fish
sudo pacman -S llama-cpp lua github-cli
gh release download v4 -R knap43/wm-config-llm -p '*.gguf'
./install.sh wmcfg-Q4_K_M.gguf   # copies the CLI and model
wmai serve &          # or: systemctl --user enable --now wmai-server
wmai init
wmai "bind super+b to firefox"
```

Environment variables: `WMAI_SERVER` (default `http://127.0.0.1:8089`),
`WMAI_MODEL` (GGUF path for `wmai serve`).
