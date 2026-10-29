"""Offline integrity/provenance checks; no candidate imports or scoring."""

from copy import deepcopy
import csv
from datetime import date
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/external"
MANIFEST = json.loads((DATA / "manifest.json").read_text())
LOCK = json.loads((ROOT / "docs/review-evidence/external-holdout-windows.json").read_text())
RETRIEVALS = json.loads((DATA / "retrievals.json").read_text())
SPEC = importlib.util.spec_from_file_location("external_source_normalizer", DATA / "normalize.py")
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)


def read_rows(key):
    with (DATA / f"{key}.csv").open(newline="") as stream:
        return list(csv.DictReader(stream))


def check_window(rows, registration):
    assert len(rows) == 700, "missing/replaced fixed-window slot"
    assert [int(r["ordinal"]) for r in rows] == list(range(1, 701))
    assert len({r["issue"] for r in rows}) == 700, "duplicate issue"
    known_dates = [r["date"] for r in rows if r["date"] != "NA"]
    assert known_dates == sorted(set(known_dates)), "duplicate/reordered date"
    for phase, part in [("warmup", rows[:200]), ("holdout", rows[200:])]:
        lock = registration[phase]
        assert len(part) == lock["count"] == (200 if phase == "warmup" else 500)
        assert all(r["phase"] == phase for r in part), "wrong partition"
        assert part[0]["issue"] == lock["issue_start"]
        assert part[-1]["issue"] == lock["issue_end"]
        assert part[0]["date"] == lock["date_start"], "shifted start"
        assert part[-1]["date"] == lock["date_end"], "shifted end"
    main_fields = [f"n{i}" for i in range(1, 7)]
    missing = []
    for r in rows:
        if r["date"] != "NA":
            date.fromisoformat(r["date"])
        assert int(r["main_pool_expected"]) == registration["main_pool"], "wrong expected matrix"
        if r["status"] == "missing":
            # All absent main-ball fields remain explicit NA, never zero/previous draw.
            assert all(r[k] == "NA" for k in main_fields + ["extra_ball"])
            missing.append(r["issue"])
            continue
        assert r["status"] == "observed_backup"
        numbers = [int(r[k]) for k in main_fields]
        assert numbers == sorted(set(numbers)), "invalid main-six set"
        assert all(1 <= n <= registration["main_pool"] for n in numbers), "outside matrix"
        extra = int(r["extra_ball"])
        if registration["lottery"] == "China SSQ red":
            assert 1 <= extra <= 16  # blue may have the same value as a red ball
        else:
            assert 1 <= extra <= registration["main_pool"] and extra not in numbers
        assert r["source_url"].startswith("https://") and r["raw_path"].startswith("raw/")
        for change in registration["known_changes"]:
            if change["kind"] == "matrix":
                boundary = change.get("conservative_exclusion_start") or change.get("date")
                if boundary and registration["main_pool"] == change["old_pool"]:
                    assert r["date"] != "NA" and r["date"] < boundary, "old matrix outside era"
    return missing


@pytest.mark.parametrize("index", range(4))
def test_downloaded_data_match_fixed_200_500_windows_and_matrix_values(index):
    dataset = MANIFEST["datasets"][index]
    rows = read_rows(dataset["key"])
    assert check_window(rows, LOCK["games"][index]) == dataset["missing_main_issues"] == []
    assert sum(r["status"] == "observed_backup" for r in rows) == 700
    if dataset["key"] != "ssq":
        assert [int(r["issue"]) for r in rows] == list(range(1, 701))
    else:
        calendar = json.loads((ROOT / "docs/review-evidence/external-ssq-issue-calendar.json").read_text())
        assert [{"issue": r["issue"], "date": r["date"]} for r in rows] == calendar["rows"]


@pytest.fixture(scope="module")
def reparsed():
    return NORMALIZER.normalize(DATA)


@pytest.mark.parametrize("key", ["uk", "japan", "korea", "ssq"])
def test_every_csv_is_reproducible_from_archived_http_bodies(key, reparsed):
    assert NORMALIZER.csv_bytes(reparsed[key]) == (DATA / f"{key}.csv").read_bytes()


def test_download_manifest_hashes_and_per_row_provenance():
    assert hashlib.sha256((DATA / "retrievals.json").read_bytes()).hexdigest() == MANIFEST["retrievals_sha256"]
    by_path = {r["raw_path"]: r for r in RETRIEVALS if "raw_path" in r}
    for source in RETRIEVALS:
        assert source["url"].startswith("https://") and source["retrieved_at_utc"].endswith("+00:00")
        if "raw_path" in source:
            body = (DATA / source["raw_path"]).read_bytes()
            assert hashlib.sha256(body).hexdigest() == source["sha256"]
            original = gzip.decompress(body)
            assert len(original) == source["decompressed_bytes"]
            assert hashlib.sha256(original).hexdigest() == source["decompressed_sha256"]
        else:
            assert source["error"]  # failed HTTP/SSL is never a successful archive
    for dataset in MANIFEST["datasets"]:
        assert hashlib.sha256((DATA / dataset["path"]).read_bytes()).hexdigest() == dataset["sha256"]
        for row in read_rows(dataset["key"]):
            source = by_path[row["raw_path"]]
            assert source["url"] == row["source_url"]
            assert row["source_url"] in dataset["source_urls"]
            assert source["kind"] == dataset["key"]  # official/latest-only response cannot enter


def test_all_data_files_are_covered_by_checksum_list():
    expected = {str(p.relative_to(DATA)) for p in DATA.rglob("*")
                if p.is_file() and p.name != "SHA256SUMS" and "__pycache__" not in p.parts}
    listed = set()
    for line in (DATA / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        assert hashlib.sha256((DATA / path).read_bytes()).hexdigest() == digest
        listed.add(path)
    assert listed == expected


def test_uk_chronological_indices_match_four_printed_draw_boundaries():
    expected = {"1994-11-19": 1, "1997-11-22": 200, "1997-11-26": 201, "2002-09-07": 700}
    sources = [r for r in RETRIEVALS if r["kind"] == "uk_boundary"]
    assert len(sources) == 4
    for source in sources:
        day = source["url"].rsplit("lotto-result-", 1)[1]
        tree = NORMALIZER.Tree(gzip.decompress((DATA / source["raw_path"]).read_bytes())).root
        match = re.search(r"The (\d+)(?:st|nd|rd|th) Lotto draw", tree.text)
        assert match and int(match[1]) == expected[day]


def test_japan_reported_order_is_permutation_and_remains_unverified():
    for row in read_rows("japan"):
        assert sorted(map(int, row["reported_main_order"].split())) == [int(row[f"n{i}"]) for i in range(1, 7)]
        assert row["reported_ball_set"] != "NA"
        assert row["physical_fields_verification"] == "unverified"
        assert row["reported_machine"] == "NA"


@pytest.mark.parametrize("defect", ["drop", "duplicate", "pool", "partition", "date", "unsorted"])
def test_bad_or_changed_data_cannot_pass_integrity_checks(defect):
    rows = deepcopy(read_rows("uk"))
    if defect == "drop":
        rows.pop(300)
    elif defect == "duplicate":
        rows[300]["issue"] = rows[299]["issue"]
    elif defect == "pool":
        rows[300]["n6"] = "59"
    elif defect == "partition":
        rows[200]["phase"] = "warmup"
    elif defect == "date":
        rows[-1]["date"] = "2015-10-10"
    else:
        rows[300]["n1"], rows[300]["n2"] = rows[300]["n2"], rows[300]["n1"]
    with pytest.raises(AssertionError):
        check_window(rows, LOCK["games"][0])


def test_na_keeps_original_issue_but_never_counts_as_observed_or_qualified():
    rows = deepcopy(read_rows("uk"))
    issue = rows[300]["issue"]
    for field in [*[f"n{i}" for i in range(1, 7)], "extra_ball", "date"]:
        rows[300][field] = "NA"
    rows[300]["status"] = "missing"
    assert check_window(rows, LOCK["games"][0]) == [issue]
    assert len(rows) == 700 and rows[300]["issue"] == issue
    assert sum(r["status"] == "observed_backup" for r in rows[200:]) == 499
    # Inventing even one replacement ball is invalid for an absent draw.
    rows[300]["n1"] = "3"
    with pytest.raises(AssertionError):
        check_window(rows, LOCK["games"][0])


def test_complete_backup_is_not_official_regime_or_unexposed_qualification():
    for game, dataset in zip(LOCK["games"], MANIFEST["datasets"]):
        assert dataset["warmup"] == game["warmup"] and dataset["holdout"] == game["holdout"]
        assert dataset["known_changes"] == game["known_changes"]
        assert dataset["backup_continuity_verified"] is True
        assert dataset["observed_values_match_expected_matrix"] is True
        for flag in ["official_full700_verified", "complete_matrix_history_verified",
                     "physical_fields_officially_verified", "no_prior_exposure_verified", "execution_eligible"]:
            assert dataset[flag] is False
    assert MANIFEST["candidate_evaluations"] == MANIFEST["new_ids"] == 0
    assert MANIFEST["attempts_used"] == 14
