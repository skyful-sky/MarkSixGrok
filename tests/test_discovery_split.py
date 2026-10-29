"""Acquisition/separation tests only; no candidate or distribution analysis."""

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

import pytest


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data/discovery"
MANIFEST = json.loads((DATA / "manifest.json").read_text())
RETRIEVALS = json.loads((DATA / "retrievals.json").read_text())


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCESS = module_at("discovery_access", DATA / "access.py")
PREP = module_at("discovery_acquisition", REPO / "docs/review-evidence/prepare_discovery.py")


@pytest.mark.parametrize("key", ["uk", "japan", "korea"])
def test_actual_discovery_issues_do_not_overlap_sealed_window(key):
    rows = ACCESS.load_discovery(key)
    first, last, pool, start, end = ACCESS.BOUNDS[key]
    # The auditor may compare sealed data; the exploration API below must not open it.
    with (REPO / f"data/external/{key}.csv").open() as stream:
        sealed = list(csv.DictReader(stream))
    assert {r["issue"] for r in rows}.isdisjoint(r["issue"] for r in sealed)
    assert {r["date"] for r in rows}.isdisjoint(r["date"] for r in sealed)
    assert len(sealed) == 700 and first == 701
    assert len(rows) == last - first + 1 <= 1000
    assert (rows[0]["date"], rows[-1]["date"]) == (start, end)
    assert start > sealed[-1]["date"]
    assert [int(r["issue"]) for r in rows] == list(range(first, last + 1))
    assert all(r["status"] == "observed_backup" for r in rows)
    dataset = next(d for d in MANIFEST["datasets"] if d["key"] == key)
    assert dataset["rows"] == len(rows) and dataset["missing_issues"] == []
    assert rows[-1]["date"] < dataset["regime_boundary"]["excluded_from_date"]
    if "excluded_from_issue" in dataset["regime_boundary"]:
        assert last < dataset["regime_boundary"]["excluded_from_issue"]


@pytest.fixture(scope="module")
def reparsed():
    return PREP.normalize(REPO)


@pytest.mark.parametrize("key", ["uk", "japan", "korea"])
def test_discovery_csv_reproduces_from_new_forensic_snapshots(key, reparsed):
    assert PREP.csv_bytes(reparsed[key]) == (DATA / f"{key}.csv").read_bytes()


def test_raw_hashes_urls_and_dataset_provenance():
    assert hashlib.sha256((DATA / "retrievals.json").read_bytes()).hexdigest() == MANIFEST["retrievals_sha256"]
    by_path = {}
    for source in RETRIEVALS:
        assert source["url"].startswith("https://")
        if "raw_path" not in source:
            assert source["error"]
            continue
        path = REPO / source["raw_path"]
        assert any(path.is_relative_to(REPO / root) for root in [
            "docs/review-evidence/discovery-source-snapshots",
            "docs/review-evidence/cal-ext-gap1-rand-v1/source-snapshots"])
        body = path.read_bytes()
        assert hashlib.sha256(body).hexdigest() == source["sha256"]
        original = gzip.decompress(body)
        assert len(original) == source["decompressed_bytes"]
        assert hashlib.sha256(original).hexdigest() == source["decompressed_sha256"]
        by_path[source["raw_path"]] = source
    for dataset in MANIFEST["datasets"]:
        for row in ACCESS.load_discovery(dataset["key"]):
            source = by_path[row["source_snapshot"]]
            assert source["kind"] == dataset["key"]
            assert source["url"] == row["source_url"]
            assert source["url"] in dataset["source_urls"]


def test_all_discovery_files_have_valid_checksums():
    files = {str(p.relative_to(DATA)) for p in DATA.rglob("*")
             if p.is_file() and p.name != "SHA256SUMS" and "__pycache__" not in p.parts}
    listed = set()
    for line in (DATA / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest
        listed.add(name)
    assert files == listed


def test_uk_indices_are_anchored_to_printed_701_and_1700():
    expected = {"2002-09-11": 701, "2012-04-07": 1700}
    sources = [r for r in RETRIEVALS if r["kind"] == "uk_boundary"]
    assert len(sources) == 2
    for source in sources:
        tree = PREP.Tree(gzip.decompress((REPO / source["raw_path"]).read_bytes())).root
        match = re.search(r"The (\d[\d,]*)(?:st|nd|rd|th) Lotto draw", tree.text)
        assert match and int(match[1].replace(",", "")) == expected[source["url"].rsplit("lotto-result-", 1)[1]]


@pytest.mark.parametrize("key", ["uk", "japan", "korea"])
def test_exploration_api_only_opens_allowlisted_discovery_files(monkeypatch, key):
    opened = []
    original = Path.open
    allowed = {(DATA / "manifest.json").resolve(), (DATA / f"{key}.csv").resolve()}

    def guarded(path, *args, **kwargs):
        assert path.resolve() in allowed, f"Exploration read forbidden file: {path}"
        opened.append(path.resolve())
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    rows = ACCESS.load_discovery(key)
    assert rows and set(opened) == allowed


@pytest.mark.parametrize("key", ["uk", "japan", "korea"])
def test_history_returns_neither_target_nor_future_rows(key):
    first, last, *_ = ACCESS.BOUNDS[key]
    assert ACCESS.history_before(key, first) == []
    assert [int(r["issue"]) for r in ACCESS.history_before(key, first + 3)] == [701, 702, 703]
    assert len(ACCESS.history_before(key, last + 1)) == last - first + 1
    for target in [700, last + 2, True]:
        with pytest.raises(ValueError):
            ACCESS.history_before(key, target)


@pytest.mark.parametrize("bad_key", ["../external/uk.csv", "uk.csv", "unknown", "/tmp/uk.csv"])
def test_arbitrary_or_sealed_paths_rejected_before_open(monkeypatch, bad_key):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid dataset key must be rejected before opening any file")
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(ValueError):
        ACCESS.load_discovery(bad_key)


@pytest.fixture
def isolated_discovery(tmp_path, monkeypatch):
    root = tmp_path / "discovery"
    root.mkdir()
    for name in ["manifest.json", "uk.csv"]:
        shutil.copyfile(DATA / name, root / name)
    monkeypatch.setattr(ACCESS, "ROOT", root)
    return root


def test_symlink_to_sealed_csv_is_rejected_without_opening_it(isolated_discovery, monkeypatch):
    root = isolated_discovery
    sealed = REPO / "data/external/uk.csv"
    (root / "uk.csv").unlink()
    (root / "uk.csv").symlink_to(sealed)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.resolve() != sealed.resolve(), "Sealed results must never be opened"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(ValueError, match="allowlist"):
        ACCESS.load_discovery("uk")


def test_manifest_cannot_redirect_to_sealed_data(isolated_discovery):
    p = isolated_discovery / "manifest.json"
    manifest = json.loads(p.read_text())
    manifest["datasets"][0]["path"] = "../external/uk.csv"
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="scope"):
        ACCESS.load_discovery("uk")


def write_temp_rows(root, rows):
    body = PREP.csv_bytes(rows)
    (root / "uk.csv").write_bytes(body)
    p = root / "manifest.json"
    manifest = json.loads(p.read_text())
    manifest["datasets"][0]["sha256"] = hashlib.sha256(body).hexdigest()
    p.write_text(json.dumps(manifest))


@pytest.mark.parametrize("defect", ["sealed", "future", "date", "matrix", "split"])
def test_scope_is_enforced_even_with_recomputed_hash(isolated_discovery, defect):
    with (isolated_discovery / "uk.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    if defect == "sealed":
        rows[0]["issue"] = "700"
    elif defect == "future":
        rows[-1]["issue"] = "1701"
    elif defect == "date":
        rows[-1]["date"] = "2015-10-10"
    elif defect == "matrix":
        rows[10]["main_pool_expected"] = "59"
    else:
        rows[10]["split"] = "holdout"
    write_temp_rows(isolated_discovery, rows)
    with pytest.raises(ValueError):
        ACCESS.load_discovery("uk")


def test_missing_issue_stays_na_without_replacement_or_extension():
    rows = ACCESS.load_discovery("japan")
    aligned = PREP.keep_original_slots("japan", {701: rows[0], 703: rows[2]})
    assert len(aligned) == 446 and aligned[-1]["issue"] == "1146"
    assert aligned[1]["issue"] == "702" and aligned[1]["status"] == "missing"
    assert aligned[2]["issue"] == "703" and aligned[2]["date"] == rows[2]["date"]
    for field in ["date", *[f"n{i}" for i in range(1, 7)], "extra_ball"]:
        assert aligned[1][field] == "NA"


def test_missing_slot_is_retained_in_history_and_cannot_be_imputed(isolated_discovery):
    with (isolated_discovery / "uk.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    for field in ["date", *[f"n{i}" for i in range(1, 7)], "extra_ball"]:
        rows[1][field] = "NA"
    rows[1].update(status="missing", missing_reason="source_issue_not_obtained")
    write_temp_rows(isolated_discovery, rows)
    history = ACCESS.history_before("uk", 704)
    assert [r["issue"] for r in history] == ["701", "702", "703"]
    assert history[1]["n1"] == "NA"
    rows[1]["n1"] = "1"
    write_temp_rows(isolated_discovery, rows)
    with pytest.raises(ValueError, match="imputed"):
        ACCESS.load_discovery("uk")


def test_original_sealed_manifest_and_exposure_status_are_not_reset():
    p = REPO / MANIFEST["sealed_window_manifest_path"]
    assert hashlib.sha256(p.read_bytes()).hexdigest() == MANIFEST["sealed_window_manifest_sha256"]
    assert MANIFEST["candidate_evaluations"] == MANIFEST["distribution_analyses"] == MANIFEST["new_ids"] == 0
    assert MANIFEST["attempts_used"] == 14
    assert MANIFEST["raw_snapshots_analysis_allowed"] is False
    for record in MANIFEST["datasets"]:
        assert record["no_prior_exposure_verified"] is False
        assert record["confirmatory_holdout_eligible"] is False
        assert record["complete_matrix_history_verified"] is False
        assert record["physical_regime_continuity_verified"] is False
