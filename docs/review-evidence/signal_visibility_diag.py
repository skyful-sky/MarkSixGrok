"""Synthetic-only method calibration; never loads lottery data or emits tickets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from math import comb, sqrt
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
SEED = 20261030
PER_CELL = 100000
WEIGHTS = (1, 2, 4)
VISIBILITIES = (0.0, 0.5, 1.0)
Z95 = 1.959963984540054
SPEC = {
    "purpose": "synthetic signal visibility method calibration; no model ID or attempt",
    "distribution": "unordered six-subset D of1..49; P(D) proportional to w**len(D intersection {1..6})",
    "weights": list(WEIGHTS), "visibilities": list(VISIBILITIES), "per_cell": PER_CELL,
    "seed": SEED, "bit_generator": "PCG64",
    "cell_order": "w1,2,4 outer; visibility0,.5,1 inner; one continuous Generator(PCG64(seed))",
    "sample": "draw K with probabilities C(6,k)*C(43,6-k)*w**k/Z; rng.choice(7,size=N,p=...); rng.permuted broadcast0..5 and6..48 separately per row; keep first K and6-K",
    "rank": "after drawing D, draw visibility flags with rng.random(N)<v; then independent uniform row permutations of0..48 for ALL rows; replace visible rows by ascending0..48; all draws independent of rank visibility",
    "ideal": "S first then complement; within tied group smaller number; w1 all equally likely, ascending order is arbitrary deterministic tie break, no useful signal",
    "A": "positions1..48 cut into8 disjoint groups of6; position49 unused",
    "B": "shared positions1,2,3 plus unique groups4..6,7..9,...,25..27; other positions unused",
    "pairing": "A and B share same D and supplied rank within each cell; nine cells use successive independent samples",
    "success": "at least one group contains>=3 selected main numbers; one success max per period; no special number",
    "rank_diagnostic": "actual supplied-order positions1..49; main-six average; not midrank and not a selection rule",
    "difference": "B-A; SE from sample variance of paired indicator difference divided by N; normal95% Monte Carlo error halfwidth=1.959963984540054*SE",
    "binomial": "fixed constant p, independent20 Bernoulli periods; sum k9..20 C(20,k)*p**k*(1-p)**(20-k); MC plug-in p and analytic p both reported; no inference about HKJC",
    "analytic_check": "integer generating-function counts for each fixed positional template; random order baseline independent of w; visibility mixture linear in v",
    "protected": "no real CSV read; no096-115 backtest; no registered model, protocol, predictor or forecast changes; attempts14/20,remaining6",
}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def k_probabilities(w: int) -> tuple[list[int], np.ndarray]:
    if w not in WEIGHTS:
        raise ValueError("Weight outside locked grid")
    counts = [comb(6, k) * comb(43, 6 - k) * w**k for k in range(7)]
    return counts, np.asarray(counts, dtype=float) / sum(counts)


def sample_masks(rng, n: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    _, probabilities = k_probabilities(w)
    k = rng.choice(7, size=n, p=probabilities)
    support = rng.permuted(np.broadcast_to(np.arange(6), (n, 6)), axis=1)
    other = rng.permuted(np.broadcast_to(np.arange(6, 49), (n, 43)), axis=1)
    masks = np.zeros((n, 49), dtype=bool)
    rows = np.arange(n)[:, None]
    masks[rows, support] = np.arange(6)[None, :] < k[:, None]
    masks[rows, other] = np.arange(43)[None, :] < (6 - k[:, None])
    return masks, k


def supplied_order(rng, n: int, visibility: float) -> tuple[np.ndarray, np.ndarray]:
    if visibility not in VISIBILITIES:
        raise ValueError("Visibility outside locked grid")
    visible = rng.random(n) < visibility
    order = rng.permuted(np.broadcast_to(np.arange(49), (n, 49)), axis=1)
    order[visible] = np.arange(49)
    return order, visible


def evaluate(masks: np.ndarray, order: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    positions = np.take_along_axis(masks, order, axis=1)
    a = positions[:, :48].reshape(-1, 8, 6).sum(axis=2).max(axis=1) >= 3
    b = (positions[:, :3].sum(axis=1)[:, None] +
         positions[:, 3:27].reshape(-1, 8, 3).sum(axis=2)).max(axis=1) >= 3
    rank_sums = (positions * np.arange(1, 50)).sum(axis=1)
    return a, b, rank_sums


def binomial_pass(p: float) -> float:
    return sum(comb(20, k) * p**k * (1 - p)**(20 - k) for k in range(9, 21))


def paired_summary(a: np.ndarray, b: np.ndarray) -> dict:
    n = len(a)
    if n < 2 or len(b) != n:
        raise ValueError("At least two paired periods required")
    a_only = int(np.count_nonzero(a & ~b))
    b_only = int(np.count_nonzero(~a & b))
    both = int(np.count_nonzero(a & b))
    difference = (b_only - a_only) / n
    se = sqrt(max(0, (a_only + b_only - n * difference**2) / (n - 1)) / n)
    rates = {"A": float(a.mean()), "B": float(b.mean())}
    return {"periods": n, "successes_A": int(a.sum()), "successes_B": int(b.sum()),
        "rates": rates, "difference_B_minus_A": difference, "paired_MC_SE": se,
        "difference_95_MC_halfwidth": Z95 * se,
        "paired_counts": {"A_only": a_only, "B_only": b_only, "both": both,
                          "neither": n - a_only - b_only - both},
        "binomial_pass_plugin": {name: binomial_pass(p) for name, p in rates.items()}}


def multiply(a: list[int], b: list[int]) -> list[int]:
    out = [0] * min(7, len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            if i + j < len(out):
                out[i + j] += x * y
    return out


def polynomial(size: int, weight: int = 1, cutoff: int = 6) -> list[int]:
    return [comb(size, k) * weight**k for k in range(min(size, cutoff, 6) + 1)]


def analytic_ideal(w: int) -> dict[str, Fraction]:
    """Count weighted non-success subsets; ideal rank has the six S numbers first."""
    total = sum(k_probabilities(w)[0])
    no_a = polynomial(6, w, 2)
    for _ in range(7):
        no_a = multiply(no_a, polynomial(6, cutoff=2))
    no_a = multiply(no_a, polynomial(1))[6]
    no_b = 0
    for common in range(3):
        cap = 2 - common
        product = polynomial(3, w, cap)
        for _ in range(7):
            product = multiply(product, polynomial(3, cutoff=cap))
        product = multiply(product, polynomial(22))
        no_b += comb(3, common) * w**common * product[6 - common]
    return {"A": Fraction(total - no_a, total), "B": Fraction(total - no_b, total)}


def analytic_cell(w: int, visibility: float) -> dict:
    base, ideal = analytic_ideal(1), analytic_ideal(w)
    v = Fraction(str(visibility))
    q = {name: (1 - v) * base[name] + v * ideal[name] for name in base}
    counts, _ = k_probabilities(w)
    expected_k = sum(k * count for k, count in enumerate(counts)) / sum(counts)
    ideal_rank = 28 - 24.5 * expected_k / 6
    return {"exact_rates": {name: str(value) for name, value in q.items()},
        "rates": {name: float(value) for name, value in q.items()},
        "difference_B_minus_A": float(q["B"] - q["A"]),
        "binomial_pass": {name: binomial_pass(float(value)) for name, value in q.items()},
        "expected_mean_main_rank": (1 - visibility) * 25 + visibility * ideal_rank}


def run(n: int = PER_CELL) -> list[dict]:
    rng = np.random.Generator(np.random.PCG64(SEED))
    cells = []
    for w in WEIGHTS:
        for visibility in VISIBILITIES:
            masks, k = sample_masks(rng, n, w)
            order, visible = supplied_order(rng, n, visibility)
            a, b, rank_sums = evaluate(masks, order)
            cells.append({"w": w, "visibility": visibility, **paired_summary(a, b),
                "visible_periods": int(visible.sum()),
                "K_histogram": np.bincount(k, minlength=7).tolist(),
                "main_rank_sum": int(rank_sums.sum()), "mean_main_rank": float(rank_sums.sum() / (6 * n)),
                "draw_masks_packed_sha256": hashlib.sha256(np.packbits(masks, axis=1).tobytes()).hexdigest(),
                "order_uint8_sha256": hashlib.sha256(order.astype(np.uint8).tobytes()).hexdigest(),
                "visible_packed_sha256": hashlib.sha256(np.packbits(visible).tobytes()).hexdigest(),
                "analytic": analytic_cell(w, visibility)})
    return cells


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "signal-visibility-results.json")
    args = parser.parse_args()
    lock_path = HERE / "signal-visibility-lock.json"
    lock_bytes = lock_path.read_bytes()
    lock = json.loads(lock_bytes)
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if lock["specification"] != SPEC or lock["implementation_sha256"] != code_hash:
        raise ValueError("Locked synthetic method changed")
    marker = args.output.with_suffix(".started.json")
    if args.output.exists() or marker.exists():
        raise ValueError("Diagnostic already started/completed; no overwrite")
    audit = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
        "lock_sha256": hashlib.sha256(lock_bytes).hexdigest(), "implementation_sha256": code_hash,
        "python": sys.version.split()[0], "numpy": np.__version__,
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip(),
        "real_data_read": False, "new_models": 0, "new_attempts": 0,
        "attempts_used": 14, "attempts_remaining": 6}
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(canonical(audit))
    result = {"audit": audit, "specification": SPEC, "cells": run()}
    audit["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical(result))
    for cell in result["cells"]:
        print(canonical({key: cell[key] for key in ("w", "visibility", "mean_main_rank", "rates",
            "difference_B_minus_A", "difference_95_MC_halfwidth", "binomial_pass_plugin")}), end="", flush=True)


if __name__ == "__main__":
    main()
