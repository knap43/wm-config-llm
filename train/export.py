"""Merge the LoRA adapter and export a quantised GGUF for llama.cpp.

    uv run python train/export.py --run runs/minicpm5-1b

Uses llama.cpp's convert_hf_to_gguf.py, which Arch's llama-cpp package does
not ship, so llama.cpp is shallow-cloned into .tools/ on first use (pass
--llamacpp-dir to use an existing checkout instead). Quantisation uses the
system `llama-quantize`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / ".tools" / "llama.cpp"


def merge(run: Path, base: str | None) -> Path:
    merged = run / "merged"
    if merged.exists():
        return merged
    import torch
    from peft import PeftConfig, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter = run / "adapter"
    tok = AutoTokenizer.from_pretrained(adapter)
    base_name = base or PeftConfig.from_pretrained(adapter).base_model_name_or_path
    print(f"merging {adapter} into {base_name}")
    model = AutoModelForCausalLM.from_pretrained(base_name, dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    model.save_pretrained(merged, safe_serialization=True)
    tok.save_pretrained(merged)
    return merged


def via_llamacpp(merged: Path, run: Path, out: Path, quant: str, name: str, tools: Path):
    script = tools / "convert_hf_to_gguf.py"
    if not script.exists():
        tools.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(tools)], check=True)
    f16 = run / f"{name}-f16.gguf"
    if not f16.exists():
        env = {**os.environ, "PYTHONPATH": str(tools / "gguf-py")}
        subprocess.run([sys.executable, str(script), str(merged), "--outfile", str(f16), "--outtype", "f16"], check=True, env=env)
    subprocess.run(["llama-quantize", str(f16), str(out), quant], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/minicpm5-1b")
    ap.add_argument("--base", default=None, help="defaults to the adapter's recorded base model")
    ap.add_argument("--name", default="wmcfg")
    ap.add_argument("--quant", default="Q4_K_M")
    ap.add_argument("--llamacpp-dir", type=Path, default=TOOLS)
    args = ap.parse_args()

    run = Path(args.run)
    merged = merge(run, args.base)
    out = run / f"{args.name}-{args.quant}.gguf"
    via_llamacpp(merged, run, out, args.quant, args.name, args.llamacpp_dir)
    print(f"{out}  {out.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
