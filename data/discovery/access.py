"""Allowlisted discovery data access only; no model, prediction or scoring.

This API is an application guardrail, not an OS sandbox or a way to undo
prior exposure. Sealed results and forensic raw captures are never inputs.
"""

import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BOUNDS = {
    "uk": (701, 1700, 49, "2002-09-11", "2012-04-07"),
    "japan": (701, 1146, 43, "2012-10-11", "2017-02-06"),
    "korea": (701, 835, 45, "2016-05-07", "2018-12-01"),
    "ssq": (701, 792, 33, "2008-03-16", "2008-10-14"),
}


def ordinal(key, row):
    """SSQ keeps its original year-prefixed issue alongside global ordinal."""
    return int(row["ordinal"] if key == "ssq" else row["issue"])


def local_file(name):
    """Reject symlinks leaving this directory before any file is opened."""
    path = ROOT / name
    resolved = path.resolve()
    if resolved.parent != ROOT.resolve() or resolved.name != name:
        raise ValueError("File outside discovery allowlist")
    return resolved


def load_discovery(key):
    if key not in BOUNDS:
        raise ValueError("Unknown discovery dataset; arbitrary paths are forbidden")
    first, last, pool, start_date, end_date = BOUNDS[key]
    manifest = json.loads(local_file("manifest.json").read_bytes())
    matches = [r for r in manifest["datasets"] if r["key"] == key]
    if len(matches) != 1:
        raise ValueError("Missing/duplicate dataset registration")
    record = matches[0]
    if (record["path"] != f"{key}.csv" or record.get("ordinal_start", record["issue_start"]) != first
            or record.get("ordinal_end", record["issue_end"]) != last or record["main_pool_expected"] != pool):
        raise ValueError("Discovery manifest changed its allowed scope")
    body = local_file(f"{key}.csv").read_bytes()
    if hashlib.sha256(body).hexdigest() != record["sha256"]:
        raise ValueError("Discovery checksum mismatch")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    if len(rows) != last - first + 1:
        raise ValueError("Missing/replaced discovery issue slot")
    previous_date = None
    for expected_issue, row in enumerate(rows, first):
        source_issue = 2008030 + expected_issue - 701 if key == "ssq" else expected_issue
        if (ordinal(key, row) != expected_issue or int(row["issue"]) != source_issue or row["split"] != "discovery"
                or int(row["main_pool_expected"]) != pool):
            raise ValueError("Sealed/future/mismatched issue in discovery input")
        if row["date"] != "NA":
            day = date.fromisoformat(row["date"])
            if not start_date <= row["date"] <= end_date or (previous_date and day <= previous_date):
                raise ValueError("Date outside discovery regime/order")
            previous_date = day
        if row["status"] == "missing":
            if not all(row[f] == "NA" for f in [*[f"n{i}" for i in range(1, 7)], "extra_ball"]):
                raise ValueError("Missing draw was imputed")
            if row["missing_reason"] in ("", "NA"):
                raise ValueError("Missing draw needs a reason")
            continue
        if row["status"] != "observed_backup" or row["date"] == "NA":
            raise ValueError("Unknown observation status/date")
        numbers = [int(row[f"n{i}"]) for i in range(1, 7)]
        extra = int(row["extra_ball"])
        extra_valid = 1 <= extra <= 16 if key == "ssq" else 1 <= extra <= pool and extra not in numbers
        if (numbers != sorted(set(numbers)) or not all(1 <= n <= pool for n in numbers)
                or not extra_valid):
            raise ValueError("Invalid main-six/extra fields")
    return rows


def history_before(key, target_issue):
    """Return discovery rows strictly before t, retaining explicit NA slots.

The fixed snapshot is hashed/validated as a whole; only the returned prefix
is a potential model input. This is not a blind result-reveal or scoring API.
"""
    if key not in BOUNDS:
        raise ValueError("Unknown discovery dataset")
    first, last, *_ = BOUNDS[key]
    if type(target_issue) is not int or not first <= target_issue <= last + 1:
        raise ValueError("Target outside discovery history interface")
    # For SSQ, target_issue is the global ordinal, not the year-prefixed ID.
    return [row for row in load_discovery(key) if ordinal(key, row) < target_issue]
