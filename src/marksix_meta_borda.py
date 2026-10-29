"""Forward-only, equal-weight ten-model Borda shadow; no backtest command."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
from zoneinfo import ZoneInfo

import numpy as np
import yaml

import marksix_r2 as r2
import marksix_shadows as legacy
import marksix_shadow_batch2 as batch2

ROOT = r2.ROOT
SEED = 20261029
PROTOCOL = ROOT / "prereg/round3.yaml"
CODE_LOCK = ROOT / "archive/meta-borda-v1.lock.json"
COMPONENTS = ("SH-GAP1", "SH-GAP20-v1", "SH-LAG1-v1", "SH-LAG-RNO-v1", "SH-HARM48-v1",
              "SH-WDAY20-v1", "SH-RESFOLD-v1", "SH-CENTROID-v1", "SH-TAIL-v1", "SH-ORDSTAT-v1")
SPEC = {"id": "SH-META-BORDA-v1", "components": list(COMPONENTS), "weights": "all exactly1/10",
    "component_rank": "actual fixed ticket-order positions1..49 for every component; do not mix historical reporting midranks",
    "score": "integer sum of10 component ranks; ascending; mean=sum/10",
    "ties": "independent Python Random20261029 forward stream starting26/116; stable sort ascending rank sum",
    "component_seeds": "continue each legacy seeded component stream from its original first eligible draw067; advance prior permutations without scoring old outcomes",
    "tickets": "first48 positions cut6; exclude49th position", "first_draw": "26/116",
    "first_target_date": "2026-10-31", "historical_screening": False,
    "same_window_attempt_cost": 0, "formal_bet_added_hkd": 0,
    "confirmation": "logging-only shadow; no pass statistic, alpha or confirmation horizon allocated; separate protocol needed before any inferential claim"}


def seeded_component_rng(history_count: int) -> random.Random:
    rng = random.Random(SEED)
    for _ in range(max(0, history_count - 20)):
        priority = list(range(1, 50)); rng.shuffle(priority)
    return rng


def component_record(values, rng=None) -> dict:
    priority = list(range(1, 50))
    if rng is not None: rng.shuffle(priority)
    order = sorted(priority, key=lambda n: -values[n - 1])
    ranks = [0] * 49
    for rank, n in enumerate(order, 1): ranks[n - 1] = rank
    return {"scores": [str(value) for value in values], "order": order, "ranks": ranks}


def aggregate_ranks(components: dict, forward_index: int = 0) -> dict:
    if tuple(components) != COMPONENTS:
        raise ValueError("All ten fixed components required, no selection or reweighting")
    if any(sorted(rec["ranks"]) != list(range(1, 50)) for rec in components.values()):
        raise ValueError("Each component needs all49 actual ticket-order ranks")
    sums = [sum(rec["ranks"][j] for rec in components.values()) for j in range(49)]
    rng = random.Random(SEED)
    for _ in range(forward_index):
        priority = list(range(1, 50)); rng.shuffle(priority)
    priority = list(range(1, 50)); rng.shuffle(priority)
    order = sorted(priority, key=lambda n: sums[n - 1])
    ranks = [0] * 49
    for rank, n in enumerate(order, 1): ranks[n - 1] = rank
    return {"rank_sum_keys": sums, "mean_component_ranks": [value / 10 for value in sums],
            "order": order, "ranks": ranks, "tickets": [order[i:i + 6] for i in range(0, 48, 6)],
            "excluded": order[-1]}


def predict(history, target: str, target_date: date, forward_index: int = 0) -> dict:
    r2.validate_sequence(history)
    if len(history) < 20 or history[0].issue != "26/047" or not r2.follows(history[-1].issue, target):
        raise ValueError("Use complete past history from047 and the immediate next target")
    if target_date <= history[-1].day:
        raise ValueError("Target date must be future relative to observed history")
    n = len(history)
    state = legacy.HistoryState()
    for draw in history: state.observe(draw)
    components = {}
    for model in COMPONENTS[:4]:
        rng = seeded_component_rng(n) if legacy.MODEL_SPECS[model]["ties"] == "seeded_permutation" else None
        prediction = legacy.predict(state, model, rng)
        values = state.scores(model)
        order = [0] * 49
        for number, rank in enumerate(prediction["ranks"], 1): order[rank - 1] = number
        components[model] = {"scores": [str(x) for x in values], "order": order, "ranks": prediction["ranks"]}
    sets = [set(draw.main) for draw in history]
    L = min(48, n)
    harmonic = [round(2 / (3 * L) * sum(((j in sets[u]) - 6 / 49) * math.cos(2 * math.pi * (n - u) / p)
                     for p in (8, 12, 16) for u in range(n - L, n)), 12) for j in range(1, 50)]
    components["SH-HARM48-v1"] = component_record(harmonic)
    weekday_indices = [u for u, draw in enumerate(history) if draw.day.weekday() == target_date.weekday()]
    weekday = []
    for j in range(1, 50):
        b = (sum(j in row for row in sets) + 20 * 6 / 49) / (n + 20)
        weekday.append(round((sum(j in sets[u] for u in weekday_indices) + 20 * b) / (len(weekday_indices) + 20) - b, 12))
    components["SH-WDAY20-v1"] = component_record(weekday)
    masks = batch2.main_masks(history)
    phase_hits = {p: np.zeros((1, p, 49), np.int16) for p in batch2.PERIODS}
    numbers = np.arange(1, 50)
    tails = numbers % 10
    tail_members = (tails[:, None] == np.arange(10)).astype(int)
    center_sum = np.zeros(1); center_weight = 0.0
    tail_sum = np.zeros((1, 10)); tail_weight = 0.0
    locations_sum = np.zeros((1, 6)); locations_weight = 0.0
    for u in range(n):
        current = masks[:, u, :]
        for period in batch2.PERIODS: phase_hits[period][:, u % period, :] += current
        center_sum = 2 ** (-1 / 5) * center_sum + current @ numbers / 6
        center_weight = 2 ** (-1 / 5) * center_weight + 1
        tail_sum = 2 ** (-1 / 10) * tail_sum + current @ tail_members
        tail_weight = 2 ** (-1 / 10) * tail_weight + 1
        locations_sum = 2 ** (-1 / 10) * locations_sum + np.sort(np.where(current, numbers, 50), axis=1)[:, :6]
        locations_weight = 2 ** (-1 / 10) * locations_weight + 1
    folded, denominator = batch2.resfold_keys(phase_hits, n)
    components["SH-RESFOLD-v1"] = component_record([Fraction(int(x), denominator) for x in folded[0]], seeded_component_rng(n))
    center = center_sum[0] / center_weight
    components["SH-CENTROID-v1"] = component_record(-np.abs(numbers - center))
    density = tail_sum[0] / tail_weight / np.bincount(tails, minlength=10)
    components["SH-TAIL-v1"] = component_record(density[tails], seeded_component_rng(n))
    locations = locations_sum[0] / locations_weight
    distances = np.min(np.abs(numbers[:, None] - locations[None, :]), axis=1)
    components["SH-ORDSTAT-v1"] = component_record(-distances)
    result = aggregate_ranks(components, forward_index)
    result.update(model="SH-META-BORDA-v1", protocol="prereg-r3", target=target, target_date=target_date.isoformat(),
        through=history[-1].issue, history_rows=n, training_sha256=r2.DATA_SHA256, components=components,
        shadow_only=True, formal_bet_added_hkd=0, historical_screening_performed=False)
    return result


def verify_lock() -> tuple[dict, str]:
    raw = CODE_LOCK.read_bytes(); lock = json.loads(raw)
    if lock["specification"] != SPEC:
        raise ValueError("META specification differs from lock")
    for filename, expected in lock["file_sha256"].items():
        if hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"META dependency changed: {filename}")
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["specification"] != SPEC:
        raise ValueError("prereg-r3 specification mismatch")
    return lock, hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=ROOT / "forward/meta-borda")
    args = parser.parse_args()
    lock, lock_hash = verify_lock()
    history = r2.load_training()
    existing = list(args.output_directory.glob("26-116.prediction.*.json")) if args.output_directory.exists() else []
    if existing: parser.error("Initial META prediction already exists; do not overwrite or rerun")
    result = predict(history, SPEC["first_draw"], date.fromisoformat(SPEC["first_target_date"]))
    payload = canonical_json(result).encode()
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    path = args.output_directory / f"26-116.prediction.{stamp}.json"
    result["audit"] = {"recorded_at_utc": now.isoformat(), "recorded_at_hkt": now.astimezone(ZoneInfo('Asia/Hong_Kong')).isoformat(),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "lock_sha256": lock_hash, "prereg_r3_sha256": lock["file_sha256"]["prereg/round3.yaml"],
        "deterministic_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "payload_hash_definition": "canonical_json of all top-level fields except audit,UTF8 with trailing LF",
        "historical_component_backtests_rerun": False, "same_window_attempt_cost": 0,
        "purpose": "forward paper shadow only; no pass statistic/alpha or inferential confirmation allocated",
        "public_preregistration_verified": False, "original_formal_26116_unchanged": True}
    content = canonical_json(result).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(content)
    with Path(str(path)+'.sha256').open('x',encoding='ascii') as stream:
        stream.write(f'{hashlib.sha256(content).hexdigest()}  {path.name}\n')
    print(canonical_json({"path": str(path.relative_to(ROOT)), "recorded_at_hkt": result['audit']['recorded_at_hkt'],
        "tickets": result['tickets'], "payload_sha256": result['audit']['deterministic_payload_sha256']}), end='')


if __name__ == "__main__": main()
