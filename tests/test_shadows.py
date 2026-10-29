"""Synthetic fixtures validate the fixed shadows without pre-running the CSV."""

from dataclasses import replace
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
import random
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import marksix_r2 as r2
import marksix_shadows as sh


def test_lock_and_implementation_hash_and_tampering(tmp_path):
    lock, digest = sh.verify_lock()
    assert len(digest) == 64
    assert lock["implementation_sha256"] == hashlib.sha256(Path(sh.__file__).read_bytes()).hexdigest()
    lock["models"]["SH-GAP1"]["kappa"] = 31
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="pre-run lock"):
        sh.verify_lock(path)


def fixture_draws(count):
    draws = []
    for i in range(count):
        main = tuple(sorted({(i * 7 + j * 5) % 49 + 1 for j in range(6)}))
        special = next(n for n in range(1, 50) if n not in main)
        draws.append(r2.Draw(f"26/{47+i:03}", date(2026, 5, 5) + timedelta(days=i), main, special))
    return draws


def build_state(draws):
    state = sh.HistoryState()
    for draw in draws:
        state.observe(draw)
    return state


def test_gap_age_unseen_and_cap():
    draws = fixture_draws(22)
    repeated = [replace(draw, main=(1, 2, 3, 4, 5, 6), special=49) for draw in draws]
    for n in (1, 5, 20, 22):
        state = build_state(repeated[:n])
        scores = state.scores("SH-GAP20-v1")
        assert scores[:6] == (0,) * 6
        assert scores[6:] == (min(n, 20),) * 43
        assert state.gaps[6] == n
        assert state.gap_bins()[6] == 15
    state = build_state(repeated[:1] + [replace(draw, main=(7, 8, 9, 10, 11, 12), special=49)
                                      for draw in repeated[1:4]])
    assert state.gaps[0] == 3
    assert state.gaps[6] == 0


def test_rno_priority_boundaries_and_no_wrap():
    classes = sh.rno_classes((1, 2, 10, 20, 30, 40))
    assert classes[0] == classes[1] == "R"
    assert classes[2] == classes[8] == classes[10] == "N"
    assert classes[48] == "O"  # 1 never wraps to49.
    classes = sh.rno_classes((49, 20, 21, 30, 40, 10))
    assert classes[47] == "N" and classes[0] == "O"
    assert classes[19] == classes[20] == "R"
    assert all(c in "RNO" for c in classes)


def test_gap_exposures_and_shrinkage_match_independent_history_scan():
    draws = fixture_draws(24)
    exposure = [0] * 16
    hits = [0] * 16
    for t, draw in enumerate(draws):
        for number in range(1, 50):
            last = next((j for j in range(t - 1, -1, -1) if number in draws[j].main), None)
            group = 15 if last is None else min(t - 1 - last, 15)
            exposure[group] += 1
            hits[group] += number in draw.main
    state = build_state(draws)
    assert state.gap_exposures == exposure
    assert state.gap_hits == hits
    assert sum(exposure) == 49 * 24 and sum(hits) == 6 * 24
    for number, score in enumerate(state.scores("SH-GAP1"), 1):
        last = next((j for j in range(23, -1, -1) if number in draws[j].main), None)
        group = 15 if last is None else min(23 - last, 15)
        assert score == (hits[group] + 30 * Fraction(6, 49)) / (exposure[group] + 30)
    empty_group = next(i for i, total in enumerate(exposure) if total == 0)
    assert (hits[empty_group] + 30 * sh.PRIOR) / (exposure[empty_group] + 30) == sh.PRIOR


def test_rno_exposures_are_member_trials_not_draw_counts():
    draws = [replace(draw, main=(1, 2, 3, 4, 5, 6), special=49) for draw in fixture_draws(20)]
    state = build_state(draws)
    assert state.class_exposures == {"R": 19 * 6, "N": 19, "O": 19 * 42}
    assert state.class_hits == {"R": 19 * 6, "N": 0, "O": 0}
    values = state.scores("SH-LAG-RNO-v1")
    assert values[0] == Fraction(114, 1) / 144 + 30 * sh.PRIOR / 144
    assert values[6] == 30 * sh.PRIOR / 49
    assert values[7] == 30 * sh.PRIOR / 828
    assert sum(state.class_exposures.values()) == 49 * 19
    assert sum(state.class_hits.values()) == 6 * 19


def test_lag_formula_matches_explicit_adjacent_pairs_and_diagonal():
    draws = fixture_draws(8)
    # Force a repeated number so the i=j transition must be retained.
    draws[1] = replace(draws[1], main=draws[0].main, special=draws[0].special)
    state = build_state(draws)
    pairs = list(zip(draws, draws[1:]))
    assert sum(state.n) == 6 * 7
    assert sum(state.b) == 6 * 7
    assert sum(map(sum, state.c)) == 36 * 7
    assert state.c[draws[0].main[0] - 1][draws[0].main[0] - 1] >= 1
    expected = []
    for j in range(1, 50):
        bj = (sum(j in after.main for before, after in pairs) + 20 * sh.PRIOR) / (7 + 20)
        conditionals = []
        for i in draws[-1].main:
            ni = sum(i in before.main for before, after in pairs)
            cij = sum(i in before.main and j in after.main for before, after in pairs)
            conditionals.append((cij + 20 * bj) / (ni + 20))
        expected.append(sum(conditionals) / 6 - bj)
    assert state.scores("SH-LAG1-v1") == tuple(expected)
    one = build_state(draws[:1])
    assert one.scores("SH-LAG1-v1") == (0,) * 49


def test_exact_ties_and_seeded_ticket_order_are_fixed():
    values = (Fraction(2, 4),) * 49
    assert sh.order_numbers(values, None) == tuple(range(1, 50))
    rng = random.Random(20261029)
    expected = list(range(1, 50))
    rng.shuffle(expected)
    assert sh.order_numbers(values, random.Random(20261029)) == tuple(expected)
    assert sh.score_midranks(values) == (25.0,) * 49
    state = build_state(fixture_draws(1))
    prediction = sh.predict(state, "SH-LAG1-v1", None)
    assert prediction["tickets"] == r2.TICKETS
    assert prediction["excluded"] == 49
    assert sorted(sum((list(t) for t in prediction["tickets"]), [])) == list(range(1, 49))
    assert sorted(prediction["ranks"]) == list(range(1, 50))


def test_warmup_20_draws_and_full_segment_counts():
    output = sh.backtest(fixture_draws(69))
    for model in sh.MODEL_IDS:
        entry = output["models"][model]
        assert entry["window_26096_26115"]["draws"] == 20
        assert entry["common_26067_26115"]["draws"] == 49
        expected = 49 if model in ("SH-GAP1", "SH-LAG-RNO-v1") else 68
        assert entry["full_segment"]["draws"] == expected
        assert entry["records"][0]["target"] == ("26/067" if expected == 49 else "26/048")
    with pytest.raises(ValueError, match="warmup"):
        build_state(fixture_draws(19)).scores("SH-GAP1")
    for model in ("SH-GAP1", "SH-LAG-RNO-v1"):
        # The very first eligible target consumes the very first permutation.
        state = build_state(fixture_draws(20))
        first = sh.predict(state, model, random.Random(sh.SEED))
        assert output["models"][model]["records"][0]["prediction"] == first


def test_prefix_invariance_and_current_target_cannot_change_its_prediction():
    draws = fixture_draws(24)
    original = sh.backtest(draws)
    prefix = sh.backtest(draws[:23])
    changed = list(draws)
    changed[21] = replace(changed[21], main=(1, 2, 3, 4, 5, 6), special=49)
    alternate = sh.backtest(changed)
    for model in sh.MODEL_IDS:
        records = original["models"][model]["records"]
        prior = prefix["models"][model]["records"]
        assert records[:len(prior)] == prior
        current = next(r for r in records if r["target"] == draws[21].issue)
        replacement = next(r for r in alternate["models"][model]["records"] if r["target"] == draws[21].issue)
        assert current["prediction"] == replacement["prediction"]
        assert current["through"] == draws[20].issue


def test_special_numbers_are_ignored_for_all_shadows():
    draws = fixture_draws(22)
    changed = [replace(draw, special=next(n for n in range(49, 0, -1)
                                        if n not in draw.main and n != draw.special)) for draw in draws]
    original = sh.backtest(draws)
    alternate = sh.backtest(changed)
    for model in sh.MODEL_IDS:
        a = original["models"][model]
        b = alternate["models"][model]
        assert a["full_segment"] == b["full_segment"]
        assert [r["prediction"] for r in a["records"]] == [r["prediction"] for r in b["records"]]


def test_summary_rank_counts_success_once_and_paired_comparison():
    draws = [replace(draw, main=(1, 2, 3, 7, 8, 9), special=49) for draw in fixture_draws(2)]
    result = sh.backtest(draws)["models"]["SH-LAG1-v1"]
    assert result["full_segment"]["successes"] == 1
    assert result["full_segment"]["mean_main_rank"] == Fraction(1 + 2 + 3 + 7 + 8 + 9, 6)
    assert result["full_segment"]["mean_main_midrank"] == 25
    assert result["full_segment"]["paired_with_fixed_blocks"] == {
        "both": 1, "shadow_only": 0, "fixed_only": 0, "neither": 0}
