"""Generate, validate, deduplicate and split the dataset.

    python -m data.build --per-wm 9000 --out data/out

Train/val use worlds built from one seed; the test split uses worlds built
from a different seed and a different sampling seed, so it measures
generalisation to configs the model has never seen.

Every sample is validated twice with the real compositor (managed file before
and after the edit). For Sway, every command inside an added bindsym /
for_window / bindgesture line is also executed in a headless Sway.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from data import hypr, sway
from data.engine import build_one
from wmllm.context import SYSTEM_PROMPTS, render_user
from wmllm.validate import SwayCommandChecker, sway_runtime_commands, validate_hyprland, validate_sway

MODULES = {"hyprland": hypr, "sway": sway}


def generate(wm: str, n: int, n_worlds: int, world_seed: int, sample_seed: int):
    mod = MODULES[wm]
    worlds = mod.build_worlds(n_worlds, seed=world_seed)
    rng = random.Random(sample_seed)
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < n * 5:
        tries += 1
        b = build_one(rng, wm, worlds, mod.FAMILIES, mod.PRIOR_FAMILIES)
        if b is None:
            continue
        key = (b.request.lower(), tuple(b.context), tuple(b.managed_before))
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return worlds, out


def validate_all(wm: str, worlds, samples, jobs: int):
    def check(b):
        text = worlds[b.world_id].text
        if wm == "hyprland":
            return validate_hyprland(text, b.managed_before) or validate_hyprland(text, b.managed_after)
        return (validate_sway(text, b.managed_before, ignore_missing_files=True)
                or validate_sway(text, b.managed_after, ignore_missing_files=True))

    with ThreadPoolExecutor(jobs) as ex:
        results = list(ex.map(check, samples))
    good, bad = [], collections.Counter()
    examples = {}
    for b, errs in zip(samples, results):
        if errs:
            bad[b.family] += 1
            examples.setdefault(b.family, errs[:2])
        else:
            good.append(b)

    if wm == "sway":
        cmds = {c for b in good for l in b.edit.adds for c in sway_runtime_commands(l)}
        with SwayCommandChecker() as chk:
            rejected = {c: e for c in sorted(cmds) if (e := chk.check(c))}
        if rejected:
            print(f"  sway rejected {len(rejected)} command(s): {list(rejected.items())[:5]}", file=sys.stderr)
        kept = []
        for b in good:
            if any(c in rejected for l in b.edit.adds for c in sway_runtime_commands(l)):
                bad[b.family + " (runtime)"] += 1
            else:
                kept.append(b)
        good = kept
    return good, bad, examples


def to_record(b) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[b.wm]},
            {"role": "user", "content": render_user(b.wm, b.request, b.context, b.managed_before)},
            {"role": "assistant", "content": b.edit.render()},
        ],
        "meta": {"wm": b.wm, "family": b.family, "world": b.world_id, "managed_before": b.managed_before},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-wm", type=int, default=9000, help="train+val samples per compositor")
    ap.add_argument("--test-per-wm", type=int, default=400)
    ap.add_argument("--val-frac", type=float, default=0.04)
    ap.add_argument("--worlds", type=int, default=400)
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--out", default="data/out")
    ap.add_argument("--only-test", action="store_true", help="regenerate only test.jsonl (+ worlds)")
    args = ap.parse_args()

    missing = hypr.check_tables()
    if missing:
        sys.exit(f"Hyprland option tables reference unknown keys: {missing}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "val": [], "test": []}
    report = {}
    for wm in ("hyprland", "sway"):
        plan = [("trainval", args.per_wm, 1, 100, args.worlds), ("test", args.test_per_wm, 2, 200, max(40, args.worlds // 10))]
        if args.only_test:
            plan = plan[1:]
        for split, n, wseed, sseed, nworlds in plan:
            print(f"[{wm}/{split}] generating {n} ...", file=sys.stderr)
            worlds, samples = generate(wm, n, nworlds, wseed, sseed)
            good, bad, examples = validate_all(wm, worlds, samples, args.jobs)
            print(f"[{wm}/{split}] {len(good)}/{len(samples)} valid; rejected by family: {dict(bad)}", file=sys.stderr)
            for fam, errs in examples.items():
                print(f"    e.g. {fam}: {errs}", file=sys.stderr)
            fams = collections.Counter(b.family.split("+")[0] for b in good)
            report[f"{wm}/{split}"] = {"valid": len(good), "generated": len(samples), "families": dict(fams), "rejected": dict(bad)}
            recs = [to_record(b) for b in good]
            if split == "test":
                splits["test"] += recs
                (out / f"worlds-{wm}-test.json").write_text(json.dumps([w.text for w in worlds]))
            else:
                rng = random.Random(42)
                rng.shuffle(recs)
                nval = int(len(recs) * args.val_frac)
                splits["val"] += recs[:nval]
                splits["train"] += recs[nval:]

    rng = random.Random(0)
    for name, recs in splits.items():
        if args.only_test and name != "test":
            continue
        rng.shuffle(recs)
        with open(out / f"{name}.jsonl", "w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(recs)} records to {out / (name + '.jsonl')}", file=sys.stderr)
    (out / ("report-test.json" if args.only_test else "report.json")).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
