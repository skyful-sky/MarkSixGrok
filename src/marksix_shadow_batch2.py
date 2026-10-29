"""Three locked shadows and 10,000 complete-history fair null simulations."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import numpy as np

from marksix_r2 import DATA_SHA256, ROOT, canonical_json, load_training

SEED = 20261029
MC_PATHS = 10000
ATTEMPT_CAP = 20
WARMUP = 20
PERIODS = tuple(range(2, 11))
MODEL_IDS = ("SH-RESFOLD-v1", "SH-CENTROID-v1", "SH-TAIL-v1")
SEGMENTS = {"26067_26095": (20, 49), "26096_26115": (49, 69), "26067_26115": (20, 69)}
LOCK_PATH = ROOT / "archive/shadow-batch2-v1.lock.json"
SPECS = {
    "SH-RESFOLD-v1": {"periods": list(PERIODS), "kappa": 10, "W": 20,
        "phase": "CSV zero-based index i modulo P;26/047=0",
        "score": "mean_P((past_phase_number_hits+10*(6/49))/(past_phase_draws+10))",
        "ties": "seeded_permutation", "seed": SEED},
    "SH-CENTROID-v1": {"half_life": 5, "W": 20,
        "score": "negative absolute distance to normalized EWM of historical main-six means",
        "ties": "smaller_number_first", "excluded": "rank_position49, per original Research wording"},
    "SH-TAIL-v1": {"half_life": 10, "W": 20, "seed": SEED,
        "tail": "number modulo10; sizes[4,5,5,5,5,5,5,5,5,5]",
        "score": "normalized EWM of main-six tail count divided by that tail's number count",
        "ties": "seeded_permutation", "mechanism": "無物理機制"},
}
CONVENTIONS = {
    "history": "expanding from26/047; predict before update; W20 is warmup, not a rolling window",
    "EWM": "adjusted normalized weights decay**(target_index-1-history_index), with zero numerator/denominator initially; prior draw relative age0",
    "seeded_ties": "independent random.Random(20261029) per seeded model; shuffle ascending1..49 once per scored target, stable score sort; no warmup RNG use",
    "centroid_exclusion": "exclude sorted position49; not forcibly number49 (Research says rank49)",
    "numeric": "RESFOLD exact int64 common-denominator ordering; CENTROID/TAIL float64, no posthoc rounding or tolerance",
    "tickets": "first48 positions cut6;8 disjoint tickets; one remaining number excluded",
    "success": "at least one ticket contains>=3 mains, count once per draw; special numbers ignored",
    "rank": "actual ticket-order positions1..49; score midranks also reported",
    "screen": "096-115 hits>=9 is exploratory screening only; fewer than9 disables the version",
    "MC": "10000 independent full69-draw uniform6-subset paths; refit each path from its first draw; replay identical fixed tie permutations",
    "MC_rng": "NumPy default_rng(20261029), independent from Python tie RNGs",
    "p_values": "plus-one upper tail for hits, lower tail for rank sums and score-midrank sums; (1+as_or_more_extreme)/(10000+1)",
    "multiplicity": "raw MC p plus Bonferroni20 descriptive bound; do not claim complete-family Holm without old p-values; old failures must not be rerun",
    "attempt_count": "unique known models tested on096-115; include fixed blocks and24-number pool; merge explore-blocks/canonical archive alias; exclude forward-only hypotheses, dissent, reserved H2, validation-only permutation",
    "attempt_cap": 20,
}


def attempt_budget(path: Path = ROOT / "registry/attempts.csv") -> dict:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    counted = []
    for row in rows:
        model = row["attempt_id"]
        if model == "explore-blocks":
            model = "EXP-R1-FB8-26096-26115"
        if model.startswith("SH-") or model in ("EXP-R1-FB8-26096-26115", "explore-24"):
            if model not in counted:
                counted.append(model)
    if len(counted) > ATTEMPT_CAP:
        raise ValueError("Same-window attempt cap exceeded; no more model execution")
    return {"limit": ATTEMPT_CAP, "used": len(counted), "remaining": ATTEMPT_CAP - len(counted),
            "counted_model_ids": counted, "registry_rows": len(rows),
            "scope": "known registered model versions on26/096-115, including legacy models; alias-deduplicated"}


def main_masks(draws) -> np.ndarray:
    masks = np.zeros((1, len(draws), 49), dtype=bool)
    for t, draw in enumerate(draws):
        masks[0, t, np.asarray(draw.main) - 1] = True
    return masks


def fair_histories(paths: int, draws: int, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    masks = np.zeros((paths, draws, 49), dtype=bool)
    row = np.arange(paths)[:, None]
    for t in range(draws):
        selected = np.argpartition(rng.random((paths, 49)), 5, axis=1)[:, :6]
        masks[row, t, selected] = True
    return masks


def resfold_keys(hits: dict[int, np.ndarray], target: int) -> tuple[np.ndarray, int]:
    denominators = [target // period + 10 for period in PERIODS]
    common = math.lcm(*denominators)
    values = np.zeros_like(hits[2][:, 0, :], dtype=np.int64)
    for period, denominator in zip(PERIODS, denominators):
        values += (49 * hits[period][:, target % period, :].astype(np.int64) + 60) * (common // denominator)
    return values, 49 * 9 * common


def rank_paths(scores: np.ndarray, priority: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    paths = len(scores)
    sorted_indices = np.argsort(-scores[:, priority], axis=1, kind="stable")
    order = priority[sorted_indices]
    ranks = np.empty_like(order)
    positions = np.broadcast_to(np.arange(1, 50), (paths, 49))
    np.put_along_axis(ranks, order, positions, axis=1)
    sorted_scores = np.take_along_axis(scores, order, axis=1)
    starts = np.concatenate((np.ones((paths, 1), bool), np.diff(sorted_scores, axis=1) != 0), axis=1)
    ends = np.concatenate((starts[:, 1:], np.ones((paths, 1), bool)), axis=1)
    low = np.maximum.accumulate(np.where(starts, positions, 0), axis=1)
    high = np.minimum.accumulate(np.where(ends, positions, 50)[:, ::-1], axis=1)[:, ::-1]
    midranks = np.empty_like(scores, dtype=np.float64)
    np.put_along_axis(midranks, order, (low + high) / 2, axis=1)
    return order, ranks, midranks


def run_paths(masks: np.ndarray, *, retain_records: bool = False) -> dict:
    """Same batch implementation for observed history and every null history."""
    if masks.ndim != 3 or masks.shape[2] != 49 or not np.all(masks.sum(axis=2) == 6):
        raise ValueError("Expected whole six-subset histories")
    paths, draws, _ = masks.shape
    if retain_records and paths != 1:
        raise ValueError("Detailed records require exactly one history")
    if draws > 69:
        raise ValueError("This locked batch is restricted to the69-draw snapshot")
    phase_hits = {p: np.zeros((paths, p, 49), dtype=np.int16) for p in PERIODS}
    center_sum = np.zeros(paths)
    center_weight = 0.0
    tail_sum = np.zeros((paths, 10))
    tail_weight = 0.0
    center_decay = 2 ** (-1 / 5)
    tail_decay = 2 ** (-1 / 10)
    numbers = np.arange(1, 50)
    tails = numbers % 10
    tail_sizes = np.bincount(tails, minlength=10)
    tail_members = (tails[:, None] == np.arange(10)[None, :]).astype(np.int64)
    rngs = {model: random.Random(SEED) for model in MODEL_IDS if SPECS[model]["ties"] == "seeded_permutation"}
    aggregates = {model: {segment: {"draws": 0, "hits": np.zeros(paths, dtype=np.int16),
                   "rank_sum": np.zeros(paths, dtype=np.int32), "midrank_sum2": np.zeros(paths, dtype=np.int32)}
                   for segment in SEGMENTS} for model in MODEL_IDS}
    records = {model: [] for model in MODEL_IDS}
    for t in range(draws):
        current = masks[:, t, :]
        if t >= WARMUP:
            phase_scores, phase_denominator = resfold_keys(phase_hits, t)
            center = center_sum / center_weight
            distances = np.abs(numbers[None, :] - center[:, None])
            tail_density = tail_sum / tail_weight / tail_sizes[None, :]
            scores_by_model = {"SH-RESFOLD-v1": phase_scores,
                               "SH-CENTROID-v1": -distances,
                               "SH-TAIL-v1": tail_density[:, tails]}
            for model in MODEL_IDS:
                priority = list(range(49))
                if model in rngs:
                    rngs[model].shuffle(priority)
                order, ranks, midranks = rank_paths(scores_by_model[model], np.asarray(priority))
                hits_per_ticket = np.take_along_axis(current, order[:, :48], axis=1).reshape(paths, 8, 6).sum(axis=2)
                hit = np.any(hits_per_ticket >= 3, axis=1)
                rank_sum = (ranks * current).sum(axis=1)
                midrank_sum2 = np.rint((midranks * current).sum(axis=1) * 2).astype(np.int32)
                for segment, (start, end) in SEGMENTS.items():
                    if start <= t < end:
                        aggregate = aggregates[model][segment]
                        aggregate["draws"] += 1
                        aggregate["hits"] += hit
                        aggregate["rank_sum"] += rank_sum.astype(np.int32)
                        aggregate["midrank_sum2"] += midrank_sum2
                if retain_records:
                    values = scores_by_model[model][0]
                    record = {"index": t, "training_draws": t, "main": (np.flatnonzero(current[0]) + 1).tolist(),
                        "order": (order[0] + 1).tolist(), "ranks": ranks[0].tolist(), "score_midranks": midranks[0].tolist(),
                        "tickets": (order[0, :48] + 1).reshape(8, 6).tolist(), "excluded": int(order[0, -1] + 1),
                        "success": bool(hit[0]), "mean_main_rank": float(rank_sum[0] / 6),
                        "mean_main_midrank": float(midrank_sum2[0] / 12)}
                    if model == "SH-RESFOLD-v1":
                        record.update(score_keys=values.tolist(), score_common_denominator=phase_denominator,
                                      scores=(values / phase_denominator).tolist())
                    else:
                        record["scores"] = values.tolist()
                    if model == "SH-CENTROID-v1":
                        record["center"] = float(center[0])
                    records[model].append(record)
        # Only after predictions and scoring may the current main six enter state.
        for period in PERIODS:
            phase_hits[period][:, t % period, :] += current
        center_sum = center_decay * center_sum + current @ numbers / 6
        center_weight = center_decay * center_weight + 1
        tail_sum = tail_decay * tail_sum + current @ tail_members
        tail_weight = tail_decay * tail_weight + 1
    return {"aggregates": aggregates, "records": records}


def histogram(values: np.ndarray) -> dict[str, int]:
    distinct, counts = np.unique(values, return_counts=True)
    return {str(int(value)): int(count) for value, count in zip(distinct, counts)}


def summarize(observed: dict, null: dict) -> dict:
    result = {}
    for model in MODEL_IDS:
        result[model] = {}
        for segment in SEGMENTS:
            actual = observed["aggregates"][model][segment]
            simulated = null["aggregates"][model][segment]
            n = actual["draws"]
            if n == 0:
                continue
            hits = int(actual["hits"][0])
            ranks = int(actual["rank_sum"][0])
            midranks2 = int(actual["midrank_sum2"][0])
            draws = len(simulated["hits"])
            extreme_hits = int(np.count_nonzero(simulated["hits"] >= hits))
            extreme_rank = int(np.count_nonzero(simulated["rank_sum"] <= ranks))
            extreme_midrank = int(np.count_nonzero(simulated["midrank_sum2"] <= midranks2))
            p_hits = (extreme_hits + 1) / (draws + 1)
            p_rank = (extreme_rank + 1) / (draws + 1)
            result[model][segment] = {"draws": n, "successes": hits, "success_rate": hits / n,
                "main_rank_sum": ranks, "mean_main_rank": ranks / (6 * n),
                "main_midrank_sum2": midranks2, "mean_main_midrank": midranks2 / (12 * n),
                "MC_paths": draws, "p_hits_upper": p_hits, "p_rank_lower": p_rank,
                "p_midrank_lower": (extreme_midrank + 1) / (draws + 1),
                "p_hits_Bonferroni20": min(1.0, ATTEMPT_CAP * p_hits),
                "p_rank_Bonferroni20": min(1.0, ATTEMPT_CAP * p_rank),
                "extreme_hits": extreme_hits, "extreme_rank": extreme_rank, "extreme_midrank": extreme_midrank,
                "null_hits_histogram": histogram(simulated["hits"]),
                "null_rank_sum_histogram": histogram(simulated["rank_sum"]),
                "null_midrank_sum2_histogram": histogram(simulated["midrank_sum2"]),
                "null_mean_rank": float(np.mean(simulated["rank_sum"]) / (6 * n)),
                "null_success_rate": float(np.mean(simulated["hits"]) / n)}
    return result


def verify_lock(path: Path = LOCK_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    lock = json.loads(raw)
    if lock["models"] != SPECS or lock["conventions"] != CONVENTIONS or lock["data_sha256"] != DATA_SHA256:
        raise ValueError("Parameters differ from pre-run lock")
    if lock["implementation_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Implementation differs from pre-run lock")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "backtests/shadow-batch2-v1.json")
    args = parser.parse_args()
    lock, lock_hash = verify_lock()
    budget = attempt_budget()
    if not set(MODEL_IDS).issubset(budget["counted_model_ids"]):
        parser.error("Register all three candidates before execution")
    if args.output.exists():
        parser.error("Result already exists; do not overwrite or retune")
    started = datetime.now(timezone.utc).isoformat()
    draws = load_training()
    observed = run_paths(main_masks(draws), retain_records=True)
    print("Observed history evaluated once; simulating10000 complete fair histories.", flush=True)
    null_masks = fair_histories(MC_PATHS, len(draws))
    null_hash = hashlib.sha256(null_masks.tobytes()).hexdigest()
    null = run_paths(null_masks)
    summaries = summarize(observed, null)
    for model, records in observed["records"].items():
        for record in records:
            index = record["index"]
            record.update(target=draws[index].issue, through=draws[index - 1].issue,
                          date=draws[index].day.isoformat(), special_excluded=draws[index].special)
    result = {"audit": {"started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_sha256": DATA_SHA256, "lock_sha256": lock_hash,
            "implementation_sha256": lock["implementation_sha256"],
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "python": sys.version.split()[0], "numpy": np.__version__, "MC_paths": MC_PATHS,
            "MC_seed": SEED, "MC_whole_history_masks_sha256": null_hash,
            "MC_mask_hash_encoding": "bool C-order (path,69,49), one byte per value",
            "observed_history_runs_per_new_version": 1, "old_failures_rerun": False},
        "models": {model: {"specification": SPECS[model], "segments": summaries[model],
            "records": observed["records"][model],
            "status": "disabled" if summaries[model]["26096_26115"]["successes"] < 9 else "screening_only_not_confirmed"}
            for model in MODEL_IDS}, "attempt_budget": budget,
        "comparison": {"fair_q_exact": "12344/83237", "fair_success_rate": 12344 / 83237,
            "fair_mean_rank": 25, "FixedBlocks_E20_successes": 8, "window_draws": 20},
        "evidence": "Exploratory only; MC p-values do not repair already-viewed window selection. No forward pass, no H3 change.",
        "mechanism_warning": "SH-TAIL-v1：無物理機制"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(result))
    print(canonical_json({model: {key: summaries[model]["26096_26115"][key]
            for key in ("successes", "mean_main_rank", "mean_main_midrank", "p_hits_upper", "p_rank_lower")}
            for model in MODEL_IDS}), end="")


if __name__ == "__main__":
    main()
