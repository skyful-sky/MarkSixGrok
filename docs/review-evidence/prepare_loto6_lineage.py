"""Metadata-only lineage inventory. No models, outcomes, calibration or scores."""

from collections import Counter
import csv
from datetime import date
import importlib.util
from pathlib import Path
import re


spec = importlib.util.spec_from_file_location("apparatus_html", Path(__file__).with_name("prepare_apparatus.py"))
html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(html)


def inspect_response(status, content_type, body):
    if status != 200:
        return "http_failure"
    if body.startswith(b"%PDF-"):
        return "pdf_received_not_itself_lineage_verified"
    doc = html.tree(body)
    titles = doc.find("title")
    if titles and "NOT FOUND" in titles[0].text.upper():
        return "soft_not_found"
    if "pdf" in (content_type or "").lower():
        return "wrong_content_type_not_pdf"
    if "過去の当せん番号案内()" in doc.text:
        return "empty_draw_table_not_date_evidence"
    return "html_received_not_itself_lineage_verified"


def date_projection(body):
    """Retain period/date only; never persist old main or bonus results."""
    out = {}
    for tr in html.tree(body).find("tr"):
        cells = html.cells(tr)
        if len(cells) < 2:
            continue
        issue = re.fullmatch(r"第(\d+)回", cells[0].text)
        day = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日", cells[1].text)
        if issue and day:
            key, value = int(issue[1]), date(*map(int, day.groups())).isoformat()
            if key in out and out[key] != value:
                raise ValueError("Conflicting official issue/date entries")
            out[key] = value
    return [{"issue": k, "date": out[k]} for k in sorted(out)]


def inventory(rows, lo, hi, stage=None):
    subset = [r for r in rows if lo <= int(r["issue"]) <= hi
              and (stage is None or r["source_stage_id"] == stage)]
    counts = Counter(r["ball_set"] for r in subset)
    return {"issue_start": lo, "issue_end": hi, "source_stage_id": stage or "all",
            "rows": len(subset), "label_counts": {label: counts[label] for label in "ABCDEFGHIJ"},
            "NA": counts["NA"], "physical_lineage_verified": False,
            "eligible_physical_calibration_rows": 0,
            "meaning": "Source-label inventory only; not certified same physical balls or machines"}


def stage_runs(rows):
    """List every observed source-category boundary without relabeling it."""
    selected = [r for r in rows if int(r["issue"]) >= 701]
    runs = []
    for row in selected:
        if not runs or runs[-1]["source_stage_id"] != row["source_stage_id"]:
            runs.append(dict(first_issue=int(row["issue"]), last_issue=int(row["issue"]),
                first_date=row["date"], last_date=row["date"], source_stage_id=row["source_stage_id"],
                rows=1, official_actual_venue_verified=False,
                interpretation="Third-party stage category run, not a physical-venue change proof"))
        else:
            runs[-1].update(last_issue=int(row["issue"]), last_date=row["date"], rows=runs[-1]["rows"]+1)
    return runs
