"""One locked TRIPLECOVER historical run; conditional ticket-geometry simulation."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from marksix_r2 import DATA_SHA256, ROOT, Q, TICKETS, canonical_json, load_training, validate_main

MODEL_ID = "SH-TRIPLECOVER-v1"
SEED = 20261029
MC_SAMPLES = 100000
LOCK_PATH = ROOT / "archive/triplecover-v1.lock.json"
RESULT_PATH = ROOT / "backtests/triplecover-v1.json"
SPEC = {
    "id": MODEL_ID,
    "history": "all main-six draws from26/047 strictly before each target; no decay/window search",
    "triples": "20 unordered sorted triples per draw; cumulative c_S; w_S=max(c_S-1,0)",
    "seed_triple": "highest positive weight not covered by any earlier ticket; ties lexicographic",
    "grow": "add one distinct number1..49 maximizing newly covered residual triple weight until six; ties smallest number",
    "coverage": "mark all positive triples contained in the completed ticket; no weight counted twice across tickets",
    "overlap": "numbers may occur in multiple tickets; no global number exclusion",
    "fallback": "when no positive residual triple remains, append unused exact FixedBlocks-E20 tickets in original order until eight; no duplicate whole tickets",
    "diagnostic": "sum all positive triple weights containing each number; descending score midrank; never used to select tickets",
    "window": "26/096-115 exactly20 targets; train starts26/047; no other historical window scored",
    "success": "at least one of eight tickets has>=3 main numbers; at most once per target; special ignored",
    "effective_triples": "count of distinct historical triples with c_S>=2, before the target",
    "fallback_contribution": "report fallback tickets, fallback-success draws, greedy-success draws, fallback-only draws and both; overlapping successes not double counted",
    "screen": "successes>=9/20 passes exploratory screen only; otherwise disable; no retuning or forward authorization",
    "MC": {"seed": SEED, "samples": MC_SAMPLES,
        "generator": "NumPy default_rng;100000 calls choice(49,6,replace=False); sort each row, add1; same fair main-six samples for all20 fixed allocations and FixedBlocks",
        "estimand": "conditional success probability for each saved eight-ticket configuration; preserve all overlap; arithmetic mean across20 configurations",
        "error": "per-configuration binomial Monte Carlo standard error; pooled standard error from per-sample mean across20 using common random numbers",
        "inference": "configuration geometry only; no adaptive history refit, no null p-value or Holm claim; does not test predictive advantage"},
}


def positive_weights(counts: Counter) -> dict[tuple[int, int, int], int]:
    return {triple: count - 1 for triple, count in sorted(counts.items()) if count >= 2}


def make_tickets(weights: dict) -> tuple[list[dict], dict]:
    """Greedy residual coverage; only an exact whole ticket is 'used' for fallback."""
    if any(len(s) != 3 or tuple(sorted(set(s))) != s or
           any(n not in range(1, 50) for n in s) or not isinstance(w, int) or w <= 0
           for s, w in weights.items()):
        raise ValueError("Expected sorted triples and positive integer weights")
    residual = dict(weights)
    tickets = []
    while residual and len(tickets) < 8:
        seed = min(residual, key=lambda s: (-residual[s], s))
        chosen = set(seed)
        additions = []
        while len(chosen) < 6:
            gains = {n: sum(w for s, w in residual.items()
                            if n in s and set(s).issubset(chosen | {n}))
                     for n in range(1, 50) if n not in chosen}
            n = min(gains, key=lambda n: (-gains[n], n))
            chosen.add(n)
            additions.append({"number": n, "new_weight": gains[n]})
        covered = sorted(s for s in residual if set(s).issubset(chosen))
        tickets.append({"numbers": sorted(chosen), "kind": "greedy", "seed": list(seed),
            "seed_weight": residual[seed], "additions": additions,
            "newly_covered_triples": [list(s) for s in covered],
            "newly_covered_weight": sum(residual[s] for s in covered)})
        for s in covered:
            del residual[s]
    for block in TICKETS:
        if len(tickets) == 8:
            break
        if list(block) not in [t["numbers"] for t in tickets]:
            tickets.append({"numbers": list(block), "kind": "fallback",
                "newly_covered_triples": [], "newly_covered_weight": 0})
    assert len(tickets) == 8 and len({tuple(t["numbers"]) for t in tickets}) == 8
    return tickets, {"uncovered_effective_triples": len(residual),
        "uncovered_weight": sum(residual.values())}


def diagnostics(weights: dict) -> tuple[list[int], list[float]]:
    scores = [sum(w for s, w in weights.items() if n in s) for n in range(1, 50)]
    midranks = [1 + sum(v > s for v in scores) + (sum(v == s for v in scores) - 1) / 2
                for s in scores]
    return scores, midranks


def backtest(draws, first: int = 49) -> list[dict]:
    """Predict before updating; only the requested target window is evaluated."""
    if first < 1 or first >= len(draws):
        raise ValueError("Need prior history and at least one target")
    counts = Counter()
    records = []
    for index, draw in enumerate(draws):
        validate_main(draw.main)
        if index >= first:
            weights = positive_weights(counts)
            tickets, residual = make_tickets(weights)
            scores, ranks = diagnostics(weights)
            actual = set(draw.main)
            for ticket in tickets:
                ticket["main_hits"] = len(actual.intersection(ticket["numbers"]))
            greedy = any(t["main_hits"] >= 3 for t in tickets if t["kind"] == "greedy")
            fallback = any(t["main_hits"] >= 3 for t in tickets if t["kind"] == "fallback")
            fixed_hits = [len(actual.intersection(t)) for t in TICKETS]
            records.append({"index": index, "target": draw.issue, "through": draws[index - 1].issue,
                "history_draws": index, "main": list(draw.main), "tickets": tickets,
                "max_main_hits": max(t["main_hits"] for t in tickets), "success": greedy or fallback,
                "greedy_success": greedy, "fallback_success": fallback,
                "fallback_only_success": fallback and not greedy, "both_success": fallback and greedy,
                "fallback_tickets": sum(t["kind"] == "fallback" for t in tickets),
                "effective_triples": len(weights), "total_weight": sum(weights.values()),
                "positive_triples": [{"numbers": list(s), "count": counts[s], "weight": w}
                                     for s, w in weights.items()],
                "diagnostic_scores": scores, "diagnostic_midranks": ranks,
                "mean_main_midrank": sum(ranks[n - 1] for n in draw.main) / 6,
                "fixedblocks_max_main_hits": max(fixed_hits), "fixedblocks_success": max(fixed_hits) >= 3,
                **residual})
        counts.update(combinations(sorted(draw.main), 3))
    return records


def fair_samples(count: int = MC_SAMPLES, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.asarray([np.sort(rng.choice(49, 6, replace=False)) + 1
                       for _ in range(count)], dtype=np.uint8)


def configuration_successes(samples: np.ndarray, tickets: list) -> np.ndarray:
    if samples.ndim != 2 or samples.shape[1] != 6 or np.any(samples < 1) or np.any(samples > 49):
        raise ValueError("Expected six distinct numbers1..49 per sample")
    if np.any(np.diff(np.sort(samples.astype(int), axis=1), axis=1) == 0):
        raise ValueError("Duplicate number in fair sample")
    mask = np.zeros((len(samples), 50), bool)
    mask[np.arange(len(samples))[:, None], samples] = True
    return mask[:, np.asarray(tickets)].sum(axis=2).max(axis=1) >= 3


def configuration_mc(records: list, samples: np.ndarray) -> dict:
    indicators = []
    per_target = []
    for record in records:
        hits = configuration_successes(samples, [t["numbers"] for t in record["tickets"]])
        indicators.append(hits)
        q = float(hits.mean())
        per_target.append({"target": record["target"], "successes": int(hits.sum()),
            "samples": len(samples), "success_probability": q,
            "mc_standard_error": float(np.sqrt(q * (1 - q) / len(samples)))})
    row_means = np.mean(np.asarray(indicators), axis=0)
    fixed = configuration_successes(samples, list(TICKETS))
    return {"samples": len(samples), "seed": SEED,
        "sorted_sample_uint8_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
        "per_target": per_target, "mean_success_probability": float(row_means.mean()),
        "mean_mc_standard_error": float(row_means.std(ddof=1) / np.sqrt(len(samples))),
        "expected_successes_in_window": float(row_means.mean() * len(records)),
        "fixedblocks_simulated_success_probability": float(fixed.mean()),
        "fixedblocks_exact_success_probability": float(Q),
        "label": SPEC["MC"]["inference"]}


def summary(records: list) -> dict:
    n = len(records)
    return {"draws": n, "successes": sum(r["success"] for r in records),
        "mean_max_main_hits": sum(r["max_main_hits"] for r in records) / n,
        "mean_main_midrank": sum(r["mean_main_midrank"] for r in records) / n,
        "effective_triples_min": min(r["effective_triples"] for r in records),
        "effective_triples_max": max(r["effective_triples"] for r in records),
        "effective_triples_mean": sum(r["effective_triples"] for r in records) / n,
        "fallback_tickets": sum(r["fallback_tickets"] for r in records),
        "total_tickets": 8 * n,
        "fallback_ticket_fraction": sum(r["fallback_tickets"] for r in records) / (8 * n),
        "draws_with_fallback": sum(r["fallback_tickets"] > 0 for r in records),
        "greedy_successes": sum(r["greedy_success"] for r in records),
        "fallback_successes": sum(r["fallback_success"] for r in records),
        "fallback_only_successes": sum(r["fallback_only_success"] for r in records),
        "both_successes": sum(r["both_success"] for r in records),
        "fixedblocks_successes": sum(r["fixedblocks_success"] for r in records)}


def verify_lock(path: Path = LOCK_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    lock = json.loads(raw)
    if lock["specification"] != SPEC or lock["data_sha256"] != DATA_SHA256:
        raise ValueError("Locked specification/data changed")
    if lock["parameter_sha256"] != hashlib.sha256(canonical_json(SPEC).encode()).hexdigest():
        raise ValueError("Locked parameter hash changed")
    if lock["implementation_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Locked implementation changed")
    for name, sha in lock["dependency_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise ValueError("Locked dependency changed")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    lock, lock_hash = verify_lock()
    # An initial committed lock and registry are required, not merely working files.
    committed = subprocess.check_output(["git", "show", "HEAD:archive/triplecover-v1.lock.json"], cwd=ROOT)
    if committed != LOCK_PATH.read_bytes():
        raise ValueError("Lock must be committed before running")
    registry = ROOT / "registry/attempts.csv"
    committed_registry = subprocess.check_output(["git", "show", "HEAD:registry/attempts.csv"], cwd=ROOT)
    if committed_registry != registry.read_bytes():
        raise ValueError("Registry must be committed before running")
    with registry.open(newline="", encoding="utf-8") as stream:
        rows = [r for r in csv.DictReader(stream) if r["attempt_id"] == MODEL_ID]
    budget = json.loads((ROOT / "registry/window-26096-26115.json").read_bytes())
    if len(rows) != 1 or rows[0]["status"] != "registered_pending_backtest" or lock_hash not in rows[0]["notes"]:
        raise ValueError("Exactly one pending hash-locked model registration required")
    if json.loads(rows[0]["parameters"]) != SPEC:
        raise ValueError("Registry parameters differ from locked specification")
    if MODEL_ID not in budget["counted_model_ids"] or budget["used"] != 14 or budget["used"] > budget["limit"]:
        raise ValueError("Expected14/20 cumulative attempts including this model")
    started_path = RESULT_PATH.with_suffix(".started.json")
    if RESULT_PATH.exists() or started_path.exists():
        raise ValueError("Run already started or completed; no historical rerun/overwrite")
    draws = load_training()
    audit = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "data_sha256": DATA_SHA256, "lock_sha256": lock_hash,
        "implementation_sha256": lock["implementation_sha256"], "observed_runs": 1,
        "python": sys.version.split()[0], "numpy": np.__version__}
    with started_path.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(audit))
    records = backtest(draws)
    stats = summary(records)
    mc = configuration_mc(records, fair_samples())
    result = {"model_id": MODEL_ID, "specification": SPEC, "audit": audit, "summary": stats,
        "status": "disabled" if stats["successes"] < 9 else "exploratory_screen_passed_only",
        "records": records, "configuration_MC": mc, "attempt_budget": budget,
        "comparison": {"FixedBlocks_E20": "8/20", "fair_fixedblocks_q": float(Q)},
        "evidence": "Historical exploratory screen only; diagnostic rank does not select tickets; geometry MC is not a predictive p-value."}
    audit["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    with RESULT_PATH.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(result))
    sha = hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest()
    RESULT_PATH.with_suffix(".json.sha256").write_text(f"{sha}  {RESULT_PATH.name}\n", encoding="utf-8")
    print(canonical_json({"summary": stats, "status": result["status"],
        "mean_configuration_q": mc["mean_success_probability"], "result_sha256": sha}), end="")


if __name__ == "__main__":
    main()
