"""Plot sealed estimates only. Does not import or execute the model/MC code."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "ev/EV-DYN-DILUTE-R1/run"
OUT = ROOT / "docs/review-evidence/ev-dyn-dilute-r1"


def main():
    OUT.mkdir(exist_ok=True)
    results = json.loads((RUN / "results.json").read_text())
    rows = results["comparisons"]
    labels = [f"{'UK' if r['country'] == 'uk' else 'Japan'} vs "
              f"{'Static' if r['comparison'].endswith('static') else 'Uniform count model'} (n={r['n']})" for r in rows]
    fig, ax = plt.subplots(figsize=(10.4, 4.9))
    fig.subplots_adjust(left=.35, right=.98, top=.82, bottom=.26)
    for i, r in enumerate(rows):
        color = "#2369a8" if r["country"] == "uk" else "#7b4c83"
        estimate, lower = r["mean_log_score_gain"], r["lower_9875"]
        ax.plot([lower, estimate], [i, i], color=color, lw=2)
        ax.plot(lower, i, marker="|", color=color, markersize=12)
        ax.plot(estimate, i, marker="o", color=color, markersize=7)
    ax.axvline(0, color="#444444", linestyle="--", linewidth=1)
    ax.set_yticks(range(4), labels)
    ax.set_ylim(3.55, -.65)
    ax.set_xlim(-.165, .015)
    ax.set_xlabel("Dynamic minus comparator: mean log score (nats / observed grade / draw)")
    ax.set_title("R1: small gains over Static; no gains over Uniform", loc="left", pad=18, fontsize=14)
    ax.grid(axis="x", color="#dddddd", linewidth=.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=10)
    fig.text(.02, .025, "Dots: estimates. Segments: one-sided 98.75% lower bound to estimate (no upper bound shown).\n"
             "Retrospective discovery; circular block bootstrap approximation. These are count scores, not payout or ROI.",
             fontsize=9, color="#444444")
    for extension in ("png", "svg"):
        fig.savefig(OUT / ("count-comparisons." + extension), dpi=180, bbox_inches="tight", facecolor="white")
    svg = OUT / "count-comparisons.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)
    (OUT / "plot-source.json").write_text(json.dumps(dict(
        source_path=str((RUN / "results.json").relative_to(ROOT)),
        source_sha256=hashlib.sha256((RUN / "results.json").read_bytes()).hexdigest(),
        matplotlib=matplotlib.__version__, values=rows,
        scope="Visualization only of sealed values, no refit, scoring or resampling"), indent=2) + "\n")


if __name__ == "__main__":
    main()
