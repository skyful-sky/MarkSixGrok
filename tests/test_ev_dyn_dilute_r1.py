"""Independent small-universe checks; never refit or rerun the real R1."""

import hashlib
import importlib.util
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import nbinom


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ev_r1", ROOT / "src/ev_dyn_dilute_r1.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
EV_HOME = ROOT / "ev/EV-DYN-DILUTE-R1"
CFG = json.loads((EV_HOME / "lock.json").read_text())["spec"]


def test_exact_weighted_tiers_against_full_small_universe():
    n = 9
    weights = np.array([1.1, 2.3, 5.7, 7.8, 11.9, 13.1, 19.2, 23.6, 28.1])
    main, bonus = [1, 2, 3, 4, 5, 6], 7
    expected, z = np.zeros(5), 0
    for ticket in combinations(range(1, n + 1), 6):
        mass = math.prod(weights[i - 1] for i in ticket)
        z += mass
        grade = ev.grade(ticket, main, bonus)
        if grade:
            expected[grade - 1] += mass
    assert np.allclose(ev.preference_tiers(weights, [main], [bonus])[0], expected / z, rtol=1e-12)
    assert np.allclose(ev.preference_tiers(np.ones(n), [main], [bonus])[0], ev.uniform_tiers(n), rtol=1e-12)


def test_nb_includes_zero_and_matches_independent_distribution():
    y, mu, shape = np.array([0, 1, 40, 4000]), np.array([.2, 2, 25, 5000]), np.array([.8, 3, 12, 40])
    expected = nbinom.logpmf(y, shape, shape / (shape + mu))
    assert np.allclose(ev.nb_logpmf(y, mu, shape), expected, rtol=1e-10, atol=1e-10)
    assert np.isfinite(ev.nb_logpmf(np.array([0]), np.array([3]), np.array([30]))).all()


def test_complex_step_probability_gradient_matches_central_difference():
    main, bonus, issue = [[1, 4, 12, 24, 38, 49]], [20], np.array([901])
    values = np.r_[[.2, -.1, .3, -.15, .4, -.2], np.full(5, np.log(30))]
    def fun(x):
        return ev.probabilities(x, "dynamic", 49, main, bonus, issue, CFG)[0, 3]
    for k in range(6):
        xc = values.astype(complex)
        xc[k] += 1e-20j
        derivative = fun(xc).imag / 1e-20
        xp, xm = values.copy(), values.copy()
        xp[k] += 1e-5
        xm[k] -= 1e-5
        finite = (fun(xp) - fun(xm)) / 2e-5
        assert derivative == pytest.approx(finite, rel=1e-6, abs=1e-10)


def test_greedy_matches_full_enumeration_and_has_no_overlap_cap():
    weights = np.array([1.1, 2.3, 5.7, 7.8, 11.9, 13.1, 19.2, 23.6, 28.1])
    expected = sorted(combinations(range(1, 10), 6), key=lambda t: (math.prod(weights[i - 1] for i in t), t))[:8]
    assert ev.greedy(weights) == [list(t) for t in expected]
    assert max(len(set(a) & set(b)) for a, b in combinations(expected, 2)) > 2


@pytest.mark.parametrize("pool", [43, 49])
def test_portfolio_templates_are_fixed_distinct_six_sets(pool):
    tickets = ev.template(list(range(1, pool + 1)))
    assert len(tickets) == len({tuple(t) for t in tickets}) == 8
    assert all(len(t) == len(set(t)) == 6 and min(t) >= 1 and max(t) <= pool for t in tickets)
    if pool == 43:
        assert len(set(sum(tickets, []))) == 43
    else:
        assert len(set(sum(tickets, []))) == 48 and all(49 not in t for t in tickets)


def test_forecast_does_not_read_target_outcomes_or_sales():
    training = [dict(issue=701 + i, date="2012-10-11", sales=2e9 + i * 10000, ticket_price=200) for i in range(200)]
    fitted = ev.fit_sales(training, 0, CFG)
    target = dict(issue=901, date="2014-10-11")
    a = ev.forecast_entries(fitted, target, CFG)
    assert a == ev.forecast_entries(fitted, dict(target, sales=1e99, counts=[999] * 5, main=[1] * 6), CFG)
    assert fitted["max_training_issue"] == 900


def test_reveal_requires_persisted_untampered_prior_training_receipt(tmp_path):
    broker = object.__new__(ev.SourceBroker)
    broker.cfg = CFG
    broker._outcome = lambda country, issue: (country, issue)
    journal = tmp_path / "journal.jsonl"
    with pytest.raises(FileNotFoundError):
        broker.reveal("uk", 901, journal, 0, "0" * 64)
    pred = dict(country="uk", target_issue=901, max_training_issue=900)
    offset, digest = ev.append_prediction(journal, pred)
    assert broker.reveal("uk", 901, journal, offset, digest) == ("uk", 901)
    with pytest.raises(ValueError, match="SHA"):
        broker.reveal("uk", 901, journal, offset, "0" * 64)
    offset, digest = ev.append_prediction(journal, dict(pred, max_training_issue=902))
    with pytest.raises(ValueError, match="leakage"):
        broker.reveal("uk", 901, journal, offset, digest)


def test_bootstrap_null_zero_and_four_comparison_direction():
    config = dict(CFG, bootstrap_reps=199, minimum_score_periods=20)
    null = ev.block_comparison(np.zeros(40), ev.rng(20261030, 20), config)
    assert null["p_value"] == 1 and not null["pass_count"]
    gains = np.tile([.8, .9, 1.0, 1.1, 1.2], 8)
    result = ev.block_comparison(gains, ev.rng(20261030, 20), config)
    assert result["mean_log_score_gain"] == pytest.approx(1)
    assert result["lower_9875"] > 0 and result["pass_count"]
    assert result["bonferroni_p"] == 4 * result["p_value"]
    negative = ev.block_comparison(-gains, ev.rng(20261030, 20), config)
    assert not negative["pass_count"]


def test_na_financial_contract_is_not_zero_or_positive_ev():
    gate = ev.financial_gate([dict(original_announcement="NA", legal_version="NA")])
    assert gate["conditional_payout_ratio"] is None and gate["roi_lower"] is None
    assert not gate["passed"]
    assert gate["missing_original_announcement"] == gate["missing_complete_legal_version"] == 1


def test_power_is_synthetic_and_seeded_not_real_run():
    cfg = dict(CFG, power=dict(CFG["power"], n=[50], p=[.01], ratio=[1, 1.1], reps=100))
    assert ev.power_diagnostic(cfg) == ev.power_diagnostic(cfg)
    results = ev.power_diagnostic(cfg)
    assert len(results) == 2
    assert all(0 <= r["rejection_rate"] <= 1 for r in results)
    assert results[0]["interpretation"] == "type_I_diagnostic"


def test_synthetic_optimizer_handles_missing_cells_and_observed_zero():
    # Artificial9-ball universe, never a UK/JP fit or an extra registered run.
    training = [dict(issue=701 + i, date="2000-01-01", main=[1, 2, 3, 4, 5, 6],
                     bonus=7, sales=100, ticket_price=1, counts=[0, 1, 2, 3, None]) for i in range(20)]
    fit = ev.fit_count(training, "dynamic", 9, CFG)
    assert fit["success"], fit["message"]
    assert fit["observed_training_cells"] == 80
    assert fit["missing_training_cells"] == 20
    assert np.isfinite(fit["values"]).all()


def test_locked_input_hashes_and_prereg_are_unchanged():
    lock = json.loads((EV_HOME / "lock.json").read_text())
    assert lock["spec_sha256"] == ev.sha(ev.canonical(CFG))
    assert ev.sha((ROOT / lock["prereg_path"]).read_bytes()) == lock["prereg_sha256"]
    for name, expected in lock["inputs_sha256"].items():
        assert name.startswith("data/discovery/ev1/")
        assert ev.sha((ROOT / name).read_bytes()) == expected


def test_real_run_artifacts_if_already_sealed():
    run = EV_HOME / "run"
    if not (run / "sealed.json").exists():
        pytest.skip("One real run not started; unit tests must not create it")
    sealed = json.loads((run / "sealed.json").read_text())
    for name, digest in sealed["files_sha256"].items():
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
    result = json.loads((run / "results.json").read_text())
    assert result["run_count"] == 1 and result["status"] == "archived"
    assert result["hk_attempts_cumulative"] == 14 and result["hk_attempts_added"] == 0
    assert result["conditional_payout_ratio"] is None and not result["positive_ev"]
    assert len(result["comparisons"]) == 4
    predictions = {int(offset): line for offset, line in _journal_offsets(run / "predictions.jsonl")}
    for line in (run / "scores.jsonl").read_text().splitlines():
        row = json.loads(line)
        raw = predictions[row["prediction_offset"]]
        assert ev.sha(raw) == row["prediction_sha256"]
        p = json.loads(raw)
        assert p["target_issue"] == row["issue"] and p["max_training_issue"] == 900
        assert p["max_training_issue"] < p["target_issue"]


def _journal_offsets(path):
    with path.open("rb") as f:
        while True:
            offset = f.tell()
            line = f.readline()
            if not line:
                break
            yield offset, line.removesuffix(b"\n")
