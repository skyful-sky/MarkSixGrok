"""Source acquisition/integrity only; no models or sealed result reads."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data/discovery/apparatus"
spec = importlib.util.spec_from_file_location("apparatus_acquisition", REPO / "docs/review-evidence/prepare_apparatus.py")
PREP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PREP)


@pytest.fixture(scope="module")
def evidence():
    return PREP.load_evidence()


@pytest.fixture(scope="module")
def reparsed(evidence):
    with (REPO / "data/discovery/uk.csv").open() as stream:
        reference = list(csv.DictReader(stream))
    return PREP.normalize(evidence, reference)


@pytest.fixture(scope="module")
def manifest():
    return json.loads((ROOT / "manifest.json").read_text())


@pytest.mark.parametrize("name", ["uk-lotto-701-1400-apparatus.csv", "japan-loto6-all-setballs.csv",
                                  "japan-loto6-701-onwards-draw-order.csv"])
def test_apparatus_reproduces_from_retained_evidence(name, reparsed, manifest):
    rows = reparsed[0][name]
    body = (ROOT / name).read_bytes()
    assert PREP.csv_bytes(rows) == body
    entry = next(d for d in manifest["datasets"] if d["path"] == name)
    assert hashlib.sha256(body).hexdigest() == entry["sha256"]
    assert len(rows) == entry["rows"]
    assert [int(r["issue"]) for r in rows] == list(range(entry["issue_start"], entry["issue_end"] + 1))
    assert (rows[0]["date"], rows[-1]["date"]) == (entry["date_start"], entry["date_end"])
    assert all(not d["pre_sales_close_availability_verified"] for d in manifest["datasets"])


def test_uk_date_alignment_and_unresolved_ball_set(reparsed):
    rows = reparsed[0]["uk-lotto-701-1400-apparatus.csv"]
    assert all(r["date"] < "2026-01-01" and r["machine"] != "NA" for r in rows)
    assert [int(r["issue"]) for r in rows if r["ball_set"] == "NA"] == [1322]
    conflict = next(r for r in rows if r["issue"] == "1322")
    assert conflict["mersey_ball_set"] == "1" and conflict["lottery_co_uk_ball_set"] == "5"
    assert conflict["machine"] == "Sapphire"


def test_three_full_range_japanese_sources_and_no_majority_vote(reparsed, evidence):
    tatuo = PREP.parse_tatuo(evidence["tatuo_set"])
    umiduki = PREP.parse_umiduki(evidence["umiduki_2150"])
    assert set(tatuo) == set(umiduki) == set(range(1, 2151))
    rows = reparsed[0]["japan-loto6-all-setballs.csv"]
    assert len([r for r in rows if r["ball_set"] == "NA"]) == 25
    for r in rows:
        valid = [r[f"{s}_label"] for s in ("tatuo", "loto6_jp", "umiduki", "psshc", "hpfree")
                 if r[f"{s}_label"] != "NA"]
        if len(set(valid)) > 1:
            assert r["ball_set"] == "NA" and r["status"] == "conflict"
        elif r["ball_set"] != "NA":
            assert len(valid) >= 2 and set(valid) == {r["ball_set"]}
        assert r["physical_set_id"] == r["machine_id"] == "NA"
    # Two sites agree on A, two on J: never silently select a side.
    r = next(r for r in rows if r["issue"] == "2149")
    assert r["tatuo_raw"] == r["umiduki_raw"] == "A"
    assert r["loto6_jp_raw"] == r["hpfree_raw"] == "J"
    assert r["ball_set"] == "NA"
    assert reparsed[1] == [{"printed_issue": 12923, "reason": "outside_snapshot_range_do_not_repair"}]


def test_claimed_orders_keep_conflicts_and_single_source_status(reparsed):
    rows = reparsed[0]["japan-loto6-701-onwards-draw-order.csv"]
    assert [int(r["issue"]) for r in rows if r["draw_1"] == "NA"] == [1519, 1758, 2007]
    assert sum(r["status"] == "single_nonofficial_source" for r in rows) == 520
    assert sum(r["status"] == "crosschecked_nonofficial" for r in rows) == 927
    for r in rows:
        assert r["official_order_verified"] == "false"
        if r["draw_1"] == "NA":
            assert all(r[f"draw_{i}"] == "NA" for i in range(1, 7))
            assert r["bonus"] == "NA"
        else:
            assert PREP.valid_order([int(r[f"draw_{i}"]) for i in range(1, 7)] + [int(r["bonus"])])


def test_old_japanese_results_removed_before_persistence(evidence):
    for start in range(1, 701, 100):
        rows = json.loads(evidence[f"jp_{start}"])["data"]
        assert rows and all(set(r) == {"id", "date", "setball", "setball_id", "stage_id"} for r in rows)
        assert all(1 <= int(r["id"]) <= 700 for r in rows)
    oldest = json.loads(evidence["hpfree_oldest"])["metadata_rows"]
    assert oldest and all(set(r) == {"label"} for r in oldest.values())
    uk = json.loads(evidence["mersey_csv"])
    assert len(uk["metadata_rows"]) == 700
    assert all(set(r) == {"issue", "date", "machine", "ball_set"} for r in uk["metadata_rows"])
    assert all(701 <= r["issue"] <= 1400 for r in uk["metadata_rows"])
    assert uk["excluded_2026_or_later_rows"] == 127


def test_retrieval_provenance_and_hashes(evidence, manifest):
    retrievals = json.loads((ROOT / "retrievals.json").read_text())
    assert len(retrievals) == 782
    for r in retrievals:
        assert r["url"].startswith(("https://", "http://"))
        assert r["downloaded_at_utc"].endswith("+00:00")
        if "bundle_path" in r:
            assert r["bundle_key"] == r["key"]
            assert hashlib.sha256(evidence[r["key"]]).hexdigest() == r["stored_sha256"]
            assert len(evidence[r["key"]]) == r["stored_bytes"]
            if r["content_projection"].startswith("none;"):
                assert r["stored_sha256"] == r["sha256"]
        else:
            assert r["error"]
    for entry in manifest["evidence"]:
        assert hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("columns,values", [("Machine,Set", "Merlin,3"), ("Set,Machine", "3,Merlin")])
def test_named_column_mapping_survives_machine_set_reordering(columns, values):
    body = f"<pre>No.,DD,MMM,YYYY,{columns}\n701,11,Sep,2002,{values}\n3219,28,Oct,2026,{values}\n3219,28,Oct,2026,{values}\n</pre>".encode()
    projected = PREP.project_uk_mersey(body)
    assert projected["metadata_rows"] == [dict(issue=701, date="2002-09-11", machine="Merlin", ball_set="3")]
    assert projected["excluded_2026_or_later_rows"] == 2


def test_duplicate_target_draw_cannot_silently_collapse_rounds():
    body = b"<pre>No.,DD,MMM,YYYY,Machine,Set\n701,11,Sep,2002,Merlin,3\n701,11,Sep,2002,Arthur,4\n</pre>"
    with pytest.raises(ValueError, match="Duplicate target UK issue"):
        PREP.project_uk_mersey(body)


def test_empty_label_preserves_slot_and_normalization_is_explicit():
    body = '<table class="ysotable22"><tr><td>第1回～第3回</td></tr><tr><td>A</td><td></td><td>j</td></tr></table>'.encode()
    assert PREP.parse_tatuo(body) == {1: "A", 2: "", 3: "j"}
    assert PREP.letter("") == PREP.letter("円") == "NA"
    assert PREP.letter("Ａ") == "A" and PREP.letter("Ⅾ") == "D"
    assert PREP.consensus(["A", "A", "J"]) == ("NA", "conflict")


def test_duplicate_hpfree_issue_is_preserved_as_ambiguity():
    body = ('<table><tr><th>第1758回</th><td>Iセット</td>' + '<td>01</td>' * 7 + '</tr>'
            '<tr><th>第1758回</th><td>Jセット</td>' + '<td>02</td>' * 7 + '</tr></table>').encode()
    row = PREP.parse_hpfree(body)[1758]
    assert row["label"] == "I|J" and row["order"] == [] and row["source_issue_conflict"]


def test_apparatus_not_accepted_by_existing_discovery_access(monkeypatch):
    spec = importlib.util.spec_from_file_location("old_discovery_access", REPO / "data/discovery/access.py")
    access = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(access)
    def forbidden(*args, **kwargs):
        pytest.fail("Unregistered metadata dataset must be rejected before reading a file")
    monkeypatch.setattr(Path, "open", forbidden)
    for key in ("apparatus", "japan-loto6-all-setballs", "apparatus/japan-loto6-all-setballs.csv"):
        with pytest.raises(ValueError):
            access.load_discovery(key)


def test_id_history_does_not_assert_physical_continuity():
    history = json.loads((ROOT / "id-history.json").read_text())
    assert history["physical_id_continuity_verified"] is False
    assert len(history["uk_observed_label_spans"]) == 24
    assert all(r["verification"] == "secondary_report_only_not_officially_verified"
               for r in history["japan_reported_changes"])
    assert [r["issue"] for r in history["japan_reported_changes"]] == [138, 649, 1367, 336, 944, 1768]
