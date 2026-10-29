"""Offline source normalization only: no forecasts, fitting or evaluation.

All input is the archived HTTP bodies indexed by retrievals.json. The strict
parser fails on missing/changed markup instead of guessing balls or dates.
"""

import csv
import gzip
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
FIELDS = ["ordinal", "issue", "date", "phase", "main_pool_expected",
          *[f"n{i}" for i in range(1, 7)], "extra_ball", "status",
          "source_url", "raw_path", "reported_ball_set", "reported_machine",
          "reported_main_order", "physical_fields_verification"]
POOLS = {"uk": 49, "japan": 43, "korea": 45, "ssq": 33}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    @property
    def text(self):
        return "".join(x.text if isinstance(x, Node) else x for x in self.children).strip()

    def find(self, tag=None, cls=None):
        found = []
        for x in self.children:
            if isinstance(x, Node):
                if (tag is None or x.tag == tag) and (cls is None or cls in x.attrs.get("class", "").split()):
                    found.append(x)
                found.extend(x.find(tag, cls))
        return found


class Tree(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(body.decode("utf-8-sig"))
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def base_row(kind, issue, day, balls, source, **reported):
    assert len(balls) == 7, "expected six main balls and one separate extra"
    numbers = list(map(int, balls))
    assert numbers[:6] == sorted(set(numbers[:6])), "invalid main-six set"
    assert all(1 <= n <= POOLS[kind] for n in numbers[:6]), "outside expected pool"
    return dict(ordinal="", issue=str(issue), date=day, phase="",
                main_pool_expected=str(POOLS[kind]),
                **{f"n{i+1}": str(n) for i, n in enumerate(numbers[:6])},
                extra_ball=str(numbers[6]), status="observed_backup",
                source_url=source["url"], raw_path=source["raw_path"],
                reported_ball_set="NA", reported_machine="NA",
                reported_main_order="NA", physical_fields_verification="unverified",
                **reported)


def normalize(root=ROOT):
    result = {k: [] for k in POOLS}
    for source in json.loads((root / "retrievals.json").read_text()):
        kind = source["kind"]
        if kind not in result or "raw_path" not in source:
            continue
        body = gzip.decompress((root / source["raw_path"]).read_bytes())
        if kind == "japan":
            for r in json.loads(body)["data"]:
                if 1 <= int(r["id"]) <= 700:
                    row = base_row(kind, r["id"], r["date"],
                                   [r[f"n{i}"] for i in range(1, 7)] + [r["nbo"]], source)
                    row.update(reported_ball_set=str(r["setball"]),
                               reported_main_order=" ".join(str(int(r[f"o{i}"])) for i in range(1, 7)))
                    result[kind].append(row)
            continue
        tree = Tree(body).root
        if kind == "uk":
            for tr in tree.find("tr"):
                links = [a.attrs["href"] for a in tr.find("a")
                         if a.attrs.get("href", "").startswith("/lotto-result-")]
                if not links:
                    continue
                day = links[0].removeprefix("/lotto-result-")
                if "1994-11-19" <= day <= "2002-09-07":
                    balls = [n.text for n in tr.find("span", "result")]
                    result[kind].append(base_row(kind, "", day, balls, source))
        elif kind == "korea":
            year = source["url"].rsplit("/", 1)[-1]
            for article in tree.find("article", "hist-item"):
                issue = int(article.attrs["id"].removeprefix("draw-"))
                if 1 <= issue <= 700:
                    day = year + "-" + article.find("small")[0].text.replace(".", "-")
                    balls = [n.text for n in article.find("span", "ball")]
                    result[kind].append(base_row(kind, issue, day, balls, source))
        else:
            tbody = [n for n in tree.find("tbody") if n.attrs.get("id") == "tdata"]
            assert len(tbody) == 1, "missing SSQ result table"
            for tr in tbody[0].find("tr"):
                cells = [n.text for n in tr.find("td")]
                assert re.fullmatch(r"\d{5}", cells[0])
                result[kind].append(base_row(kind, "20" + cells[0], cells[-1], cells[1:8], source))
    for kind, rows in result.items():
        rows.sort(key=lambda r: r["date"])
        assert len(rows) == 700, f"{kind}: source gap; do not replace periods"
        assert len({r["date"] for r in rows}) == 700, "duplicate date"
        for ordinal, row in enumerate(rows, 1):
            row.update(ordinal=str(ordinal), phase="warmup" if ordinal <= 200 else "holdout")
            if kind == "uk":
                # Yearly backup pages carry dates, not printed draw numbers.
                # This issue label is a chronological index, boundary-checked separately.
                row["issue"] = str(ordinal)
            elif kind != "ssq":
                assert int(row["issue"]) == ordinal, "missing/reordered source issue"
    return result


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


if __name__ == "__main__":
    for key, rows in normalize().items():
        path = ROOT / f"{key}.csv"
        if path.exists():
            raise SystemExit(f"Refusing to overwrite {path}; compare normalization offline instead")
        path.write_bytes(csv_bytes(rows))
        print(f"{key}: {len(rows)} source observations; no predictions/evaluation")
