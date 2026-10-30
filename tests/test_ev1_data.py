"""EV-1 financial provenance/integrity only; no network or model execution."""

import base64
from collections import Counter
import csv
from decimal import Decimal
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data/discovery/ev1"
spec = importlib.util.spec_from_file_location("ev1_parser", REPO / "docs/review-evidence/prepare_ev1.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


@pytest.fixture(scope="module")
def manifest():
    return json.loads((ROOT / "manifest.json").read_text())


@pytest.fixture(scope="module")
def captures():
    return {r["key"]: r for r in json.loads((ROOT / "retrievals.json").read_text())}


@pytest.fixture(scope="module")
def raw(captures):
    out = {}
    for path in sorted((ROOT / "raw").glob("*.jsonl.gz")):
        with gzip.open(path, "rt") as f:
            for line in f:
                r = json.loads(line)
                assert r["key"] not in out
                body = base64.b64decode(r["body_base64"], validate=True)
                meta = captures[r["key"]]
                assert hashlib.sha256(body).hexdigest() == meta["stored_body_sha256"]
                if meta["stored_body_kind"] == "original_http_entity":
                    assert hashlib.sha256(body).hexdigest() == meta["sha256"]
                else:
                    assert json.loads(body)["original_body_sha256"] == meta["sha256"]
                out[r["key"]] = body
    return out


@pytest.mark.parametrize("country,count", [("uk", 700), ("japan", 446), ("hongkong", 69)])
def test_exact_fixed_scope_and_financial_schema(country, count, manifest, captures):
    plan = json.loads((ROOT / "acquisition-plan.json").read_text())
    rows = list(csv.DictReader((ROOT / (country + ".csv")).open()))
    assert len(rows) == count
    assert [(r["issue"], r["draw_date"]) for r in rows] == [tuple(x) for x in plan["scope"][country]]
    assert len({r["issue"] for r in rows}) == count
    assert list(rows[0]) == ev.fields(country)
    data = next(d for d in manifest["datasets"] if d["country"] == country)
    assert data["na_by_column"] == {f: sum(r[f] == "NA" for r in rows) for f in rows[0]}
    assert data["na_cells"] == sum(data["na_by_column"].values())
    for r in rows:
        assert all(v != "" for v in r.values())
        source = captures[r["primary_source_key"]]
        assert source["status"] == 200
        assert source["sha256"] == r["primary_source_sha256"]
        assert source["url"] == r["primary_source_url"]
        assert source["completed_at_utc"] == r["primary_fetched_at_utc"]
        assert r["primary_fetched_at_utc"].endswith("+00:00")
        assert r["announcement_at_utc"] == r["announcement_source_key"] == "NA"
        assert r["full_prize_rule_version"] == "NA"
        reasons = json.loads(r["missing_reasons"])
        for k, v in r.items():
            if v == "NA":
                assert k in reasons
            if k in ("sales", "ticket_price") or re.fullmatch(r"tier\d_(?:winners|payout|reported_prize)", k):
                assert v == "NA" or Decimal(v) >= 0
        scheme = json.loads(r["prize_scheme"])
        assert scheme["drawn_main"] == 6
        assert len(scheme["tiers"]) == ev.TIERS[country]
        for k in range(1, ev.TIERS[country] + 1):
            if r[f"tier{k}_winners"] == "0":
                assert r[f"tier{k}_payout"] == "NA"


def test_manifest_hashes_and_checklists(manifest):
    assert manifest["acquisition_plan_sha256"] == ev.digest((ROOT / "acquisition-plan.json").read_bytes())
    for item in manifest["artifacts"]:
        assert ev.digest((ROOT / item["path"]).read_bytes()) == item["sha256"]
    for d in manifest["datasets"]:
        assert ev.digest((ROOT / d["path"]).read_bytes()) == d["sha256"]
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert ev.digest((ROOT / name).read_bytes()) == expected


def test_every_target_source_body_retained_and_reparses(raw, captures):
    for country in ev.TIERS:
        for r in csv.DictReader((ROOT / (country + ".csv")).open()):
            keys = [r["primary_source_key"], *r["crosscheck_source_keys"].split(";")]
            assert all(k in raw for k in keys)
            assert all(captures[k]["stored_body_kind"] == "original_http_entity" for k in keys)
            if country == "uk":
                primary = ev.parse_uk_mersey(raw[keys[0]])
                secondary = ev.parse_uk_lottery(raw[keys[1]])
                assert secondary["issue"] == r["issue"]
            elif country == "japan":
                primary = ev.parse_jp_official(raw[keys[0]])
            else:
                items = json.loads(raw[keys[0]])["data"]["lotteryDraws"]
                primary = ev.parse_hk_official(next(x for x in items if int(x["no"]) == int(r["issue"].split("/")[1])))
            assert (primary["issue"], primary["date"]) == (r["issue"], r["draw_date"])
            for k in range(1, ev.TIERS[country] + 1):
                for f in ("winners", "payout", "reported_prize"):
                    v = r[f"tier{k}_{f}"]
                    if v != "NA":
                        assert v == primary["tiers"][k][f]
            if r["sales"] != "NA":
                assert r["sales"] == primary["sales"]


def test_conflicts_are_na_without_majority_vote(manifest):
    comparisons = list(csv.DictReader((ROOT / "crosschecks.csv").open()))
    conflict_rows = [r for r in comparisons if r["status"] == "conflict"]
    assert conflict_rows == list(csv.DictReader((ROOT / "conflicts.csv").open()))
    assert len({r["issue"] for r in conflict_rows if r["country"] == "uk"}) == 8
    assert len({r["issue"] for r in conflict_rows if r["country"] == "japan"}) == 5
    for c in ev.TIERS:
        rows = {r["issue"]: r for r in csv.DictReader((ROOT / (c + ".csv")).open())}
        assert dict(Counter(r["status"] for r in comparisons if r["country"] == c)) == manifest["crosscheck_status_counts"][c]
        for r in conflict_rows:
            if r["country"] == c:
                assert rows[r["issue"]][r["field"]] == "NA"
                assert r["primary_value"] != r["secondary_value"]
    uk_sales = [r for r in comparisons if r["country"] == "uk" and r["field"] == "sales"]
    assert len(uk_sales) == 700 and all(r["status"] == "not_comparable" for r in uk_sales)


def test_hk_fractional_units_and_failed_sources(raw, captures):
    official = next(x for x in json.loads(raw["hk_month_05"])["data"]["lotteryDraws"] if x["no"] == 47)
    result = ev.parse_hk_official(official)
    assert result["raw_winning_unit"][3] == "1345"
    assert result["tiers"][3]["winners"] == "134.5"
    assert result["tiers"][3]["payout"] == "25810"
    assert result["tiers"][1]["payout"] == "NA"
    for no in (108, 113, 115):
        meta = captures[f"hk_lottery_{no}"]
        assert meta["status"] == 200
        assert meta["semantic_status"] == "captcha_challenge_not_data_no_bypass"
    assert captures["hk_post_base"]["semantic_status"].startswith("empty_array")
    assert captures["hk_api_base"]["status"] == 400


def test_japanese_official_zero_winner_not_invented_dividend(raw):
    result = ev.parse_jp_official(raw["jp_csv_701"])
    assert result["sales"] == "2178661400"
    assert result["tiers"][1] == {"winners": "0", "reported_prize": "NA", "payout": "NA"}
    assert result["tiers"][2]["payout"] == "58329700"
    with pytest.raises(ValueError):
        ev.parse_jp_official(b"<html>error</html>")


def test_uk_main_sales_not_hotpicks_or_combined_week(raw):
    assert ev.parse_uk_mersey(raw["uk_mw_701"])["sales"] == "21731295"
    assert ev.parse_uk_mersey(raw["uk_mw_1100"])["sales"] == "33952654"
    assert ev.parse_uk_lottery(raw["uk_lottery_1000"])["issue"] == "1000"
    assert ev.parse_uk_mersey(raw["uk_mw_702"])["issue"] == "702"
    assert ev.number("not supplied") == "NA"
    assert ev.number("HK$134.5") == "134.5"


def test_operational_record_not_model_attempt(manifest):
    ledger = json.loads((ROOT / "run-ledger.json").read_text())
    for key in ("models_executed", "candidate_evaluations", "predictions_generated", "new_shadow_ids", "hit_attempts_added"):
        assert ledger[key] == 0
    assert ledger["run_count"] == 1 and ledger["hit_attempts_cumulative"] == 14
    assert ledger["external_sealed_window_opened"] is False
    assert ledger["registry_modified"] is False
    assert manifest["eligible_for_modeling"] is False
    assert manifest["original_publication_verified"] is False
    # Acquisition remains disconnected from the existing candidate data loader.
    assert "ev1" not in (REPO / "data/discovery/access.py").read_text()
