"""EV-COMP-NB-R3: exact grouped seven-feature NB2, one authorized run.

No tickets or financial counterfactuals. Does not invoke R1 or AUD-SERIAL runs.
Only tiny synthetic universes are used by tests before the implementation lock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
from itertools import chain, combinations, islice
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import scipy
from scipy import sparse
from scipy.optimize import minimize
from scipy.special import digamma, gammaln


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "ev/EV-COMP-NB-R3"
PREREG = ROOT / "docs/prereg/ev-comp-nb-r3.lock.json"
spec = importlib.util.spec_from_file_location("frozen_r1_helpers", ROOT / "src/ev_dyn_dilute_r1.py")
r1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r1)

DECADE_PARTITIONS = ((6,), (5, 1), (4, 2), (4, 1, 1), (3, 3), (3, 2, 1),
                     (3, 1, 1, 1), (2, 2, 2), (2, 2, 1, 1), (2, 1, 1, 1, 1))
GAP_PARTITIONS = ((5,), (4, 1), (3, 2), (3, 1, 1), (2, 2, 1), (2, 1, 1, 1),
                  (1, 1, 1, 1, 1))
DOMAIN = 7 * 2 * 5 * 7 * 7 * 10 * 7
ENUM_BATCH = 65536
MODELS = ("r3", "random", "static")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    r1.write_json(Path(path), value, exclusive=True)


def event(payload):
    path = HOME / "ledger.jsonl"
    previous = None
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line); digest = row.pop("record_sha256")
            if row["previous_sha256"] != previous or hashlib.sha256(r1.canonical(row)).hexdigest() != digest:
                raise ValueError("R3 append-only ledger changed")
            previous = digest
    row = dict(previous_sha256=previous,payload=payload)
    row["record_sha256"] = hashlib.sha256(r1.canonical(row)).hexdigest()
    with path.open("ab") as handle:
        handle.write(r1.canonical(row)+b"\n");handle.flush();os.fsync(handle.fileno())


def entropy_feature(partition, total):
    if len(partition) == 1:
        return 1.0
    if total == 5 and len(partition) == 5:
        return 0.0
    return 1 + sum((x / total) * math.log(x / total) for x in partition) / math.log(5)


DECADE_FEATURES = np.array([entropy_feature(p, 6) for p in DECADE_PARTITIONS])
GAP_FEATURES = np.array([entropy_feature(p, 5) for p in GAP_PARTITIONS])
DECADE_LOOKUP = np.full(36 * 217 + 217, -1, dtype=np.int8)
for i, partition in enumerate(DECADE_PARTITIONS):
    DECADE_LOOKUP[217 * sum(x*x for x in partition) + sum(x**3 for x in partition)] = i
GAP_LOOKUP = np.full(26, -1, dtype=np.int8)
for i, partition in enumerate(GAP_PARTITIONS):
    GAP_LOOKUP[sum(x*x for x in partition)] = i


def feature_codes(tickets, pool):
    """Unique integer class for the seven frozen features, using counts/partitions."""
    a = np.asarray(tickets)
    if a.ndim != 2 or a.shape[1] != 6:
        raise ValueError("Need sorted complete-six tickets")
    prime = np.array([n >= 2 and all(n % j for j in range(2, math.isqrt(n) + 1))
                      for n in range(pool + 1)])
    pc = prime[a].sum(axis=1)
    seven = (a == 7).any(axis=1)
    tail = ((a % 10 == 7) & (a != 7)).sum(axis=1)
    month = ((a >= 1) & (a <= 12)).sum(axis=1)
    day = ((a >= 13) & (a <= 31)).sum(axis=1)
    bins = a // 10
    counts = np.stack([(bins == i).sum(axis=1) for i in range(5)], axis=1)
    decade_key = 217 * (counts * counts).sum(axis=1) + (counts ** 3).sum(axis=1)
    dc = DECADE_LOOKUP[decade_key]
    gaps = np.diff(a.astype(np.int16), axis=1)
    gap_key = (gaps[:, :, None] == gaps[:, None, :]).sum(axis=(1, 2))
    gc = GAP_LOOKUP[gap_key]
    if np.any(dc < 0) or np.any(gc < 0):
        raise ValueError("Entropy partition class not recognized")
    code = ((((((pc * 2 + seven) * 5 + tail) * 7 + month) * 7 + day) * 10 + dc) * 7 + gc)
    return code.astype(np.int32)


def decode_features(codes):
    c = np.asarray(codes, dtype=np.int64).copy()
    gc, c = c % 7, c // 7
    dc, c = c % 10, c // 10
    day, c = c % 7, c // 7
    month, c = c % 7, c // 7
    tail, c = c % 5, c // 5
    seven, prime = c % 2, c // 2
    return np.column_stack((prime / 6, seven, tail / 6, month / 6, day / 6,
                            DECADE_FEATURES[dc], GAP_FEATURES[gc]))


def combo_array(values, degree):
    count = math.comb(len(values), degree) if degree <= len(values) else 0
    if not count:
        return np.empty((0, degree), dtype=np.uint8)
    return np.fromiter(chain.from_iterable(combinations(values, degree)), dtype=np.uint8,
                       count=count * degree).reshape(count, degree)


class ExactClasses:
    """Data-independent exact normalization and exact condition-on-draw projection."""
    def __init__(self, pool):
        if not 9 <= pool <= 49:
            raise ValueError("Supported complete-six universe is 9..49")
        self.pool = pool
        omega = np.zeros(DOMAIN, dtype=np.int64)
        iterator = combinations(range(1, pool + 1), 6)
        while True:
            batch = list(islice(iterator, ENUM_BATCH))
            if not batch:
                break
            codes = feature_codes(np.array(batch, dtype=np.uint8), pool)
            omega += np.bincount(codes, minlength=DOMAIN)
        self.codes = np.flatnonzero(omega).astype(np.int32)
        self.omega = omega[self.codes]
        if int(self.omega.sum()) != math.comb(pool, 6):
            raise ValueError("Exact normalization lost/duplicated combinations")
        self.features = decode_features(self.codes)
        self.lookup = np.full(DOMAIN, -1, dtype=np.int32)
        self.lookup[self.codes] = np.arange(len(self.codes))
        self.expected_sizes = np.array([1, 6, 6 * (pool - 7),
            15 * math.comb(pool - 6, 2), 20 * math.comb(pool - 6, 3)], dtype=np.int64)
        self.main_indices = {k: combo_array(list(range(6)), k) for k in (3, 4, 5)}
        self.out_indices = {k: combo_array(list(range(pool - 6)), k) for k in (2, 3)}
        birthday = np.rint((self.features[:, 3] + self.features[:, 4]) * 6).astype(int)
        self.birthday = birthday
        self.static_omega = np.bincount(birthday, weights=self.omega, minlength=7)

    def projection(self, main, bonus):
        if main is None:
            return sparse.csr_matrix((5, len(self.codes)), dtype=np.int32)
        main = np.array(main, dtype=np.uint8)
        if (len(main) != 6 or len(set(main.tolist())) != 6 or not np.all(main[1:] > main[:-1])
                or int(main[0]) < 1 or int(main[-1]) > self.pool
                or not 1 <= int(bonus) <= self.pool or int(bonus) in main):
            raise ValueError("Invalid complete main/bonus draw")
        outside = np.array([i for i in range(1, self.pool + 1) if i not in main], dtype=np.uint8)
        rest = outside[outside != bonus]
        groups = [main[None, :],
            np.column_stack((main[self.main_indices[5]], np.full(6, bonus, dtype=np.uint8)))]
        fives = main[self.main_indices[5]]
        groups.append(np.concatenate((np.repeat(fives, len(rest), axis=0),
                                      np.tile(rest, 6)[:, None]), axis=1))
        for k in (4, 3):
            inside = main[self.main_indices[k]]
            other = outside[self.out_indices[6-k]]
            groups.append(np.concatenate((np.repeat(inside, len(other), axis=0),
                                          np.tile(other, (len(inside), 1))), axis=1))
        indices, counts, pointers = [], [], [0]
        for tier, group in enumerate(groups):
            group.sort(axis=1)
            codes = feature_codes(group, self.pool)
            positions = self.lookup[codes]
            if np.any(positions < 0):
                raise ValueError("Projection class absent from full universe")
            counter = np.bincount(positions, minlength=len(self.codes))
            if int(counter.sum()) != int(self.expected_sizes[tier]):
                raise ValueError("Exact prize projection lost/duplicated combinations")
            present = np.flatnonzero(counter)
            indices.extend(present.tolist()); counts.extend(counter[present].tolist())
            pointers.append(len(indices))
        return sparse.csr_matrix((np.array(counts, dtype=np.int32),
                                  np.array(indices, dtype=np.int32),
                                  np.array(pointers, dtype=np.int32)), shape=(5, len(self.codes)))

    def save(self, path):
        np.savez_compressed(path, codes=self.codes, omega=self.omega,
                            features=self.features, expected_sizes=self.expected_sizes)


def q_and_gradient(theta, features, omega, projection):
    logits = features @ theta
    weights = np.exp(logits - logits.max())
    denominator = float(omega @ weights)
    numerator = np.asarray(projection @ weights).ravel()
    q = numerator / denominator
    if not np.isfinite(q).all() or np.any(q <= 0) or np.any(q > 1 + 1e-12):
        raise ValueError("Nonfinite/invalid exact tier probability")
    return q, weights, numerator, denominator


def nb_values_gradient(y, mu, shape):
    """NB2 including zero, derivatives in log(mu) and log(shape)."""
    total = shape + mu
    logp = (gammaln(y + shape) - gammaln(shape) - gammaln(y + 1)
            + shape * (np.log(shape) - np.log(total))
            + y * (np.log(mu) - np.log(total)))
    dlogmu = shape * (y - mu) / total
    dlogr = shape * (digamma(y + shape) - digamma(shape) + np.log(shape / total)
                    + 1 - (shape + y) / total)
    return logp, dlogmu, dlogr


def objective_factory(history, matrix, classes, kind):
    observed = [(i, k, y) for i, row in enumerate(history)
                if row["sales"] is not None and row["ticket_price"] is not None
                for k, y in enumerate(row["counts"]) if y is not None]
    if not observed:
        raise ValueError("No valid past NB2 count cells")
    ii, kk, yy = map(np.array, zip(*observed)); ii, kk = ii.astype(int), kk.astype(int)
    exposures = np.array([history[i]["sales"] / history[i]["ticket_price"] for i in ii])
    if not np.isfinite(exposures).all() or np.any(exposures <= 0):
        raise ValueError("Invalid observed training entry count")
    projection = matrix[ii * 5 + kk]
    if kind == "r3":
        features, omega = classes.features, classes.omega
    elif kind == "static":
        # Exact aggregation by the single <=31 count, not a new feature/model.
        onehot = sparse.csr_matrix((np.ones(len(classes.codes)),
            (np.arange(len(classes.codes)), classes.birthday)), shape=(len(classes.codes), 7))
        projection = (projection @ onehot).toarray()
        features, omega = np.arange(7)[:, None] / 6, classes.static_omega
    elif kind == "random":
        features, omega, projection = np.empty((0, 0)), None, None
    else:
        raise ValueError("Unknown locked model")
    dimension = 0 if kind == "random" else features.shape[1]
    uniform = r1.uniform_tiers(classes.pool)[kk]

    def objective(parameters):
        theta, logs = parameters[:dimension], parameters[dimension:]
        shape = np.exp(logs)[kk]
        if kind == "random":
            q = uniform
        else:
            q, weights, numerator, denominator = q_and_gradient(theta, features, omega, projection)
        ll, dm, dr = nb_values_gradient(yy, exposures * q, shape)
        value = -float(ll.mean()) + .1 / 2 * float(theta @ theta)
        value += .01 / 2 * float(np.sum((logs - math.log(30)) ** 2))
        grad_shape = np.bincount(kk, weights=-dr / len(yy), minlength=5)
        grad_shape += .01 * (logs - math.log(30))
        if kind == "random":
            gradient = grad_shape
        else:
            sensitivity = -dm / len(yy)
            lifted = np.asarray(projection.T @ (sensitivity / numerator)).ravel()
            expectation = features.T @ (omega * weights) / denominator
            gradient_theta = features.T @ (weights * lifted) - sensitivity.sum() * expectation + .1 * theta
            gradient = np.r_[gradient_theta, grad_shape]
        if not math.isfinite(value) or not np.isfinite(gradient).all():
            raise ValueError("Nonfinite exact NB2 objective or analytic gradient")
        return value, gradient

    return objective, dimension, len(observed)


def fit(history, matrix, classes, kind):
    objective, dimension, observed = objective_factory(history, matrix, classes, kind)
    initial = np.r_[np.zeros(dimension), np.full(5, math.log(30))]
    bounds = [(-4, 4)] * dimension + [(math.log(.1), math.log(10000))] * 5
    result = minimize(objective, initial, jac=True, method="L-BFGS-B", bounds=bounds,
                      options=dict(maxiter=1000, maxfun=30000, maxls=50, ftol=1e-10, gtol=1e-5))
    return dict(kind=kind, values=result.x.tolist(), theta_dimension=dimension,
                success=bool(result.success), status=int(result.status), message=str(result.message),
                objective=float(result.fun), nit=int(result.nit), nfev=int(result.nfev), njev=int(result.njev),
                gradient_max_abs=float(np.max(np.abs(result.jac))), observed_training_cells=observed,
                missing_training_cells=len(history)*5-observed,
                max_training_issue=max(row["issue"] for row in history))


def frozen_q(fitted, projection, classes):
    kind, dimension = fitted["kind"], fitted["theta_dimension"]
    if kind == "random":
        return r1.uniform_tiers(classes.pool)
    theta = np.array(fitted["values"][:dimension])
    if kind == "static":
        theta = np.r_[np.zeros(3), theta[0], theta[0], 0, 0]
    return q_and_gradient(theta, classes.features, classes.omega, projection)[0]


def primary_comparison(gains, country_index, bootstrap_path=None):
    a = np.asarray(gains, dtype=float)
    if len(a) == 0 or not np.isfinite(a).all():
        raise ValueError("Invalid paired score gains")
    generator = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261030, 20, country_index, 0])))
    starts = generator.integers(0, len(a), size=(10000, math.ceil(len(a) / 10)))
    indices = ((starts[:, :, None] + np.arange(10)) % len(a)).reshape(10000, -1)[:, :len(a)]
    mean = float(a.mean())
    centered = a[indices].mean(axis=1) - mean
    if bootstrap_path is not None:
        np.savez_compressed(bootstrap_path, centered_bootstrap_mean=centered)
    p = (1 + int((centered >= mean).sum())) / 10001
    lower = float(mean - np.quantile(centered, .9875))
    return dict(n=len(a), mean_log_score_gain=mean, lower_9875=lower, p_value=p, alpha=.0125,
                pass_count=bool(len(a) >= 200 and mean > 0 and lower > 0 and p <= .0125),
                seed_sequence_entropy=[20261030, 20, country_index, 0], block_length=10, bootstrap_reps=10000,
                inference="nominal exploratory screen; prior EV comparisons/exposure not reset")


def install_guard():
    forbidden = [(ROOT / p).resolve() for p in ("data/external", "marksix_data.csv", "audits/AUD-SERIAL-K6-v1/run")]
    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if any(path == p or path.is_relative_to(p) for p in forbidden):
                raise PermissionError("R3 forbids sealed windows, HK CSV and AUD result access")
    sys.addaudithook(guard)


class SourceBroker(r1.SourceBroker):
    """Keep an unverifiable original slot as NA, never guess or replace balls."""
    def _outcome(self, country, issue):
        try:
            value = super()._outcome(country, issue)
            value["source_na_reason"] = None
            return value
        except (ValueError, KeyError, IndexError, StopIteration, UnicodeDecodeError) as exc:
            row = self.rows[country][issue]
            return dict(issue=issue, date=row["draw_date"], main=None, bonus=None,
                        counts=[None]*5, sales=None, ticket_price=None,
                        original_announcement=row["announcement_at_utc"],
                        legal_version=row["full_prize_rule_version"],
                        source_sha256=None, source_key=None,
                        source_na_reason=type(exc).__name__ + ": " + str(exc))


def verify():
    prereg = json.loads(PREREG.read_text())
    implementation = json.loads((HOME / "implementation-lock.json").read_text())
    for name, expected in {**prereg["inputs_sha256"], **implementation["files_sha256"]}.items():
        if sha(ROOT / name) != expected:
            raise ValueError("Locked input/implementation hash mismatch: " + name)
    if (platform.python_version() != implementation["environment"]["python"] or
            np.__version__ != implementation["environment"]["numpy"] or
            scipy.__version__ != implementation["environment"]["scipy"]):
        raise ValueError("Locked runtime changed")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("Commit a clean implementation before run")
    subprocess.run(["git", "merge-base", "--is-ancestor", implementation["prereg_commit"], "HEAD"],
                   cwd=ROOT, check=True)
    return prereg, implementation


def run():
    install_guard()
    prereg, implementation = verify()
    out = HOME / "run"; out.mkdir(exist_ok=False)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    started = dict(id="EV-COMP-NB-R3", run_count=1, started_at_utc=now(), implementation_commit=commit,
                   prereg_commit=implementation["prereg_commit"], prereg_sha256=prereg["prereg_sha256"],
                   implementation_lock_sha256=sha(HOME / "implementation-lock.json"))
    write(out / "started.json", started)
    event(dict(event="run_started", **started))
    cfg = {"countries": {c: {**s, "pool": 49 if c == "uk" else 43,
                             "weekday": 5 if c == "uk" else 0} for c, s in prereg["countries"].items()},
           "time_center": 800.5, "time_scale": 500, "sales_ridge": [0, 10, 10]}
    journal, scores_path = out / "predictions.jsonl", out / "scores.jsonl"
    countries, comparisons = {}, []
    try:
        broker = SourceBroker(ROOT / "data/discovery/ev1", cfg)
        old_scores = [json.loads(line) for line in (ROOT / "ev/EV-DYN-DILUTE-R1/run/scores.jsonl").read_text().splitlines()]
        old = {(r["country"], r["issue"]): r for r in old_scores}
        for ci, (country, spec_country) in enumerate(cfg["countries"].items()):
            pool = spec_country["pool"]
            print(country, "exact full-universe class enumeration starting", flush=True)
            classes = ExactClasses(pool)
            classes.save(out / (country + ".exact-classes.npz"))
            print(country, "exact combinations", int(classes.omega.sum()), "classes", len(classes.codes), flush=True)
            history = broker.training(country)
            projections = []
            for i, row in enumerate(history):
                projections.append(classes.projection(row["main"], row["bonus"]))
                if (i+1) % 50 == 0:
                    print(country, "warmup exact projections", i+1, flush=True)
            records, updates, revealed, failed = [], [], [], None
            fits, sales = None, None
            for slot in broker.slots[country][200:]:
                target = slot["issue"]
                if (target - 901) % 20 == 0:
                    matrix = sparse.vstack(projections, format="csr")
                    sales = r1.fit_sales(history, spec_country["weekday"], cfg)
                    fits = {}
                    for kind in MODELS:
                        try:
                            fitted = fit(history, matrix, classes, kind)
                        except (ValueError, FloatingPointError, ArithmeticError) as exc:
                            fitted = dict(kind=kind, values=[], success=False, status=-1,
                                          message=type(exc).__name__+": "+str(exc), nit=0)
                        fits[kind] = fitted
                        print(country, target, kind, fitted["success"], fitted["nit"], fitted["message"], flush=True)
                        if not fitted["success"] or not np.isfinite(fitted["values"]).all():
                            failed = dict(target_issue=target, kind=kind, reason="optimizer_failure", fit=fitted)
                            break
                    updates.append(dict(target_issue=target, history_through=history[-1]["issue"],
                                        sales=sales, fits=fits))
                    write(out / f"{country}.update-{target}.json", updates[-1])
                    if failed:
                        break
                prediction = dict(id="EV-COMP-NB-R3", country=country, target_issue=target,
                    target_date=slot["date"], created_at_utc=now(), history_through=history[-1]["issue"],
                    max_training_issue=fits["r3"]["max_training_issue"],
                    forecast_entries=r1.forecast_entries(sales, slot, cfg),
                    parameters={k: f["values"] for k, f in fits.items()},
                    conditional_count_function="exact classes/prize projection; draw supplied only after receipt reveal",
                    implementation_commit=commit, prereg_sha256=prereg["prereg_sha256"], tickets_generated=0)
                offset, fingerprint = r1.append_prediction(journal, prediction)
                actual = broker.reveal(country, target, journal, offset, fingerprint)
                projection = classes.projection(actual["main"], actual["bonus"])
                valid = [k for k, y in enumerate(actual["counts"]) if y is not None]
                scores, tier_scores, probabilities = {}, {}, {}
                for kind in MODELS:
                    fitted = fits[kind]
                    if actual["main"] is None:
                        probabilities[kind], scores[kind], tier_scores[kind] = None, None, {}
                        continue
                    q = frozen_q(fitted, projection, classes)
                    if q.sum() > 1 + 1e-12:
                        raise ValueError("Five disjoint prize probabilities exceed one")
                    probabilities[kind] = q.tolist()
                    shape = np.exp(fitted["values"][fitted["theta_dimension"]:])
                    ll = nb_values_gradient(np.array([actual["counts"][k] for k in valid]),
                        prediction["forecast_entries"] * q[valid], shape[valid])[0]
                    scores[kind] = float(ll.mean()) if valid else None
                    tier_scores[kind] = {str(k+1): float(v) for k, v in zip(valid, ll)}
                record = dict(country=country, issue=target, observed_count_cells=len(valid),
                    count_values=actual["counts"], scores=scores, log_probability_by_tier=tier_scores,
                    conditional_tier_probabilities=probabilities, prediction_offset=offset,
                    prediction_sha256=fingerprint, source_sha256=actual["source_sha256"],
                    source_na_reason=actual["source_na_reason"],
                    r1_reused_log_probability_by_tier=old[(country,target)]["log_probability_by_tier"]["dynamic"])
                if not all(v is None or math.isfinite(v) for v in scores.values()):
                    raise ValueError("Nonfinite predictive log score")
                with scores_path.open("ab") as handle:
                    handle.write(r1.canonical(record) + b"\n");handle.flush();os.fsync(handle.fileno())
                records.append(record);revealed.append(actual)
                history.append(actual);projections.append(projection)
            paired = [r["scores"]["r3"] - r["scores"]["random"] for r in records if r["scores"]["r3"] is not None]
            if failed:
                comparison = dict(n=len(paired), mean_log_score_gain=float(np.mean(paired)) if paired else None,
                    lower_9875=None, p_value=None, pass_count=False, reason="country stopped at first optimizer failure; no retry")
            else:
                comparison = primary_comparison(paired, ci, out / (country + ".bootstrap.npz"))
            comparisons.append(dict(country=country, comparison="R3_vs_Random", **comparison))
            # Descriptive secondary differences only; R1 per-tier values are reused.
            static_gains, r1_gains = [], []
            for row in records:
                if row["scores"]["r3"] is None:
                    continue
                static_gains.append(row["scores"]["r3"]-row["scores"]["static"])
                common = sorted(set(row["log_probability_by_tier"]["r3"]) & set(row["r1_reused_log_probability_by_tier"]))
                if common:
                    r1_gains.append(float(np.mean([row["log_probability_by_tier"]["r3"][k]
                        -row["r1_reused_log_probability_by_tier"][k] for k in common])))
            countries[country] = dict(status="archived_optimizer_failure" if failed else "count_scoring_complete",
                planned_score_n=spec_country["scoring"][1]-900, processed_score_slots=len(records),
                valid_paired_score_n=len(paired), failed=failed, updates_completed=len(updates),
                exact_universe_size=int(classes.omega.sum()), exact_feature_classes=len(classes.codes),
                observed_count_cells=sum(r["observed_count_cells"] for r in records),
                missing_count_cells=len(records)*5-sum(r["observed_count_cells"] for r in records),
                mean_scores={k: float(np.mean([r["scores"][k] for r in records if r["scores"][k] is not None]))
                             if paired else None for k in MODELS},
                descriptive_secondary={"R3_minus_static_mean": float(np.mean(static_gains)) if static_gains else None,
                                       "R3_minus_sealed_R1_same_cell_mean": float(np.mean(r1_gains)) if r1_gains else None,
                                       "p_values": None, "R1_refits": 0},
                financial_gate=r1.financial_gate(revealed), count_pass=comparison["pass_count"])
            sparse.save_npz(out / (country + ".revealed-projections.npz"), sparse.vstack(projections, format="csr"))
            print(country, countries[country]["status"], "scored", len(paired), flush=True)
        count_pass = all(c["count_pass"] for c in countries.values())
        results = dict(**started, completed_at_utc=now(), status="archived", countries=countries,
            primary_comparisons=comparisons, both_countries_count_pass=count_pass,
            financial_pass=False, passed=False, conditional_payout_ratio=None, corrected_payout_ratio_lower=None,
            roi_lower=None, positive_ev=False,
            reason="No complete legal/timing/payout inputs or separately locked cashflow/ticket protocol; financial gate NA. Count gate reported separately without substitution.",
            ev_comparison_accounting={"previous_R1_comparisons":4,"R3_primary_slots":2,"new_confirmatory_alpha_budget":False},
            hk_attempts_added=0, hk_attempts_cumulative=14, tickets_generated=0, AUD_SERIAL_reruns=0,
            prediction_journal_sha256=sha(journal) if journal.exists() else None,
            score_file_sha256=sha(scores_path) if scores_path.exists() else None)
        write(out / "results.json", results)
        event(dict(event="run_completed",at_utc=now(),run_count=1,status=results["status"],
                   results_sha256=sha(out/"results.json"),hk_attempts_added=0))
    except BaseException as exc:
        write(out / "aborted.json", dict(run_count=1, status="aborted_archived_do_not_rerun",
                                         error_type=type(exc).__name__, error=str(exc), at_utc=now()))
        event(dict(event="aborted_archived",at_utc=now(),run_count=1,error=str(exc),no_rerun=True))
        raise
    files = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    write(out / "sealed.json", dict(run_count=1,status="archived",sealed_at_utc=now(),files_sha256=files,
                                    ledger_sha256=sha(HOME/"ledger.jsonl")))
    print(json.dumps(dict(status=results["status"], comparisons=comparisons, results_sha256=sha(out/"results.json"))), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", required=True)
    parser.parse_args()
    run()
