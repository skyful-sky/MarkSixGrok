"""Locked external k-of-N audit; no tickets, predictions, EV fit or HK input.

Only --run operates on the real allowlisted discovery snapshots. Unit tests use
small synthetic arrays. A real run is exclusive, records failure, and cannot be
resumed or repeated by this program.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from math import comb, sqrt
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy.stats import beta


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/AUD-SERIAL-K6-v1"
KEYS = ("marginal_ssq", "pair_deviation", "serial_overlap")
NAMES = ("marginal_chi_square", "pair_max_absolute_z", "positive_serial_overlap")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def ledger_append(path, payload):
    previous = None
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            record = json.loads(line)
            digest = record.pop("record_sha256")
            if (record["previous_sha256"] != previous or
                    hashlib.sha256(canonical(record)).hexdigest() != digest):
                raise ValueError("Broken append-only audit ledger")
            previous = digest
    record = {"previous_sha256": previous, "payload": payload}
    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(canonical(record).decode() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record["record_sha256"]


def uniform_sets(rng, shape, pool, k=6):
    """Vectorized Floyd sampler: exact uniform unordered k-subsets, zero based.

    In iteration j, replace an already selected candidate by j; j cannot have
    appeared in earlier iterations. Sorting discards construction order.
    """
    if not 0 <= k <= pool <= 255:
        raise ValueError("Invalid sampling matrix")
    result = np.empty((*shape, k), dtype=np.uint8)
    for column, j in enumerate(range(pool - k, pool)):
        candidate = rng.integers(0, j + 1, size=shape, dtype=np.int16)
        collision = np.any(result[..., :column] == candidate[..., None], axis=-1)
        result[..., column] = np.where(collision, j, candidate)
    result.sort(axis=-1)
    return result


def simulate_series(rng, reps, periods, pool, family="uniform", strength=1.0):
    """Artificial complete-six set series; strength is not a fitted parameter."""
    if family == "uniform":
        return uniform_sets(rng, (reps, periods), pool)
    if family == "weighted_set":
        masses = np.array([comb(6, m) * comb(pool - 6, 6 - m) * strength ** m
                           for m in range(7)], dtype=float)
        counts = np.searchsorted(np.cumsum(masses / masses.sum()),
                                 rng.random((reps, periods)), side="right")
        result = np.empty((reps * periods, 6), dtype=np.uint8)
        for m in range(7):
            indices = np.flatnonzero(counts.ravel() == m)
            if len(indices):
                a = uniform_sets(rng, (len(indices),), 6, m)
                b = uniform_sets(rng, (len(indices),), pool - 6, 6 - m) + 6
                result[indices] = np.concatenate((a, b), axis=-1)
        return result.reshape(reps, periods, 6)
    if family == "cyclic_cluster":
        result = uniform_sets(rng, (reps, periods), pool)
        use = rng.random((reps, periods)) < strength
        starts = rng.integers(0, pool, size=(reps, periods), dtype=np.int16)
        cluster = ((starts[..., None] + np.arange(6)) % pool).astype(np.uint8)
        cluster.sort(axis=-1)
        return np.where(use[..., None], cluster, result)
    if family == "serial_copy_one":
        result = uniform_sets(rng, (reps, periods), pool)
        for t in range(1, periods):
            use = rng.random(reps) < strength
            slot = rng.integers(0, 6, size=reps)
            kept = result[np.arange(reps), t - 1, slot]
            other = uniform_sets(rng, (reps,), pool - 1, 5)
            other += (other >= kept[:, None]).astype(np.uint8)
            copied = np.concatenate((kept[:, None], other), axis=-1)
            copied.sort(axis=-1)
            result[:, t] = np.where(use[:, None], copied, result[:, t])
        return result
    raise ValueError("Unknown synthetic family")


def validate_sets(draws, pool):
    a = np.asarray(draws)
    if (a.ndim != 3 or a.shape[-1] != 6 or not np.issubdtype(a.dtype, np.integer)
            or np.any(a < 0) or np.any(a >= pool)
            or np.any(np.diff(a.astype(np.int16), axis=-1) <= 0)):
        raise ValueError("Need ascending, distinct, in-range complete-six draws")


def statistic_keys(draws, pool, warmup=200, include_counts=False):
    """Integer keys preserve exact MC ties; each comparison is an upper tail."""
    draws = np.asarray(draws)
    if draws.ndim != 3 or draws.shape[-1] != 6 or not 1 <= warmup < draws.shape[1]:
        raise ValueError("Need one predecessor and a nonempty score window")
    score = draws[:, warmup:]
    reps, n, _ = score.shape
    offsets = np.arange(reps, dtype=np.int64)
    ids = score.astype(np.int64) + offsets[:, None, None] * pool
    marginal = np.bincount(ids.ravel(), minlength=reps * pool).reshape(reps, pool)
    left, right = np.triu_indices(6, 1)
    a = score[:, :, left].astype(np.int64)
    b = score[:, :, right].astype(np.int64)
    pair_ids = a * (2 * pool - a - 1) // 2 + b - a - 1
    pair_total = comb(pool, 2)
    pair_ids += offsets[:, None, None] * pair_total
    pairs = np.bincount(pair_ids.ravel(), minlength=reps * pair_total)
    pairs = pairs.reshape(reps, pair_total)
    previous = draws[:, warmup - 1:-1]
    overlap = (score[..., :, None] == previous[..., None, :]).sum(axis=(1, 2, 3))
    values = {
        "marginal_ssq": (marginal * marginal).sum(axis=1),
        "pair_deviation": np.abs(pairs * (pool * (pool - 1)) - 30 * n).max(axis=1),
        "serial_overlap": overlap.astype(np.int64),
    }
    if include_counts:
        return values, marginal, pairs
    return values


def displayed_statistics(keys, pool, n):
    p2 = 30 / (pool * (pool - 1))
    return {
        NAMES[0]: pool * int(keys[KEYS[0]]) / (6 * n) - 6 * n,
        NAMES[1]: int(keys[KEYS[1]]) / (pool * (pool - 1) * sqrt(n * p2 * (1 - p2))),
        NAMES[2]: int(keys[KEYS[2]]),
    }


def monte_carlo_p(sorted_null, observed):
    values = np.asarray(observed)
    extreme = len(sorted_null) - np.searchsorted(sorted_null, values, side="left")
    return (extreme + 1) / (len(sorted_null) + 1)


def rejection_mask(sorted_null, observed):
    extreme = len(sorted_null) - np.searchsorted(sorted_null, observed, side="left")
    # Exact alpha=.0125/9=1/720, including ties and the +1 MC correction.
    return (extreme + 1) * 720 <= len(sorted_null) + 1


def binomial_summary(successes, n):
    lo = 0.0 if successes == 0 else float(beta.ppf(.025, successes, n - successes + 1))
    hi = 1.0 if successes == n else float(beta.ppf(.975, successes + 1, n - successes))
    p = successes / n
    return {"detected": int(successes), "replicates": n, "rate": p,
            "mc_se": sqrt(p * (1 - p) / n), "clopper_pearson_95": [lo, hi]}


def power_summary(sorted_nulls, simulated_keys):
    masks = [rejection_mask(sorted_nulls[k], simulated_keys[k]) for k in KEYS]
    n = len(masks[0])
    result = {name: binomial_summary(int(mask.sum()), n)
              for name, mask in zip(NAMES, masks)}
    result["any_of_three"] = binomial_summary(int(np.logical_or.reduce(masks).sum()), n)
    return result


def descriptive_appendices(draws, pool, warmup=200):
    """No p-values, extra gates, scans, or fitted mechanism."""
    validate_sets(draws[None, ...], pool)
    last = np.full(pool, -1, dtype=int)
    bins = np.zeros(16, dtype=int)
    left_censored = 0
    for t, row in enumerate(draws):
        if t >= warmup:
            for ball in row:
                if last[ball] < 0:
                    left_censored += 1
                else:
                    bins[min(t - last[ball] - 1, 15)] += 1
        last[row] = t
    p = 6 / pool
    gap = {"bins": [str(i) for i in range(15)] + [">=15"],
           "complete_intervals": int(bins.sum()), "counts": bins.tolist(),
           "iid_single_number_geometric_probabilities":
               [p * (1 - p) ** i for i in range(15)] + [(1 - p) ** 15],
           "left_censored_score_hits": left_censored,
           "right_censored_numbers": int((last >= 0).sum()),
           "not_seen_since_701": int((last < 0).sum()),
           "right_edge_unseen_periods": [None if t < 0 else len(draws) - 1 - int(t)
                                         for t in last],
           "p_value": None, "selection_allowed": False}
    sums = (draws.astype(int) + 1).sum(axis=1)
    cuts = np.quantile(sums[:warmup], [.25, .5, .75], method="inverted_cdf")
    labels = np.searchsorted(cuts, sums, side="left")
    counts = np.bincount(4 * labels[warmup - 1:-1] + labels[warmup:], minlength=16)
    counts = counts.reshape(4, 4)
    joint = counts / counts.sum()
    independent = joint.sum(axis=1)[:, None] * joint.sum(axis=0)[None, :]
    valid = independent > 0
    phi = float(((joint[valid] - independent[valid]) ** 2 / independent[valid]).sum())
    return {"gap_geometric": gap, "phi_descriptive_only": {
        "definition": "Pearson Phi divergence of lag1 warmup-quartile symbols of sum",
        "not_reproduction_of_maximum_phi_entropy_paper": True,
        "warmup_quantile_cuts": [int(x) for x in cuts], "lag1_counts": counts.tolist(),
        "value": phi, "p_value": None, "selection_allowed": False}}


def read_snapshot(root, source):
    """Hash the locked file, parse only original 701..last required slots."""
    path = root / source["path"]
    allowed = (root / "data/discovery").resolve()
    if path.resolve().parent != allowed or path.name != source["key"] + ".csv":
        raise ValueError("Discovery source escaped allowlist")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Locked discovery checksum mismatch")
    stop = source["score_last"] or source["available_last"]
    rows = []
    previous_date = None
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    for expected in range(701, stop + 1):
        row = next(reader, None)
        if row is None or int(row["issue"]) != expected:
            raise ValueError("Missing/replaced original issue slot")
        if row["split"] != "discovery" or int(row["main_pool_expected"]) != source["N"]:
            raise ValueError("Wrong split or matrix")
        if row["date"] != "NA":
            d = date.fromisoformat(row["date"])
            if previous_date is not None and d <= previous_date:
                raise ValueError("Dates not increasing")
            previous_date = d
        if row["status"] == "missing":
            if (any(row[f"n{i}"] != "NA" for i in range(1, 7)) or
                    row["missing_reason"] in ("", "NA")):
                raise ValueError("Imputed/undocumented missing draw")
        elif row["status"] == "observed_backup" and row["date"] != "NA":
            a = np.array([int(row[f"n{i}"]) - 1 for i in range(1, 7)], dtype=np.int64)
            validate_sets(a[None, None, :], source["N"])
        else:
            raise ValueError("Unknown observation status/date")
        rows.append(row)
    missing = [int(row["issue"]) for row in rows if row["status"] == "missing"]
    if missing or source["score_n"] == 0:
        return {"eligible": False, "reason": "missing_required_slots" if missing else
                "insufficient_warmup_135_of_200", "rows_parsed": len(rows),
                "missing_issues": missing, "draws": None}
    draws = np.array([[int(row[f"n{i}"]) - 1 for i in range(1, 7)] for row in rows],
                     dtype=np.uint8)
    if len(draws) != 200 + source["score_n"]:
        raise ValueError("Window length mismatch")
    return {"eligible": True, "reason": None, "rows_parsed": len(rows),
            "missing_issues": [], "draws": draws, "score_first_date": rows[200]["date"],
            "score_last_date": rows[-1]["date"],
            "selected_main_rows_sha256": hashlib.sha256(draws.tobytes()).hexdigest()}


def simulate_and_save(source, lock, stream, family, strength, reps, output):
    seed = [lock["seed"], source["country_index"], stream]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    arrays = {k: [] for k in KEYS}
    batches = []
    started = time.monotonic()
    for first in range(0, reps, lock["batch"]):
        count = min(lock["batch"], reps - first)
        draws = simulate_series(rng, count, 200 + source["score_n"], source["N"],
                                family, strength)
        validate_sets(draws, source["N"])
        values = statistic_keys(draws, source["N"])
        for k in KEYS:
            arrays[k].append(values[k])
        batches.append({"first_replicate_zero_based": first, "replicates": count,
                        "canonical_uint8_draws_sha256":
                            hashlib.sha256(draws.tobytes()).hexdigest()})
    arrays = {k: np.concatenate(parts).astype(np.int64) for k, parts in arrays.items()}
    np.savez_compressed(output, **arrays)
    return arrays, {"stream": stream, "seed_sequence_entropy": seed,
                    "family": family, "strength": strength, "replicates": reps,
                    "periods": 200 + source["score_n"], "warmup": 200,
                    "file": str(output.relative_to(ROOT)), "sha256": sha(output),
                    "batches": batches, "final_rng_state": rng.bit_generator.state,
                    "elapsed_seconds": time.monotonic() - started}


def audit_slots(source, snapshot, sorted_nulls=None):
    if not snapshot["eligible"]:
        return [{"country": source["key"], "statistic": name, "score_n": 0,
                 "statistic_value": None, "integer_key": None, "p_mc": None,
                 "p_bonferroni": None, "significant": False,
                 "status": "NA", "reason": snapshot["reason"]} for name in NAMES], None
    draws = snapshot["draws"]
    keys, marginal, pairs = statistic_keys(draws[None, ...], source["N"], include_counts=True)
    scalar = {k: int(v[0]) for k, v in keys.items()}
    displayed = displayed_statistics(scalar, source["N"], source["score_n"])
    slots = []
    for k, name in zip(KEYS, NAMES):
        null = sorted_nulls[k]
        extreme = int(len(null) - np.searchsorted(null, scalar[k], side="left"))
        p = (1 + extreme) / (len(null) + 1)
        slots.append({"country": source["key"], "statistic": name,
                      "score_n": source["score_n"], "statistic_value": displayed[name],
                      "integer_key": scalar[k], "null_reps": len(null),
                      "null_extreme_including_ties": extreme, "p_mc": p,
                      "p_bonferroni": min(1.0, 9 * p),
                      "significant": bool((1 + extreme) * 720 <= len(null) + 1),
                      "status": "computed", "reason": None})
    detail = {k: v for k, v in snapshot.items() if k != "draws"}
    detail.update(marginal_counts=marginal[0].tolist(),
                  pair_counts_lexicographic=pairs[0].tolist(),
                  pair_order="(1,2),(1,3),...,(1,N),(2,3),...,(N-1,N)",
                  serial_null_mean=source["score_n"] * 36 / source["N"],
                  appendices=descriptive_appendices(draws, source["N"]))
    return slots, detail


def install_sealed_guard(root):
    sealed = (root / "data/external").resolve()
    hk = (root / "marksix_data.csv").resolve()

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path == hk or path.is_relative_to(sealed):
                raise PermissionError("Audit forbids HK CSV and all sealed-window access")
    sys.addaudithook(audit)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def run():
    install_sealed_guard(ROOT)
    implementation = json.loads((AUDIT / "implementation-lock.json").read_text())
    lock = json.loads((AUDIT / "lock.json").read_text())
    if git("status", "--porcelain"):
        raise ValueError("Real audit requires a clean committed implementation")
    for path, digest in implementation["files_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("Committed implementation/spec/environment checksum mismatch")
    if (np.__version__ != implementation["environment"]["numpy"] or
            scipy.__version__ != implementation["environment"]["scipy"] or
            platform.python_version() != implementation["environment"]["python"]):
        raise ValueError("Locked runtime version mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", implementation["prereg_commit"],
                    "HEAD"], cwd=ROOT, check=True)
    output = AUDIT / "run"
    output.mkdir(exist_ok=False)
    started = {"id": lock["id"], "started_at_utc": now(), "run_count": 1,
               "prereg_commit": implementation["prereg_commit"],
               "implementation_commit": git("rev-parse", "HEAD"),
               "prereg_lock_sha256": sha(AUDIT / "lock.json"),
               "implementation_lock_sha256": sha(AUDIT / "implementation-lock.json"),
               "environment": implementation["environment"], "new_hit_attempts": 0}
    save_json(output / "started.json", started)
    ledger_append(AUDIT / "ledger.jsonl", {"event": "run_started", **started})
    try:
        if sha(ROOT / "data/discovery/manifest.json") != lock["discovery_manifest_sha256"]:
            raise ValueError("Discovery manifest checksum mismatch")
        snapshots = {s["key"]: read_snapshot(ROOT, s) for s in lock["sources"]}
        nulls = {}
        calibration = {}
        for source in lock["sources"]:
            key = source["key"]
            if not snapshots[key]["eligible"]:
                calibration[key] = {"status": "NA", "reason": snapshots[key]["reason"],
                                    "null_reps": 0, "power_reps": 0}
                continue
            print(key + ": null calibration starting (100000 complete sequences)", flush=True)
            arrays, meta = simulate_and_save(source, lock, 0, "uniform", 1.0,
                                            lock["null_reps"], output / (key + ".null.npz"))
            sorted_null = {k: np.sort(v) for k, v in arrays.items()}
            nulls[key] = sorted_null
            calibration[key] = {"null": meta, "power": []}
            print(key + ": null complete; fixed synthetic power grid starting", flush=True)
            for alternative in lock["power_alternatives"]:
                stream = alternative["stream"]
                values, meta = simulate_and_save(source, lock, stream,
                    alternative["family"], alternative["strength"], lock["power_reps"],
                    output / (key + f".power-{stream:02d}.npz"))
                meta["power"] = power_summary(sorted_null, values)
                calibration[key]["power"].append(meta)
                print(key + f": power stream {stream}/11 complete", flush=True)
        # Every calibration and its saved arrays precede real observed statistics.
        save_json(output / "calibration.json", calibration)
        slots = []
        observed = {}
        for source in lock["sources"]:
            found, detail = audit_slots(source, snapshots[source["key"]],
                                        nulls.get(source["key"]))
            slots.extend(found)
            observed[source["key"]] = detail
        any_signal = any(slot["significant"] for slot in slots)
        result = {**started, "completed_at_utc": now(), "run_count": 1,
                  "status": "audit_signal_requires_separate_proposal" if any_signal else
                            "archived_no_significant_primary_slot",
                  "alpha_total": .0125, "bonferroni_slots": 9,
                  "slots": slots, "observed": observed,
                  "calibration_file_sha256": sha(output / "calibration.json"),
                  "country_audit_signal": {s["key"]: any(x["significant"] for x in slots
                                          if x["country"] == s["key"]) for s in lock["sources"]},
                  "both_country_external_hit_thresholds_passed": False,
                  "hk_application_authorized": False, "hit_predictions": 0,
                  "new_hit_attempts": 0, "cumulative_hk_hit_attempts": 14,
                  "ev_r3_runs": 0,
                  "reference_fair_q": lock["reference_fair_q"],
                  "phi_paper_reproduction": "NA: full method/code unavailable; appendix descriptive only"}
        save_json(output / "results.json", result)
        ledger_append(AUDIT / "ledger.jsonl", {"event": "run_completed", "at_utc": now(),
                      "run_count": 1, "status": result["status"],
                      "results_sha256": sha(output / "results.json"),
                      "new_hit_attempts": 0, "cumulative_hk_hit_attempts": 14})
        save_json(output / "sealed.json", {"sealed_at_utc": now(), "run_count": 1,
                  "status": result["status"], "results_sha256": sha(output / "results.json"),
                  "ledger_sha256": sha(AUDIT / "ledger.jsonl")})
        print(json.dumps({"status": result["status"], "slots": slots}, ensure_ascii=False), flush=True)
    except BaseException as exc:
        failure = {"at_utc": now(), "status": "sealed_failed_do_not_rerun", "run_count": 1,
                   "error_type": type(exc).__name__, "error": str(exc)}
        save_json(output / "failed.json", failure)
        ledger_append(AUDIT / "ledger.jsonl", {"event": "run_failed", **failure})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True,
                        help="Execute the single committed real audit; refuses existing run")
    parser.parse_args()
    run()
