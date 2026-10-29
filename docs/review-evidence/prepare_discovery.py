"""Offline acquisition normalization, never an exploration or scoring program.

Reads only new forensic snapshots. Does not import any model, read sealed
result CSVs, analyze distributions, impute dates/balls, or shift missing issues.
"""

import csv
import gzip
from html.parser import HTMLParser
import io
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "data/discovery"
BOUNDS = {"uk": (701, 1700, 49), "japan": (701, 1146, 43),
          "korea": (701, 835, 45)}
FIELDS = ["issue", "date", "split", "main_pool_expected",
          *[f"n{i}" for i in range(1, 7)], "extra_ball", "status",
          "missing_reason", "source_url", "source_snapshot"]
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


def observed(key, issue, day, balls, source):
    first, last, pool = BOUNDS[key]
    assert first <= int(issue) <= last, "outside registered discovery issues"
    assert len(balls) == 7, "missing main/extra fields; do not guess"
    values = list(map(int, balls))
    assert values[:6] == sorted(set(values[:6])), "invalid main-six set"
    assert all(1 <= n <= pool for n in values[:6])
    assert 1 <= values[6] <= pool and values[6] not in values[:6]
    return dict(issue=str(issue), date=day, split="discovery",
                main_pool_expected=str(pool),
                **{f"n{i+1}": str(n) for i, n in enumerate(values[:6])},
                extra_ball=str(values[6]), status="observed_backup", missing_reason="NA",
                source_url=source["url"], source_snapshot=source["raw_path"])


def keep_original_slots(key, indexed):
    """Keep an absent source issue as NA; never use a later draw in its place."""
    first, last, pool = BOUNDS[key]
    assert all(first <= i <= last for i in indexed), "out-of-split issue"
    rows = []
    for issue in range(first, last + 1):
        if issue in indexed:
            rows.append(indexed[issue])
        else:
            row = {field: "NA" for field in FIELDS}
            row.update(issue=str(issue), split="discovery", main_pool_expected=str(pool),
                       status="missing", missing_reason="source_issue_not_obtained")
            rows.append(row)
    return rows


def normalize(repo=REPO):
    indexed = {key: {} for key in BOUNDS}
    uk_dates = []
    sources = json.loads((repo / "data/discovery/retrievals.json").read_text())
    for source in sources:
        key = source["kind"]
        if key not in indexed or "raw_path" not in source:
            continue
        path = (repo / source["raw_path"]).resolve()
        assert path.is_relative_to((repo / "docs/review-evidence/discovery-source-snapshots").resolve())
        body = gzip.decompress(path.read_bytes())
        if key == "japan":
            for r in json.loads(body)["data"]:
                issue = int(r["id"])
                if BOUNDS[key][0] <= issue <= BOUNDS[key][1]:
                    assert issue not in indexed[key], "duplicate source issue"
                    indexed[key][issue] = observed(key, issue, r["date"],
                                                  [r[f"n{i}"] for i in range(1, 7)] + [r["nbo"]], source)
            continue
        tree = Tree(body).root
        if key == "korea":
            year = source["url"].rsplit("/", 1)[-1]
            for article in tree.find("article", "hist-item"):
                issue = int(article.attrs["id"].removeprefix("draw-"))
                if BOUNDS[key][0] <= issue <= BOUNDS[key][1]:
                    assert issue not in indexed[key], "duplicate source issue"
                    day = year + "-" + article.find("small")[0].text.replace(".", "-")
                    balls = [n.text for n in article.find("span", "ball")]
                    indexed[key][issue] = observed(key, issue, day, balls, source)
        else:
            for tr in tree.find("tr"):
                links = [a.attrs["href"] for a in tr.find("a")
                         if a.attrs.get("href", "").startswith("/lotto-result-")]
                if not links:
                    continue
                day = links[0].removeprefix("/lotto-result-")
                if "2002-09-11" <= day <= "2012-04-07":
                    uk_dates.append((day, [n.text for n in tr.find("span", "result")], source))
    uk_dates.sort(key=lambda r: r[0])
    # UK yearly pages omit row-wise IDs. If their count is wrong, the missing
    # issue cannot be located reliably: refuse to compress/relabel later dates.
    assert len(uk_dates) == len({r[0] for r in uk_dates}) == 1000, "UK ordinal gap/duplicate: stop, do not relabel"
    for issue, (day, balls, source) in enumerate(uk_dates, 701):
        indexed["uk"][issue] = observed("uk", issue, day, balls, source)
    return {key: keep_original_slots(key, rows) for key, rows in indexed.items()}


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
            raise SystemExit(f"Refusing to overwrite {path}")
        path.write_bytes(csv_bytes(rows))
        print(f"{key}: {len(rows)} fixed issue slots; acquisition only")
