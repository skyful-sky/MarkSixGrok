"""Synthetic-only coverage, history leakage and fixed-configuration MC checks."""

from collections import Counter
from datetime import date, timedelta
import csv
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import marksix_triplecover as tc


def test_support_two_weight_and_no_decay():
    assert tc.positive_weights(Counter({(1, 2, 3): 1, (1, 2, 4): 2, (2, 3, 4): 5})) == {
        (1, 2, 4): 1, (2, 3, 4): 4}


def test_highest_seed_lex_ties_and_marginal_growth():
    w = {(7, 8, 9): 5, (1, 2, 3): 5, (1, 2, 10): 4, (1, 10, 11): 3,
         (2, 10, 11): 3, (3, 10, 12): 2}
    tickets, _ = tc.make_tickets(w)
    t = tickets[0]
    assert t["seed"] == [1, 2, 3]
    assert t["numbers"] == [1, 2, 3, 10, 11, 12]
    assert t["additions"] == [{"number": 10, "new_weight": 4},
                              {"number": 11, "new_weight": 6}, {"number": 12, "new_weight": 2}]
    assert t["newly_covered_weight"] == 17
    assert tickets[1]["seed"] == [7, 8, 9]


def test_covered_triples_never_reused_but_numbers_can_overlap():
    w = {(1, 2, 3): 9, (1, 2, 7): 8, (1, 8, 9): 7, (1, 10, 11): 6}
    tickets, remaining = tc.make_tickets(w)
    covered = [tuple(s) for t in tickets for s in t["newly_covered_triples"]]
    assert len(covered) == len(set(covered)) == len(w)
    assert sum(t["newly_covered_weight"] for t in tickets) == sum(w.values())
    assert remaining == {"uncovered_effective_triples": 0, "uncovered_weight": 0}
    assert len([t for t in tickets if t["kind"] == "greedy" and 1 in t["numbers"]]) >= 2


def test_empty_fallback_and_skip_only_exact_used_ticket():
    tickets, _ = tc.make_tickets({})
    assert [t["numbers"] for t in tickets] == list(map(list, tc.TICKETS))
    assert all(t["kind"] == "fallback" for t in tickets)
    tickets, _ = tc.make_tickets({(4, 5, 6): 1})
    assert tickets[0]["numbers"] == list(range(1, 7))
    assert [t["numbers"] for t in tickets[1:]] == list(map(list, tc.TICKETS[1:]))
    tickets, _ = tc.make_tickets({(1, 2, 49): 1})
    assert tickets[0]["numbers"] == [1, 2, 3, 4, 5, 49]
    assert tickets[1]["numbers"] == list(range(1, 7))  # overlap allowed


def test_diagnostic_midrank_not_ticket_order():
    scores, ranks = tc.diagnostics({(40, 41, 49): 2})
    assert scores[39] == scores[40] == scores[48] == 2
    assert ranks[39] == ranks[40] == ranks[48] == 2
    assert ranks[0] == 26.5
    assert tc.diagnostics({}) == ([0] * 49, [25.0] * 49)


def synthetic():
    return [SimpleNamespace(main=tuple(range(1, 7)) if t < 3 else (7, 8, 9, 10, 11, 49),
        issue=f"26/{47+t:03d}", day=date(2026, 1, 1) + timedelta(days=t)) for t in range(7)]


def test_past_only_prefix_invariance_and_counts_before_current():
    draws = synthetic()
    records = tc.backtest(draws, first=2)
    assert records[0]["effective_triples"] == 20
    assert all(s["count"] == 2 and s["weight"] == 1 for s in records[0]["positive_triples"])
    assert records == tc.backtest(draws, first=1)[1:]
    assert records[:3] == tc.backtest(draws[:5], first=2)
    changed = synthetic()
    changed[2] = SimpleNamespace(main=(15, 16, 17, 18, 19, 20), issue=draws[2].issue)
    alternate = tc.backtest(changed, first=2)
    for key in ("tickets", "diagnostic_scores", "effective_triples"):
        if key == "tickets":
            assert [{k: v for k, v in t.items() if k != "main_hits"} for t in records[0][key]] == [
                {k: v for k, v in t.items() if k != "main_hits"} for t in alternate[0][key]]
        else:
            assert records[0][key] == alternate[0][key]


def test_success_fallback_attribution_and_midrank_summary():
    records = tc.backtest(synthetic(), first=1)
    stats = tc.summary(records)
    assert stats["successes"] == stats["greedy_successes"] + stats["fallback_only_successes"]
    assert stats["fallback_successes"] == stats["fallback_only_successes"] + stats["both_successes"]
    for r in records:
        assert r["success"] == (r["max_main_hits"] >= 3)
        assert r["max_main_hits"] == max(t["main_hits"] for t in r["tickets"])
        assert r["mean_main_midrank"] == sum(r["diagnostic_midranks"][n-1] for n in r["main"]) / 6
    assert stats["fallback_tickets"] > 0


def test_configuration_mc_matches_exhaustive_toy_outcomes_and_preserves_overlap():
    samples = np.asarray(list(combinations(range(1, 9), 6)), dtype=np.uint8)
    tickets = [[1, 2, 3, 30, 31, 32], [2, 3, 4, 33, 34, 35]]
    actual = tc.configuration_successes(samples, tickets)
    expected = [any(len(set(sample).intersection(t)) >= 3 for t in tickets) for sample in samples]
    assert actual.tolist() == expected
    # Duplicate/overlapping tickets do not get treated as independent chances.
    one = tc.configuration_successes(samples, tickets[:1])
    assert np.array_equal(one, tc.configuration_successes(samples, tickets[:1] * 8))
    records = [{"target": "synthetic", "tickets": [{"numbers": t} for t in tickets]}]
    mc = tc.configuration_mc(records, samples)
    assert mc["mean_success_probability"] == pytest.approx(np.mean(expected))
    assert mc["per_target"][0]["successes"] == sum(expected)


def test_fair_sampler_seed_six_distinct_and_fixedblocks_calibration():
    samples = tc.fair_samples(12000)
    assert np.array_equal(samples[:20], tc.fair_samples(20))
    assert samples.min() == 1 and samples.max() == 49
    assert np.all(np.diff(samples.astype(int), axis=1) > 0)
    q = tc.configuration_successes(samples, list(tc.TICKETS)).mean()
    assert abs(q - float(tc.Q)) < 0.015
    with pytest.raises(ValueError, match="Duplicate"):
        tc.configuration_successes(np.ones((2, 6), dtype=np.uint8), list(tc.TICKETS))


def test_triples_are_valid_and_eight_ticket_cap_leaves_residual():
    with pytest.raises(ValueError):
        tc.make_tickets({(3, 2, 1): 1})
    weights = {s: 1 for s in combinations(range(1, 50), 3)}
    tickets, residual = tc.make_tickets(weights)
    assert len(tickets) == 8 and all(t["kind"] == "greedy" for t in tickets)
    assert residual["uncovered_effective_triples"] > 0
    assert residual["uncovered_weight"] + sum(t["newly_covered_weight"] for t in tickets) == len(weights)


def test_lock_rejects_parameter_and_implementation_changes(tmp_path):
    path = tmp_path / "lock.json"
    lock = {"specification": tc.SPEC, "data_sha256": tc.DATA_SHA256,
        "parameter_sha256": hashlib.sha256(tc.canonical_json(tc.SPEC).encode()).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(tc.__file__).read_bytes()).hexdigest(),
        "dependency_sha256": {}}
    path.write_text(tc.canonical_json(lock))
    assert tc.verify_lock(path)[0] == lock
    for key in ("parameter_sha256", "implementation_sha256"):
        path.write_text(tc.canonical_json(lock | {key: "bad"}))
        with pytest.raises(ValueError, match="changed"):
            tc.verify_lock(path)


def test_cli_serialization_hashes_committed_registration_and_no_rerun(tmp_path, monkeypatch):
    (tmp_path / "registry").mkdir()
    (tmp_path / "backtests").mkdir()
    lock_path = tmp_path / "lock.json"
    lock_path.write_bytes(b"synthetic-lock")
    result_path = tmp_path / "backtests/result.json"
    lock_hash = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    lock = {"implementation_sha256": "synthetic"}
    row = {"attempt_id": tc.MODEL_ID, "status": "registered_pending_backtest",
        "notes": lock_hash, "parameters": tc.canonical_json(tc.SPEC)}
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
    registry_bytes = buffer.getvalue().encode()
    (tmp_path / "registry/attempts.csv").write_bytes(registry_bytes)
    (tmp_path / "registry/window-26096-26115.json").write_text(json.dumps({
        "counted_model_ids": [tc.MODEL_ID], "used": 14, "limit": 20}))
    monkeypatch.setattr(tc, "ROOT", tmp_path)
    monkeypatch.setattr(tc, "LOCK_PATH", lock_path)
    monkeypatch.setattr(tc, "RESULT_PATH", result_path)
    monkeypatch.setattr(tc, "verify_lock", lambda: (lock, lock_hash))
    def git_output(args, **kwargs):
        if args[1] == "rev-parse": return "synthetic-committed-lock\n"
        return lock_path.read_bytes() if "lock.json" in args[-1] else registry_bytes
    monkeypatch.setattr(tc.subprocess, "check_output", git_output)
    monkeypatch.setattr(tc, "load_training", synthetic)
    real_backtest = tc.backtest
    calls = []
    def run_once(draws):
        calls.append(1)
        return real_backtest(draws, first=2)
    monkeypatch.setattr(tc, "backtest", run_once)
    samples = tc.fair_samples(30)
    monkeypatch.setattr(tc, "fair_samples", lambda: samples)
    tc.main()
    result = json.loads(result_path.read_bytes())
    assert result["summary"]["draws"] == 5 and result["configuration_MC"]["samples"] == 30
    assert result["audit"]["observed_runs"] == 1
    assert result_path.with_suffix(".started.json").exists()
    assert result_path.with_suffix(".json.sha256").read_text().split()[0] == hashlib.sha256(result_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="no historical rerun"):
        tc.main()
    assert calls == [1]
