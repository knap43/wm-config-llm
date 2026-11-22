#!/usr/bin/env bash
# Install the wmai CLI (and optionally a model) for the current user.
#   ./install.sh [path/to/model.gguf]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}/wmai"
app="$data/app"
bin="$HOME/.local/bin"

mkdir -p "$app/wmllm" "$app/cli" "$bin"
install -m 644 "$here"/wmllm/__init__.py "$here"/wmllm/context.py "$here"/wmllm/validate.py "$here"/wmllm/mango.py "$here"/wmllm/flatten_hypr.lua "$app/wmllm/"
install -m 755 "$here/cli/wmai.py" "$app/cli/wmai.py"
ln -sf "$app/cli/wmai.py" "$bin/wmai"
echo "installed wmai -> $bin/wmai"

if [[ $# -ge 1 ]]; then
    install -m 644 "$1" "$data/wmcfg-Q4_K_M.gguf"
    echo "installed model -> $data/wmcfg-Q4_K_M.gguf"
fi

unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/wmai-server.service" <<UNIT
[Unit]
Description=llama-server for wmai

[Service]
ExecStart=$bin/wmai serve
Restart=on-failure
Nice=10

[Install]
WantedBy=default.target
UNIT
echo "installed $unit_dir/wmai-server.service (enable with: systemctl --user enable --now wmai-server)"
command -v llama-server >/dev/null || echo "note: llama-server not found; install llama-cpp"
