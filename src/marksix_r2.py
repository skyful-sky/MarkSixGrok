"""Locked round-2 protocol. Training snapshot and forward results stay separate."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_SHA256 = "653993bd43030f7436a96a171ba98b2e73ed62e26f38108efd334fe3d88c8a5e"
FIRST_DRAW = "26/116"
HALF_LIFE = 20
LAMBDA = 0.1
HORIZON = 60
H3_THRESHOLD = 16
E_THRESHOLD = 60
Q = Fraction(12344, 83237)
TICKETS = tuple(tuple(range(6 * i + 1, 6 * i + 7)) for i in range(8))
FIELDS = ("期數", "攪珠日期", *(f"正選號碼{i}" for i in range(1, 7)), "特別號碼")
FAILURE_NOTE = "方法保守，未通過本身不足以排除中等效應；仍停用，不得聲稱已有訊號。"


@dataclass(frozen=True)
class Draw:
    issue: str
    day: date
    main: tuple[int, ...]
    special: int

    def __post_init__(self):
        issue_key(self.issue)
        validate_main(self.main)
        if self.special not in range(1, 50) or self.special in self.main:
            raise ValueError("Special number must be distinct and in 1..49")


def issue_key(issue: str) -> tuple[int, int]:
    if not re.fullmatch(r"\d{2}/\d{3}", issue) or int(issue[3:]) == 0:
        raise ValueError(f"Invalid issue: {issue}")
    return int(issue[:2]), int(issue[3:])


def validate_main(main: Sequence[int]) -> None:
    if len(main) != 6 or len(set(main)) != 6 or any(n not in range(1, 50) for n in main):
        raise ValueError("Expected six distinct main numbers in 1..49")


def follows(previous: str, current: str) -> bool:
    py, pn = issue_key(previous)
    cy, cn = issue_key(current)
    return (cy == py and cn == pn + 1) or (cy == py + 1 and cn == 1)


def validate_sequence(draws: Sequence[Draw]) -> None:
    for previous, current in zip(draws, draws[1:]):
        if not follows(previous.issue, current.issue) or current.day <= previous.day:
            raise ValueError("Draws must be consecutive, chronological and unique; never skip a draw")


def load_csv(path: Path) -> list[Draw]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Unexpected CSV header")
        draws = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row")
            draws.append(Draw(row[FIELDS[0]], date.fromisoformat(row[FIELDS[1]]),
                              tuple(int(row[f"正選號碼{i}"]) for i in range(1, 7)),
                              int(row["特別號碼"])))
    validate_sequence(draws)
    return draws


def load_training(path: Path = ROOT / "marksix_data.csv") -> list[Draw]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != DATA_SHA256:
        raise ValueError("Locked training CSV SHA-256 mismatch")
    draws = load_csv(path)
    if (len(draws), draws[0].issue, draws[-1].issue, draws[-1].day.isoformat()) != (
        69, "26/047", "26/115", "2026-10-27"
    ):
        raise ValueError("Locked training window mismatch")
    return draws


def load_protocol(path: Path = ROOT / "prereg/round2.yaml") -> dict:
    with path.open(encoding="utf-8") as stream:
        protocol = yaml.safe_load(stream)
    checks = (
        protocol["protocol_id"] == "prereg-r2",
        protocol["data"]["sha256"] == DATA_SHA256,
        protocol["data"]["first_draw"] == "26/047",
        protocol["data"]["last_draw"] == "26/115",
        protocol["data"]["special_number_used"] is False,
        protocol["window"]["first_draw"] == FIRST_DRAW,
        protocol["window"]["draws"] == HORIZON,
        protocol["window"]["extend_or_skip"] is False,
        protocol["H1"]["direction"] == "hot_first",
        protocol["H1"]["lambda"] == LAMBDA,
        protocol["H1"]["half_life_draws"] == HALF_LIFE,
        protocol["H1"]["previous_draw_age"] == 1,
        protocol["H1"]["ties"] == "average_rank",
        protocol["H1"]["pass_at_draw"] == HORIZON,
        protocol["H1"]["pass_threshold"] == E_THRESHOLD,
        protocol["H1"]["formal_betting"] is False,
        protocol["H3"]["pass_at_draw"] == HORIZON,
        protocol["H3"]["minimum_successes"] == H3_THRESHOLD,
        Fraction(protocol["H3"]["null_probability"]) == Q,
        tuple(map(tuple, protocol["H3"]["tickets"])) == TICKETS,
        protocol["futility"]["checkpoints"] == [
            {"draws": 20, "maximum_cumulative_H3_successes": 2},
            {"draws": 40, "maximum_cumulative_H3_successes": 5}],
        protocol["futility"]["early_success_allowed"] is False,
        protocol["validity"]["public_before_first_sales_cutoff_required"] is True,
        protocol["budget"]["tickets_per_draw"] == 8,
        protocol["budget"]["total_per_draw_hkd"] == 80,
    )
    if not all(checks):
        raise ValueError("Preregistration differs from the locked implementation")
    return protocol


def scores(history: Sequence[Draw]) -> tuple[float, ...]:
    """At the next target, the most recent draw has age=1, not zero."""
    values = [0.0] * 49
    for age, draw in enumerate(reversed(history), 1):
        weight = 2.0 ** (-age / HALF_LIFE)
        for number in draw.main:
            values[number - 1] += weight
    return tuple(values)


def average_ranks(values: Sequence[float]) -> tuple[float, ...]:
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for position in range(start, end):
            ranks[order[position]] = (start + 1 + end) / 2
        start = end
    return tuple(ranks)


def shadow_tickets(values: Sequence[float]) -> tuple[tuple[int, ...], ...]:
    order = sorted(range(1, 50), key=lambda n: (-values[n - 1], n))
    return tuple(tuple(order[i:i + 6]) for i in range(0, 48, 6))


def elementary_symmetric(values: Sequence[float], degree: int = 6) -> float:
    """Descending in-place updates prohibit selecting a ball twice."""
    if not 0 <= degree <= len(values):
        raise ValueError("Invalid elementary-symmetric degree")
    coefficients = [1.0] + [0.0] * degree
    for count, value in enumerate(values, 1):
        for k in range(min(degree, count), 0, -1):
            coefficients[k] += value * coefficients[k - 1]
    return coefficients[degree]


def conditional_denominator(ranks: Sequence[float]) -> float:
    if len(ranks) != 49:
        raise ValueError("Expected the current 49 average ranks")
    # Absorb exp(lambda*25) into six factors to reduce cancellation.
    weights = [math.exp(LAMBDA * (25 - rank) / 6) for rank in ranks]
    return elementary_symmetric(weights) / math.comb(49, 6)


def h1_step(ranks: Sequence[float], main: Sequence[int]) -> tuple[float, float]:
    validate_main(main)
    a = 25 - math.fsum(ranks[number - 1] for number in main) / 6
    return a, LAMBDA * a - math.log(conditional_denominator(ranks))


def success(main: Sequence[int], tickets=TICKETS) -> bool:
    validate_main(main)
    return any(len(set(main).intersection(ticket)) >= 3 for ticket in tickets)


def binomial_tail(k: int, n: int = HORIZON, q: Fraction = Q) -> Fraction:
    return sum((Fraction(math.comb(n, j)) * q ** j * (1 - q) ** (n - j)
                for j in range(k, n + 1)), Fraction(0))


def futility(n: int, cumulative_successes: int, cumulative_mean_rank: float) -> bool:
    limit = {20: 2, 40: 5}.get(n)
    return limit is not None and cumulative_successes <= limit and cumulative_mean_rank >= 25


def decision(n: int, log_e: float, cumulative_successes: int,
             cumulative_mean_rank: float, *, registration_valid: bool = False,
             invalidation_reason: str | None = None) -> dict:
    if not 0 <= n <= HORIZON or not 0 <= cumulative_successes <= n:
        raise ValueError("Invalid evaluation count")
    if invalidation_reason:
        state = "void_or_aborted"
    elif not registration_valid:
        state = "publication_unverified"
    elif futility(n, cumulative_successes, cumulative_mean_rank):
        state = "stopped_futility"
    elif n == HORIZON:
        state = "completed"
    else:
        state = "running"
    completed = state == "completed"
    return {"state": state, "H1_pass": completed and log_e >= math.log(E_THRESHOLD),
            "H3_pass": completed and cumulative_successes >= H3_THRESHOLD,
            "invalidation_reason": invalidation_reason}


def predict(history: Sequence[Draw], target: str) -> dict:
    validate_sequence(history)
    if not history or history[0].issue != "26/047" or not follows(history[-1].issue, target):
        raise ValueError("Prediction needs all history from 26/047 and the next target")
    values = scores(history)
    return {"protocol": "prereg-r2", "training_sha256": DATA_SHA256,
            "target": target, "through": history[-1].issue, "scores": values,
            "ranks": average_ranks(values), "H1_shadow": shadow_tickets(values),
            "H3_tickets": TICKETS, "budget_hkd": 80}


def evaluate(training: Sequence[Draw], forward: Sequence[Draw], *,
             registration_valid: bool = False, invalidation_reason: str | None = None,
             late_issues: Sequence[str] = ()) -> dict:
    if len(forward) > HORIZON:
        raise ValueError("Cannot extend the 60-draw window")
    if forward and forward[0].issue != FIRST_DRAW:
        raise ValueError("First prospective draw must remain 26/116")
    validate_sequence([*training, *forward])
    if set(late_issues) - {draw.issue for draw in forward}:
        raise ValueError("Late-submission issue absent from forward results")
    history = list(training)
    records, a_values = [], []
    log_e = 0.0
    hits = 0
    shadow_hits = []
    for n, draw in enumerate(forward, 1):
        prediction = predict(history, draw.issue)
        a, increment = h1_step(prediction["ranks"], draw.main)
        a_values.append(a)
        log_e += increment
        hit = success(draw.main)
        hits += hit
        shadow_hits.append(success(draw.main, prediction["H1_shadow"]))
        mean_rank = 25 - math.fsum(a_values) / n
        records.append({"n": n, "issue": draw.issue, "date": draw.day.isoformat(),
                        "prediction": prediction, "main": draw.main,
                        "special_excluded": draw.special, "A": a,
                        "log_E": log_e, "E": math.exp(log_e), "H3_success": hit,
                        "H1_shadow_success": shadow_hits[-1], "H3_cumulative": hits,
                        "cumulative_mean_rank": mean_rank,
                        "late_submission": draw.issue in late_issues})
        if n % 20 == 0:
            records[-1]["last_20"] = {
                "H3_successes": sum(row["H3_success"] for row in records[-20:]),
                "H3_rate": sum(row["H3_success"] for row in records[-20:]) / 20,
                "H1_shadow_rate": sum(shadow_hits[-20:]) / 20}
        history.append(draw)  # Observed main numbers update only the next target.
        if futility(n, hits, mean_rank):
            break
    n = len(records)
    mean_rank = 25 - math.fsum(a_values) / n if n else 25.0
    result = decision(n, log_e, hits, mean_rank, registration_valid=registration_valid,
                      invalidation_reason=invalidation_reason)
    result.update({"n": n, "log_E": log_e, "E": math.exp(log_e),
                   "sum_A_descriptive": math.fsum(a_values), "H3_successes": hits,
                   "records": records, "ignored_after_stop": len(forward) - n,
                   "futility_triggered": futility(n, hits, mean_rank),
                   "publication_attested": registration_valid,
                   "H1_failure_note": FAILURE_NOTE if result["state"] in (
                       "completed", "stopped_futility") and not result["H1_pass"] else None})
    return result


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("predict", "evaluate"))
    parser.add_argument("--training", type=Path, default=ROOT / "marksix_data.csv")
    parser.add_argument("--future", type=Path, help="Separate CSV with the same Chinese header")
    parser.add_argument("--target", help="Next draw; defaults to 26/116 only for initial prediction")
    parser.add_argument("--public-before-cutoff-verified", action="store_true",
                        help="Manager attestation; requires external public-tag and official-cutoff evidence")
    parser.add_argument("--invalidate", help="Machine/ball change, cancellation, postponement or late publication")
    parser.add_argument("--late", action="append", default=[], help="Late/missing prediction issue (repeatable)")
    args = parser.parse_args()
    load_protocol()
    training = load_training(args.training)
    future = load_csv(args.future) if args.future else []
    if args.command == "predict":
        state = evaluate(training, future)
        if args.invalidate or state["futility_triggered"] or len(future) >= HORIZON:
            parser.error("Round stopped, invalidated or completed; no further prediction")
        target = args.target or (FIRST_DRAW if not future else None)
        if target is None:
            parser.error("Supply --target for subsequent predictions (including year rollover)")
        output = predict([*training, *future], target)
    else:
        output = evaluate(training, future, registration_valid=args.public_before_cutoff_verified,
                          invalidation_reason=args.invalidate, late_issues=args.late)
    print(canonical_json(output), end="")


if __name__ == "__main__":
    main()
