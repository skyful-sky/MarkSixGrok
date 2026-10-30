"""Offline EV-1 source parsing only; no fitting, scoring or ticket generation.

Reads a directory of acquired HTTP bodies/metadata and the fixed issue/date plan.
Never opens data/external or any existing lottery results file. CLI output must
be new; source failures retain the original issue with NA, never a later draw.
"""

import argparse
import base64
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import unicodedata


spec = importlib.util.spec_from_file_location("ev1_html", Path(__file__).with_name("prepare_discovery.py"))
html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(html)

NA = "NA"
TIERS = {"uk": 5, "japan": 5, "hongkong": 7}
CONDITIONS = {"uk": ["6", "5+bonus", "5", "4", "3"],
              "japan": ["6", "5+bonus", "5", "4", "3"],
              "hongkong": ["6", "5+special", "5", "4+special", "4", "3+special", "3"]}


def digest(body):
    return hashlib.sha256(body).hexdigest()


def number(value):
    value = unicodedata.normalize("NFKC", str(value)).replace(",", "").strip()
    m = re.fullmatch(r"(?:HK\$|£)?\s*(\d+(?:\.\d+)?)(?:円|口)?", value)
    if not m:
        return NA
    return format(Decimal(m[1]).normalize(), "f")


def root(body, encoding="utf-8"):
    return html.Tree(body.decode(encoding).encode("utf-8")).root


def cells(node):
    return [n.text for n in node.children if isinstance(n, html.Node) and n.tag in ("th", "td")]


def empty_record():
    return dict(issue=NA, date=NA, sales=NA, tiers={}, conditions=[], publication_at=NA)


def tier(winners, reported):
    w, p = number(winners), number(reported)
    return dict(winners=w, reported_prize=p, payout=NA if w in (NA, "0") else p)


def english_date(text):
    m = re.search(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d+)(?:st|nd|rd|th)\s+(\w+)\s+(\d{4})", text)
    return datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat() if m else NA


def parse_uk_mersey(body):
    r, tree = empty_record(), root(body, "latin1")
    titles = tree.find("h2")
    m = re.fullmatch(r"UK National Lotto #(\d+)(?: \([^\n]+\))?", titles[0].text) if titles else None
    if not m:
        raise ValueError("Missing printed Mersey draw number")
    r["issue"] = m[1]
    headings = tree.find("h3")
    r["date"] = english_date(headings[0].text) if headings else NA
    pre = tree.find("pre")
    if not pre:
        return r
    # Main Lotto's first block only: HotPicks/Extra sales are separate products.
    text = pre[0].text
    labels = {"Jackpot": 1, "5+bonus": 2, "5 match": 3, "4 match": 4, "3 match": 5}
    for line in text.splitlines():
        m = re.match(r"\s*(Jackpot|5\+bonus|[345] match)\s+£([\d,]+)\s+([\d,]+)\s+£([\d,]+)", line)
        if m:
            r["tiers"][labels[m[1]]] = tier(m[3], m[2])
        if r["sales"] == NA and "Ticket sales" in line:
            m = re.search(r"£([\d,]+)", line)
            if m:
                r["sales"] = number(m[1])
    r["conditions"] = CONDITIONS["uk"] if len(r["tiers"]) == 5 else []
    return r


def parse_uk_lottery(body):
    r, tree = empty_record(), root(body)
    m = re.search(r"The\s+([\d,]+)(?:st|nd|rd|th)\s+Lotto draw", tree.text)
    if not m:
        raise ValueError("Missing printed Lottery.co.uk draw number")
    r["issue"] = str(int(m[1].replace(",", "")))
    headings = tree.find("h1")
    r["date"] = english_date(headings[0].text) if headings else NA
    labels = {"Match 6": 1, "Match 5 plus Bonus": 2, "Match 5": 3, "Match 4": 4, "Match 3": 5}
    for tr in tree.find("tr"):
        c = cells(tr)
        if len(c) == 4 and c[0] in labels:
            # Rollover markup includes an explicit numeric zero.
            w = re.sub(r"Rollover", "", c[1]).strip()
            r["tiers"][labels[c[0]]] = tier(w, c[2])
    r["conditions"] = CONDITIONS["uk"] if len(r["tiers"]) == 5 else []
    return r


def japanese_date(text):
    text = unicodedata.normalize("NFKC", text)
    m = re.fullmatch(r"(平成|令和)(\d+|元)年(\d+)月(\d+)日", text)
    if not m:
        return NA
    year = (1988 if m[1] == "平成" else 2018) + (1 if m[2] == "元" else int(m[2]))
    return datetime(year, int(m[3]), int(m[4])).date().isoformat()


def parse_jp_official(body):
    rows = list(csv.reader(io.StringIO(unicodedata.normalize("NFKC", body.decode("cp932")))))
    r = empty_record()
    if len(rows) < 11 or rows[0] != ["A52"]:
        raise ValueError("Not an official Loto6 A52 CSV")
    m = re.fullmatch(r"第0*(\d+)回ロト6", rows[1][0])
    if not m:
        raise ValueError("Missing official Loto6 issue")
    r["issue"], r["date"] = m[1], japanese_date(rows[1][2])
    for row in rows[4:9]:
        m = re.fullmatch(r"([1-5])等", row[0])
        if not m or len(row) != 3:
            raise ValueError("Unexpected Japanese prize row")
        # 該当なし explicitly means no winning entry, not a zero dividend quote.
        r["tiers"][int(m[1])] = tier("0" if row[1] == "該当なし" else row[1], row[2])
    for row in rows[9:]:
        if row[0] == "販売実績額":
            r["sales"] = number(row[1])
        if re.fullmatch(r"[1-5]等", row[0]) and len(row) == 2:
            r["conditions"].append(row[1])
    return r


def parse_jp_backup(item):
    r = empty_record()
    r.update(issue=str(item["id"]), date=item["date"], sales=number(item.get("sales", NA)))
    r["tiers"] = {k: tier(item.get(f"t{k}", NA), item.get(f"m{k}", NA)) for k in range(1, 6)}
    return r


def parse_hk_official(item):
    r, pool = empty_record(), item.get("lotteryPool") or {}
    if item.get("status") != "Result":
        raise ValueError("Not an official completed result")
    r.update(issue=f"{int(item['year']) % 100:02d}/{int(item['no']):03d}",
             date=item["drawDate"][:10], sales=number(pool.get("totalInvestment", NA)),
             unit_bet=number(pool.get("unitBet", NA)), raw_winning_unit={})
    for t in pool.get("lotteryPrizes") or []:
        k, raw = int(t["type"]), number(t.get("winningUnit", NA))
        r["raw_winning_unit"][k] = raw
        # Exact browser display formula, confirmed against two per-draw sites.
        w = format(Decimal(raw) / Decimal(r["unit_bet"]), "f") if raw != NA and r["unit_bet"] not in (NA, "0") else NA
        r["tiers"][k] = tier(w, t.get("dividend", NA))
    r["conditions"] = CONDITIONS["hongkong"]
    return r


def parse_hk_lottery(body):
    r, tree = empty_record(), root(body)
    m = re.search(r"draw number\s+(\d{2}/\d{3})\s+held on\s+(\d{2}/\d{2}/\d{4})", tree.text)
    if not m:
        raise ValueError("Missing printed lottery.hk issue/date")
    r["issue"], r["date"] = m[1], datetime.strptime(m[2], "%d/%m/%Y").date().isoformat()
    m = re.search(r"Total Turnover\s+HK\$([\d,]+)", tree.text)
    r["sales"] = number(m[1]) if m else NA
    for tr in tree.find("tr"):
        c = cells(tr)
        if len(c) == 5 and re.fullmatch(r"[1-7](?:st|nd|rd|th)", c[0]):
            r["tiers"][int(c[0][0])] = tier(c[3], c[2])
    return r


def parse_hk_marksixinfo(body):
    r, tree = empty_record(), root(body)
    scripts = tree.find("script")
    obj = next((json.loads(s.text) for s in scripts if s.attrs.get("type") == "application/ld+json"
                and json.loads(s.text).get("@type") == "WebPage"), None)
    if not obj:
        raise ValueError("Missing MarkSixInfo WebPage metadata")
    values = {v["name"]: v["value"] for v in obj["mainEntity"]["variableMeasured"]}
    year, no = values["期數"].split("/")
    r.update(issue=f"{int(year):02d}/{int(no):03d}", date=values["日期"],
             sales=number(values["總投注額"].removesuffix(" HKD")),
             secondary_claimed_publication_date=obj.get("datePublished", NA))
    for k, label in enumerate(["頭獎", "二獎", "三獎", "四獎", "五獎", "六獎", "七獎"], 1):
        m = re.fullmatch(r"([\d.]+) HKD per winning unit; ([\d.]+) winning units", values[label])
        if m:
            r["tiers"][k] = tier(m[2], m[1])
    return r


def fields(country):
    return ["issue", "draw_date", "currency", "sales", "ticket_price", "ticket_price_basis",
            "prize_scheme", "full_prize_rule_version", "announcement_at_utc", "announcement_source_key",
            "secondary_claimed_publication_date", "publication_precision", "primary_source_key",
            "primary_source_url", "primary_source_sha256", "primary_fetched_at_utc",
            "crosscheck_source_keys", "crosscheck_status", "missing_reasons", *[
                f"tier{k}_{f}" for k in range(1, TIERS[country] + 1)
                for f in ("winners", "payout", "reported_prize")]]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, rows, names):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(acquired, plan_path, output):
    plan = json.loads(plan_path.read_text())
    output.mkdir(exist_ok=False)
    (output / "raw").mkdir()
    captures, bodies = {}, {}
    for path in sorted(acquired.glob("*.json")):
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or "key" not in record or "url" not in record:
            continue
        key = record["key"]
        record["method"] = record.get("method", "GET")
        record["semantic_status"] = "transport_failure" if "error" in record else (
            "http_error_or_redirect" if record.get("status") != 200 else "http_200_not_yet_semantically_validated")
        body_path = acquired / (key + ".body")
        if body_path.exists():
            body = body_path.read_bytes()
            if digest(body) != record["sha256"]:
                raise ValueError(f"Source hash mismatch: {key}")
            bodies[key] = body
        captures[key] = record

    def parsed(key, parser):
        record = captures.get(key, {})
        if record.get("status") != 200:
            return empty_record()
        if b"unusual traffic from your IP address" in bodies[key]:
            record["semantic_status"] = "captcha_challenge_not_data_no_bypass"
            return empty_record()
        try:
            result = parser(bodies[key])
            record["semantic_status"] = "parsed_target_record"
            return result
        except (ValueError, KeyError, IndexError, InvalidOperation) as exc:
            record["parse_error"] = str(exc)
            record["semantic_status"] = "parse_failure_not_data"
            return empty_record()

    def source(key):
        return captures.get(key, dict(url=NA, sha256=NA, completed_at_utc=NA))

    jp_backup, hk_primary = {}, {}
    for key in ("jp_data", "jp_data_801", "jp_data_901", "jp_data_1001", "jp_data_1101"):
        if captures[key].get("status") == 200:
            captures[key]["semantic_status"] = "parsed_target_json_page"
            for item in json.loads(bodies[key])["data"]:
                issue = str(item["id"])
                if issue in jp_backup:
                    raise ValueError("Duplicate Japanese backup issue")
                jp_backup[issue] = (parse_jp_backup(item), key)
    for key in ("hk_month_" + f"{m:02d}" for m in range(5, 11)):
        obj = json.loads(bodies[key]) if captures[key].get("status") == 200 else {}
        captures[key]["semantic_status"] = "parsed_target_api_page" if obj.get("data", {}).get("lotteryDraws") else "empty_or_invalid_target_api_page"
        for item in obj.get("data", {}).get("lotteryDraws", []):
            r = parse_hk_official(item)
            if r["issue"] in hk_primary:
                raise ValueError("Duplicate official HK draw")
            hk_primary[r["issue"]] = (r, key)

    used, comparisons, diagnostics, datasets = set(), [], [], []
    for country, slots in plan["scope"].items():
        rows = []
        for issue, day in slots:
            if country == "uk":
                pk, sk = f"uk_mw_{issue}", f"uk_lottery_{issue}"
                primary = parsed(pk, parse_uk_mersey)
                others = [(parsed(sk, parse_uk_lottery), sk)]
                currency, price, basis = "GBP", "1", "uk_govpricing;uk_history (historical price corroboration)"
            elif country == "japan":
                pk = f"jp_csv_{issue}"
                primary = parsed(pk, parse_jp_official)
                others = [jp_backup.get(issue, (empty_record(), "jp_data"))]
                currency, price, basis = "JPY", "200", "jp_2011rules764;jp_rules (documented regime tariff; not per-draw serial rule history)"
            else:
                primary, pk = hk_primary.get(issue, (empty_record(), "hk_month_" + day[5:7]))
                n = int(issue.split("/")[1])
                others = [(parsed(f"hk_mi_{n}", parse_hk_marksixinfo), f"hk_mi_{n}"),
                          (parsed(f"hk_lottery_{n}", parse_hk_lottery), f"hk_lottery_{n}")]
                currency, price, basis = "HKD", primary.get("unit_bet", NA), "official per-draw lotteryPool.unitBet;hk_rules"
            used.add(pk)
            used.update(sk for _, sk in others)
            missing = {"announcement_at_utc": "original publication timestamp not present; draw/HTTP/modified/retrieval time is not publication",
                       "announcement_source_key": "no verified original publication timestamp source",
                       "full_prize_rule_version": "complete dated per-draw legal allocation/caps/promotional-version chain not obtained"}
            row = {f: NA for f in fields(country)}
            row.update(issue=issue, draw_date=day, currency=currency, ticket_price=price, ticket_price_basis=basis,
                       primary_source_key=pk, primary_source_url=source(pk)["url"],
                       primary_source_sha256=source(pk)["sha256"], primary_fetched_at_utc=source(pk)["completed_at_utc"],
                       crosscheck_source_keys=";".join(sk for _, sk in others), publication_precision="unknown")
            aligned = primary["issue"] == issue and primary["date"] == day
            if not aligned:
                missing["primary_identity"] = "missing or mismatching printed issue/date; do not infer from URL"
            row["sales"] = primary["sales"] if aligned else NA
            if aligned and primary["conditions"]:
                row["prize_scheme"] = json.dumps(dict(main_pool={"uk": 49, "japan": 43, "hongkong": 49}[country],
                    drawn_main=6, tiers=primary["conditions"], description="tier conditions only; complete legal version NA"), ensure_ascii=False, separators=(",", ":"))
            compared_status = []
            for secondary, sk in others:
                secondary_aligned = secondary["issue"] == issue and secondary["date"] == day
                if secondary.get("secondary_claimed_publication_date"):
                    row["secondary_claimed_publication_date"] = secondary["secondary_claimed_publication_date"]
                vals = [("sales", primary["sales"], secondary["sales"])]
                for k in range(1, TIERS[country] + 1):
                    a, b = primary["tiers"].get(k, {}), secondary["tiers"].get(k, {})
                    vals.extend((f"tier{k}_{f}", a.get(f, NA), b.get(f, NA)) for f in ("winners", "payout", "reported_prize"))
                for field, a, b in vals:
                    if not aligned or not secondary_aligned:
                        status = "identity_unverified"
                    elif field.endswith("_reported_prize") and primary["tiers"].get(int(field[4]), {}).get("winners") == "0":
                        status = "no_winner_quote_convention" if a != b else "match"
                    elif a == NA or b == NA:
                        status = "not_comparable" if a != b else "both_NA"
                    else:
                        status = "match" if a == b else "conflict"
                    comparisons.append(dict(country=country, issue=issue, field=field, primary_key=pk,
                        secondary_key=sk, primary_value=a, secondary_value=b, status=status))
                    if status == "conflict":
                        compared_status.append(status)
                        missing[field] = f"conflicting sources {pk}/{sk}; adopted NA, no majority vote"
            for k in range(1, TIERS[country] + 1):
                values = primary["tiers"].get(k, {}) if aligned else {}
                for f in ("winners", "payout", "reported_prize"):
                    field, value = f"tier{k}_{f}", values.get(f, NA)
                    row[field] = NA if field in missing else value
                    if row[field] == NA and field not in missing:
                        missing[field] = "no winner; per-winning-entry payout not applicable" if f == "payout" and values.get("winners") == "0" else "not supplied or invalid"
            if "sales" in missing:
                row["sales"] = NA
            if row["sales"] == NA:
                missing.setdefault("sales", "not supplied or invalid")
            row["crosscheck_status"] = "conflict" if compared_status else "see field-level crosschecks.csv; not all fields necessarily checked"
            for field, value in row.items():
                if value == NA and field != "missing_reasons":
                    missing.setdefault(field, "not supplied or not independently verified")
            row["missing_reasons"] = json.dumps(missing, ensure_ascii=False, separators=(",", ":"))
            rows.append(row)
            if country == "hongkong":
                diagnostics.append(dict(issue=issue, source_key=pk, unit_bet=primary.get("unit_bet", NA),
                    raw_winning_unit=primary.get("raw_winning_unit", {}), conversion="winningUnit / unitBet; exact Decimal, official browser formula"))
        names = fields(country)
        path = output / (country + ".csv")
        write_csv(path, rows, names)
        na = {f: sum(r[f] == NA for r in rows) for f in names}
        datasets.append(dict(country=country, path=path.name, sha256=digest(path.read_bytes()), rows=len(rows),
            issue_start=slots[0][0], issue_end=slots[-1][0], date_start=slots[0][1], date_end=slots[-1][1],
            tiers=TIERS[country], na_by_column=na, na_cells=sum(na.values()),
            source_keys=sorted({r["primary_source_key"] for r in rows}),
            numeric_financial_na=sum(na[f] for f in names if f in ("sales", "ticket_price") or re.fullmatch(r"tier\d_(?:winners|payout)", f)),
            announcement_missing=na["announcement_at_utc"], complete_legal_version_missing=na["full_prize_rule_version"]))

    # Full raw bodies retained for in-scope financial responses, not sealed or
    # out-of-scope result lists. Other requests retain an explicitly named audit
    # projection; the original HTTP hash is never called the projection hash.
    audit_keys = set(captures) - used
    for group, keys in (("target-sources", used), ("access-evidence", audit_keys)):
        bundle = output / "raw" / (group + ".jsonl.gz")
        with bundle.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
                for key in sorted(keys):
                    if key not in bodies:
                        continue
                    body = bodies[key]
                    # Broad discovery API pages contain only authorized701+;
                    # exclude unrelated historical/current outcome audit bodies.
                    keep = key in used or key in ("jp_script", "hk_bundle", "hk_config", "hk_rules", "hk_rules2026", "jp_rules", "jp_rulechange", "uk_history", "uk_govpricing", "jp_2011price765", "jp_2011rules764", "uk_prizes_old")
                    if not keep:
                        body = json.dumps({"key": key, "http_status": captures[key].get("status"),
                            "original_body_sha256": captures[key]["sha256"],
                            "note": "body not retained; audit-only request, not target financial source"}, sort_keys=True).encode()
                    captures[key].update(stored_body_kind="original_http_entity" if keep else "metadata_projection_not_original",
                        stored_body_sha256=digest(body), snapshot_path="raw/" + bundle.name)
                    stream.write((json.dumps(dict(key=key, body_base64=base64.b64encode(body).decode())) + "\n").encode())
    write_csv(output / "crosschecks.csv", comparisons,
              ["country", "issue", "field", "primary_key", "secondary_key", "primary_value", "secondary_value", "status"])
    dump(output / "hk-unit-normalization.json", diagnostics)
    dump(output / "retrievals.json", list(captures.values()))
    dump(output / "manifest.json", dict(schema="ev1-data-acceptance-v1", created_at_utc=datetime.now(timezone.utc).isoformat(),
        acquisition_plan_sha256=digest(plan_path.read_bytes()), datasets=datasets,
        operation_record="run-ledger.json", attempts_cumulative=14, hit_attempts_added=0,
        models_executed=0, predictions_generated=0, source_independence_verified=False,
        original_publication_verified=False, complete_historical_rule_chain_verified=False,
        eligible_for_modeling=False, acceptance="data/provenance inventory only; remaining gaps require review, no EV model authorized",
        crosscheck_status_counts={c: dict(Counter(r["status"] for r in comparisons if r["country"] == c)) for c in plan["scope"]},
        missing_policy=plan["missing_policy"], artifacts=[dict(path=str(p.relative_to(output)), sha256=digest(p.read_bytes())) for p in sorted(output.rglob("*")) if p.is_file()]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquired", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.acquired, args.plan, args.output)
