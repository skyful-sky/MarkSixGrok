"""Read-only independent arithmetic audit of the sealed run; no fitting/MC."""
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EV_ROOT = ROOT / "ev/EV-DYN-DILUTE-R1"
RUN = EV_ROOT / "run"


@pytest.fixture(scope="module")
def result():
    return json.loads((RUN / "results.json").read_text())


def test_means_masks_and_sales_forecasts_from_stored_inputs(result):
    scores = [json.loads(s) for s in (RUN / "scores.jsonl").read_text().splitlines()]
    predictions = [json.loads(s) for s in (RUN / "predictions.jsonl").read_text().splitlines()]
    assert len(scores) == len(predictions) == 746
    prediction_index = {(p["country"], p["target_issue"]): p for p in predictions}
    for country, count, last in (("uk", 500, 1400), ("japan", 246, 1146)):
        original = {int(r["issue"]): r for r in csv.DictReader((ROOT / f"data/discovery/ev1/{country}.csv").open())}
        rows = [r for r in scores if r["country"] == country]
        assert [r["issue"] for r in rows] == list(range(901, last + 1))
        fit = json.loads((RUN / (country + "-fits.json")).read_text())
        all_model_scores = {m: [] for m in ("dynamic", "static", "random")}
        cells = 0
        for row in rows:
            source = original[row["issue"]]
            observed = [None if source[f"tier{k}_winners"] == "NA" else float(source[f"tier{k}_winners"]) for k in range(1, 6)]
            assert observed == row["count_values"]
            valid = {str(k + 1) for k, v in enumerate(observed) if v is not None}
            assert len(valid) == row["observed_count_cells"]
            cells += len(valid)
            for model in all_model_scores:
                ll = row["log_probability_by_tier"][model]
                assert set(ll) == valid
                average = sum(ll.values()) / len(ll)
                assert row["scores"][model] == pytest.approx(average, abs=1e-12)
                all_model_scores[model].append(average)
            p = prediction_index[(country, row["issue"])]
            assert p["max_training_issue"] == 900
            for model, fitted in fit["counts"].items():
                assert p["model_parameters"][model] == fitted["values"]
                assert fitted["max_training_issue"] == 900 and fitted["success"]
            sale = fit["sales"]
            weekday = int(date.fromisoformat(source["draw_date"]).weekday() == sale["weekday"])
            beta = sale["beta"]
            expected = math.exp(beta[0] + beta[1] * (row["issue"] - 800.5) / 500 + beta[2] * weekday + sale["residual_mse"] / 2)
            assert p["forecast_entries"] == pytest.approx(expected, rel=1e-12)
        assert result["countries"][country]["observed_count_cells"] == cells
        for model, values in all_model_scores.items():
            assert result["countries"][country]["mean_scores"][model] == pytest.approx(sum(values) / count, abs=1e-12)
        for comparison in (r for r in result["comparisons"] if r["country"] == country):
            baseline = comparison["comparison"].removeprefix("dynamic_vs_")
            expected_gain = sum(a - b for a, b in zip(all_model_scores["dynamic"], all_model_scores[baseline])) / count
            assert comparison["mean_log_score_gain"] == pytest.approx(expected_gain, abs=1e-12)
            assert comparison["bonferroni_p"] == min(1, 4 * comparison["p_value"])
            assert comparison["p_value"] * 10001 == pytest.approx(round(comparison["p_value"] * 10001), abs=1e-8)
            assert comparison["pass_count"] == (comparison["p_value"] <= .0125 and expected_gain > 0 and comparison["lower_9875"] > 0)


def test_paper_configuration_grade_totals_are_per_ticket_not_success_attempts(result):
    scores = [json.loads(s) for s in (RUN / "scores.jsonl").read_text().splitlines()]
    for country in ("uk", "japan"):
        country_result = result["countries"][country]
        for portfolio, totals in country_result["paper_portfolio_grade_counts"].items():
            expected = [0] * 6
            for record in scores:
                if record["country"] == country:
                    grades = record["portfolios_prize_grades"][portfolio]
                    assert len(grades) == 8
                    for grade in grades:
                        expected[grade] += 1
            assert expected == totals
            assert sum(totals) == 8 * country_result["scored_n"]
            financial = country_result["paper_financial_results"][portfolio]
            assert financial["conditional_payout_ratio"] is None
            assert financial["corrected_ratio_lower"] is None and financial["roi_lower"] is None
            assert not financial["passed"]


def test_power_rows_are_prelocked_synthetic_scenarios():
    rows = json.loads((RUN / "power.json").read_text())
    assert len(rows) == 18
    assert {(r["n"], r["jackpot_probability"], r["expected_payout_ratio"]) for r in rows} == {
        (n, p, r) for n in (500, 246) for p in (.01, .001, .0001) for r in (1, 1.1, 1.3)}
    for r in rows:
        assert r["reps"] == 5000
        assert r["rejection_rate"] * 5000 == pytest.approx(round(r["rejection_rate"] * 5000), abs=1e-8)
        se = math.sqrt(r["rejection_rate"] * (1 - r["rejection_rate"]) / 5000)
        assert r["mc_standard_error"] == pytest.approx(se)


def test_record_has_one_run_and_matching_historical_commits(result):
    ledger = json.loads((EV_ROOT / "ledger.json").read_text())
    started = json.loads((RUN / "started.json").read_text())
    assert started["prereg_commit"] == result["prereg_commit"] == "43f1a84ef342f2b789cda00e386877bf691403a2"
    assert started["implementation_commit"] == result["implementation_commit"] == "338c4922ace20bb1f79137e0081139bbe196f6fd"
    assert started["run_count"] == ledger["run_count"] == result["run_count"] == 1
    assert ledger["results_sha256"] == hashlib.sha256((RUN / "results.json").read_bytes()).hexdigest()
    assert ledger["status"] == "archived" and not ledger["passed"]
    assert result["hk_attempts_cumulative"] == 14 and result["hk_attempts_added"] == 0
