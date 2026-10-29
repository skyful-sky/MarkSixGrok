"""Optional full-suite profile honoring a no-sealed-results work instruction.

Keeps legacy integrity tests available for ordinary runs; explicitly skips
their result-reading cases in this profile and guards against accidental reads.
"""

import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
_guard = {"enabled": False}


def pytest_addoption(parser):
    parser.addoption("--no-sealed-results", action="store_true", default=False,
                     help="Do not open sealed result CSV/raw bodies; retain and mark legacy integrity cases skipped")


def pytest_configure(config):
    if not config.getoption("--no-sealed-results"):
        return
    _guard["enabled"] = True
    captures = json.loads((ROOT/"data/discovery/retrievals.json").read_text())
    mixed = {(ROOT/r["raw_path"]).resolve() for r in captures if "raw_path" in r and
             ((r["kind"] == "uk" and r["url"].endswith("2002")) or
              (r["kind"] == "korea" and r["url"].endswith("2016")))}
    sealed = (ROOT/"data/external").resolve()

    def audit(event, args):
        if not _guard["enabled"] or event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if (p.is_relative_to(sealed) and (p.suffix == ".csv" or p.is_relative_to(sealed/"raw"))) or p in mixed:
            raise PermissionError("No-sealed-results test profile forbids this result body")
    sys.addaudithook(audit)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--no-sealed-results"):
        return
    reason = "Manager forbids sealed result reads; legacy integrity test retained but not executed in isolation profile"
    mixed_names = {"test_actual_discovery_issues_do_not_overlap_sealed_window",
                   "test_discovery_csv_reproduces_from_new_forensic_snapshots",
                   "test_raw_hashes_urls_and_dataset_provenance"}
    for item in items:
        name = getattr(item, "originalname", item.name.split("[")[0])
        if item.path.name == "test_external_data.py" or (item.path.name == "test_discovery_split.py" and name in mixed_names):
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_report_header(config):
    if config.getoption("--no-sealed-results"):
        return "Sealed result isolation enabled; only source/window metadata remains readable; legacy body-reading cases explicitly skipped"


def pytest_unconfigure(config):
    _guard["enabled"] = False
