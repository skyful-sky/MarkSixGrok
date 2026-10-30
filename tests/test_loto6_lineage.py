"""Physical lineage/source semantics and metadata counts; no outcome analysis."""

import base64
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data/discovery/apparatus/lineage"
spec = importlib.util.spec_from_file_location("lineage_prep", REPO / "docs/review-evidence/prepare_loto6_lineage.py")
PREP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PREP)


@pytest.fixture(scope="module")
def rows():
    with (ROOT.parent/"japan-loto6-all-setballs.csv").open() as stream:
        return list(csv.DictReader(stream))


@pytest.fixture(scope="module")
def sources():
    return json.loads((ROOT/"sources.json").read_text())


@pytest.fixture(scope="module")
def bodies():
    return {r["key"]: base64.b64decode(r["body_base64"], validate=True)
            for r in map(json.loads, gzip.decompress((ROOT/"source-bodies.jsonl.gz").read_bytes()).splitlines())}


def test_eligibility_stops_without_official_physical_lineage(rows):
    decision = json.loads((ROOT/"decision.json").read_text())
    assert decision["stable_A_to_J_physical_identity_established"] is False
    assert decision["official_physical_lineage_verified"] is False
    assert decision["ballset_lineage_calibration_allowed"] is False
    assert decision["qualified_same_physical_generation_intervals"] == []
    assert decision["qualified_periods"] == 0
    assert decision["qualified_label_counts"] == {k: 0 for k in "ABCDEFGHIJ"}
    assert decision["attempts_used"] == 14
    assert decision["models_executed"] == decision["calibrations_executed"] == decision["new_ids"] == 0
    assert decision["source_metadata_sha256"] == hashlib.sha256((ROOT.parent/"japan-loto6-all-setballs.csv").read_bytes()).hexdigest()
    assert len(PREP.inventory(rows, 701, 1146)["label_counts"]) == 10


def test_inventory_counts_do_not_widen_original_discovery(rows):
    inventories = json.loads((ROOT/"label-inventory.json").read_text())
    for entry in inventories.values():
        stage = None if entry["source_stage_id"] == "all" else entry["source_stage_id"]
        assert entry == PREP.inventory(rows, entry["issue_start"], entry["issue_end"], stage)
        assert sum(entry["label_counts"].values()) + entry["NA"] == entry["rows"]
        assert entry["physical_lineage_verified"] is False
        assert entry["eligible_physical_calibration_rows"] == 0
    original = inventories["original_discovery_701_1146"]
    assert original["rows"] == 446 and original["issue_end"] == 1146
    assert list(original["label_counts"].values()) == [53, 44, 46, 43, 45, 46, 42, 40, 45, 42]
    assert inventories["original_discovery_source_stage1"]["rows"] == 412
    assert inventories["original_discovery_source_stage2"]["rows"] == 34
    assert inventories["apparatus_metadata_701_2150"]["rows"] == 1450


def test_all_source_category_boundaries_retained_without_venue_inference(rows):
    with (ROOT/"venue-category-runs.csv").open() as stream:
        stored = list(csv.DictReader(stream))
    actual = PREP.stage_runs(rows)
    assert len(stored) == len(actual) == 91
    assert sum(int(r["rows"]) for r in stored) == 1450
    assert int(stored[0]["first_issue"]) == 701 and int(stored[-1]["last_issue"]) == 2150
    for a, b in zip(stored, actual):
        assert a == {k: str(v) for k, v in b.items()}
        assert a["official_actual_venue_verified"] == "False"
    assert all(a["last_issue"]+1 == b["first_issue"] for a, b in zip(actual, actual[1:]))


def test_official_schedule_and_date_do_not_certify_physical_update(sources):
    with (ROOT/"events.csv").open() as stream:
        events = list(csv.DictReader(stream))
    assert len(events) == 11
    official = [r for r in events if r["official_event_source_key"] != "NA"]
    assert {(r["issue_start"], r["issue_end"]) for r in official} == {("921", "922"), ("944", "945")}
    assert all(r["topic"] == "venue_schedule" for r in official)
    updates = [r for r in events if r["topic"] == "ballset_update"]
    assert len(updates) == 5
    assert all(r["event_verification"] == "未見官方公開" and r["official_event_source_key"] == "NA" for r in updates)
    assert all(r["physical_lineage_verified"] == "False" for r in events)
    by_key = {r["key"]: r for r in sources}
    for event in events:
        for field in ("official_event", "auxiliary", "official_date_only"):
            key = event[field+"_source_key"]
            if key != "NA":
                assert event[field+"_source_url"] == by_key[key]["url"]
                assert event[field+"_downloaded_at_utc"] == by_key[key]["downloaded_at_utc"]
    date_only = next(r for r in updates if r["issue_start"] == "138")
    assert date_only["official_date_only_source_key"] == "mizu_date_138"
    assert date_only["event_verification"] == "未見官方公開"


def test_source_hashes_and_original_vs_projection_are_distinct(sources, bodies):
    assert len(sources) == 38 and len({r["key"] for r in sources}) == 38
    for source in sources:
        assert source["supports_verified_physical_lineage"] is False
        if "stored_sha256" in source:
            body = bodies[source["key"]]
            assert hashlib.sha256(body).hexdigest() == source["stored_sha256"]
            assert len(body) == source["stored_bytes"]
            assert source["downloaded_at_utc"].endswith("+00:00")
            if source["content_projection"].startswith("none;"):
                assert source["stored_sha256"] == source["sha256"]
        else:
            assert source["error"] and source["semantic_status"] == "network_failure"
    by_key = {r["key"]: r for r in sources}
    assert by_key["news_2019apr"]["status"] == 200
    assert by_key["news_2019apr"]["semantic_status"] == "soft_not_found"
    assert by_key["mizu_date1367_detail"]["semantic_status"] == "empty_draw_table_not_date_evidence"


def test_old_official_date_pages_retain_no_results(bodies):
    for key, target in [("mizu_date_138", {"issue": 138, "date": "2003-06-05"}),
                        ("mizu_date_336", {"issue": 336, "date": "2007-03-29"})]:
        entries = json.loads(bodies[key])["issue_dates_only"]
        assert target in entries
        assert all(set(r) == {"issue", "date"} for r in entries)


@pytest.mark.parametrize("status,kind,body,expected", [
    (200, "application/pdf", b"<title>NOT FOUND</title>", "soft_not_found"),
    (200, "application/pdf", b"<title>Other HTML</title>", "wrong_content_type_not_pdf"),
    (200, "text/html", "<p>過去の当せん番号案内()</p>".encode(), "empty_draw_table_not_date_evidence"),
    (404, "text/html", b"<title>Fake success</title>", "http_failure"),
])
def test_http200_and_a_url_suffix_never_count_as_verification(status, kind, body, expected):
    assert PREP.inspect_response(status, kind, body) == expected
