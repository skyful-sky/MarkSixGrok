"""Synthetic-only audit tests; sealed real outputs are checked, never rerun."""

from collections import Counter
import csv
from datetime import date, timedelta
import hashlib
import io
from itertools import combinations, product
import json
from math import comb
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from src import aud_serial_k6_v1 as aud


def rng(seed=17):
    return np.random.Generator(np.random.PCG64(seed))


def test_floyd_exact_uniformity_by_enumerating_all_random_paths():
    # 20160 equally likely paths, 28 possible six-subsets: exactly 720 each.
    paths = np.array(list(product(*[range(j + 1) for j in range(2, 8)])))

    class Enumerated:
        column = 0

        def integers(self, low, high, size, dtype):
            assert low == 0 and high == self.column + 3
            value = paths[:, self.column]
            self.column += 1
            return value

    values = aud.uniform_sets(Enumerated(), (len(paths),), 8, 6)
    counts = Counter(map(tuple, values.tolist()))
    assert set(counts) == set(combinations(range(8), 6))
    assert set(counts.values()) == {720}


@pytest.mark.parametrize("pool", [8, 43, 45, 49])
def test_complete_six_sampler_and_reproducibility(pool):
    x = aud.uniform_sets(rng(), (9, 15), pool)
    aud.validate_sets(x, pool)
    assert x.shape == (9, 15, 6)
    assert np.array_equal(x, aud.uniform_sets(rng(), (9, 15), pool))


def test_three_integer_statistics_match_independent_set_counter():
    x = aud.uniform_sets(rng(), (4, 11), 12)
    values, marginals, pairs = aud.statistic_keys(x, 12, warmup=3, include_counts=True)
    for rep, series in enumerate(x):
        score = series[3:]
        m = Counter(int(n) for row in score for n in row)
        pair = Counter(p for row in score for p in combinations(map(int, row), 2))
        all_pairs = [pair[p] for p in combinations(range(12), 2)]
        assert marginals[rep].tolist() == [m[i] for i in range(12)]
        assert pairs[rep].tolist() == all_pairs
        assert values["marginal_ssq"][rep] == sum(c * c for c in m.values())
        assert values["pair_deviation"][rep] == max(abs(132 * c - 30 * 8) for c in all_pairs)
        assert values["serial_overlap"][rep] == sum(len(set(series[t]) & set(series[t-1]))
                                                   for t in range(3, 11))


def test_last_warmup_is_the_first_predecessor():
    a = [0, 1, 2, 3, 4, 5]
    b = [6, 7, 8, 9, 10, 11]
    x = np.array([[a, b, b, a]], dtype=np.uint8)
    values = aud.statistic_keys(x, 12, warmup=2)
    assert values["serial_overlap"].item() == 6


def test_label_permutation_does_not_change_primary_statistics():
    x = aud.uniform_sets(rng(), (3, 20), 12)
    permutation = rng(2).permutation(12)
    changed = np.sort(permutation[x], axis=-1)
    old = aud.statistic_keys(x, 12, warmup=4)
    new = aud.statistic_keys(changed, 12, warmup=4)
    for key in aud.KEYS:
        assert np.array_equal(old[key], new[key])


def test_monte_carlo_ties_plus_one_and_exact_nine_slot_boundary():
    null = np.array([1, 2, 2, 4])
    assert aud.monte_carlo_p(null, 2) == .8
    assert aud.monte_carlo_p(null, 5) == .2
    assert aud.monte_carlo_p(null, 0) == 1
    full = np.arange(100000)
    assert aud.rejection_mask(full, 99863)   # 137 extreme + 1
    assert not aud.rejection_mask(full, 99862)  # 138 extreme + 1


def test_weighted_set_count_agrees_with_exact_combinatorial_expectation():
    pool, w = 12, 1.5
    x = aud.simulate_series(rng(), 100, 200, pool, "weighted_set", w)
    aud.validate_sets(x, pool)
    masses = [comb(6, m) * comb(6, 6-m) * w**m for m in range(7)]
    expected = sum(m * p for m, p in enumerate(masses)) / sum(masses)
    assert abs((x < 6).sum(axis=-1).mean() - expected) < .04


def test_iid_cyclic_cluster_has_only_fixed_cyclic_six_support():
    pool = 12
    x = aud.simulate_series(rng(), 10, 100, pool, "cyclic_cluster", 1)
    allowed = {tuple(sorted((start + i) % pool for i in range(6))) for start in range(pool)}
    assert set(map(tuple, x.reshape(-1, 6).tolist())) == allowed
    aud.validate_sets(x, pool)


@pytest.mark.parametrize("family", ["cyclic_cluster", "serial_copy_one"])
def test_zero_mixture_reduces_to_same_uniform_draws(family):
    assert np.array_equal(aud.simulate_series(rng(), 5, 20, 12, family, 0),
                          aud.simulate_series(rng(), 5, 20, 12, "uniform", 1))


def test_copy_one_has_at_least_one_adjacent_overlap_and_complete_six():
    x = aud.simulate_series(rng(), 8, 30, 12, "serial_copy_one", 1)
    aud.validate_sets(x, 12)
    assert all(set(row) & set(previous) for series in x
               for row, previous in zip(series[1:], series[:-1]))


def test_gap_censoring_and_phi_appendix_are_not_extra_tests():
    a, b = list(range(6)), list(range(6, 12))
    x = np.array([a, b, a, a], dtype=np.uint8)
    out = aud.descriptive_appendices(x, 12, warmup=2)
    gap = out["gap_geometric"]
    assert gap["counts"][:2] == [6, 6]
    assert gap["complete_intervals"] == 12
    assert gap["left_censored_score_hits"] == 0
    assert sum(gap["iid_single_number_geometric_probabilities"]) == pytest.approx(1)
    phi = out["phi_descriptive_only"]
    assert np.array(phi["lag1_counts"]).sum() == 2
    assert gap["p_value"] is None and phi["p_value"] is None
    assert not gap["selection_allowed"] and not phi["selection_allowed"]
    changed = x.copy(); changed[2:] = b
    assert (aud.descriptive_appendices(changed, 12, warmup=2)["phi_descriptive_only"]
            ["warmup_quantile_cuts"] == phi["warmup_quantile_cuts"])


def write_fixture(root, key="uk", last=903, missing=None, suffix=""):
    d = root / "data/discovery"; d.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    fields = ["issue", "date", "split", "main_pool_expected", *[f"n{i}" for i in range(1, 7)],
              "status", "missing_reason"]
    writer = csv.DictWriter(buf, fieldnames=fields); writer.writeheader()
    for issue in range(701, last + 1):
        row = dict(issue=issue, date=str(date(2020, 1, 1) + timedelta(days=issue-701)),
                   split="discovery", main_pool_expected=12, status="observed_backup",
                   missing_reason="NA", **{f"n{i}": str(i) for i in range(1, 7)})
        if issue == missing:
            row.update(status="missing", missing_reason="synthetic missing slot",
                       **{f"n{i}": "NA" for i in range(1, 7)})
        writer.writerow(row)
    p = d / (key + ".csv");p.write_text(buf.getvalue() + suffix)
    return dict(key=key, path=f"data/discovery/{key}.csv", sha256=aud.sha(p), N=12,
                score_n=3 if last >= 900 else 0, score_last=903 if last >= 900 else None,
                available_last=last)


def test_reader_stops_at_fixed_window_and_does_not_parse_future(tmp_path):
    # pytest injects tmp_path; deliberately malformed future cannot become input.
    root = tmp_path
    source = write_fixture(root, suffix="not,a,valid,future,draw\n")
    value = aud.read_snapshot(root, source)
    assert value["eligible"] and len(value["draws"]) == 203
    assert value["rows_parsed"] == 203


@pytest.mark.parametrize("missing", [710, 902])
def test_missing_warmup_or_score_is_na_not_imputed_or_bridged(tmp_path, missing):
    source = write_fixture(tmp_path, missing=missing)
    value = aud.read_snapshot(tmp_path, source)
    assert not value["eligible"] and value["draws"] is None
    assert value["missing_issues"] == [missing]
    slots, detail = aud.audit_slots(source, value)
    assert len(slots) == 3 and all(s["p_mc"] is None for s in slots)
    assert detail is None


def test_korea_135_is_never_scored_or_borrowed(tmp_path):
    source = write_fixture(tmp_path, key="korea", last=835)
    value = aud.read_snapshot(tmp_path, source)
    assert value["rows_parsed"] == 135 and not value["eligible"]
    assert value["reason"] == "insufficient_warmup_135_of_200"


def test_checksum_or_symlink_failure_stops_reader(tmp_path):
    source = write_fixture(tmp_path)
    p = tmp_path / source["path"]
    p.write_text(p.read_text() + "changed")
    with pytest.raises(ValueError, match="checksum"):
        aud.read_snapshot(tmp_path, source)
    outside = tmp_path / "outside.csv";outside.write_bytes(p.read_bytes())
    p.unlink();p.symlink_to(outside)
    with pytest.raises(ValueError, match="allowlist"):
        aud.read_snapshot(tmp_path, source)


def test_ledger_detects_changed_history(tmp_path):
    p = tmp_path / "ledger.jsonl"
    aud.ledger_append(p, {"event": "locked"})
    aud.ledger_append(p, {"event": "start", "run_count": 1})
    lines = p.read_text().splitlines()
    row = json.loads(lines[0]);row["payload"]["event"] = "changed"
    p.write_text(json.dumps(row) + "\n" + lines[1] + "\n")
    with pytest.raises(ValueError, match="ledger"):
        aud.ledger_append(p, {"event": "finish"})


def test_full_simulation_storage_on_small_synthetic_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(aud, "ROOT", tmp_path)
    source = {"N": 12, "score_n": 3, "country_index": 0}
    lock = {"seed": 17, "batch": 4}
    output = tmp_path / "synthetic.npz"
    arrays, meta = aud.simulate_and_save(source, lock, 0, "uniform", 1, 9, output)
    assert [b["replicates"] for b in meta["batches"]] == [4, 4, 1]
    with np.load(output, allow_pickle=False) as saved:
        assert set(saved.files) == set(aud.KEYS)
        assert all(np.array_equal(saved[k], arrays[k]) for k in aud.KEYS)
    assert meta["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    summary = aud.power_summary({k: np.sort(v) for k, v in arrays.items()}, arrays)
    assert all(s["replicates"] == 9 for s in summary.values())


def test_sealed_guard_blocks_entire_sealed_directory_and_hk_csv(tmp_path):
    sealed = tmp_path / "data/external";sealed.mkdir(parents=True)
    (sealed / "metadata.json").write_text("{}")
    (tmp_path / "marksix_data.csv").write_text("do not read")
    code = """
from pathlib import Path
from src.aud_serial_k6_v1 import install_sealed_guard
import sys
root=Path(sys.argv[1]); install_sealed_guard(root)
for p in [root/'data/external/metadata.json',root/'marksix_data.csv']:
    try:p.read_bytes()
    except PermissionError:pass
    else:raise RuntimeError('Protected read was allowed')
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=aud.ROOT, check=True)


def test_locked_nine_slots_and_sources_are_not_redefined():
    lock = json.loads((aud.AUDIT / "lock.json").read_text())
    assert lock["bonferroni_slots"] == 9 and lock["alpha_total"] == .0125
    assert lock["null_reps"] == 100000 and lock["lag"] == 1
    assert [s["score_n"] for s in lock["sources"]] == [500, 246, 0]
    assert lock["hk_attempts_added"] == 0
    assert lock["reference_fair_q"]["japan"] == {"numerator": 1221091, "denominator": 6096454}


def test_completed_run_is_sealed_once_and_all_nine_slots_retained():
    p = aud.AUDIT / "run/results.json"
    if not p.exists():
        pytest.skip("Real audit not yet run; test never initiates one")
    result = json.loads(p.read_text())
    seal = json.loads((p.parent / "sealed.json").read_text())
    assert result["run_count"] == seal["run_count"] == 1
    assert aud.sha(p) == seal["results_sha256"]
    assert len(result["slots"]) == 9
    assert sum(s["p_mc"] is None for s in result["slots"]) == 3
    assert result["cumulative_hk_hit_attempts"] == 14
    assert result["new_hit_attempts"] == result["hit_predictions"] == result["ev_r3_runs"] == 0
    assert not result["hk_application_authorized"]
    for s in result["slots"]:
        if s["status"] != "NA":
            assert s["null_reps"] == 100000
            assert s["p_mc"] == (1 + s["null_extreme_including_ties"]) / 100001
            assert s["p_bonferroni"] == min(1, 9 * s["p_mc"])
