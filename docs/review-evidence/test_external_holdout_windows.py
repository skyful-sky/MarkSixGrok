"""Offline document-contract checks only; never import a lottery predictor."""

from copy import deepcopy
from datetime import date
from pathlib import Path
import json

import pytest


ROOT = Path(__file__).resolve().parent
LOCK = json.loads((ROOT / "external-holdout-windows.json").read_text())
SSQ = json.loads((ROOT / "external-ssq-issue-calendar.json").read_text())
EXPECTED_POOLS = {
    "UK historical Lotto6/49": 49,
    "Japan Loto6": 43,
    "Korea Lotto6/45": 45,
    "China SSQ red": 33,
}


def validate_document_window(game, ssq_rows=None):
    """Enforce the documented metadata contract, not evidence authenticity."""
    assert game["main_pool"] == EXPECTED_POOLS[game["lottery"]], "wrong matrix"
    assert game["main_draw_size"] == 6, "wrong draw size"
    all_issues = list(map(str, range(1, 701)))
    if game["lottery"] == "China SSQ red":
        rows = SSQ["rows"] if ssq_rows is None else ssq_rows
        assert len(rows) == 700, "missing or extra issue"
        assert len({r["issue"] for r in rows}) == 700, "duplicate issue"
        assert [r["date"] for r in rows] == sorted({r["date"] for r in rows}), "date sequence"
        all_issues = [r["issue"] for r in rows]
    selected = []
    for phase, first, last, length in [("warmup", 1, 200, 200),
                                       ("holdout", 201, 700, 500)]:
        window = game[phase]
        assert (window["ordinal_start"], window["ordinal_end"]) == (first, last), "wrong ordinal window"
        issues = all_issues[window["ordinal_start"] - 1:window["ordinal_end"]]
        assert len(issues) == length == window["count"], "wrong window length"
        assert issues[0] == window["issue_start"] and issues[-1] == window["issue_end"], "wrong issue boundary"
        assert date.fromisoformat(window["date_start"]) < date.fromisoformat(window["date_end"])
        if game["lottery"] == "China SSQ red":
            assert window["date_start"] == rows[first - 1]["date"]
            assert window["date_end"] == rows[last - 1]["date"]
        selected.append(set(issues))
    assert selected[0].isdisjoint(selected[1]), "overlapping windows"
    assert game["warmup"]["date_end"] < game["holdout"]["date_start"], "date overlap"
    start, end = game["warmup"]["date_start"], game["holdout"]["date_end"]
    for change in game["known_changes"]:
        if change["kind"] == "matrix":
            boundary = change.get("conservative_exclusion_start") or change.get("date")
            if boundary:
                assert end < boundary or start >= boundary, "crosses matrix change"
                if game["main_pool"] == change["old_pool"]:
                    assert end < boundary, "old matrix after exclusion boundary"
                else:
                    assert game["main_pool"] == change["new_pool"] and start >= boundary, "wrong matrix era"


def execution_qualified(game):
    # Unknown provenance is never upgraded by successful structural tests.
    return all(game[key] is True for key in ["official_full700_verified",
                                             "complete_matrix_history_verified",
                                             "no_prior_exposure_verified"])


@pytest.mark.parametrize("index", range(4))
def test_registered_windows_have_200_500_nonoverlapping_periods(index):
    validate_document_window(LOCK["games"][index])


@pytest.mark.parametrize("index", range(4))
def test_unknown_source_and_exposure_never_qualify_execution(index):
    game = LOCK["games"][index]
    assert not execution_qualified(game)
    assert game["execution_eligible"] is False


def test_ssq_actual_year_reset_counts_and_boundaries():
    from collections import Counter
    rows = SSQ["rows"]
    assert Counter(r["issue"][:4] for r in rows) == {
        "2003": 89, "2004": 122, "2005": 153,
        "2006": 154, "2007": 153, "2008": 29}
    assert [(rows[i]["issue"], rows[i]["date"]) for i in [0, 199, 200, 699]] == [
        ("2003001", "2003-02-23"), ("2004111", "2004-12-05"),
        ("2004112", "2004-12-07"), ("2008029", "2008-03-13")]


@pytest.mark.parametrize("defect", ["length", "overlap", "matrix", "change", "after_change"])
def test_invalid_window_metadata_is_rejected(defect):
    game = deepcopy(LOCK["games"][0])
    if defect == "length":
        game["holdout"]["count"] = 499
    elif defect == "overlap":
        game["holdout"]["ordinal_start"] = 200
    elif defect == "matrix":
        game["main_pool"] = 59
    elif defect == "change":
        game["holdout"]["date_end"] = "2015-10-10"
    else:
        game["warmup"].update(date_start="2016-01-01", date_end="2017-01-01")
        game["holdout"].update(date_start="2017-01-02", date_end="2020-01-01")
    with pytest.raises(AssertionError):
        validate_document_window(game)


def test_missing_ssq_draw_cannot_be_replaced_by_ordinal_arithmetic():
    with pytest.raises(AssertionError, match="missing or extra issue"):
        validate_document_window(LOCK["games"][3], SSQ["rows"][:400] + SSQ["rows"][401:])


def test_markdown_and_machine_readable_date_boundaries_agree():
    text = (ROOT.parent / "external-holdout-windows.md").read_text()
    for game in LOCK["games"]:
        for phase in ["warmup", "holdout"]:
            assert game[phase]["date_start"] in text
            assert game[phase]["date_end"] in text


def test_metadata_fixture_has_no_winning_numbers_or_candidate_scores():
    assert all(set(row) == {"issue", "date"} for row in SSQ["rows"])
    assert LOCK["candidate_evaluations"] == LOCK["new_ids"] == 0
    assert LOCK["attempts_used"] == 14
