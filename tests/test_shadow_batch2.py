"""Synthetic-only formula, lookahead, MC and attempt-budget checks."""

from fractions import Fraction
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import marksix_shadow_batch2 as batch


def synthetic(count=69):
    masks = np.zeros((1, count, 49), dtype=bool)
    for t in range(count):
        masks[0, t, [(t * 3 + j * 7) % 49 for j in range(6)]] = True
    return masks


def test_resfold_matches_exact_independent_phase_folding():
    masks = synthetic()
    output = batch.run_paths(masks, retain_records=True)
    for record in output["records"]["SH-RESFOLD-v1"]:
        t = record["index"]
        for j in range(49):
            expected = sum((Fraction(49 * int(masks[0, :t:1, j][np.arange(t) % p == t % p].sum()) + 60,
                                     49 * (t // p + 10)) for p in range(2, 11)), Fraction()) / 9
            assert Fraction(record["score_keys"][j], record["score_common_denominator"]) == expected
    assert max(9 * 49 * math.lcm(*(t // p + 10 for p in range(2, 11)))
               for t in range(20, 69)) < np.iinfo(np.int64).max


def test_normalized_ewm_matches_explicit_historical_weights():
    masks = synthetic(23)
    output = batch.run_paths(masks, retain_records=True)
    numbers = np.arange(1, 50)
    for model, half_life in (("SH-CENTROID-v1", 5), ("SH-TAIL-v1", 10)):
        for record in output["records"][model]:
            t = record["index"]
            weights = np.array([2 ** (-(t - 1 - u) / half_life) for u in range(t)])
            if model == "SH-CENTROID-v1":
                center = np.dot(weights, masks[0, :t] @ numbers / 6) / weights.sum()
                assert record["center"] == pytest.approx(center, abs=2e-14)
            else:
                for n in numbers:
                    group = numbers % 10 == n % 10
                    expected = np.dot(weights, masks[0, :t, group].sum(axis=0)) / weights.sum() / group.sum()
                    assert record["scores"][n - 1] == pytest.approx(expected, abs=5e-16)


def test_tail_zero_has_four_members_and_others_five():
    masks = np.zeros((1, 21, 49), bool)
    masks[:, :, np.array([10, 20, 30, 40, 1, 11]) - 1] = True
    record = batch.run_paths(masks, retain_records=True)["records"]["SH-TAIL-v1"][0]
    assert record["scores"][9] == pytest.approx(1)
    assert record["scores"][0] == pytest.approx(0.4)
    assert record["scores"][1] == 0
    assert record["scores"][9] == record["scores"][19]
    assert batch.SPECS["SH-TAIL-v1"]["mechanism"] == "無物理機制"


def test_centroid_excludes_rank49_not_forcibly_number49():
    masks = np.zeros((1, 21, 49), bool)
    masks[:, :, np.array([35, 37, 39, 41, 43, 45]) - 1] = True
    record = batch.run_paths(masks, retain_records=True)["records"]["SH-CENTROID-v1"][0]
    assert record["center"] == pytest.approx(40)
    assert record["excluded"] == 1
    assert 49 in sum(record["tickets"], [])
    scores = -np.abs(np.arange(1, 50)[None, :] - 25)
    order, ranks, midranks = batch.rank_paths(scores, np.arange(49))
    assert ranks[0, 23] < ranks[0, 25]  # Same distance:24 before26.
    assert midranks[0, 23] == midranks[0, 25]


def test_warmup_and_requested_segment_counts_and_ticket_partition():
    result = batch.run_paths(synthetic(), retain_records=True)
    for model in batch.MODEL_IDS:
        records = result["records"][model]
        assert len(records) == 49 and records[0]["index"] == 20
        assert result["aggregates"][model]["26067_26095"]["draws"] == 29
        assert result["aggregates"][model]["26096_26115"]["draws"] == 20
        for record in records:
            assert record["training_draws"] == record["index"]
            assert sorted(record["order"]) == sorted(record["ranks"]) == list(range(1, 50))
            assert len(set(sum(record["tickets"], []))) == 48
            assert record["excluded"] not in sum(record["tickets"], [])
            hit = any(len(set(ticket).intersection(record["main"])) >= 3 for ticket in record["tickets"])
            assert record["success"] == hit


def test_no_lookahead_and_prefix_and_batch_path_invariance():
    masks = synthetic(24)
    original = batch.run_paths(masks, retain_records=True)
    prefix = batch.run_paths(masks[:, :23], retain_records=True)
    changed = masks.copy()
    changed[0, 21] = False
    changed[0, 21, :6] = True
    alternative = batch.run_paths(changed, retain_records=True)
    together = batch.run_paths(np.repeat(masks, 2, axis=0))
    for model in batch.MODEL_IDS:
        assert original["records"][model][:3] == prefix["records"][model]
        a = original["records"][model][1]
        b = alternative["records"][model][1]
        for key in ("scores", "order", "ranks", "tickets", "score_midranks"):
            assert a[key] == b[key]
        for segment in batch.SEGMENTS:
            for key in ("hits", "rank_sum", "midrank_sum2"):
                expected = original["aggregates"][model][segment][key][0]
                assert together["aggregates"][model][segment][key].tolist() == [expected, expected]


def test_seeded_ties_use_same_fixed_eligible_stream():
    import random
    masks = np.zeros((1, 21, 49), bool)
    masks[:, :, :6] = True
    result = batch.run_paths(masks, retain_records=True)
    for model in ("SH-RESFOLD-v1", "SH-TAIL-v1"):
        record = result["records"][model][0]
        values = record.get("score_keys", record["scores"])
        priority = list(range(1, 50))
        random.Random(20261029).shuffle(priority)
        assert record["order"] == sorted(priority, key=lambda n: -values[n - 1])


def test_fair_mc_samples_whole_subsets_and_uses_same_adaptive_algorithm():
    masks = batch.fair_histories(128, 69)
    assert np.array_equal(masks, batch.fair_histories(128, 69))
    assert np.all(masks.sum(axis=2) == 6)
    assert not np.array_equal(masks[0], masks[1])
    result = batch.run_paths(masks)
    for model in batch.MODEL_IDS:
        full = result["aggregates"][model]["26067_26115"]
        assert np.mean(full["rank_sum"]) / (6 * 49) == pytest.approx(25, abs=0.4)
        assert np.mean(full["hits"]) / 49 == pytest.approx(12344 / 83237, abs=0.03)


def test_plus_one_p_values_count_ties_in_correct_direction():
    actual = {"draws": 20, "hits": np.array([2]), "rank_sum": np.array([300]), "midrank_sum2": np.array([600])}
    null = {"draws": 20, "hits": np.array([0, 1, 2, 3, 4]),
            "rank_sum": np.array([100, 200, 300, 400, 500]), "midrank_sum2": np.array([200, 400, 600, 800, 1000])}
    a = {"aggregates": {m: {s: actual for s in batch.SEGMENTS} for m in batch.MODEL_IDS}}
    b = {"aggregates": {m: {s: null for s in batch.SEGMENTS} for m in batch.MODEL_IDS}}
    output = batch.summarize(a, b)
    for model in batch.MODEL_IDS:
        for segment in batch.SEGMENTS:
            entry = output[model][segment]
            assert entry["p_hits_upper"] == entry["p_rank_lower"] == entry["p_midrank_lower"] == 4 / 6
            assert entry["p_rank_Bonferroni20"] == 1
            assert sum(entry["null_hits_histogram"].values()) == 5


def test_attempt_budget_merges_archive_alias_and_excludes_nonmodels(tmp_path):
    path = tmp_path / "attempts.csv"
    identifiers = ["explore-blocks", "EXP-R1-FB8-26096-26115", "explore-24",
                   "SH-HARM48-v1", "SH-WDAY20-v1", "r2-H1", "r2-H3", "r2-H1-dissent", "reserved-H2", "explore-permutation"]
    path.write_text("attempt_id\n" + "\n".join(identifiers) + "\n")
    result = batch.attempt_budget(path)
    assert result["used"] == 4 and result["remaining"] == 16
    path.write_text("attempt_id\n" + "\n".join(f"SH-FAKE-{i}" for i in range(21)) + "\n")
    with pytest.raises(ValueError, match="cap exceeded"):
        batch.attempt_budget(path)


def test_invalid_histories_and_no_result_overwrite(tmp_path):
    with pytest.raises(ValueError, match="whole six-subset"):
        batch.run_paths(np.zeros((1, 22, 49), bool))
    with pytest.raises(ValueError, match="exactly one"):
        batch.run_paths(np.repeat(synthetic(22), 2, axis=0), retain_records=True)
    with pytest.raises(ValueError, match="69-draw"):
        batch.run_paths(synthetic(70))


def test_lock_hash_matches_implementation_and_rejects_parameter_tampering(tmp_path):
    lock, digest = batch.verify_lock()
    assert len(digest) == 64
    assert lock["implementation_sha256"] == hashlib.sha256(Path(batch.__file__).read_bytes()).hexdigest()
    lock["models"]["SH-TAIL-v1"]["half_life"] = 11
    path = tmp_path / "bad-lock.json"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="pre-run lock"):
        batch.verify_lock(path)
