"""Turns family functions into complete training samples.

A family function has the signature

    family(rng, world, managed) -> (request, Change) | None

where `world` describes a synthetic main config and `managed` is the current
list of ManagedEntry. Returning None means "not applicable here, try another".

For each sample the engine:
  1. picks a world (a synthetic main config, already flattened),
  2. replays 0-4 earlier changes into the managed file, so the model learns to
     work with existing content,
  3. runs the target family, resolves slot conflicts into del lines,
  4. checks that every main-config line the answer depends on is visible in
     the retrieved context (otherwise the answer would be unlearnable).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from data.common import Change
from wmllm.context import Edit, select_context


@dataclass
class ManagedEntry:
    slot: str
    line: str
    ref: str
    cid: int


@dataclass
class Built:
    wm: str
    family: str
    request: str
    context: list[str]
    managed_before: list[str]
    edit: Edit
    world_id: int

    @property
    def managed_after(self) -> list[str]:
        from wmllm.context import apply_edit
        return apply_edit(self.managed_before, self.edit)


def apply_change(managed: list[ManagedEntry], ch: Change, cid: int) -> list[ManagedEntry]:
    claimed = {slot for slot, _ in ch.adds} | set(ch.dels_by_slot)
    kept = [e for e in managed if e.slot not in claimed and e.line not in ch.dels_lines]
    return kept + [ManagedEntry(slot, line, ch.ref, cid) for slot, line in ch.adds]


def resolve(managed: list[ManagedEntry], ch: Change) -> Edit | None:
    claimed = {slot for slot, _ in ch.adds} | set(ch.dels_by_slot)
    dels = [e.line for e in managed if e.slot in claimed or e.line in ch.dels_lines]
    adds = [line for _, line in ch.adds]
    if set(adds) & set(dels):
        return None            # the request is already satisfied; not a useful sample
    if len(set(adds)) != len(adds):
        return None
    return Edit(ch.summary, list(dict.fromkeys(dels)), adds)


def weighted(rng: random.Random, table: list[tuple[float, object]]):
    total = sum(w for w, _ in table)
    r = rng.random() * total
    for w, item in table:
        r -= w
        if r <= 0:
            return item
    return table[-1][1]


def build_one(rng: random.Random, wm: str, worlds: list, families: list[tuple[float, str, object]],
              prior_families: list, combine_prob: float = 0.12, max_tries: int = 40) -> Built | None:
    for _ in range(max_tries):
        world_id = rng.randrange(len(worlds))
        world = worlds[world_id]

        managed: list[ManagedEntry] = []
        n_prior = weighted(rng, [(0.30, 0), (0.25, 1), (0.2, 2), (0.15, 3), (0.1, 4)])
        for cid in range(n_prior):
            fam = rng.choice(prior_families)
            got = fam(rng, world, managed)
            if got is None:
                continue
            _, ch = got
            if resolve(managed, ch) is None:
                continue
            managed = apply_change(managed, ch, cid)

        name, fam = weighted(rng, [(w, (n, f)) for w, n, f in families])
        got = fam(rng, world, managed)
        if got is None:
            continue
        request, ch = got

        if rng.random() < combine_prob and not name.startswith(("remove", "noop", "undo")):
            name2, fam2 = weighted(rng, [(w, (n, f)) for w, n, f in families
                                         if not n.startswith(("remove", "noop", "undo"))])
            got2 = fam2(rng, world, managed)
            if got2 is not None:
                r2, ch2 = got2
                slots1 = {s for s, _ in ch.adds} | set(ch.dels_by_slot)
                slots2 = {s for s, _ in ch2.adds} | set(ch2.dels_by_slot)
                if not slots1 & slots2 and ch.adds and ch2.adds:
                    joiner = rng.choice([" and ", ", and also ", ". Also ", "; ", " + ", ", then "])
                    second = r2[0].lower() + r2[1:] if joiner in (" and ", ", and also ", ", then ") else r2
                    request = request.rstrip(".!?") + joiner + second
                    ch = Change(
                        summary=f"{ch.summary}; {ch2.summary[0].lower() + ch2.summary[1:]}",
                        adds=ch.adds + ch2.adds,
                        dels_by_slot=ch.dels_by_slot + ch2.dels_by_slot,
                        dels_lines=ch.dels_lines + ch2.dels_lines,
                        evidence=ch.evidence + ch2.evidence,
                    )
                    name = f"{name}+{name2}"

        edit = resolve(managed, ch)
        if edit is None:
            continue
        context = select_context(wm, request, world.flat)
        if any(ev not in context for ev in ch.evidence):
            continue
        return Built(wm, name, request, context, [e.line for e in managed], edit, world_id)
    return None
