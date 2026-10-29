"""Four fixed exploratory shadows. Never changes Round 2 formal predictions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
from typing import Sequence

from marksix_r2 import DATA_SHA256, Draw, ROOT, TICKETS, canonical_json, load_training, success, validate_sequence

PRIOR = Fraction(6, 49)
SEED = 20261029
MODEL_IDS = ("SH-GAP20-v1", "SH-GAP1", "SH-LAG1-v1", "SH-LAG-RNO-v1")
LOCK_PATH = ROOT / "archive/shadow-candidates-v1.lock.json"
MODEL_SPECS = {
    "SH-GAP20-v1": {"author": "Codex", "gap_cap": 20, "minimum_history": 1,
        "score": "min(g,20); last draw main=0; never seen=observed draw count",
        "ties": "number_ascending"},
    "SH-GAP1": {"author": "Antigravity", "G": 15, "kappa": 30, "W": 20,
        "minimum_history": 20, "score": "(hits[g]+30*(6/49))/(exposures[g]+30)",
        "never_seen": "bin15_from_start", "ties": "seeded_permutation", "seed": SEED},
    "SH-LAG1-v1": {"author": "Codex", "smoothing": 20, "minimum_history": 1,
        "score": "b_j=(B_j+20*(6/49))/(M+20); s_j=mean_i_in_previous_main((C_ij+20*b_j)/(N_i+20))-b_j",
        "lag": 1, "include_i_equals_j": True, "ties": "number_ascending"},
    "SH-LAG-RNO-v1": {"author": "Antigravity", "kappa": 30, "W": 20,
        "minimum_history": 20, "score": "(class_hits+30*(6/49))/(class_exposures+30)",
        "classes": "R=previous main; N=bounded +/-1 neighbors minus R; O=rest; no1/49wrap",
        "ties": "seeded_permutation", "seed": SEED},
}
CONVENTIONS = {
    "data_start": "26/047", "main_only": True,
    "training": "expanding history; W=20 is a warmup, not a rolling training window",
    "gap_exposures": "one exposure per number before each observed draw, including first draw; unseen numbers in bin15",
    "rno_exposures": "one exposure per class member per adjacent historical pair; first pair047->048; R has priority over N",
    "smoothing_unit": "per-number Bernoulli exposures, not per-draw counts",
    "random_ties": "independent random.Random(20261029) per seeded model; shuffle ascending1..49 once per eligible target, then stable sort by exact score descending; no draws consumed during warmup",
    "random_equal_class_rates": "shuffle all49 first, including across distinct classes with exactly equal scores",
    "rank_metric": "actual ticket-order positions1..49; also report exact-score average midranks separately",
    "tickets": "order positions1..48 cut into eight consecutive groups of6; exclude position49",
    "success": "at least one ticket has >=3 main numbers; one success per draw maximum",
    "primary_window": ["26/096", "26/115"],
    "full_segment": "GAP20/LAG1:048..115 (68); GAP1/RNO:067..115 (49); common067..115 also reported",
    "selection": ">=9/20 is descriptive exploratory screening only, never confirmation or a forward pass",
    "inference": "no p-values, MC-based stopping or Holm decision added; this delivery implements Manager's four-candidate backtest request",
}


def rno_classes(previous: Sequence[int]) -> tuple[str, ...]:
    repeated = set(previous)
    neighbors = {neighbor for n in repeated for neighbor in (n - 1, n + 1)
                 if 1 <= neighbor <= 49} - repeated
    return tuple("R" if n in repeated else "N" if n in neighbors else "O"
                 for n in range(1, 50))


class HistoryState:
    """All sufficient statistics are updated only after scoring a target."""

    def __init__(self):
        self.count = 0
        self.previous: tuple[int, ...] = ()
        self.gaps = [0] * 49
        self.seen = [False] * 49
        self.gap_exposures = [0] * 16
        self.gap_hits = [0] * 16
        self.class_exposures = dict.fromkeys("RNO", 0)
        self.class_hits = dict.fromkeys("RNO", 0)
        self.n = [0] * 49
        self.b = [0] * 49
        self.c = [[0] * 49 for _ in range(49)]

    def gap_bins(self) -> list[int]:
        return [min(gap, 15) if seen else 15 for gap, seen in zip(self.gaps, self.seen)]

    def observe(self, draw: Draw) -> None:
        main = set(draw.main)
        for number, gap_bin in enumerate(self.gap_bins(), 1):
            self.gap_exposures[gap_bin] += 1
            self.gap_hits[gap_bin] += number in main
        if self.previous:
            for number, category in enumerate(rno_classes(self.previous), 1):
                self.class_exposures[category] += 1
                self.class_hits[category] += number in main
            for i in self.previous:
                self.n[i - 1] += 1
                for j in draw.main:
                    self.c[i - 1][j - 1] += 1
            for j in draw.main:
                self.b[j - 1] += 1
        for i in range(49):
            if i + 1 in main:
                self.gaps[i] = 0
                self.seen[i] = True
            else:
                self.gaps[i] += 1
        self.count += 1
        self.previous = draw.main

    def scores(self, model: str) -> tuple[Fraction, ...]:
        if self.count < MODEL_SPECS[model]["minimum_history"]:
            raise ValueError("Insufficient history; warmup targets are never scored")
        if model == "SH-GAP20-v1":
            return tuple(Fraction(min(gap, 20)) for gap in self.gaps)
        if model == "SH-GAP1":
            rates = [(hits + 30 * PRIOR) / (exposures + 30)
                     for hits, exposures in zip(self.gap_hits, self.gap_exposures)]
            return tuple(rates[gap_bin] for gap_bin in self.gap_bins())
        if model == "SH-LAG1-v1":
            pairs = self.count - 1
            marginal = [(hits + 20 * PRIOR) / (pairs + 20) for hits in self.b]
            return tuple(sum(((self.c[i - 1][j] + 20 * marginal[j]) /
                              (self.n[i - 1] + 20) for i in self.previous), Fraction()) / 6
                         - marginal[j] for j in range(49))
        if model == "SH-LAG-RNO-v1":
            rates = {category: (self.class_hits[category] + 30 * PRIOR) /
                     (self.class_exposures[category] + 30) for category in "RNO"}
            return tuple(rates[category] for category in rno_classes(self.previous))
        raise ValueError(f"Unknown locked model: {model}")


def order_numbers(scores: Sequence[Fraction], rng: random.Random | None) -> tuple[int, ...]:
    order = list(range(1, 50))
    if rng is not None:
        rng.shuffle(order)
    return tuple(sorted(order, key=lambda n: -scores[n - 1]))


def score_midranks(scores: Sequence[Fraction]) -> tuple[float, ...]:
    # Exact Fraction comparisons preserve mathematical ties before cutting.
    return tuple(float(1 + sum(other > value for other in scores)
                       + Fraction(sum(other == value for other in scores) - 1, 2))
                 for value in scores)


def predict(state: HistoryState, model: str, rng: random.Random | None) -> dict:
    values = state.scores(model)
    order = order_numbers(values, rng)
    ranks = [0] * 49
    for rank, number in enumerate(order, 1):
        ranks[number - 1] = rank
    return {"scores_exact": [str(value) for value in values], "order": order,
            "ranks": ranks, "score_midranks": score_midranks(values),
            "tickets": tuple(tuple(order[i:i + 6]) for i in range(0, 48, 6)),
            "excluded": order[-1], "training_draws": state.count,
            "training_pairs": state.count - 1}


def summarize(records: Sequence[dict]) -> dict:
    if not records:
        return {"draws": 0, "successes": 0, "success_rate": None,
                "mean_main_rank": None, "mean_main_midrank": None}
    count = len(records)
    rank_sum = sum(sum(record["prediction"]["ranks"][n - 1] for n in record["main"])
                   for record in records)
    midrank_sum = sum(sum(Fraction(record["prediction"]["score_midranks"][n - 1])
                         for n in record["main"]) for record in records)
    hit_count = sum(record["success"] for record in records)
    paired = {"both": 0, "shadow_only": 0, "fixed_only": 0, "neither": 0}
    for record in records:
        paired[("both" if record["fixed_blocks_success"] else "shadow_only")
               if record["success"] else ("fixed_only" if record["fixed_blocks_success"] else "neither")] += 1
    return {"first_draw": records[0]["target"], "last_draw": records[-1]["target"],
            "draws": count, "successes": hit_count, "success_rate": hit_count / count,
            "main_rank_sum": rank_sum, "mean_main_rank": rank_sum / (6 * count),
            "main_midrank_sum": float(midrank_sum), "mean_main_midrank": float(midrank_sum / (6 * count)),
            "fixed_blocks_successes": sum(record["fixed_blocks_success"] for record in records),
            "paired_with_fixed_blocks": paired}


def backtest(draws: Sequence[Draw]) -> dict:
    validate_sequence(draws)
    state = HistoryState()
    rngs = {model: random.Random(SEED) if MODEL_SPECS[model]["ties"] == "seeded_permutation"
            else None for model in MODEL_IDS}
    records = {model: [] for model in MODEL_IDS}
    for index, draw in enumerate(draws):
        for model in MODEL_IDS:
            if state.count < MODEL_SPECS[model]["minimum_history"]:
                continue
            prediction = predict(state, model, rngs[model])
            record = {"target": draw.issue, "date": draw.day.isoformat(),
                      "through": draws[index - 1].issue, "main": draw.main,
                      "special_excluded": draw.special, "prediction": prediction,
                      "success": success(draw.main, prediction["tickets"]),
                      "fixed_blocks_success": success(draw.main, TICKETS)}
            records[model].append(record)
        state.observe(draw)
    models = {}
    for model in MODEL_IDS:
        window = [record for record in records[model] if "26/096" <= record["target"] <= "26/115"]
        common = [record for record in records[model] if "26/067" <= record["target"] <= "26/115"]
        primary = summarize(window)
        primary["screening_ge9of20_only"] = primary["draws"] == 20 and primary["successes"] >= 9
        models[model] = {"specification": MODEL_SPECS[model], "window_26096_26115": primary,
                         "full_segment": summarize(records[model]),
                         "common_26067_26115": summarize(common), "records": records[model]}
    fixed_window = [draw for draw in draws if "26/096" <= draw.issue <= "26/115"]
    return {"models": models,
            "comparison": {"fair_nonoverlap_q_exact": "12344/83237",
                           "fair_nonoverlap_rate": 12344 / 83237, "fair_mean_rank": 25,
                           "FixedBlocks_E20": {"draws": len(fixed_window),
                               "successes": sum(success(draw.main) for draw in fixed_window),
                               "archive_id": "EXP-R1-FB8-26096-26115"}},
            "evidence_status": "Exploratory historical results only. >=9/20 is screening, not confirmation. No forward prediction or formal bet changed."}


def verify_lock(path: Path = LOCK_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    lock = json.loads(raw)
    if lock["models"] != MODEL_SPECS or lock["conventions"] != CONVENTIONS or lock["data_sha256"] != DATA_SHA256:
        raise ValueError("Shadow specification differs from the pre-run lock")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "backtests/shadow-candidates-v1.json")
    args = parser.parse_args()
    lock, lock_hash = verify_lock()
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if lock["implementation_sha256"] != code_hash:
        parser.error("Implementation changed after the pre-run lock")
    # Refuse accidental overwriting of a completed exploratory result.
    if args.output.exists():
        parser.error("Result already exists; retain the original result and history")
    before = datetime.now(timezone.utc).isoformat()
    result = backtest(load_training())
    result["audit"] = {"started_at_utc": before, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_sha256": DATA_SHA256, "source_first_draw": "26/047", "source_last_draw": "26/115",
        "source_rows": 69, "lock_sha256": lock_hash, "implementation_sha256": code_hash,
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": sys.version.split()[0], "new_model_versions": list(MODEL_IDS),
        "registered_R2_method_changed": False, "actual_bets_added": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(canonical_json(result))
    print(canonical_json({model: values["window_26096_26115"] for model, values in result["models"].items()}), end="")


if __name__ == "__main__":
    main()
