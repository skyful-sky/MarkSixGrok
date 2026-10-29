"""Offline apparatus acquisition audit only: no models, scores or predictions.

Never opens data/external. Earlier Japanese issues carry labels only; physical
order fields are deliberately withheld through issue 700. Raw capture bundles
are forensic evidence, never inputs to the existing discovery access module.
"""

import base64
import csv
from datetime import date
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import unicodedata


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data/discovery/apparatus"
spec = importlib.util.spec_from_file_location("acquisition_html", Path(__file__).with_name("prepare_discovery.py"))
html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(html)


def tree(body):
    match = re.search(br"charset\s*=\s*[\"']?([A-Za-z0-9_-]+)", body[:4096], re.IGNORECASE)
    encoding = match[1].decode("ascii") if match else "utf-8-sig"
    return html.Tree(body.decode(encoding).encode("utf-8")).root


def cells(node):
    return [c for c in node.children if isinstance(c, html.Node) and c.tag in ("td", "th")]


def letter(value):
    value = unicodedata.normalize("NFKC", value.strip()).upper()
    return value if re.fullmatch("[A-J]", value) else "NA"


def record(index, issue, value):
    if issue in index and index[issue] != value:
        raise ValueError(f"Conflicting duplicate source issue {issue}")
    index[issue] = value


def parse_tatuo(body):
    out = {}
    for table in tree(body).find("table", "ysotable22"):
        start = end = None
        for tr in table.find("tr"):
            c = cells(tr)
            m = re.fullmatch(r"第(\d+)回～第(\d+)回", c[0].text) if len(c) == 1 else None
            if m:
                start, end = map(int, m.groups())
            elif start is not None and len(c) == end - start + 1:
                # Preserve empty cells in place; never drop a cell and shift IDs.
                for issue, cell in enumerate(c, start):
                    record(out, issue, cell.text)
                start = end = None
    return out


def parse_umiduki(body):
    out = {}
    for table in tree(body).find("table", "table2"):
        for tr in table.find("tr"):
            c = cells(tr)
            m = re.fullmatch(r"(\d+)～(\d+)", c[0].text) if c else None
            if m:
                start, end = map(int, m.groups())
                if len(c) != end - start + 2:
                    raise ValueError("Umiduki range/cell count mismatch")
                for issue, cell in enumerate(c[1:], start):
                    record(out, issue, cell.text)
    return out


def parse_psshc(body):
    out, rejected = {}, []
    for block in tree(body).find("div", "waku"):
        children = [c for c in block.children if isinstance(c, html.Node)]
        for pos, node in enumerate(children[:-1]):
            if "kaisuudates" not in node.attrs.get("class", "").split():
                continue
            m = re.fullmatch(r"第(\d+)回", node.text)
            images = children[pos + 1].find("img")
            if m and images:
                issue = int(m[1])
                if not 1 <= issue <= 2150:
                    rejected.append({"printed_issue": issue, "reason": "outside_snapshot_range_do_not_repair"})
                else:
                    value = images[0].attrs.get("alt", "")
                    if issue in out and out[issue] != value:
                        value = out[issue] + "|" + value
                    out[issue] = value
    return out, rejected


def parse_hpfree(body):
    out = {}
    for tr in tree(body).find("tr"):
        c = cells(tr)
        m = re.fullmatch(r"第0*(\d+)回", c[0].text) if c else None
        if not m or len(c) != 9:
            continue
        label = c[1].text.removesuffix("セット")
        if letter(label) == "NA":
            continue  # A future empty placeholder is not a completed draw.
        issue = int(m[1])
        values = []
        for cell in c[2:]:
            match = re.match(r"\s*(\d{1,2})", cell.text)
            values.append(int(match[1]) if match else None)
        item = {"label": label, "order": values}
        if issue in out and out[issue] != item:
            item = {"label": out[issue]["label"] + "|" + label, "order": [],
                    "source_issue_conflict": True}
        out[issue] = item
    return out


def valid_order(values):
    return (len(values) == 7 and all(isinstance(v, int) and 1 <= v <= 43 for v in values)
            and len(set(values)) == 7)


def consensus(values):
    present = [v for v in values if v != "NA"]
    if len(set(present)) > 1:
        return "NA", "conflict"
    if len(present) < 2:
        return "NA", "insufficient_sources"
    return present[0], "crosschecked_nonofficial"


def parse_uk_mersey(body):
    # The retained projection excludes all results and all out-of-range draws.
    return {int(r["issue"]): r for r in json.loads(body)["metadata_rows"]}


def project_uk_mersey(body):
    """Retain metadata by explicit column name; never positional Machine/Set."""
    pre = tree(body).find("pre")
    if len(pre) != 1:
        raise ValueError("Missing Merseyworld preformatted CSV")
    header, rows, excluded_2026, excluded_other = None, {}, 0, 0
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    for fields in csv.reader(pre[0].text.splitlines(), skipinitialspace=True):
        fields = [f.strip() for f in fields]
        if fields and fields[0] == "No.":
            header = fields
            if len(header) != len(set(header)) or not {"No.", "YYYY", "MMM", "DD", "Machine", "Set"} <= set(header):
                raise ValueError("Unknown or duplicated Merseyworld headers")
            continue
        if not fields or not fields[0].isdigit():
            continue
        if not header or len(fields) != len(header):
            raise ValueError("Merseyworld row/header mismatch")
        row = dict(zip(header, fields))
        issue, year = int(row["No."]), int(row["YYYY"])
        if year >= 2026:
            excluded_2026 += 1
            continue
        if not 701 <= issue <= 1400:
            excluded_other += 1
            continue
        if issue in rows:
            raise ValueError("Duplicate target UK issue; do not collapse rounds")
        day = date(year, months.index(row["MMM"]) + 1, int(row["DD"])).isoformat()
        rows[issue] = dict(issue=issue, date=day, machine=row["Machine"], ball_set=row["Set"])
    return dict(source_header=header, metadata_rows=[rows[i] for i in sorted(rows)],
                excluded_2026_or_later_rows=excluded_2026, excluded_other_rows=excluded_other)


def parse_uk_secondary(body):
    doc = tree(body)
    result = {}
    for td in doc.find("td"):
        for label, key in [("Ball Set Used:", "ball_set"), ("Ball Machine Used:", "machine")]:
            if td.text.startswith(label):
                result[key] = td.text.removeprefix(label).strip()
    # Use printed ID, never infer one by sorting dates or counting rows.
    m = re.search(r"The\s+(\d[\d,]*)(?:st|nd|rd|th)\s+Lotto draw", doc.text)
    result["issue"] = int(m[1].replace(",", "")) if m else None
    return result


def load_evidence(root=ROOT):
    retrievals = json.loads((root / "retrievals.json").read_text())
    bodies = {}
    for filename in sorted({r["bundle_path"] for r in retrievals if "bundle_path" in r}):
        path = (root / filename).resolve()
        if not path.is_relative_to((root / "raw").resolve()):
            raise ValueError("Evidence path outside new raw directory")
        for line in gzip.decompress(path.read_bytes()).splitlines():
            entry = json.loads(line)
            if entry["key"] in bodies:
                raise ValueError("Duplicate evidence key")
            bodies[entry["key"]] = base64.b64decode(entry["body_base64"], validate=True)
    for r in retrievals:
        if "bundle_path" in r:
            if hashlib.sha256(bodies[r["key"]]).hexdigest() != r["stored_sha256"]:
                raise ValueError("Evidence content hash mismatch")
    return bodies


def normalize(bodies, uk_reference):
    uk = []
    indexed = parse_uk_mersey(bodies["mersey_csv"])
    reference = {int(r["issue"]): r["date"] for r in uk_reference}
    for issue in range(701, 1401):
        primary = indexed.get(issue, {})
        key = "uk_701_second" if issue == 701 else f"uk_second_{issue}"
        secondary = parse_uk_secondary(bodies[key]) if key in bodies else {}
        if secondary and secondary["issue"] != issue:
            raise ValueError("UK secondary printed issue mismatch")
        day = primary.get("date", reference.get(issue, "NA"))
        if primary and day != reference.get(issue):
            raise ValueError("UK original discovery date mismatch")
        row = dict(issue=str(issue), date=day)
        statuses = []
        for field in ("machine", "ball_set"):
            p, s = primary.get(field, "NA"), secondary.get(field, "NA")
            row[f"mersey_{field}"] = p
            row[f"lottery_co_uk_{field}"] = s
            row[field], status = consensus([p, s])
            statuses.append(status)
        row["status"] = "crosschecked_nonofficial" if all(s == "crosschecked_nonofficial" for s in statuses) else ";".join(statuses)
        row["source_keys"] = f"mersey_csv;{key}"
        row["pre_sales_close_verified"] = "false"
        uk.append(row)

    tatuo, umiduki = parse_tatuo(bodies["tatuo_set"]), parse_umiduki(bodies["umiduki_2150"])
    psshc, rejected = parse_psshc(bodies["psshc_0"])
    loto, loto_keys, hp, hp_keys = {}, {}, {}, {}
    for key, body in sorted(bodies.items()):
        if re.fullmatch(r"jp_\d+", key):
            for item in json.loads(body)["data"]:
                issue = int(item["id"])
                record(loto, issue, item)
                loto_keys[issue] = key
        if key in ("hpfree", "hpfree_old", "hpfree_latest", "hpfree_oldest"):
            entries = json.loads(body)["metadata_rows"] if key == "hpfree_oldest" else parse_hpfree(body)
            for issue, item in entries.items():
                issue = int(issue)
                record(hp, issue, item)
                hp_keys[issue] = key
    japan, orders = [], []
    for issue in range(1, 2151):
        item = loto.get(issue, {})
        h = hp.get(issue, {})
        raw_values = {"tatuo": tatuo.get(issue, "NA"), "loto6_jp": item.get("setball", "NA"),
                      "umiduki": umiduki.get(issue, "NA"), "psshc": psshc.get(issue, "NA"),
                      "hpfree": h.get("label", "NA")}
        row = dict(issue=str(issue), date=item.get("date", "NA"),
                   source_stage_id=str(item.get("stage_id", "NA")),
                   source_setball_id=str(item.get("setball_id", "NA")))
        row.update({f"{k}_raw": v or "NA" for k, v in raw_values.items()})
        normalized = {k: letter(v) for k, v in raw_values.items()}
        row.update({f"{k}_label": v for k, v in normalized.items()})
        row["ball_set"], row["status"] = consensus(normalized.values())
        if any("|" in v for v in raw_values.values()):
            row["ball_set"], row["status"] = "NA", "source_issue_conflict"
        row["valid_source_count"] = str(sum(v != "NA" for v in normalized.values()))
        row["source_keys"] = ";".join(["tatuo_set", "umiduki_2150", "psshc_0", loto_keys.get(issue, "NA"), hp_keys.get(issue, "NA")])
        row["physical_set_id"] = "NA"
        row["machine_id"] = "NA"
        row["pre_sales_close_verified"] = "false"
        japan.append(row)
        # Old sealed window remains labels-only, with no newly persisted order.
        if issue <= 700:
            continue
        order = [int(item.get(f"o{i}") or 0) for i in range(1, 7)] + [int(item.get("nbo") or 0)]
        other = h.get("order", [])
        primary_valid, other_valid = valid_order(order), valid_order(other)
        if h.get("source_issue_conflict"):
            accepted, status = None, "source_issue_conflict"
        elif primary_valid and other_valid:
            accepted = order if order == other else None
            status = "crosschecked_nonofficial" if accepted else "conflict"
        elif primary_valid:
            accepted, status = order, "single_nonofficial_source"
        elif other_valid:
            accepted, status = other, "single_nonofficial_source"
        else:
            accepted, status = None, "missing"
        if primary_valid:
            main = [int(item[f"n{i}"]) for i in range(1, 7)]
            if sorted(order[:6]) != main:
                raise ValueError("Claimed extraction order is not a permutation of main six")
        values = accepted or ["NA"] * 7
        orders.append(dict(issue=str(issue), date=item.get("date", "NA"),
            **{f"draw_{i+1}": str(v) for i, v in enumerate(values[:6])}, bonus=str(values[6]),
            loto6_jp_order=" ".join(map(str, order)) if primary_valid else "NA",
            hpfree_order=" ".join(map(str, other)) if other_valid else "NA",
            status=status, official_order_verified="false",
            source_keys=";".join([loto_keys.get(issue, "NA"), hp_keys.get(issue, "NA")]),
            pre_sales_close_verified="false"))
    return {"uk-lotto-701-1400-apparatus.csv": uk,
            "japan-loto6-all-setballs.csv": japan,
            "japan-loto6-701-onwards-draw-order.csv": orders}, rejected


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


if __name__ == "__main__":
    with (REPO / "data/discovery/uk.csv").open() as stream:
        uk_reference = list(csv.DictReader(stream))
    tables, rejected = normalize(load_evidence(), uk_reference)
    for name, rows in tables.items():
        path = ROOT / name
        if path.exists():
            raise SystemExit(f"Refusing to overwrite {path}")
        path.write_bytes(csv_bytes(rows))
    print(json.dumps({"rows": {k: len(v) for k, v in tables.items()}, "rejected_source_ids": rejected}))
