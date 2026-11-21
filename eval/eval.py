"""Evaluate a GGUF model served by llama-server on the held-out test split.

    llama-server -m runs/minicpm5-1b/wmcfg-Q4_K_M.gguf --port 8089 -c 4096 -np 4 &
    python3 -m eval.eval --server http://127.0.0.1:8089 --jobs 4

Metrics:
  parse    answer follows the summary/add/del format and its del lines exist
  exact    the set of del lines and the list of add lines match the reference
  valid    the resulting managed file passes the real compositor check
  noop_ok  for reference no-op answers: the model also proposed no change
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cli.wmai import GRAMMAR
from wmllm.context import ParseError, apply_edit, parse_answer
from wmllm.validate import validate_hyprland, validate_sway


def chatml(messages) -> str:
    sys_m, user = messages[0]["content"], messages[1]["content"]
    return (f"<|im_start|>system\n{sys_m}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def complete(server: str, prompt: str, grammar: bool) -> tuple[str, float]:
    body = {"prompt": prompt, "n_predict": 600, "temperature": 0.0, "stop": ["<|im_end|>"], "cache_prompt": False}
    if grammar:
        body["grammar"] = GRAMMAR
    req = urllib.request.Request(f"{server}/completion", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=600) as r:
        return json.loads(r.read())["content"], time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8089")
    ap.add_argument("--data", default="data/out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--no-grammar", action="store_true")
    ap.add_argument("--out", default=None, help="write per-sample results as jsonl")
    args = ap.parse_args()

    data = Path(args.data)
    recs = [json.loads(l) for l in (data / "test.jsonl").read_text().splitlines()]
    if args.limit:
        recs = recs[: args.limit]
    worlds = {wm: json.loads((data / f"worlds-{wm}-test.json").read_text()) for wm in ("hyprland", "sway")}

    def run(rec):
        wm = rec["meta"]["wm"]
        ref = parse_answer(rec["messages"][2]["content"])
        before = rec["meta"]["managed_before"]
        text, secs = complete(args.server, chatml(rec["messages"]), not args.no_grammar)
        res = {"wm": wm, "family": rec["meta"]["family"], "secs": secs, "answer": text, "reference": rec["messages"][2]["content"]}
        try:
            edit = parse_answer(text)
            after = apply_edit(before, edit)
        except ParseError as e:
            return {**res, "parse": False, "exact": False, "valid": False, "error": str(e)}
        exact = set(edit.dels) == set(ref.dels) and edit.adds == ref.adds
        main_text = worlds[wm][rec["meta"]["world"]]
        if edit.is_noop:
            valid = True
        elif wm == "hyprland":
            valid = not validate_hyprland(main_text, after)
        else:
            valid = not validate_sway(main_text, after, ignore_missing_files=True)
        return {**res, "parse": True, "exact": exact, "valid": valid, "noop_ref": ref.is_noop, "noop_pred": edit.is_noop}

    t0 = time.time()
    with ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(run, recs))
    total = time.time() - t0

    def pct(xs):
        return f"{100 * sum(xs) / max(1, len(xs)):5.1f}%"

    print(f"{len(results)} samples in {total:.0f}s ({sum(r['secs'] for r in results) / len(results):.2f}s per request)")
    for wm in ("hyprland", "sway", None):
        rs = [r for r in results if wm is None or r["wm"] == wm]
        noop = [r for r in rs if r.get("noop_ref")]
        print(f"{wm or 'all':9s} n={len(rs):4d}  parse {pct([r['parse'] for r in rs])}  exact {pct([r['exact'] for r in rs])}  "
              f"valid {pct([r['valid'] for r in rs])}  noop_ok {pct([r.get('noop_pred', False) for r in noop])} (n={len(noop)})")
    fam = collections.defaultdict(list)
    for r in results:
        fam[(r["wm"], r["family"].split("+")[0])].append(r)
    print("\nper family (exact / valid):")
    for (wm, f), rs in sorted(fam.items(), key=lambda kv: sum(r["exact"] for r in kv[1]) / len(kv[1])):
        print(f"  {wm:8s} {f:16s} n={len(rs):3d}  {pct([r['exact'] for r in rs])}  {pct([r['valid'] for r in rs])}")
    if args.out:
        with open(args.out, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    sys.exit(main())
