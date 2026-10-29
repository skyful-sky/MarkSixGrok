"""One registered discovery-only descriptive calibration. No Hong Kong data.

The model process receives outcomes from a separate broker only after a
prediction journal entry is persisted and checked. Never imports old models.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ID = "CAL-EXT-GAP1-RAND-v1"
LOCK = ROOT / f"archive/{ID}.lock.json"
OUTPUT = ROOT / "calibration" / ID
GAMES = ("uk", "japan", "korea", "ssq")
Q = {"uk": Fraction(12344, 83237), "japan": Fraction(1221091, 6096454),
     "korea": Fraction(50363, 271502), "ssq": Fraction(218093, 553784)}
SPEC = {"id": ID, "role": "descriptive_calibration_not_prediction_attempt", "hk_attempt_cost": 0,
        "G": 15, "kappa": 30, "minimum_history": 20, "warmup_slots": 200, "max_scored_slots": 500,
        "gap_seed": 20261029, "random_seed": 20261030, "expanding": True,
        "unseen_bin": 15, "gap_rng_first_local_target": 21, "random_rng_first_local_target": 201,
        "j": 1, "alpha": "1/160", "confidence": "one-sided exact Clopper-Pearson lower",
        "success": "at least one of eight tickets has at least3 main balls; once per draw",
        "template": "r[(6*b+j)%N], b=0..7,j=0..5; SSQ fixed blue1 excluded from score",
        "missing": "retain NA at original slot; stop that dataset at first missing draw; no imputation or later replacement; suppress p/CI if missing",
        "inference": "GAP1 binomial upper tail against exact template q only; random/paired descriptive",
        "short_series": "first200 original slots warmup; score available following slots up to500; fewer than200 => zero scores",
        "same_tickets": "whole unordered eight-ticket configuration equality; also count individual shared tickets",
        "freeze": "one exclusive output directory; abort is recorded and not automatically rerun"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def environment():
    return {"python": sys.version, "implementation": platform.python_implementation(),
            "platform": platform.platform(), "random_state_version": random.Random(0).getstate()[0],
            "optimization": sys.flags.optimize, "runtime_dependencies": "Python standard library only"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_main(main, pool):
    require(len(main) == 6 and all(type(n) is int and 1 <= n <= pool for n in main)
            and list(main) == sorted(set(main)), "Invalid six main balls")


def tickets(order):
    pool = len(order)
    require(sorted(order) == list(range(1, pool + 1)), "Invalid ranking permutation")
    result = [[order[(6*b+j) % pool] for j in range(6)] for b in range(8)]
    require(all(len(set(t)) == 6 for t in result), "Repeated ball in ticket")
    require(len({tuple(sorted(t)) for t in result}) == 8, "Repeated whole ticket")
    return result


def midranks(values):
    return [1 + sum(x > v for x in values) + Fraction(sum(x == v for x in values)-1, 2) for v in values]


def ranked(values, rng):
    order = list(range(1, len(values) + 1))
    rng.shuffle(order)
    order.sort(key=lambda n: -values[n-1])  # stable and exact Fraction comparisons
    ranks = [0]*len(order)
    for i, number in enumerate(order, 1):
        ranks[number-1] = i
    return {"scores_exact": [str(x) for x in values], "order": order, "ranks": ranks,
            "score_midranks": [str(x) for x in midranks(values)], "tickets": tickets(order),
            "attached_blue_ball": 1 if len(order) == 33 else None}


class GapState:
    def __init__(self, pool):
        self.pool, self.count = pool, 0
        self.gaps, self.seen = [0]*pool, [False]*pool
        self.exposures, self.hits = [0]*16, [0]*16

    def bins(self):
        return [min(g, 15) if s else 15 for g, s in zip(self.gaps, self.seen)]

    def observe(self, main):
        valid_main(main, self.pool)
        chosen = set(main)
        for number, group in enumerate(self.bins(), 1):
            self.exposures[group] += 1
            self.hits[group] += number in chosen
        for i in range(self.pool):
            if i+1 in chosen:
                self.gaps[i], self.seen[i] = 0, True
            else:
                self.gaps[i] += 1
        self.count += 1

    def predict(self, rng):
        require(self.count >= 20, "Insufficient minimum history")
        prior = Fraction(6, self.pool)
        rates = [(h+30*prior)/(e+30) for h, e in zip(self.hits, self.exposures)]
        return ranked([rates[g] for g in self.bins()], rng)


def random_prediction(pool, rng):
    # All uniform scores tie, so stable sorting preserves exactly one shuffle.
    return ranked([Fraction(6, pool)]*pool, rng)


def validate_prediction(prediction, pool):
    order = prediction["order"]
    require(len(order) == pool and sorted(order) == list(range(1, pool+1)), "Ranking check failed")
    require(prediction["tickets"] == tickets(order), "Template check failed")
    require(prediction["attached_blue_ball"] == (1 if pool == 33 else None), "Blue policy changed")
    ranks = [0]*pool
    for i, n in enumerate(order, 1):
        ranks[n-1] = i
    require(prediction["ranks"] == ranks, "Rank map check failed")
    values = [Fraction(x) for x in prediction["scores_exact"]]
    require(len(values) == pool and all(0 <= x <= 1 for x in values), "Score check failed")
    require([values[n-1] for n in order] == sorted(values, reverse=True), "Score order check failed")
    require(prediction["score_midranks"] == [str(x) for x in midranks(values)], "Midrank check failed")


def binomial_upper(n, k, q):
    require(0 <= k <= n and 0 <= q <= 1, "Invalid binomial arguments")
    a, b = q.numerator, q.denominator
    return Fraction(sum(math.comb(n, i)*a**i*(b-a)**(n-i) for i in range(k, n+1)), b**n)


def cp_lower(n, k, alpha):
    if k == 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(90):
        p = (lo+hi)/2
        tail = math.fsum(math.comb(n, i)*p**i*(1-p)**(n-i) for i in range(k, n+1))
        if tail < float(alpha):
            lo = p
        else:
            hi = p
    return (lo+hi)/2


def group_score(prediction, main):
    chosen = set(main)
    hits = [len(chosen.intersection(t)) for t in prediction["tickets"]]
    rank_sum = sum(prediction["ranks"][n-1] for n in main)
    midrank_sum = sum((Fraction(prediction["score_midranks"][n-1]) for n in main), Fraction())
    return {"ticket_hits": hits, "max_hits": max(hits), "success": max(hits) >= 3,
            "main_rank_sum": rank_sum, "main_midrank_sum": str(midrank_sum)}


def paired(gap, control):
    return ("both" if control else "gap_only") if gap else ("random_only" if control else "neither")


def summary(records, game, alpha, inference=True):
    count = len(records)
    result = {"n": count, "paired": dict.fromkeys(["both", "gap_only", "random_only", "neither"], 0)}
    for model in ["gap1", "random"]:
        hits = sum(r[model]["success"] for r in records)
        result[model] = {"successes": hits, "rate": hits/count if count else None,
                         "difference_from_exact_q": hits/count-float(Q[game]) if count else None,
                         "mean_main_rank": sum(r[model]["main_rank_sum"] for r in records)/(6*count) if count else None,
                         "mean_main_midrank": float(sum((Fraction(r[model]["main_midrank_sum"]) for r in records), Fraction())/(6*count)) if count else None}
    for r in records:
        result["paired"][paired(r["gap1"]["success"], r["random"]["success"])] += 1
    result.update(paired_rate_difference=(result["gap1"]["successes"]-result["random"]["successes"])/count if count else None,
                  same_eight_ticket_draws=sum(r["same_configuration"] for r in records),
                  same_eight_ticket_rate=sum(r["same_configuration"] for r in records)/count if count else None,
                  shared_individual_tickets=sum(r["shared_tickets"] for r in records),
                  shared_ticket_fraction=sum(r["shared_tickets"] for r in records)/(8*count) if count else None)
    if count and inference:
        k = result["gap1"]["successes"]
        p = binomial_upper(count, k, Q[game])
        result["gap1"].update(binomial_upper_p=float(p), binomial_upper_p_exact=str(p),
                              lower_bound=cp_lower(count, k, alpha), lower_bound_alpha=str(alpha))
    elif inference:
        result["gap1"].update(binomial_upper_p=None, binomial_upper_p_exact=None, lower_bound=None, lower_bound_alpha=str(alpha))
    return result


def history_step(previous, row, main):
    return sha(bytes.fromhex(previous)+canonical({"ordinal": row["ordinal"], "issue": row["issue"], "main": main}))


def exclusive_json(path, value):
    with path.open("xb") as f:
        f.write(canonical(value)+b"\n")
        f.flush()
        os.fsync(f.fileno())


class Journal:
    def __init__(self, path):
        self.path, self.previous, self.offset = path, None, 0
        self.stream = path.open("xb")

    def append(self, payload):
        envelope = {"payload": payload, "payload_sha256": sha(canonical(payload)),
                    "previous_chunk_sha256": self.previous, "saved_at_utc": now()}
        line = canonical(envelope)+b"\n"
        self.stream.write(line)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        digest = sha(line)
        proof = {"offset": self.offset, "length": len(line), "sha256": digest, "fsync_complete_at_utc": now()}
        self.previous, self.offset = digest, self.offset+len(line)
        return proof

    def close(self):
        self.stream.close()


class RevealBroker:
    """Lives in a child process. Only validated committed predictions unlock results."""
    def __init__(self, game, rows, pool, source_sha, lock_sha, output):
        self.game, self.pool, self.source_sha, self.lock_sha = game, pool, source_sha, lock_sha
        self.rows, self.index, self.output = rows[:700], 0, output
        self.history_sha = sha(b"")
        self.offsets, self.previous = {}, {}
        self.masked = [{"ordinal": int(r.get("ordinal", r["issue"])), "issue": r["issue"], "date": r["date"],
                        "row_sha256": sha(canonical(r))} for r in self.rows]

    def metadata(self):
        # No main numbers or extra ball values cross the process boundary here.
        return [dict(row) for row in self.masked]

    def reveal(self, proof):
        require(self.index < len(self.rows), "No future/extra reveal")
        row, meta = self.rows[self.index], self.masked[self.index]
        local = self.index+1
        prediction_sha = None
        if local > 20:
            require(proof is not None, "Prediction must be saved before reveal")
            name = "predictions.jsonl" if local > 200 else "warmup-predictions.jsonl"
            path = self.output/name
            require(path.resolve().parent == self.output.resolve(), "Prediction path escaped")
            require(proof["offset"] == self.offsets.get(name, 0) and proof["length"] > 0, "Prediction journal sequence failed")
            with path.open("rb") as f:
                f.seek(proof["offset"])
                line = f.read(proof["length"])
                require(not f.read(1), "Uncommitted extra prediction bytes")
            require(sha(line) == proof["sha256"], "Prediction byte hash failed")
            envelope = json.loads(line)
            payload = envelope["payload"]
            require(envelope["payload_sha256"] == sha(canonical(payload)), "Prediction content hash failed")
            require(envelope["previous_chunk_sha256"] == self.previous.get(name), "Prediction hash chain failed")
            require(payload["target"] == meta and payload["game"] == self.game and payload["local_index"] == local, "Prediction target failed")
            require(payload["source_sha256"] == self.source_sha and payload["lock_sha256"] == self.lock_sha, "Source/lock hash failed")
            require(payload["history_sha256"] == self.history_sha and payload["training_draws"] == self.index, "History cutoff failed")
            expected_through = self.masked[self.index-1]
            require(payload["through"] == {"ordinal": expected_through["ordinal"], "issue": expected_through["issue"]}, "Issue cutoff failed")
            require(set(payload["models"]) == ({"gap1", "random"} if local > 200 else {"gap1"}), "Model set changed")
            for pred in payload["models"].values():
                validate_prediction(pred, self.pool)
            self.offsets[name] = proof["offset"]+proof["length"]
            self.previous[name] = prediction_sha = proof["sha256"]
        else:
            require(proof is None, "Unexpected prediction before minimum history")
        main = None if row["status"] == "missing" else [int(row[f"n{i}"]) for i in range(1, 7)]
        if main is not None:
            valid_main(main, self.pool)
        reveal = {"target": meta, "local_index": local, "main": main, "prediction_chunk_sha256": prediction_sha,
                  "revealed_at_utc": now(), "missing_reason": row.get("missing_reason", "NA")}
        if proof:
            require(proof["fsync_complete_at_utc"] <= reveal["revealed_at_utc"], "Reveal preceded durable prediction")
        if main is not None:
            self.history_sha = history_step(self.history_sha, meta, main)
        self.index += 1
        return reveal


def install_guard(audit_path):
    """Record discovery reads; deny old sealed directory reads in both processes."""
    fd = os.open(audit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    forbidden = (ROOT/"data/external").resolve()
    discovery = (ROOT/"data/discovery").resolve()

    def hook(event, args):
        if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if path.is_relative_to(forbidden):
            raise PermissionError("Sealed data/external access forbidden during calibration")
        if path.is_relative_to(discovery):
            os.write(fd, canonical({"path": str(path.relative_to(ROOT)), "time_utc": now()})+b"\n")
    sys.addaudithook(hook)
    return fd


def load_access():
    spec = importlib.util.spec_from_file_location("calibration_discovery_access", ROOT/"data/discovery/access.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def broker_main(game):
    directory = OUTPUT/game
    fd = install_guard(directory/"broker-access.jsonl")
    try:
        lock = json.loads(LOCK.read_bytes())
        record = next(x for x in lock["datasets"] if x["key"] == game)
        access = load_access()
        rows = access.load_discovery(game)
        require(sha((ROOT/f"data/discovery/{game}.csv").read_bytes()) == record["sha256"], "Locked source hash failed")
        broker = RevealBroker(game, rows, record["main_pool_expected"], record["sha256"], sha(LOCK.read_bytes()), directory)
        print(json.dumps({"ok": True, "metadata": broker.metadata()}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request["op"] == "close":
                break
            require(request["op"] == "reveal", "Unknown broker operation")
            print(json.dumps({"ok": True, "result": broker.reveal(request.get("proof"))}), flush=True)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        raise
    finally:
        os.fsync(fd)
        os.close(fd)


class BrokerClient:
    def __init__(self, game, directory):
        self.errors = (directory/"broker-stderr.txt").open("xb")
        self.process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--broker", game],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, text=True,
                                        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.metadata = self.receive()["metadata"]

    def receive(self):
        line = self.process.stdout.readline()
        require(bool(line), "Broker terminated without a response")
        result = json.loads(line)
        require(result["ok"], result.get("error", "Broker error"))
        return result

    def reveal(self, proof):
        self.process.stdin.write(json.dumps({"op": "reveal", "proof": proof})+"\n")
        self.process.stdin.flush()
        return self.receive()["result"]

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"op":"close"}\n')
            self.process.stdin.flush()
        self.process.stdin.close()
        self.process.stdout.close()
        require(self.process.wait(timeout=15) == 0, "Broker failed")
        self.errors.close()


def run_game(game, record, lock_hash):
    directory = OUTPUT/game
    directory.mkdir()
    broker = BrokerClient(game, directory)
    require(len(broker.metadata) == min(record["rows"], 700), "Locked period count changed")
    state, gap_rng, random_rng = GapState(record["main_pool_expected"]), random.Random(20261029), random.Random(20261030)
    journals = {"warmup": Journal(directory/"warmup-predictions.jsonl"),
                "scored": Journal(directory/"predictions.jsonl"), "outcomes": Journal(directory/"outcomes.jsonl")}
    history_hash, records, missing = sha(b""), [], None
    gap_advances = control_advances = 0
    try:
        for local, target in enumerate(broker.metadata, 1):
            payload = proof = None
            if local > 20:
                models = {"gap1": state.predict(gap_rng)}
                gap_advances += 1
                if local > 200:
                    models["random"] = random_prediction(state.pool, random_rng)
                    control_advances += 1
                through = broker.metadata[local-2]
                payload = {"id": ID, "game": game, "local_index": local, "target": target,
                           "through": {"ordinal": through["ordinal"], "issue": through["issue"]},
                           "training_draws": state.count, "history_sha256": history_hash,
                           "source_sha256": record["sha256"], "lock_sha256": lock_hash, "models": models}
                proof = journals["scored" if local > 200 else "warmup"].append(payload)
            reveal = broker.reveal(proof)
            require(reveal["target"] == target, "Revealed issue changed")
            if reveal["main"] is None:
                missing = target
                journals["outcomes"].append({"reveal": reveal, "score": None, "status": "NA_stop_no_replacement"})
                break
            main = reveal["main"]
            scored = None
            if local > 200:
                scored = {"target": target, "local_index": local,
                          **{model: group_score(pred, main) for model, pred in payload["models"].items()}}
                a, b = [{tuple(sorted(t)) for t in payload["models"][m]["tickets"]} for m in ["gap1", "random"]]
                scored.update(same_configuration=a == b, shared_tickets=len(a & b))
                records.append(scored)
            journals["outcomes"].append({"reveal": reveal, "score": scored, "prediction_receipt": proof})
            # Only now are exposures, hits and gaps updated using the revealed draw.
            state.observe(main)
            history_hash = history_step(history_hash, target, main)
    finally:
        for journal in journals.values():
            journal.close()
        broker.close()
    alpha = Fraction(SPEC["alpha"])
    total = summary(records, game, alpha)
    status = "missing_data_stopped" if missing else ("insufficient_warmup" if record["rows"] < 200
             else "partial_available_scoring" if record["rows"] < 700 else "completed_500")
    if missing:
        for key in ["binomial_upper_p", "binomial_upper_p_exact", "lower_bound"]:
            total["gap1"][key] = None
    result = {"game": game, "status": status, "available_slots": record["rows"],
              "warmup_slots_used": min(state.count, 200), "scored_slots_planned": max(0, min(record["rows"], 700)-200),
              "missing": missing, "gap_rng_shuffles": gap_advances, "random_rng_shuffles": control_advances,
              "exact_q": str(Q[game]), "q": float(Q[game]), "j": SPEC["j"], "alpha": str(alpha),
              "total": total, "blocks": [{"block": b+1, "local_slots": [201+100*b, 300+100*b],
                                          **summary([r for r in records if 201+100*b <= r["local_index"] <= 300+100*b], game, alpha, inference=False)} for b in range(5)],
              "inference_scope": "GAP1 total only; per-block values are descriptive, no extra tests or bounds",
              "confirmatory_eligible": False, "hk_attempt_cost": 0}
    exclusive_json(directory/"summary.json", result)
    return result


def check_lock():
    body = LOCK.read_bytes()
    lock = json.loads(body)
    require(lock["spec"] == SPEC, "Locked calibration parameters changed")
    require(lock["environment_sha256"] == sha(canonical(environment())), "Locked environment changed")
    for path, expected in lock["implementation_hashes"].items():
        require(sha((ROOT/path).read_bytes()) == expected, f"Locked implementation changed: {path}")
    require(sha((ROOT/"data/discovery/manifest.json").read_bytes()) == lock["discovery_manifest_sha256"], "Discovery manifest changed")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    committed = subprocess.check_output(["git", "show", f"{head}:archive/{ID}.lock.json"], cwd=ROOT)
    require(committed == body, "Lock is not committed before run")
    with (ROOT/lock["ledger_path"]).open() as f:
        rows = [r for r in csv.DictReader(f) if r["calibration_id"] == ID]
    require(len(rows) == 4 and {r["lottery"] for r in rows} == set(GAMES), "Calibration not registered")
    require(all(r["status"] == "locked" and r["j"] == "1" and r["hk_attempt_cost"] == "0" for r in rows), "Calibration ledger not locked")
    return lock, sha(body), head


def run():
    require(not OUTPUT.exists(), "Calibration already started/sealed; reruns forbidden")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    fd = install_guard(OUTPUT/"model-access.jsonl")
    try:
        lock, digest, commit = check_lock()
        exclusive_json(OUTPUT/"started.json", {"id": ID, "started_at_utc": now(), "lock_sha256": digest,
                                             "lock_commit": commit, "environment": environment(), "environment_sha256": sha(canonical(environment()))})
        results = [run_game(game, next(r for r in lock["datasets"] if r["key"] == game), digest) for game in GAMES]
        exclusive_json(OUTPUT/"results.json", {"id": ID, "role": SPEC["role"], "lock_commit": commit,
                                              "lock_sha256": digest, "datasets": results, "completed_at_utc": now(),
                                              "hk_attempt_cost": 0, "confirmatory_eligible": False})
        exclusive_json(OUTPUT/"sealed.json", {"id": ID, "sealed_at_utc": now(), "run_count": 1,
                                             "results_sha256": sha((OUTPUT/"results.json").read_bytes()), "rerun_allowed": False})
        for result in results:
            total = result["total"]
            print(result["game"], result["status"], "GAP", total["gap1"]["successes"], "/", total["n"],
                  "random", total["random"]["successes"], "/", total["n"], "p", total["gap1"]["binomial_upper_p"], flush=True)
    except Exception as exc:
        exclusive_json(OUTPUT/"aborted.json", {"id": ID, "aborted_at_utc": now(), "error": f"{type(exc).__name__}: {exc}", "rerun_allowed": False})
        raise
    finally:
        os.fsync(fd)
        os.close(fd)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--broker" and sys.argv[2] in GAMES:
        broker_main(sys.argv[2])
    elif sys.argv[1:] == ["--run"]:
        run()
    else:
        raise SystemExit("Use --run only after the lock commit; no parameter overrides or reruns")
