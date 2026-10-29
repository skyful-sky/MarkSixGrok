"""Synthetic tests only; do not execute observed-history candidate backtests."""

import hashlib
from itertools import product
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import marksix_shadow_batch3 as batch


def synthetic(count=69):
    masks = np.zeros((1, count, 49), bool)
    for t in range(count):
        masks[0, t, [(t * 5 + 9 * k) % 49 for k in range(6)]] = True
    return masks


def test_ordstat_sorts_six_positions_then_normalized_ewm():
    masks = synthetic(23)
    result = batch.run_paths(masks, retain_records=True)
    for record in result["records"]["SH-ORDSTAT-v1"]:
        t = record["index"]
        positions = np.array([np.flatnonzero(masks[0, u]) + 1 for u in range(t)])
        weights = np.array([2 ** (-(t - 1 - u) / 10) for u in range(t)])
        expected = np.sum(positions * weights[:, None], axis=0) / weights.sum()
        assert record["ewm_locations"] == pytest.approx(expected, abs=2e-14)
        distances = np.min(np.abs(np.arange(1, 50)[:, None] - expected[None, :]), axis=1)
        assert record["distances"] == pytest.approx(distances, abs=3e-14)
        assert record["order"] == sorted(range(1, 50), key=lambda n: (record["distances"][n - 1], n))
        assert all(a <= b for a, b in zip(record["ewm_locations"], record["ewm_locations"][1:]))


def test_blockx_drops_one_then_numeric_chunks_then_frequency_order():
    frequencies = np.arange(49, dtype=float)[None, :]
    order, totals, identical = batch.blockx_order(frequencies, np.arange(49), np.arange(8))
    ascending_blocks = np.arange(1, 49).reshape(8, 6)
    assert order[0].tolist() == [*ascending_blocks[::-1].ravel(), 0]
    assert totals[0].tolist() == ascending_blocks.sum(axis=1)[::-1].tolist()
    assert not identical[0]
    assert np.all(np.diff(order[0, :48].reshape(8, 6), axis=1) > 0)


def test_blockx_two_seeded_tie_priorities_and_order_free_overlap():
    frequencies = np.zeros((1, 49))
    number_priority = np.array([48, *range(48)])
    block_priority = np.arange(7, -1, -1)
    order, totals, identical = batch.blockx_order(frequencies, number_priority, block_priority)
    assert order[0, -1] == 48
    assert order[0, :48].tolist() == np.arange(48).reshape(8, 6)[::-1].ravel().tolist()
    assert identical[0] and np.all(totals == 0)
    fixed = {tuple(range(6 * k + 1, 6 * k + 7)) for k in range(8)}
    actual = {tuple(sorted(ticket)) for ticket in (order[0, :48] + 1).reshape(8, 6)}
    assert actual == fixed  # Reversing ticket order is still identical allocation.


def test_blockx_frequency_matches_explicit_normalized_history():
    masks = synthetic(24)
    result = batch.run_paths(masks, retain_records=True)
    for record in result["records"]["SH-BLOCKX-v1"]:
        t = record["index"]
        weights = np.array([2 ** (-(t - 1 - u) / 20) for u in range(t)])
        expected = (weights[:, None] * masks[0, :t]).sum(axis=0) / weights.sum()
        assert record["frequencies"] == pytest.approx(expected, abs=3e-16)
        assert expected[record["excluded"] - 1] == pytest.approx(min(expected))
        assert sorted(sum(record["tickets"], []) + [record["excluded"]]) == list(range(1, 50))


def test_warmup_segments_success_and_overlap_recording():
    result = batch.run_paths(synthetic(), retain_records=True)
    fixed = {tuple(range(6 * k + 1, 6 * k + 7)) for k in range(8)}
    for model in batch.MODEL_IDS:
        records = result["records"][model]
        assert len(records) == 49 and records[0]["index"] == 20
        assert result["aggregates"][model]["26067_26095"]["draws"] == 29
        assert result["aggregates"][model]["26096_26115"]["draws"] == 20
        for r in records:
            assert r["success"] == any(len(set(t).intersection(r["main"])) >= 3 for t in r["tickets"])
            assert r["fixedblocks_tickets_identical"] == ({tuple(sorted(t)) for t in r["tickets"]} == fixed)
            assert sorted(r["order"]) == sorted(r["ranks"]) == list(range(1, 50))


def test_prefix_current_target_and_batch_invariance():
    masks = synthetic(24)
    original = batch.run_paths(masks, retain_records=True)
    prefix = batch.run_paths(masks[:, :23], retain_records=True)
    changed = masks.copy()
    changed[0, 21] = False
    changed[0, 21, :6] = True
    alternate = batch.run_paths(changed, retain_records=True)
    parallel = batch.run_paths(np.repeat(masks, 2, axis=0))
    for model in batch.MODEL_IDS:
        assert original["records"][model][:3] == prefix["records"][model]
        first = original["records"][model][1]
        second = alternate["records"][model][1]
        for key in ("order", "ranks", "tickets", "excluded"):
            assert first[key] == second[key]
        for segment in batch.SEGMENTS:
            for key in ("hits", "rank_sum", "fixed_identical"):
                value = original["aggregates"][model][segment][key][0]
                assert parallel["aggregates"][model][segment][key].tolist() == [value, value]


def test_prerequisite_reads_saved_gate_without_rerunning_centroid(tmp_path):
    actual = batch.prerequisite()
    assert actual["mean_main_rank"] == pytest.approx(24.88095238095238)
    assert actual["p_rank_lower"] == pytest.approx(0.4333566643335666)
    path = tmp_path / "failed.json"
    path.write_text(json.dumps({"models": {"SH-CENTROID-v1": {"segments": {"26067_26115": {
        "draws": 49, "mean_main_rank": 25, "p_rank_lower": 0.5}}}}}))
    with pytest.raises(ValueError, match="prerequisite failed"):
        batch.prerequisite(path)


def test_holm_cumulative_family_and_missing_p_conservative_upper_bound():
    known = {"a": 0.01, "b": 0.04}
    family = ["a", "b", "c", "d", "e"]
    bounds = batch.holm_bounds(known, family)
    assert bounds["adjusted_upper_bounds"]["a"] == pytest.approx(0.05)
    assert bounds["adjusted_upper_bounds"]["b"] == pytest.approx(0.16)
    assert bounds["raw_p"]["c"] is None
    for values in product((0, 0.005, 0.03, 0.08, 0.9, 1), repeat=3):
        complete = batch.holm_bounds(known | dict(zip(("c", "d", "e"), values)), family)
        for model in known:
            assert complete["adjusted_upper_bounds"][model] <= bounds["adjusted_upper_bounds"][model] + 1e-15
    tied = batch.holm_bounds({"a": 0.02, "b": 0.02, "c": 0.9}, ["a", "b", "c"])
    assert tied["adjusted_upper_bounds"]["a"] == tied["adjusted_upper_bounds"]["b"] == 0.06
    with pytest.raises(ValueError):
        batch.holm_bounds({"bad": 0.1}, family)


def test_screening_and_strictly_greater_than_half_overlap():
    segments = {"26096_26115": {"successes": 9, "fixedblocks_identical_fraction": 0.5},
                "26067_26115": {"fixedblocks_identical_fraction": 0.5}}
    assert batch.model_status("SH-BLOCKX-v1", segments) == "screening_only_not_confirmed"
    segments["26096_26115"]["fixedblocks_identical_fraction"] = 0.50001
    assert batch.model_status("SH-BLOCKX-v1", segments) == "descriptive_only_high_fixedblocks_overlap"
    assert batch.model_status("SH-ORDSTAT-v1", segments) == "screening_only_not_confirmed"
    segments["26096_26115"]["successes"] = 8
    assert batch.model_status("SH-BLOCKX-v1", segments) == "disabled"


def test_complete_history_null_sanity():
    result = batch.run_paths(batch.common.fair_histories(128, 69))
    for model in batch.MODEL_IDS:
        a = result["aggregates"][model]["26067_26115"]
        assert np.mean(a["rank_sum"]) / (6 * 49) == pytest.approx(25, abs=0.4)
        assert np.mean(a["hits"]) / 49 == pytest.approx(12344 / 83237, abs=0.03)


def test_lock_hash_and_tampering(tmp_path):
    lock, digest = batch.verify_lock()
    assert len(digest) == 64
    assert lock["implementation_sha256"] == hashlib.sha256(Path(batch.__file__).read_bytes()).hexdigest()
    lock["models"]["SH-ORDSTAT-v1"]["half_life"] = 11
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="pre-run lock"):
        batch.verify_lock(path)
