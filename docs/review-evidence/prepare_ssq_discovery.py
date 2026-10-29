"""Acquisition-only parser; never reads the old sealed result window."""

import csv
import importlib.util
import io
from pathlib import Path


spec = importlib.util.spec_from_file_location("discovery_html", Path(__file__).with_name("prepare_discovery.py"))
html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(html)
FIELDS = ["ordinal", *html.FIELDS]


def parse(body, source):
    tree = html.Tree(body).root
    table = [n for n in tree.find("tbody") if n.attrs.get("id") == "tdata"]
    if len(table) != 1:
        raise ValueError("Missing SSQ table")
    by_issue = {}
    for tr in table[0].find("tr"):
        cells = [n.text for n in tr.find("td")]
        issue = int("20" + cells[0])
        if not 2008030 <= issue <= 2008121:
            continue
        if issue in by_issue or not "2008-03-16" <= cells[-1] < "2008-10-16":
            raise ValueError("Duplicate/out-of-regime SSQ issue")
        main = list(map(int, cells[1:7]))
        blue = int(cells[7])
        if main != sorted(set(main)) or not all(1 <= n <= 33 for n in main) or not 1 <= blue <= 16:
            raise ValueError("Invalid red/blue fields")
        by_issue[issue] = dict(ordinal=str(701 + issue - 2008030), issue=str(issue), date=cells[-1],
            split="discovery", main_pool_expected="33", **{f"n{i+1}":str(n) for i,n in enumerate(main)},
            extra_ball=str(blue), status="observed_backup", missing_reason="NA", source_url=source["url"],
            source_snapshot=source["raw_path"])
    rows = []
    for issue in range(2008030, 2008122):
        if issue not in by_issue:
            r = {k:"NA" for k in FIELDS}
            r.update(ordinal=str(701+issue-2008030), issue=str(issue), split="discovery",main_pool_expected="33",
                     status="missing",missing_reason="source_issue_not_obtained")
            by_issue[issue] = r
        rows.append(by_issue[issue])
    return rows


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")
