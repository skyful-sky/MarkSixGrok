"""Locked, one-run EV count diagnostics. Never edits input or HK artifacts.

The financial result is NA when the source's legal/timing fields are NA.
Paper portfolios minimize modeled crowd probability, not a claimed actual EV.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timezone
import gzip
import hashlib
import heapq
import importlib.util
import io
import csv
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import unicodedata

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.special import loggamma
from scipy.stats import t as student_t


ROOT = Path(__file__).resolve().parents[1]
ID = "EV-DYN-DILUTE-R1"
EV_HOME = ROOT / "ev" / ID
DATA = ROOT / "data/discovery/ev1"
spec = importlib.util.spec_from_file_location("ev_source_parser", ROOT / "docs/review-evidence/prepare_ev1.py")
source_parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_parser)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, obj, exclusive=False):
    with path.open("xb" if exclusive else "wb") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n")
        f.flush()
        os.fsync(f.fileno())


def rng(seed, purpose, country=0, comparison=0):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, purpose, country, comparison])))


def features(pool):
    n = np.arange(1, pool + 1, dtype=float)
    return np.column_stack(((n - (pool + 1) / 2) / pool,
                            (n <= 31) - 31 / pool,
                            (n % 2 == 1) - math.ceil(pool / 2) / pool,
                            (n % 5 == 0) - math.floor(pool / 5) / pool))


def esp(weights, degree=6):
    """Elementary symmetric sums for each matrix row, including complex steps."""
    weights = np.atleast_2d(weights)
    e = np.zeros((len(weights), degree + 1), dtype=weights.dtype)
    e[:, 0] = 1
    for j in range(weights.shape[1]):
        for k in range(min(j + 1, degree), 0, -1):
            e[:, k] += weights[:, j] * e[:, k - 1]
    return e


def uniform_tiers(pool):
    denominator = math.comb(pool, 6)
    return np.array([1, 6, 6 * (pool - 7),
                     math.comb(6, 4) * math.comb(pool - 6, 2),
                     math.comb(6, 3) * math.comb(pool - 6, 3)]) / denominator


def preference_tiers(weights, main, bonus, background_mask=None):
    """Five disjoint UK/JP grades; grades4/5 may include the bonus ball."""
    main, bonus = np.asarray(main, int), np.asarray(bonus, int)
    if background_mask is None:
        background_mask = np.ones((len(main), len(weights)), dtype=bool)
        background_mask[np.arange(len(main))[:, None], main - 1] = False
        background_mask[np.arange(len(main)), bonus - 1] = False
    a = esp(weights[main - 1])
    b = weights[bonus - 1]
    rest = esp(background_mask * weights)
    z = esp(weights[None, :])[0, 6]
    return np.column_stack((a[:, 6], a[:, 5] * b, a[:, 5] * rest[:, 1],
                            a[:, 4] * (rest[:, 2] + b * rest[:, 1]),
                            a[:, 3] * (rest[:, 3] + b * rest[:, 2]))) / z


def nb_logpmf(y, mu, shape):
    # Analytic in the positive parameters, so complex-step derivatives work.
    total = shape + mu
    return (loggamma(y + shape) - loggamma(shape) - loggamma(y + 1)
            + shape * (np.log(shape) - np.log(total))
            + y * (np.log(mu) - np.log(total)))


def time_feature(issue, cfg):
    return (np.asarray(issue) - cfg["time_center"]) / cfg["time_scale"]


def sales_design(records, weekday, cfg):
    return np.array([[1, float(time_feature(r["issue"], cfg)),
                      float(date.fromisoformat(r["date"]).weekday() == weekday)] for r in records])


def fit_sales(training, weekday, cfg):
    valid = [r for r in training if r["sales"] is not None and r["ticket_price"] is not None]
    require(bool(valid), "No observed training sales; no imputation allowed")
    x = sales_design(valid, weekday, cfg)
    y = np.log([r["sales"] / r["ticket_price"] for r in valid])
    beta = np.linalg.solve(x.T @ x + np.diag(cfg["sales_ridge"]), x.T @ y)
    mse = float(np.mean((y - x @ beta) ** 2))
    return dict(beta=beta.tolist(), residual_mse=mse, observed_training_rows=len(valid),
                max_training_issue=max(r["issue"] for r in training), weekday=weekday)


def forecast_entries(fitted, record, cfg):
    x = sales_design([record], fitted["weekday"], cfg)[0]
    value = float(np.exp(x @ fitted["beta"] + fitted["residual_mse"] / 2))
    require(math.isfinite(value) and value > 0, "Invalid frozen sales forecast")
    return value


def split_parameters(values, kind):
    offset = 0 if kind == "random" else (6 if kind == "dynamic" else 5)
    return (None if kind == "random" else values[:4],
            None if kind == "random" else values[4:offset], np.exp(values[offset:]))


def probabilities(values, kind, pool, main, bonus, issue, cfg, mask=None):
    theta, eta, _ = split_parameters(values, kind)
    uniform = np.broadcast_to(uniform_tiers(pool), (len(main), 5))
    if kind == "random":
        return uniform
    w = np.exp(features(pool) @ theta)
    pref = preference_tiers(w, main, bonus, mask)
    logits = eta[0] + (eta[1] * time_feature(issue, cfg) if kind == "dynamic" else 0)
    omega = 1 / (1 + np.exp(-logits))
    if np.ndim(omega) == 0:
        omega = np.full(len(main), omega)
    return omega[:, None] * uniform + (1 - omega[:, None]) * pref


def fit_count(training, kind, pool, cfg):
    rows = [r for r in training if r["sales"] is not None and r["ticket_price"] is not None]
    main = np.array([r["main"] for r in rows])
    bonus = np.array([r["bonus"] for r in rows])
    issue = np.array([r["issue"] for r in rows])
    exposure = np.array([r["sales"] / r["ticket_price"] for r in rows])
    observed = [(i, k, y) for i, r in enumerate(rows) for k, y in enumerate(r["counts"]) if y is not None]
    require(bool(observed), "No observed training count cells")
    ii, kk, yy = (np.array(v) for v in zip(*observed))
    ii, kk = ii.astype(int), kk.astype(int)
    mask = np.ones((len(rows), pool), bool)
    mask[np.arange(len(rows))[:, None], main - 1] = False
    mask[np.arange(len(rows)), bonus - 1] = False
    offset = 0 if kind == "random" else (6 if kind == "dynamic" else 5)
    initial = np.r_[np.zeros(offset), np.full(5, np.log(cfg["shape_prior"]))]
    bounds = ([] if kind == "random" else [cfg["theta_bounds"]] * 4 + [cfg["eta_bounds"]] * (offset - 4))
    bounds += [(math.log(cfg["shape_bounds"][0]), math.log(cfg["shape_bounds"][1]))] * 5

    def objective(values):
        theta, eta, shape = split_parameters(values, kind)
        p = probabilities(values, kind, pool, main, bonus, issue, cfg, mask)
        value = -np.mean(nb_logpmf(yy, (exposure[:, None] * p)[ii, kk], shape[kk]))
        if theta is not None:
            value += cfg["theta_ridge"] / 2 * np.sum(theta ** 2)
            value += cfg["eta_ridge"] / 2 * np.sum(eta ** 2)
        value += cfg["shape_log_ridge"] / 2 * np.sum((values[offset:] - np.log(cfg["shape_prior"])) ** 2)
        return value

    options = {k: v for k, v in cfg["optimizer"].items() if k not in ("method", "jac")}
    result = minimize(objective, initial, bounds=bounds, method=cfg["optimizer"]["method"],
                      jac=cfg["optimizer"]["jac"], options=options)
    return dict(kind=kind, values=result.x.tolist(), success=bool(result.success), status=int(result.status),
                message=str(result.message), objective=float(result.fun), nit=int(result.nit),
                nfev=int(result.nfev), njev=int(result.njev), observed_training_cells=len(observed),
                missing_training_cells=len(training) * 5 - len(observed), max_training_issue=max(r["issue"] for r in training))


def template(order):
    n = len(order)
    tickets = [sorted(order[(6 * b + j) % n] for j in range(6)) for b in range(8)]
    require(all(len(set(t)) == 6 for t in tickets) and len({tuple(t) for t in tickets}) == 8,
            "Invalid eight-ticket template")
    return tickets


def greedy(weights):
    order = sorted(range(1, len(weights) + 1), key=lambda n: (float(weights[n - 1]), n))
    logs = np.log(weights)
    def entry(indices):
        ticket = tuple(sorted(order[i] for i in indices))
        return (float(sum(logs[n - 1] for n in ticket)), ticket, indices)
    first = tuple(range(6))
    heap, seen, result = [entry(first)], {first}, []
    while len(result) < 8:
        _, ticket, indices = heapq.heappop(heap)
        result.append(list(ticket))
        for k in range(6):
            nxt = indices[k] + 1
            if nxt >= (indices[k + 1] if k < 5 else len(weights)):
                continue
            candidate = (*indices[:k], nxt, *indices[k + 1:])
            if candidate not in seen:
                seen.add(candidate)
                heapq.heappush(heap, entry(candidate))
    return result


def paper_portfolios(fits, pool, seed, country_index, issue):
    out, dynamic_weights = {}, None
    for kind in ("dynamic", "static"):
        weights = np.exp(features(pool) @ np.array(fits[kind]["values"][:4]))
        order = sorted(range(1, pool + 1), key=lambda n: (float(weights[n - 1]), n))
        out[kind + "_template"] = template(order)
        if kind == "dynamic":
            dynamic_weights = weights
    order = rng(seed, 10, country_index, issue).permutation(np.arange(1, pool + 1)).tolist()
    out["random_template"] = template(order)
    out["dynamic_greedy"] = greedy(dynamic_weights)
    return out


def grade(ticket, main, bonus):
    k, b = len(set(ticket) & set(main)), bonus in ticket
    if k == 6:
        return 1
    if k == 5:
        return 2 if b else 3
    return 4 if k == 4 else (5 if k == 3 else 0)


def append_prediction(path, prediction):
    body = canonical(prediction)
    with path.open("ab") as f:
        offset = f.tell()
        f.write(body + b"\n")
        f.flush()
        os.fsync(f.fileno())
    return offset, sha(body)


class SourceBroker:
    """Only the broker sees adopted financial outcomes and raw draw bodies.

    Functions fitting models receive first200 records, not the broker itself.
    Score-target reveal requires a persisted matching prediction receipt.
    """
    def __init__(self, data, cfg):
        self.data, self.cfg = data, cfg
        self.rows = {c: {int(r["issue"]): r for r in csv.DictReader((data / (c + ".csv")).open())}
                     for c in cfg["countries"]}
        plan = json.loads((data / "acquisition-plan.json").read_text())["scope"]
        self.slots = {c: [dict(issue=int(i), date=d) for i, d in plan[c]] for c in cfg["countries"]}
        self.sources = {r["key"]: r for r in json.loads((data / "retrievals.json").read_text())}
        self.encoded = None
        for c, config in cfg["countries"].items():
            expected = list(range(config["training"][0], config["scoring"][1] + 1))
            require([r["issue"] for r in self.slots[c]] == expected, "Fixed window mismatch")
            require(sorted(self.rows[c]) == expected, "Missing/extra financial issue; no replacement")

    def body(self, key):
        if self.encoded is None:
            self.encoded = {}
            with gzip.open(self.data / "raw/target-sources.jsonl.gz", "rt") as f:
                for line in f:
                    obj = json.loads(line)
                    self.encoded[obj["key"]] = obj["body_base64"]
        body = base64.b64decode(self.encoded[key], validate=True)
        require(sha(body) == self.sources[key]["sha256"], "Source body SHA mismatch")
        return body

    def _outcome(self, country, issue):
        row = self.rows[country][issue]
        if country == "uk":
            key = f"uk_lottery_{issue}"
            body = self.body(key)
            identity = source_parser.parse_uk_lottery(body)
            tree = source_parser.root(body)
            container = next(n for n in tree.find("span") if n.attrs.get("id") == "ballsAscending")
            main = sorted(int(n.text) for n in container.find("span", "lotto-ball"))
            bonus = int(container.find("span", "lotto-bonus-ball")[0].text)
        else:
            key = row["primary_source_key"]
            body = self.body(key)
            identity = source_parser.parse_jp_official(body)
            raw = list(csv.reader(io.StringIO(unicodedata.normalize("NFKC", body.decode("cp932")))))
            main, bonus = sorted(map(int, raw[3][1:7])), int(raw[3][8])
        require(identity["issue"] == row["issue"] and identity["date"] == row["draw_date"], "Draw identity mismatch")
        pool = self.cfg["countries"][country]["pool"]
        require(len(main) == 6 and len(set(main)) == 6 and all(1 <= n <= pool for n in main)
                and 1 <= bonus <= pool and bonus not in main, "Invalid main/bonus set")
        counts = [None if row[f"tier{k}_winners"] == "NA" else float(row[f"tier{k}_winners"]) for k in range(1, 6)]
        require(all(y is None or y >= 0 and y.is_integer() for y in counts), "Count is not an observed nonnegative integer")
        return dict(issue=issue, date=row["draw_date"], main=main, bonus=bonus, counts=counts,
                    sales=None if row["sales"] == "NA" else float(row["sales"]),
                    ticket_price=None if row["ticket_price"] == "NA" else float(row["ticket_price"]),
                    original_announcement=row["announcement_at_utc"], legal_version=row["full_prize_rule_version"],
                    source_key=key, source_sha256=self.sources[key]["sha256"])

    def training(self, country):
        a, b = self.cfg["countries"][country]["training"]
        return [self._outcome(country, i) for i in range(a, b + 1)]

    def reveal(self, country, issue, journal, offset, expected_sha):
        require(issue > self.cfg["countries"][country]["training"][1], "Use training path for training records")
        with journal.open("rb") as f:
            f.seek(offset)
            body = f.readline().removesuffix(b"\n")
        require(sha(body) == expected_sha, "Prediction receipt SHA mismatch")
        prediction = json.loads(body)
        require(prediction["country"] == country and prediction["target_issue"] == issue,
                "Wrong prediction receipt issue/country")
        require(prediction["max_training_issue"] < issue, "Future training leakage")
        return self._outcome(country, issue)


def block_comparison(gains, generator, cfg):
    values = np.asarray(gains, float)
    require(len(values) > 0 and np.isfinite(values).all(), "Invalid paired scores")
    n, b, length = len(values), cfg["bootstrap_reps"], cfg["block_length"]
    starts = generator.integers(0, n, size=(b, math.ceil(n / length)))
    indices = ((starts[:, :, None] + np.arange(length)) % n).reshape(b, -1)[:, :n]
    boot = np.mean(values[indices], axis=1)
    mean = float(np.mean(values))
    centered = boot - mean
    p = (1 + int(np.count_nonzero(centered >= mean))) / (b + 1)
    lower = float(mean - np.quantile(centered, 1 - cfg["alpha"]))
    return dict(n=n, mean_log_score_gain=mean, lower_9875=lower, p_value=p, bonferroni_p=min(1.0, 4 * p),
                alpha=cfg["alpha"], pass_count=bool(n >= cfg["minimum_score_periods"] and mean > 0 and lower > 0 and p <= cfg["alpha"]),
                inference="centered circular block bootstrap approximation; retrospective discovery, no repaired blindness")


def financial_gate(outcomes):
    missing_time = sum(r["original_announcement"] == "NA" for r in outcomes)
    missing_rules = sum(r["legal_version"] == "NA" for r in outcomes)
    return dict(status="not_evaluable", missing_original_announcement=missing_time, missing_complete_legal_version=missing_rules,
                conditional_payout_ratio=None, corrected_ratio_lower=None, roi_lower=None, passed=False,
                reason="No complete applicable payout/legal/timing inputs; no sales or dividend imputation, no counterfactual own-share/cap/floor calculation claimed")


def power_diagnostic(cfg):
    spec = cfg["power"]
    generator = rng(cfg["seed"], 30)
    out = []
    for n in spec["n"]:
        for p in spec["p"]:
            joint = spec["shared_probability"] * p + (1 - spec["shared_probability"]) * p * p
            one = p - joint
            probabilities_ = [1 - 2 * p + joint, joint, one, one]
            for ratio in spec["ratio"]:
                counts = generator.multinomial(n, probabilities_, size=spec["reps"])
                differences = np.array([0, (ratio - 1) / p, ratio / p, -1 / p])
                total, squares = counts @ differences, counts @ differences ** 2
                mean = total / n
                variance = np.maximum(0, (squares - total ** 2 / n) / (n - 1))
                nonzero = variance > 0
                stat = np.zeros(spec["reps"])
                stat[nonzero] = mean[nonzero] / np.sqrt(variance[nonzero] / n)
                ps = np.ones(spec["reps"])
                ps[nonzero] = student_t.sf(stat[nonzero], n - 1)
                rejected = nonzero & (mean > 0) & (ps <= cfg["alpha"])
                rate = float(np.mean(rejected))
                out.append(dict(n=n, jackpot_probability=p, expected_payout_ratio=ratio, reps=spec["reps"],
                    rejection_rate=rate, mc_standard_error=math.sqrt(rate * (1 - rate) / spec["reps"]),
                    no_event_fraction=float(np.mean(counts[:, 0] == n)),
                    interpretation="type_I_diagnostic" if ratio == 1 else "synthetic_rule_power_not_actual_EV_power"))
    return out


def verify_lock(home, root):
    lock = json.loads((home / "lock.json").read_text())
    require(lock["spec_sha256"] == sha(canonical(lock["spec"])), "Parameter lock SHA mismatch")
    require(sha((root / lock["prereg_path"]).read_bytes()) == lock["prereg_sha256"], "Prereg changed")
    for name, expected in lock["inputs_sha256"].items():
        path = root / name
        require(path.is_relative_to(root / "data/discovery/ev1"), "Input outside EV-1")
        require(sha(path.read_bytes()) == expected, f"Input changed: {name}")
    implementation = json.loads((home / "implementation-lock.json").read_text())
    for name, expected in implementation["files_sha256"].items():
        require(sha((root / name).read_bytes()) == expected, "Implementation changed after pinning")
    require(np.__version__ == lock["spec"]["numpy"] and scipy.__version__ == lock["spec"]["scipy"], "Runtime version mismatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", implementation["prereg_commit"], "HEAD"], cwd=root, check=True)
    require(not subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=root, text=True), "Commit clean implementation before run")
    require(not (home / "run").exists(), "This R1 already started; no rerun")
    return lock, implementation


def run(home=EV_HOME, root=ROOT):
    lock, implementation = verify_lock(home, root)
    cfg = lock["spec"]
    out = home / "run"
    out.mkdir(exist_ok=False)
    run_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    write_json(out / "started.json", dict(id=ID, run_count=1, started_at_utc=now(),
               prereg_commit=implementation["prereg_commit"], implementation_commit=run_commit,
               lock_sha256=sha((home / "lock.json").read_bytes()), python=platform.python_version(),
               scipy=scipy.__version__, numpy=np.__version__), exclusive=True)
    ledger = json.loads((home / "ledger.json").read_text())
    ledger.update(status="running", run_count=1, implementation_commit=run_commit, started_at_utc=now())
    write_json(home / "ledger.json", ledger)
    country_results, comparisons, all_scores = {}, [], []
    journal = out / "predictions.jsonl"
    try:
        broker = SourceBroker(root / "data/discovery/ev1", cfg)
        for ci, (country, c) in enumerate(cfg["countries"].items()):
            print(f"{country}: fitting frozen first200 NB2 models", flush=True)
            training = broker.training(country)
            sales = fit_sales(training, c["weekday"], cfg)
            fits = {}
            for kind in cfg["models"]:
                fits[kind] = fit_count(training, kind, c["pool"], cfg)
                print(country, kind, fits[kind]["success"], fits[kind]["message"], flush=True)
                if not fits[kind]["success"] or not np.isfinite(fits[kind]["values"]).all():
                    break
            write_json(out / (country + "-fits.json"), dict(sales=sales, counts=fits), exclusive=True)
            if len(fits) != 3 or not all(f["success"] for f in fits.values()):
                country_results[country] = dict(status="archived_optimizer_failure", fits=fits, scored_n=0)
                comparisons.extend(dict(country=country, comparison="dynamic_vs_" + baseline,
                    n=0, mean_log_score_gain=None, lower_9875=None, p_value=None,
                    bonferroni_p=None, alpha=cfg["alpha"], pass_count=False,
                    inference="not evaluable: an optimizer failed; no retry") for baseline in ("static", "random"))
                continue
            records, observed, omega_values = [], [], []
            grades = {p: [0] * 6 for p in cfg["portfolios"]}
            for slot in broker.slots[country][200:]:
                target = slot["issue"]
                predicted_entries = forecast_entries(sales, slot, cfg)
                portfolios = paper_portfolios(fits, c["pool"], cfg["seed"], ci, target)
                eta = fits["dynamic"]["values"][4:6]
                omega = float(1 / (1 + np.exp(-(eta[0] + eta[1] * time_feature(target, cfg)))))
                prediction = dict(id=ID, country=country, target_issue=target, target_date=slot["date"],
                    created_at_utc=now(), max_training_issue=900, forecast_entries=predicted_entries,
                    model_parameters={k: f["values"] for k, f in fits.items()}, omega=omega,
                    portfolios=portfolios, conditional_count_function="locked probabilities(); draw argument only after broker reveal",
                    prereg_sha256=lock["prereg_sha256"], implementation_commit=run_commit)
                offset, fingerprint = append_prediction(journal, prediction)
                actual = broker.reveal(country, target, journal, offset, fingerprint)
                valid = [k for k, y in enumerate(actual["counts"]) if y is not None]
                values, log_prob = {}, {}
                for kind in cfg["models"]:
                    parameters = np.array(fits[kind]["values"])
                    probs = probabilities(parameters, kind, c["pool"], [actual["main"]], [actual["bonus"]], np.array([target]), cfg)[0]
                    _, _, shape = split_parameters(parameters, kind)
                    ll = nb_logpmf(np.array([actual["counts"][k] for k in valid]),
                                   predicted_entries * probs[valid], shape[valid])
                    values[kind] = float(np.mean(ll)) if valid else None
                    log_prob[kind] = {str(k + 1): float(v) for k, v in zip(valid, ll)}
                port_grades = {p: [grade(ticket, actual["main"], actual["bonus"]) for ticket in tickets]
                               for p, tickets in portfolios.items()}
                for p, gg in port_grades.items():
                    for g in gg:
                        grades[p][g] += 1
                record = dict(country=country, issue=target, observed_count_cells=len(valid),
                    count_values=actual["counts"], scores=values, log_probability_by_tier=log_prob,
                    portfolios_prize_grades=port_grades, prediction_offset=offset, prediction_sha256=fingerprint,
                    outcome_source_sha256=actual["source_sha256"], outcome_source_key=actual["source_key"])
                require(all(v is None or math.isfinite(v) for v in values.values()), "Non-finite predictive score")
                records.append(record)
                observed.append(actual)
                omega_values.append(omega)
            all_scores.extend(records)
            for bi, baseline in enumerate(("static", "random")):
                paired = [r["scores"]["dynamic"] - r["scores"][baseline] for r in records if r["scores"]["dynamic"] is not None]
                result = block_comparison(paired, rng(cfg["seed"], 20, ci, bi), cfg)
                comparisons.append(dict(country=country, comparison="dynamic_vs_" + baseline, **result))
            gate = financial_gate(observed)
            country_results[country] = dict(status="archived", scored_n=len(records),
                observed_count_cells=sum(r["observed_count_cells"] for r in records),
                missing_count_cells=len(records) * 5 - sum(r["observed_count_cells"] for r in records),
                omega_first=omega_values[0], omega_last=omega_values[-1],
                mean_scores={k: float(np.mean([r["scores"][k] for r in records if r["scores"][k] is not None])) for k in cfg["models"]},
                paper_portfolio_grade_counts=grades, paper_financial_results={p: gate for p in cfg["portfolios"]},
                financial_gate=gate, count_pass=all(x["pass_count"] for x in comparisons if x["country"] == country))
            print(country, "scored", len(records), "financial gate not evaluable; archive", flush=True)
        with (out / "scores.jsonl").open("xb") as f:
            for r in all_scores:
                f.write(canonical(r) + b"\n")
        power = power_diagnostic(cfg)
        write_json(out / "power.json", power, exclusive=True)
        results = dict(id=ID, status="archived", run_count=1, completed_at_utc=now(),
            prereg_commit=implementation["prereg_commit"], implementation_commit=run_commit,
            spec_sha256=lock["spec_sha256"], countries=country_results, comparisons=comparisons,
            passed=False, reason="R1 archived: financial/timing gate unavailable; additionally report each locked count gate without substitution",
            conditional_payout_ratio=None, corrected_payout_ratio_lower=None, positive_ev=False, roi_lower=None,
            hk_attempts_cumulative=14, hk_attempts_added=0, power_scope="synthetic paired-t rule, not actual financial or NB count-test power",
            prediction_journal_sha256=sha(journal.read_bytes()) if journal.exists() else None,
            score_file_sha256=sha((out / "scores.jsonl").read_bytes()))
        write_json(out / "results.json", results, exclusive=True)
        ledger.update(status="archived", completed_at_utc=results["completed_at_utc"],
                      results_sha256=sha((out / "results.json").read_bytes()), passed=False)
        write_json(home / "ledger.json", ledger)
    except Exception as exc:
        write_json(out / "aborted.json", dict(id=ID, error=type(exc).__name__, message=str(exc), at_utc=now(), no_rerun=True), exclusive=True)
        ledger.update(status="aborted_archived", error=str(exc), no_rerun=True)
        write_json(home / "ledger.json", ledger)
        raise
    files = {p.name: sha(p.read_bytes()) for p in sorted(out.iterdir()) if p.is_file()}
    write_json(out / "sealed.json", dict(run_count=1, status="archived", files_sha256=files,
               implementation_commit=run_commit, sealed_at_utc=now()), exclusive=True)
    print(json.dumps(dict(status="archived", result_sha256=sha((out / "results.json").read_bytes()), comparisons=comparisons)), flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", required=True)
    parser.parse_args()
    run()
