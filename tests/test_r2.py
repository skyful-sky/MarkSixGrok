"""Exact combinatorics, conditional null calibration and protocol boundary tests."""

from dataclasses import replace
from datetime import date, timedelta
from fractions import Fraction
import hashlib
from itertools import combinations, product
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import marksix_r2 as r2


@pytest.fixture(scope="module")
def training():
    return r2.load_training()


def future_draws(n, main=(1, 7, 13, 19, 25, 31)):
    return [r2.Draw(f"26/{116+i:03}", date(2026, 10, 29) + timedelta(days=i),
                    main, 49) for i in range(n)]


def test_locked_snapshot_and_yaml(training):
    p = r2.load_protocol()
    assert hashlib.sha256((ROOT / "marksix_data.csv").read_bytes()).hexdigest() == r2.DATA_SHA256
    assert (len(training), training[0].issue, training[-1].issue) == (69, "26/047", "26/115")
    assert p["data"]["last_date"] == training[-1].day.isoformat()
    assert p["H1"]["pass_at_draw"] == p["H3"]["pass_at_draw"] == 60
    assert p["H1"]["direction"] == "hot_first"
    assert not p["validity"]["publication_verified"]
    assert p["futility"]["checkpoints"] == [
        {"draws": 20, "maximum_cumulative_H3_successes": 2},
        {"draws": 40, "maximum_cumulative_H3_successes": 5}]
    assert sum(Fraction(v) for k, v in p["alpha"].items() if k in ("H1", "H3", "H2_reserved")) == Fraction(1, 20)


def test_tampered_snapshot_and_protocol_rejected(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_bytes((ROOT / "marksix_data.csv").read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256"):
        r2.load_training(csv)
    p = r2.load_protocol()
    p["H1"]["lambda"] = 0.2
    path = tmp_path / "round2.yaml"
    path.write_text(yaml.safe_dump(p), encoding="utf-8")
    with pytest.raises(ValueError, match="locked implementation"):
        r2.load_protocol(path)


def test_q_exhaustive_occupancy_enumeration():
    # Exhaust all disjoint-block occupancy vectors, weighted by the number of
    # actual six-subsets each represents. Includes 49 as a singleton block.
    # This partitions all C(49,6) outcomes without 14 million Python tuples.
    total = successful = 0
    for counts in product(range(7), repeat=8):
        remainder = 6 - sum(counts)
        if remainder not in (0, 1):
            continue
        multiplicity = math.prod(math.comb(6, count) for count in counts)
        total += multiplicity
        if max(counts) >= 3:
            successful += multiplicity
    assert total == math.comb(49, 6) == 13983816
    assert successful == 2073792
    assert Fraction(successful, total) == r2.Q == Fraction(12344, 83237)


def test_exact_binomial_threshold_is_minimal():
    alpha = Fraction(1, 60)
    assert r2.binomial_tail(16) <= alpha < r2.binomial_tail(15)
    assert min(k for k in range(61) if r2.binomial_tail(k) <= alpha) == 16
    assert float(r2.binomial_tail(16)) == pytest.approx(0.01225785, abs=5e-9)
    assert float(r2.binomial_tail(15)) == pytest.approx(0.02657537, abs=5e-9)


@pytest.mark.parametrize("values", [(1.0,) * 9, tuple(math.exp(-i / 60) for i in range(10))])
def test_e6_against_brute_force(values):
    expected = math.fsum(math.prod(subset) for subset in combinations(values, 6))
    assert r2.elementary_symmetric(values) == pytest.approx(expected, rel=2e-15)
    assert r2.elementary_symmetric(values, 0) == 1
    with pytest.raises(ValueError):
        r2.elementary_symmetric(values, len(values) + 1)


@pytest.mark.parametrize("length", [0, 1, 5, 69])
def test_conditional_null_mean_exact_rank_sum_enumeration(training, length):
    ranks = r2.average_ranks(r2.scores(training[:length]))
    # Independent integer subset-sum enumeration; twice a midrank is integral.
    # Counts the exact null distribution of six-rank sums, ties included.
    counts = [dict() for _ in range(7)]
    counts[0][0] = 1
    for rank in ranks:
        doubled = round(2 * rank)
        for k in range(6, 0, -1):
            for total, multiplicity in list(counts[k - 1].items()):
                key = total + doubled
                counts[k][key] = counts[k].get(key, 0) + multiplicity
    assert sum(counts[6].values()) == math.comb(49, 6)
    null_mean_numerator = math.fsum(
        count * math.exp(0.1 * (25 - rank_sum / 12))
        for rank_sum, count in counts[6].items()) / math.comb(49, 6)
    denominator = r2.conditional_denominator(ranks)
    assert denominator == pytest.approx(null_mean_numerator, rel=3e-15)
    assert null_mean_numerator / denominator == pytest.approx(1, abs=3e-15)
    # Each conditional factor has mean one, so tower expectation gives E[E_60]=1
    # even with adaptive rankings. Markov gives P(E_60>=60)<=1/60 exactly;
    # Monte Carlo alone cannot establish this inequality or estimate a heavy
    # tailed E_60 mean reliably.
    assert Fraction(1, r2.E_THRESHOLD) == Fraction(1, 60)


def test_age_half_life_ties_and_special_exclusion(training):
    d = training[0]
    values = r2.scores([d])
    for n in range(1, 50):
        assert values[n - 1] == (2 ** (-1 / 20) if n in d.main else 0)
    repeated = r2.scores([d] * 21)
    assert repeated[d.main[0] - 1] == pytest.approx(sum(2 ** (-age / 20) for age in range(1, 22)))
    changed_special = replace(d, special=49)
    assert r2.scores([d]) == r2.scores([changed_special])
    ranks = r2.average_ranks(values)
    assert all(ranks[n - 1] == 3.5 for n in d.main)
    assert all(ranks[n - 1] == 28 for n in range(1, 50) if n not in d.main)
    assert sum(ranks) == 49 * 25
    assert r2.average_ranks([0.0] * 49) == (25.0,) * 49
    assert r2.shadow_tickets([0.0] * 49) == r2.TICKETS


def test_formal_tickets_and_success():
    assert len(set(sum(r2.TICKETS, ()))) == 48
    assert 49 not in sum(r2.TICKETS, ())
    assert r2.success((1, 2, 3, 7, 8, 9)) is True  # Two winning tickets count once.
    assert r2.success((1, 2, 7, 8, 13, 49)) is False
    with pytest.raises(ValueError):
        r2.success((1, 1, 2, 3, 4, 5))


def test_archived_20_draw_exploration_is_reproducible(training):
    window = training[-20:]
    assert (window[0].issue, window[-1].issue) == ("26/096", "26/115")
    assert sum(r2.success(draw.main) for draw in window) == 8


@pytest.mark.parametrize("n,hit,rank,expected", [
    (20, 2, 25, True), (20, 3, 26, False), (20, 2, 24.999, False),
    (40, 5, 25, True), (40, 6, 26, False), (40, 5, 24.999, False),
    (19, 0, 40, False), (21, 0, 40, False), (60, 0, 40, False)])
def test_futility_conjunction_boundaries(n, hit, rank, expected):
    assert r2.futility(n, hit, rank) is expected


def test_only_terminal_decision_and_publication_gate():
    for n in (1, 20, 40, 59):
        result = r2.decision(n, 20, n, 10, registration_valid=True)
        assert not result["H1_pass"] and not result["H3_pass"]
    result = r2.decision(60, math.log(60), 16, 25, registration_valid=True)
    assert result["H1_pass"] and result["H3_pass"]
    result = r2.decision(60, math.log(60) - 1e-12, 15, 20, registration_valid=True)
    assert not result["H1_pass"] and not result["H3_pass"]
    for kwargs in ({}, {"registration_valid": True, "invalidation_reason": "machine_change"}):
        result = r2.decision(60, 20, 60, 1, **kwargs)
        assert not result["H1_pass"] and not result["H3_pass"]
    result = r2.decision(20, 20, 2, 25, registration_valid=True)
    assert result["state"] == "stopped_futility" and not result["H1_pass"]
    with pytest.raises(ValueError):
        r2.decision(61, 0, 0, 25)


def test_no_lookahead_and_late_draw_counts(training):
    forward = future_draws(3)
    original = r2.evaluate(training, forward, registration_valid=True, late_issues=["26/116"])
    changed = [replace(forward[0], main=(2, 8, 14, 20, 26, 32)), *forward[1:]]
    alternate = r2.evaluate(training, changed, registration_valid=True)
    assert original["n"] == 3
    assert original["records"][0]["late_submission"]
    assert original["records"][0]["prediction"] == alternate["records"][0]["prediction"]
    assert original["records"][1]["prediction"] != alternate["records"][1]["prediction"]
    assert original["records"][0]["prediction"] == r2.predict(training, "26/116")
    assert original["records"][0]["A"] == pytest.approx(25 - sum(
        original["records"][0]["prediction"]["ranks"][n - 1] for n in forward[0].main) / 6)


def test_futility_stops_entire_path_and_reports_recent20(training):
    # Bottom-ranked dispersed main numbers force negative cumulative A and no
    # formal success, even as scores update; no future target data enters ranks.
    history = list(training)
    forward = []
    for i in range(60):
        values = r2.scores(history)
        main = tuple(min(ticket, key=lambda n: values[n - 1]) for ticket in r2.TICKETS[:6])
        draw = future_draws(60)[i]
        draw = replace(draw, main=main)
        forward.append(draw)
        history.append(draw)
    result = r2.evaluate(training, forward, registration_valid=True)
    assert result["n"] == 20
    assert result["state"] == "stopped_futility"
    assert result["ignored_after_stop"] == 40
    assert not result["H1_pass"] and not result["H3_pass"]
    assert result["records"][-1]["last_20"]["H3_rate"] == 0
    assert result["H1_failure_note"] == r2.FAILURE_NOTE


def test_full60_and_year_rollover_do_not_pass_early(training):
    forward = future_draws(60, main=(1, 2, 3, 4, 5, 6))
    # A year boundary is determined from actual results, never a hard-coded
    # guessed last annual issue. This fixture rolls over after 26/140.
    forward = [replace(draw, issue=f"27/{i-24:03}") if i >= 25 else draw
               for i, draw in enumerate(forward)]
    early = r2.evaluate(training, forward[:59], registration_valid=True)
    assert early["state"] == "running"
    assert not early["H1_pass"] and not early["H3_pass"]
    terminal = r2.evaluate(training, forward, registration_valid=True)
    assert terminal["state"] == "completed"
    assert terminal["n"] == terminal["H3_successes"] == 60
    assert terminal["H1_pass"] and terminal["H3_pass"]
    assert terminal["records"][-1]["last_20"]["H3_rate"] == 1
    assert terminal["records"][25]["prediction"]["target"] == "27/001"
    unverified = r2.evaluate(training, forward)
    assert not unverified["H1_pass"] and not unverified["H3_pass"]
    aborted = r2.evaluate(training, forward, registration_valid=True,
                          invalidation_reason="postponed_draw")
    assert aborted["state"] == "void_or_aborted"
    assert not aborted["H1_pass"] and not aborted["H3_pass"]


def test_full60_h3_can_pass_while_h1_fails(training):
    history = list(training)
    forward = []
    for i, draw in enumerate(future_draws(60)):
        values = r2.scores(history)
        main = min(r2.TICKETS, key=lambda ticket: sum(values[n - 1] for n in ticket))
        draw = replace(draw, main=main)
        forward.append(draw)
        history.append(draw)
    result = r2.evaluate(training, forward, registration_valid=True)
    assert result["n"] == 60
    assert result["H3_pass"] and not result["H1_pass"]
    assert result["H1_failure_note"] == r2.FAILURE_NOTE


def test_csv_and_forward_window_validation(training, tmp_path):
    forward = future_draws(3)
    for invalid in (forward[1:], [forward[0], forward[2]], forward[::-1], future_draws(61)):
        with pytest.raises(ValueError):
            r2.evaluate(training, invalid)
    with pytest.raises(ValueError):
        r2.evaluate(training, forward, late_issues=["26/119"])
    with pytest.raises(ValueError):
        r2.predict(training, "26/117")
    assert r2.follows("26/150", "27/001")
    assert not r2.follows("26/150", "27/002")
    assert not r2.follows("26/150", "28/001")
    csv = tmp_path / "bad.csv"
    csv.write_text("bad,header\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        r2.load_csv(csv)
    with pytest.raises(ValueError):
        replace(training[-1], special=training[-1].main[0])


def test_seeded_adaptive_null_60_draws(training):
    # Whole six-subsets, not independent ball draws; rankings and their exact
    # conditional normalizer are recomputed after every simulated observation.
    rng = np.random.default_rng(20261028)
    paths = 12000
    values = np.tile(np.array(r2.scores(training)), (paths, 1))
    log_e = np.zeros(paths)
    factor_sum = 0.0
    row = np.arange(paths)[:, None]
    for t in range(60):
        order = np.argsort(-values, axis=1, kind="stable")
        sorted_values = np.take_along_axis(values, order, axis=1)
        starts = np.concatenate((np.ones((paths, 1), dtype=bool), np.diff(sorted_values, axis=1) != 0), axis=1)
        ends = np.concatenate((starts[:, 1:], np.ones((paths, 1), dtype=bool)), axis=1)
        positions = np.broadcast_to(np.arange(1, 50), values.shape)
        low = np.maximum.accumulate(np.where(starts, positions, 0), axis=1)
        high = np.minimum.accumulate(np.where(ends, positions, 50)[:, ::-1], axis=1)[:, ::-1]
        ranks = np.empty_like(values)
        np.put_along_axis(ranks, order, (low + high) / 2, axis=1)
        if t in (0, 20, 59):
            for i in range(3):
                assert ranks[i] == pytest.approx(r2.average_ranks(values[i]))
        w = np.exp(0.1 * (25 - ranks) / 6)
        coeff = np.zeros((paths, 7))
        coeff[:, 0] = 1
        for j in range(49):
            for k in range(min(j + 1, 6), 0, -1):
                coeff[:, k] += w[:, j] * coeff[:, k - 1]
        denom = coeff[:, 6] / math.comb(49, 6)
        if t in (0, 20, 59):
            assert denom[0] == pytest.approx(r2.conditional_denominator(ranks[0]))
        selected = np.argpartition(rng.random((paths, 49)), 5, axis=1)[:, :6]
        a = 25 - ranks[row, selected].mean(axis=1)
        increments = 0.1 * a - np.log(denom)
        factor_sum += np.exp(increments).sum()
        log_e += increments
        values *= 2 ** (-1 / 20)
        values[row, selected] += 2 ** (-1 / 20)
    assert factor_sum / (paths * 60) == pytest.approx(1, abs=0.004)
    # Exact one-sided binomial inversion: upper 99.9% confidence bound for the
    # simulated rejection rate must also be below 1/60 (supporting, not proving,
    # the exact conditional martingale argument above).
    rejections = int(np.count_nonzero(log_e >= math.log(60)))
    alpha = 1 / 60
    cdf_at_alpha = math.fsum(math.exp(
        math.lgamma(paths + 1) - math.lgamma(k + 1) - math.lgamma(paths - k + 1)
        + k * math.log(alpha) + (paths - k) * math.log1p(-alpha))
        for k in range(rejections + 1))
    assert cdf_at_alpha < 0.001


def test_two_cli_runs_have_identical_output_hash():
    command = [sys.executable, str(ROOT / "src/marksix_r2.py"), "predict"]
    first = subprocess.check_output(command, cwd=ROOT)
    second = subprocess.check_output(command, cwd=ROOT)
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    output = json.loads(first)
    assert output["target"] == "26/116"
    assert output["H3_tickets"] == [list(t) for t in r2.TICKETS]
    assert output["through"] == "26/115"


def test_registry_includes_explorations_and_full_dissent():
    import csv
    with (ROOT / "registry/attempts.csv").open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    by_id = {row["attempt_id"]: row for row in records}
    assert {"r2-H1", "r2-H3", "explore-24", "explore-blocks", "explore-permutation", "r2-H1-dissent", "reserved-H2"} <= by_id.keys()
    assert all(row["data_sha256"] == r2.DATA_SHA256 for row in records)
    assert by_id["explore-24"]["status"] == "disabled"
    assert "40%" in by_id["r2-H1-dissent"]["notes"]
    assert "76%" in by_id["r2-H1-dissent"]["notes"]
    assert "2.18" in by_id["r2-H1-dissent"]["notes"]
    assert "1.50" in by_id["r2-H1-dissent"]["notes"]
