"""Pre-registered warmup gates and conditional DISPREG/COMPREV backtests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess

import numpy as np

from marksix_r2 import DATA_SHA256, ROOT, canonical_json, load_training
import marksix_shadow_batch2 as common

SEED = 20261029
PERMUTATIONS = 10000
MODELS = ("SH-DISPREG-v1", "SH-COMPREV-v1")
LOCK_PATH = ROOT / "archive/shadow-gates-v1.lock.json"
GATE_PATH = ROOT / "backtests/shadow-gates-v1.json"
SPECS = {
    "SH-DISPREG-v1": {"D": "sample standard deviation of main six,ddof1", "W": 20,
        "gate": "Pearson(D[0:19],D[1:20])>0 and upper-tail permutation p<0.20",
        "half_life": 3, "regime": "normalized EWM of past D < median(all past D) =>cluster; otherwise dispersed",
        "cluster": "1-6,7-12,...,43-48", "dispersed": "{k,k+8,k+16,k+24,k+32,k+40},k1..8",
        "rank_metric": None, "M_bar": "mean maximum main hits among eight tickets",
        "description_gate": "cluster fraction>0.5 in primary or full49 =>descriptive only"},
    "SH-COMPREV-v1": {"W": 20, "rho": 0.5, "cells": "1-24 odd/even;25-49 odd/even; sizes12,12,13,12",
        "gate": "r_odd<0 AND r_high<0 AND lower-tail permutation p(S=r_odd+r_high)<0.20",
        "prediction": "e_c=6*size/49;pred_c=e_c-0.5*(previous_count-e_c);score=pred_c/size;do not clip",
        "ties": "seeded_permutation20261029", "rank_metric": "exact-score midrank; actual cut-order also saved",
        "M_bar": "mean maximum main hits among eight tickets"},
}
CONVENTIONS = {
    "gate_data": "only first20 draws26/047-066;19 adjacent pairs; no later outcomes",
    "correlation": "Pearson with separate lag-side means; constant lag vector=>r0 and gate cannot pass",
    "permutations": "10000 full20-row permutations from NumPy default_rng20261029; same row indices for D and paired odd/high series",
    "p": "(1+count upper D r or lower paired S at least as extreme)/10001; strict gate inequalities",
    "warmup": 20, "sample_start": "26/047", "main_only": True,
    "candidate_MC": "only passed versions;10000 complete69-draw fair histories, same engine; whole-history refit; unconditional fixed-model exploratory p",
    "tickets": "eight disjoint six-subsets covering1-48;49 excluded for DISPREG; COMPREV top48 sorted-score positions",
    "random_ties": "COMPREV independent Python Random20261029; shuffle49 once per eligible target, no warmup draws; exact rational integer score keys",
    "EWM": "normalized full expanding history; initial numerator/weight0; predict before current update; equality with median=>dispersed",
    "M": "M_t=max main hits among8 tickets;M_bar=sum(M_t)/n;M-upper-tail MC; supplementary, no old criteria changes",
    "COMPREV_rank": "midranks are primary; equally-scored cells share midrank; actual seed-cut ranking separate",
    "failed_gate": "withdraw;no candidate historical run, no attempt count; gate record ID uses GATE- prefix",
    "screen": "no new OR/rank promotion rule inferred; historical results descriptive; <9/20 disables; no forward claim",
}


def lag_pearson(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    left = values[..., :-1]
    right = values[..., 1:]
    left = left - left.mean(axis=-1, keepdims=True)
    right = right - right.mean(axis=-1, keepdims=True)
    denominator = np.sqrt(np.sum(left * left, axis=-1) * np.sum(right * right, axis=-1))
    return np.divide(np.sum(left * right, axis=-1), denominator,
                     out=np.zeros_like(denominator), where=denominator > 0)


def gate_test(warmup: np.ndarray) -> dict:
    if warmup.shape != (20, 49) or not np.all(warmup.sum(axis=1) == 6):
        raise ValueError("Exactly20 warmup six-subsets required")
    numbers = np.arange(1, 50)
    six = np.sort(np.where(warmup, numbers, 50), axis=1)[:, :6]
    D = six.std(axis=1, ddof=1)
    odd = warmup[:, numbers % 2 == 1].sum(axis=1)
    high = warmup[:, numbers >= 25].sum(axis=1)
    rng = np.random.default_rng(SEED)
    indices = np.stack([rng.permutation(20) for _ in range(PERMUTATIONS)])
    perm_D = lag_pearson(D[indices])
    perm_odd = lag_pearson(odd[indices])
    perm_high = lag_pearson(high[indices])
    rD, rO, rH = (float(lag_pearson(x)) for x in (D, odd, high))
    S = rO + rH
    perm_S = perm_odd + perm_high
    extreme_D = int(np.count_nonzero(perm_D >= rD))
    extreme_S = int(np.count_nonzero(perm_S <= S))
    pD, pS = (extreme_D + 1) / 10001, (extreme_S + 1) / 10001
    return {"warmup": {"first_draw": "26/047", "last_draw": "26/066", "draws": 20, "pairs": 19,
                       "D_sample_std": D.tolist(), "odd_counts": odd.tolist(), "high_counts": high.tolist()},
        "permutations": 10000, "seed": SEED,
        "permutation_indices_sha256": hashlib.sha256(indices.astype('<i2').tobytes()).hexdigest(),
        "models": {"SH-DISPREG-v1": {"r1": rD, "p_upper": pD, "extreme": extreme_D,
            "passed": rD > 0 and pD < 0.20},
            "SH-COMPREV-v1": {"r_odd": rO, "r_high": rH, "S": S, "p_lower": pS,
            "extreme": extreme_S, "passed": rO < 0 and rH < 0 and pS < 0.20}},
        "permutation_statistics": {"D_r": perm_D.tolist(), "paired_S": perm_S.tolist()},
        "evidence": "warmup-only exploratory gate; failures withdrawn, not a model attempt"}


def run_paths(masks: np.ndarray, allowed: tuple[str, ...], retain_records: bool = False) -> dict:
    if not set(allowed).issubset(MODELS) or not allowed:
        raise ValueError("Only explicitly passed candidates may be run")
    if masks.ndim != 3 or masks.shape[2] != 49 or not np.all(masks.sum(axis=2) == 6):
        raise ValueError("Whole six-subsets required")
    paths, draws, _ = masks.shape
    if draws > 69 or (retain_records and paths != 1):
        raise ValueError("At most69 draws; one path for records")
    numbers = np.arange(1, 50)
    cells = (numbers >= 25).astype(int) * 2 + (numbers % 2 == 0).astype(int)
    members = (cells[:, None] == np.arange(4)).astype(int)
    sizes = members.sum(axis=0)
    all_six = np.sort(np.where(masks, numbers, 50), axis=2)[:, :, :6]
    deviations = all_six.std(axis=2, ddof=1)
    D_sum = np.zeros(paths)
    D_weight = 0.0
    decay = 2 ** (-1 / 3)
    clustered_tickets = np.arange(48).reshape(8, 6)
    dispersed_tickets = np.arange(48).reshape(6, 8).T
    rng = random.Random(SEED)
    aggregates = {model: {segment: {"draws": 0, **{key: np.zeros(paths, np.int32) for key in
        ("hits", "M_sum", "rank_sum2", "actual_rank_sum", "clustered", "dispersed", "dispersed_hits", "fixed_dispersed_hits")}}
        for segment in common.SEGMENTS} for model in allowed}
    records = {model: [] for model in allowed}
    for t in range(draws):
        current = masks[:, t, :]
        fixed_M = current[:, :48].reshape(paths, 8, 6).sum(axis=2).max(axis=1)
        if t >= 20:
            for model in allowed:
                if model == "SH-DISPREG-v1":
                    median = np.median(deviations[:, :t], axis=1)
                    ewm = D_sum / D_weight
                    cluster = ewm < median
                    tickets = np.where(cluster[:, None, None], clustered_tickets, dispersed_tickets)
                    M = np.take_along_axis(current, tickets.reshape(paths, 48), axis=1).reshape(paths, 8, 6).sum(axis=2).max(axis=1)
                    rank_sum2 = actual_rank_sum = np.zeros(paths, np.int32)
                else:
                    counts = masks[:, t - 1, :] @ members
                    cell_keys = (18 * sizes[None, :] - 49 * counts) * (156 // sizes[None, :])
                    keys = cell_keys[:, cells]
                    priority = list(range(49)); rng.shuffle(priority)
                    order, ranks, midranks = common.rank_paths(keys, np.asarray(priority))
                    tickets = order[:, :48].reshape(paths, 8, 6)
                    M = np.take_along_axis(current, order[:, :48], axis=1).reshape(paths, 8, 6).sum(axis=2).max(axis=1)
                    rank_sum2 = np.rint((midranks * current).sum(axis=1) * 2).astype(np.int32)
                    actual_rank_sum = (ranks * current).sum(axis=1).astype(np.int32)
                    cluster = np.zeros(paths, bool)
                hit = M >= 3
                for segment, (start, end) in common.SEGMENTS.items():
                    if start <= t < end:
                        a = aggregates[model][segment]; a["draws"] += 1
                        for key, value in (("hits", hit), ("M_sum", M), ("rank_sum2", rank_sum2),
                            ("actual_rank_sum", actual_rank_sum), ("clustered", cluster)):
                            a[key] += value.astype(np.int32)
                        if model == "SH-DISPREG-v1":
                            a["dispersed"] += ~cluster
                            a["dispersed_hits"] += (~cluster) & hit
                            a["fixed_dispersed_hits"] += (~cluster) & (fixed_M >= 3)
                if retain_records:
                    rec = {"index": t, "training_draws": t, "main": (np.flatnonzero(current[0]) + 1).tolist(),
                        "tickets": (tickets[0] + 1).tolist(), "M": int(M[0]), "success": bool(hit[0])}
                    if model == "SH-DISPREG-v1":
                        rec.update(regime="clustered" if cluster[0] else "dispersed", EWM_D=float(ewm[0]),
                                   historical_median_D=float(median[0]), fixed_M=int(fixed_M[0]), mean_main_rank=None)
                    else:
                        rec.update(score_keys=keys[0].tolist(), score_denominator=98 * 156,
                            order=(order[0] + 1).tolist(), ranks=ranks[0].tolist(), score_midranks=midranks[0].tolist(),
                            mean_main_rank=float(rank_sum2[0] / 12), actual_mean_main_rank=float(actual_rank_sum[0] / 6))
                    records[model].append(rec)
        D_sum = decay * D_sum + deviations[:, t]
        D_weight = decay * D_weight + 1
    return {"aggregates": aggregates, "records": records}


def summaries(observed: dict, null: dict) -> dict:
    result = {}
    for model, segments in observed["aggregates"].items():
        result[model] = {}
        for segment, a in segments.items():
            b = null["aggregates"][model][segment]; n = a["draws"]
            if not n: continue
            values = {key: int(value[0]) for key, value in a.items() if key != "draws"}
            values.update(draws=n, mean_M=values["M_sum"] / n,
                mean_main_rank=values["rank_sum2"] / (12 * n) if model == "SH-COMPREV-v1" else None,
                actual_mean_main_rank=values["actual_rank_sum"] / (6 * n) if model == "SH-COMPREV-v1" else None,
                clustered_fraction=values["clustered"] / n, MC_paths=len(b["hits"]))
            for statistic, direction in (("hits", "upper"), ("M_sum", "upper"), ("rank_sum2", "lower")):
                if statistic == "rank_sum2" and model == "SH-DISPREG-v1": continue
                extreme = np.count_nonzero(b[statistic] >= values[statistic] if direction == "upper" else b[statistic] <= values[statistic])
                values["p_" + statistic] = (int(extreme) + 1) / (len(b[statistic]) + 1)
                values["null_" + statistic + "_histogram"] = common.histogram(b[statistic])
            result[model][segment] = values
    return result


def verify_lock(path: Path = LOCK_PATH) -> tuple[dict, str]:
    raw = path.read_bytes(); lock = json.loads(raw)
    if lock["models"] != SPECS or lock["conventions"] != CONVENTIONS or lock["data_sha256"] != DATA_SHA256:
        raise ValueError("Gate/model parameters changed after lock")
    if lock["implementation_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Gate implementation changed after lock")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("gates", "backtest"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    lock, lock_hash = verify_lock()
    draws = load_training()
    masks = common.main_masks(draws)
    path = args.output or (GATE_PATH if args.command == "gates" else ROOT / "backtests/shadow-gated-backtests-v1.json")
    if path.exists(): parser.error("Result exists; do not overwrite or rerun")
    started = datetime.now(timezone.utc).isoformat()
    if args.command == "gates":
        result = gate_test(masks[0, :20])
    else:
        gates = json.loads(GATE_PATH.read_bytes())
        allowed = tuple(model for model in MODELS if gates["models"][model]["passed"])
        if not allowed: parser.error("Both gates failed; no candidate backtest or MC is authorized")
        budget = common.attempt_budget()
        if not set(allowed).issubset(budget["counted_model_ids"]):
            parser.error("Register passed candidates before running historical backtests")
        observed = run_paths(masks, allowed, True)
        null = run_paths(common.fair_histories(10000, len(draws)), allowed)
        stats = summaries(observed, null)
        for records in observed["records"].values():
            for rec in records:
                t = rec["index"]; rec.update(target=draws[t].issue, through=draws[t - 1].issue)
        result = {"models": {m: {"segments": stats[m], "records": observed["records"][m],
            "status": "disabled" if stats[m]["26096_26115"]["hits"] < 9 else "exploratory_only",
            "descriptive_only_cluster_majority": m == "SH-DISPREG-v1" and any(stats[m][s]["clustered_fraction"] > 0.5 for s in ("26096_26115", "26067_26115"))}
            for m in allowed}, "gate_result_sha256": hashlib.sha256(GATE_PATH.read_bytes()).hexdigest(), "attempt_budget": budget}
    result["audit"] = {"started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_sha256": DATA_SHA256, "lock_sha256": lock_hash, "implementation_sha256": lock["implementation_sha256"],
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream: stream.write(canonical_json(result))
    print(canonical_json(result["models"] if args.command == "gates" else {m: e["segments"]["26096_26115"] for m, e in result["models"].items()}), end="")


if __name__ == "__main__": main()
