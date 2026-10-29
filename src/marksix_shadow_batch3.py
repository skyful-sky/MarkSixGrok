"""Locked ORDSTAT/BLOCKX exploration; cumulative conservative Holm bounds."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

import numpy as np

from marksix_r2 import DATA_SHA256, ROOT, canonical_json, load_training
import marksix_shadow_batch2 as common

SEED = 20261029
MC_PATHS = 10000
MODEL_IDS = ("SH-ORDSTAT-v1", "SH-BLOCKX-v1")
SEGMENTS = common.SEGMENTS
LOCK_PATH = ROOT / "archive/shadow-batch3-v1.lock.json"
PREREQUISITE_PATH = ROOT / "backtests/shadow-batch2-v1.json"
SPECS = {
    "SH-ORDSTAT-v1": {"half_life": 10, "W": 20,
        "score": "negative distance to nearest of six normalized EWM historical order-statistic locations",
        "ties": "smaller_number_first", "excluded": "rank_position49"},
    "SH-BLOCKX-v1": {"half_life": 20, "W": 20, "seed": SEED,
        "excluded": "one minimum-EWM-frequency number, seeded tie break",
        "partition": "sort remaining48 numerically; consecutive groups of6",
        "order": "block total EWM frequency descending; within block number ascending",
        "block_ties": "seeded priority over eight ascending base-block indices",
        "prerequisite": "saved CENTROID067-115 actual-order mean rank<25",
        "overlap": "exact equality of unordered sets of eight tickets; ignore ticket order",
        "description_gate": "if overlap fraction>0.5 in096-115 OR full067-115, descriptive only, no screening qualification"},
}
CONVENTIONS = {
    "EWM": "normalized expanding weighted history, initial numerator/weight0; relative prior age0; predict then update",
    "warmup": "20 observed draws047-066; score067-115; report067-095,096-115,full49",
    "ORDSTAT": "sort each past main six separately before EWM by position; no fitting or search across k",
    "BLOCKX_seed": "one independent random.Random(20261029); per eligible target shuffle1..49 for min-frequency ties, then shuffle base-block indices0..7 for block-total ties; no warmup RNG consumption",
    "BLOCKX_overlap_gate": "report all segments;096-115 or full49 overlap>50% blocks screening; equality50% does not trigger this clause",
    "rank": "actual complete ticket-order positions1..49; BLOCKX includes block order and within-block numeric order",
    "success": ">=one ticket containing>=3 main numbers, at most once per draw; special ignored",
    "numeric": "float64; no post-result rounding or distance/frequency tie tolerance",
    "MC": "10000 independent complete69-draw uniform6-subset histories; same observed/null engine and fixed seeded tie priorities",
    "MC_seed": 20261029,
    "MC_p": "plus-one hits upper tail and actual-rank-sum lower tail, separately for each segment",
    "Holm": "each segment/statistic family includes all13 cumulative known models; use existing batch2 MC p and current2 p; missing old MC p remains null, substituted1 only for conservative Holm upper bounds; no old observed reruns",
    "inference": "descriptive only; neither MC nor cumulative Holm repairs already-viewed data or same-data prerequisite selection; no cross-endpoint/segment alpha claim",
    "budget": "unique registered same-window models, legacy fixed/24 included; aliases merged; maximum20; this batch13/20",
    "screen": "096-115 hits<9 disables; >=9 only screening, subject to BLOCKX overlap gate; no retuning or forward authorization",
}


def prerequisite(path: Path = PREREQUISITE_PATH) -> dict:
    raw = path.read_bytes()
    data = json.loads(raw)
    summary = data["models"]["SH-CENTROID-v1"]["segments"]["26067_26115"]
    if summary["draws"] != 49 or summary["mean_main_rank"] >= 25:
        raise ValueError("BLOCKX prerequisite failed; withdraw before registering/executing it")
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "sha256": hashlib.sha256(raw).hexdigest(), "draws": 49,
            "mean_main_rank": summary["mean_main_rank"], "p_rank_lower": summary["p_rank_lower"],
            "passed": True, "evidence": "gate barely passed; no predictive confirmation"}


def holm_bounds(known: dict[str, float], family: list[str]) -> dict:
    if len(set(family)) != len(family) or set(known) - set(family):
        raise ValueError("Invalid cumulative Holm family")
    if any(not 0 <= value <= 1 for value in known.values()):
        raise ValueError("Invalid p-value")
    substituted = {model: known.get(model, 1.0) for model in family}
    order = sorted(family, key=lambda model: (substituted[model], model))
    adjusted = {}
    running = 0.0
    for index, model in enumerate(order):
        running = max(running, min(1.0, (len(family) - index) * substituted[model]))
        adjusted[model] = running
    return {"family_size": len(family), "family_ids": family,
            "missing_raw_p_ids": [model for model in family if model not in known],
            "raw_p": {model: known.get(model) for model in family},
            "substitution_for_upper_bound_only": 1,
            "adjusted_upper_bounds": adjusted,
            "label": "conservative Holm upper bounds; missing p not measured or claimed equal to1"}


def blockx_order(frequencies: np.ndarray, number_priority: np.ndarray,
                 block_priority: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    paths = len(frequencies)
    excluded = number_priority[np.argmin(frequencies[:, number_priority], axis=1)]
    numbers = np.broadcast_to(np.arange(49), (paths, 49))
    base_blocks = numbers[numbers != excluded[:, None]].reshape(paths, 8, 6)
    totals = np.take_along_axis(frequencies, base_blocks.reshape(paths, 48), axis=1).reshape(paths, 8, 6).sum(axis=2)
    relative = np.argsort(-totals[:, block_priority], axis=1, kind="stable")
    sorted_indices = block_priority[relative]
    blocks = np.take_along_axis(base_blocks, sorted_indices[:, :, None], axis=1)
    order = np.concatenate((blocks.reshape(paths, 48), excluded[:, None]), axis=1)
    sorted_totals = np.take_along_axis(totals, sorted_indices, axis=1)
    identical = np.all(base_blocks == np.arange(48).reshape(1, 8, 6), axis=(1, 2))
    return order, sorted_totals, identical


def ranks_from_order(order: np.ndarray) -> np.ndarray:
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.broadcast_to(np.arange(1, 50), order.shape), axis=1)
    return ranks


def run_paths(masks: np.ndarray, *, retain_records: bool = False) -> dict:
    if masks.ndim != 3 or masks.shape[2] != 49 or not np.all(masks.sum(axis=2) == 6):
        raise ValueError("Expected whole six-subset histories")
    paths, draws, _ = masks.shape
    if draws > 69 or (retain_records and paths != 1):
        raise ValueError("At most69 draws; records require one path")
    locations_sum = np.zeros((paths, 6))
    locations_weight = 0.0
    frequency_sum = np.zeros((paths, 49))
    frequency_weight = 0.0
    order_decay = 2 ** (-1 / 10)
    frequency_decay = 2 ** (-1 / 20)
    numbers = np.arange(1, 50)
    rng = random.Random(SEED)
    aggregates = {model: {segment: {"draws": 0, "hits": np.zeros(paths, np.int16),
                   "rank_sum": np.zeros(paths, np.int32), "fixed_identical": np.zeros(paths, np.int16)}
                   for segment in SEGMENTS} for model in MODEL_IDS}
    records = {model: [] for model in MODEL_IDS}
    for t in range(draws):
        current = masks[:, t, :]
        if t >= 20:
            locations = locations_sum / locations_weight
            distances = np.min(np.abs(numbers[None, :, None] - locations[:, None, :]), axis=2)
            ord_order, ord_ranks, _ = common.rank_paths(-distances, np.arange(49))
            frequencies = frequency_sum / frequency_weight
            number_priority = list(range(49))
            block_priority = list(range(8))
            rng.shuffle(number_priority)
            rng.shuffle(block_priority)
            bx_order, totals, bx_identical = blockx_order(frequencies, np.asarray(number_priority), np.asarray(block_priority))
            orders = {"SH-ORDSTAT-v1": ord_order, "SH-BLOCKX-v1": bx_order}
            for model in MODEL_IDS:
                order = orders[model]
                ranks = ord_ranks if model == "SH-ORDSTAT-v1" else ranks_from_order(order)
                hits = np.take_along_axis(current, order[:, :48], axis=1).reshape(paths, 8, 6).sum(axis=2)
                success = np.any(hits >= 3, axis=1)
                rank_sum = (ranks * current).sum(axis=1).astype(np.int32)
                if model == "SH-BLOCKX-v1":
                    identical = bx_identical
                else:
                    ascending_tickets = np.sort(order[:, :48].reshape(paths, 8, 6), axis=2)
                    # Disjoint tickets equal fixed blocks iff every ticket spans
                    # exactly its canonical block, with all eight blocks present.
                    block_index = ascending_tickets[:, :, 0] // 6
                    valid = np.all(ascending_tickets == 6 * block_index[:, :, None] + np.arange(6), axis=2)
                    identical = np.all(valid, axis=1) & (order[:, -1] == 48)
                for segment, (start, end) in SEGMENTS.items():
                    if start <= t < end:
                        a = aggregates[model][segment]
                        a["draws"] += 1
                        a["hits"] += success
                        a["rank_sum"] += rank_sum
                        a["fixed_identical"] += identical
                if retain_records:
                    record = {"index": t, "training_draws": t, "main": (np.flatnonzero(current[0]) + 1).tolist(),
                        "order": (order[0] + 1).tolist(), "ranks": ranks[0].tolist(),
                        "tickets": (order[0, :48] + 1).reshape(8, 6).tolist(), "excluded": int(order[0, -1] + 1),
                        "success": bool(success[0]), "mean_main_rank": float(rank_sum[0] / 6),
                        "fixedblocks_tickets_identical": bool(identical[0])}
                    if model == "SH-ORDSTAT-v1":
                        record.update(ewm_locations=locations[0].tolist(), distances=distances[0].tolist())
                    else:
                        record.update(frequencies=frequencies[0].tolist(), ordered_block_totals=totals[0].tolist())
                    records[model].append(record)
        sorted_six = np.sort(np.where(current, numbers[None, :], 50), axis=1)[:, :6]
        locations_sum = order_decay * locations_sum + sorted_six
        locations_weight = order_decay * locations_weight + 1
        frequency_sum = frequency_decay * frequency_sum + current
        frequency_weight = frequency_decay * frequency_weight + 1
    return {"aggregates": aggregates, "records": records}


def summaries(observed: dict, null: dict) -> dict:
    result = {model: {} for model in MODEL_IDS}
    for model in MODEL_IDS:
        for segment in SEGMENTS:
            a = observed["aggregates"][model][segment]
            b = null["aggregates"][model][segment]
            n = a["draws"]
            if not n:
                continue
            hits, rank_sum, overlap = (int(a[key][0]) for key in ("hits", "rank_sum", "fixed_identical"))
            trials = len(b["hits"])
            eh = int(np.count_nonzero(b["hits"] >= hits))
            er = int(np.count_nonzero(b["rank_sum"] <= rank_sum))
            result[model][segment] = {"draws": n, "successes": hits, "success_rate": hits / n,
                "main_rank_sum": rank_sum, "mean_main_rank": rank_sum / (6 * n),
                "fixedblocks_identical_draws": overlap, "fixedblocks_identical_fraction": overlap / n,
                "MC_paths": trials, "p_hits_upper": (eh + 1) / (trials + 1),
                "p_rank_lower": (er + 1) / (trials + 1), "extreme_hits": eh, "extreme_rank": er,
                "null_hits_histogram": common.histogram(b["hits"]),
                "null_rank_sum_histogram": common.histogram(b["rank_sum"]),
                "null_mean_rank": float(np.mean(b["rank_sum"]) / (6 * n)),
                "null_success_rate": float(np.mean(b["hits"]) / n)}
    return result


def model_status(model: str, segments: dict) -> str:
    if segments["26096_26115"]["successes"] < 9:
        return "disabled"
    if model == "SH-BLOCKX-v1" and any(segments[s]["fixedblocks_identical_fraction"] > 0.5
                                       for s in ("26096_26115", "26067_26115")):
        return "descriptive_only_high_fixedblocks_overlap"
    return "screening_only_not_confirmed"


def cumulative_holm(summary: dict, old: dict, family: list[str]) -> dict:
    result = {}
    for segment in SEGMENTS:
        result[segment] = {}
        for key in ("p_hits_upper", "p_rank_lower"):
            known = {model: entry["segments"][segment][key] for model, entry in old["models"].items()}
            known.update({model: summary[model][segment][key] for model in MODEL_IDS})
            result[segment][key] = holm_bounds(known, family)
            for model in MODEL_IDS:
                summary[model][segment][key + "_Holm13_upper"] = result[segment][key]["adjusted_upper_bounds"][model]
    return result


def verify_lock(path: Path = LOCK_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    lock = json.loads(raw)
    if lock["models"] != SPECS or lock["conventions"] != CONVENTIONS or lock["data_sha256"] != DATA_SHA256:
        raise ValueError("Parameters differ from pre-run lock")
    if lock["implementation_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Implementation changed after lock")
    if lock["batch2_dependency_sha256"] != hashlib.sha256(Path(common.__file__).read_bytes()).hexdigest():
        raise ValueError("MC utility dependency changed after lock")
    if lock["prerequisite"] != prerequisite():
        raise ValueError("BLOCKX prerequisite source changed after lock")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "backtests/shadow-batch3-v1.json")
    args = parser.parse_args()
    lock, lock_hash = verify_lock()
    budget = common.attempt_budget()
    if budget["used"] != 13 or not set(MODEL_IDS).issubset(budget["counted_model_ids"]):
        parser.error("Both candidates must be registered in the13-model cumulative family")
    if args.output.exists():
        parser.error("Result already exists; do not overwrite or retune")
    started = datetime.now(timezone.utc).isoformat()
    draws = load_training()
    observed = run_paths(common.main_masks(draws), retain_records=True)
    print("Observed two candidates evaluated once; simulating10000 complete fair histories.", flush=True)
    null_masks = common.fair_histories(MC_PATHS, len(draws))
    null_hash = hashlib.sha256(null_masks.tobytes()).hexdigest()
    null = run_paths(null_masks)
    summary = summaries(observed, null)
    old = json.loads(PREREQUISITE_PATH.read_bytes())
    holm = cumulative_holm(summary, old, budget["counted_model_ids"])
    for records in observed["records"].values():
        for record in records:
            t = record["index"]
            record.update(target=draws[t].issue, through=draws[t - 1].issue, date=draws[t].day.isoformat(),
                          special_excluded=draws[t].special)
    result = {"audit": {"started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "implementation_sha256": lock["implementation_sha256"], "lock_sha256": lock_hash,
            "data_sha256": DATA_SHA256, "MC_paths": MC_PATHS, "MC_seed": SEED,
            "MC_whole_history_masks_sha256": null_hash, "python": sys.version.split()[0], "numpy": np.__version__,
            "observed_runs_per_new_version": 1, "old_observed_models_rerun": False},
        "models": {model: {"specification": SPECS[model], "segments": summary[model],
            "records": observed["records"][model], "status": model_status(model, summary[model]),
            "overlap_descriptive_only": model == "SH-BLOCKX-v1" and any(summary[model][s]["fixedblocks_identical_fraction"] > 0.5
                for s in ("26096_26115", "26067_26115"))} for model in MODEL_IDS},
        "cumulative_holm": holm, "attempt_budget": budget, "BLOCKX_prerequisite": lock["prerequisite"],
        "comparison": {"fair_q_exact": "12344/83237", "fair_mean_rank": 25, "FixedBlocks_E20": "8/20"},
        "evidence": "Exploratory only;13-model Holm upper bounds do not fix historical selection; no forward confirmation or formal changes."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(result))
    print(canonical_json({model: {key: summary[model]["26096_26115"][key]
        for key in ("successes", "mean_main_rank", "p_hits_upper", "p_rank_lower", "fixedblocks_identical_fraction")}
        for model in MODEL_IDS}), end="")


if __name__ == "__main__":
    main()
