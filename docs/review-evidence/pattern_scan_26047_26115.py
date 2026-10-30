"""Fixed in-sample descriptive scan. Reads only the locked HK CSV and plan.

No prediction, training, candidate registration or external data access. The
large real-data run has an exclusive output directory; tests use synthetic data.
"""

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import platform

import numpy as np


REPO = Path(__file__).resolve().parents[2]
PLAN = Path(__file__).with_name("pattern-scan-26047-26115-plan.json")
OUTPUT = Path(__file__).with_name("pattern-scan-26047-26115")
SHA = "653993bd43030f7436a96a171ba98b2e73ed62e26f38108efd334fe3d88c8a5e"
P = 6 / 49
PAIR_P = 30 / (49 * 48)
FIELDS = ["期數", "攪珠日期", *[f"正選號碼{i}" for i in range(1, 7)], "特別號碼"]
TAILS = [np.array([n % 10 == d for n in range(1, 50)]) for d in range(10)]
SECTIONS = [np.array([lo <= n <= hi for n in range(1, 50)])
            for lo, hi in [(1, 9), (10, 19), (20, 29), (30, 39), (40, 49)]]
UPPER_I, UPPER_J = np.triu_indices(49, 1)


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_input(path):
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != SHA:
        raise ValueError("CSV SHA-256 mismatch; stop before analysis")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != FIELDS:
        raise ValueError("Unexpected CSV fields")
    rows = list(reader)
    if [r["期數"] for r in rows] != [f"26/{i:03d}" for i in range(47, 116)]:
        raise ValueError("Expected exactly69 consecutive original issues")
    days = [date.fromisoformat(r["攪珠日期"]) for r in rows]
    if any(a >= b for a, b in zip(days, days[1:])):
        raise ValueError("Nonchronological dates")
    sample = np.array([[int(r[f"正選號碼{i}"]) - 1 for i in range(1, 7)] +
                       [int(r["特別號碼"]) - 1] for r in rows], dtype=np.int16)
    if np.any((sample < 0) | (sample >= 49)) or np.any(np.diff(np.sort(sample, axis=-1), axis=-1) == 0):
        raise ValueError("Balls must be seven distinct integers in1..49")
    if not np.array_equal(sample[:, :6], np.sort(sample[:, :6], axis=-1)):
        raise ValueError("Expected sorted main fields; these are not physical draw order")
    return rows, days, sample[None, ...]


def choose(n, k):
    return math.comb(n, k) if 0 <= k <= n else 0


def binomial_pmf(n, p):
    return np.array([choose(n, k) * p**k * (1-p)**(n-k) for k in range(n+1)])


def hypergeom_pmf(pool, successes, draws):
    return np.array([choose(successes, k) * choose(pool-successes, draws-k) / choose(pool, draws)
                     for k in range(draws+1)])


def sum_hypergeom_pmf(periods, size):
    one = hypergeom_pmf(49, size, 6)
    result = np.array([1.0])
    for _ in range(periods):
        result = np.convolve(result, one)
    return result / result.sum()


def longest_zero_pmf(n, p):
    """Exact finite-window distribution; includes observed boundary runs."""
    cdfs = []
    for limit in range(n+1):
        states = np.zeros(limit+1)
        states[0] = 1
        for _ in range(n):
            previous = states.copy()
            states[0] = p * previous.sum()
            states[1:] = (1-p) * previous[:-1]
        cdfs.append(states.sum())
    pmf = np.maximum(np.diff([0, *cdfs]), 0)
    return pmf / pmf.sum()


def probability_ordered_p(pmf, value):
    if not 0 <= value < len(pmf):
        raise ValueError("Observation outside exact support")
    return min(1.0, float(pmf[pmf <= pmf[value] * (1+1e-12)].sum()))


def adjust_bh(pvalues):
    values = np.asarray(pvalues, dtype=float)
    if np.any(~np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("Invalid p-values")
    order = np.argsort(values, kind="stable")
    q = values[order] * len(values) / np.arange(1, len(values)+1)
    q = np.minimum(1, np.minimum.accumulate(q[::-1])[::-1])
    result = np.empty_like(q)
    result[order] = q
    return result


def monte_carlo_p(null, observed):
    null = np.asarray(null)
    extreme = int((null >= observed-1e-12*max(1, abs(observed))).sum())
    return extreme, (1+extreme)/(1+len(null))


def sample_fair(rng, batch, periods):
    """Rejection of repeated labels yields uniform ordered seven-tuples."""
    samples = rng.integers(0, 49, size=(batch*periods, 7), dtype=np.int16)
    while True:
        invalid = np.any(np.diff(np.sort(samples, axis=-1), axis=-1) == 0, axis=-1)
        if not invalid.any():
            break
        samples[invalid] = rng.integers(0, 49, size=(int(invalid.sum()), 7), dtype=np.int16)
    return samples.reshape(batch, periods, 7)


def indicators(sample):
    batch, periods, _ = sample.shape
    x = np.zeros((batch, periods, 49), dtype=bool)
    x[np.arange(batch)[:, None, None], np.arange(periods)[None, :, None], sample[..., :6]] = True
    return x


def packed_periods(x):
    packed = np.packbits(x.transpose(0, 2, 1), axis=-1, bitorder="little")
    pad = (-packed.shape[-1]) % 8
    return np.ascontiguousarray(np.pad(packed, ((0, 0), (0, 0), (0, pad)))).view("<u8")


def cross_counts(left, right):
    a, b = packed_periods(left), packed_periods(right)
    result = np.zeros((left.shape[0], 49, 49), dtype=np.int16)
    for word in range(a.shape[-1]):
        result += np.bitwise_count(a[:, :, word, None] & b[:, None, :, word])
    return result


def longest_gaps(x):
    current = np.zeros((x.shape[0], 49), dtype=np.int16)
    longest = current.copy()
    for t in range(x.shape[1]):
        current = np.where(x[:, t], 0, current+1)
        longest = np.maximum(longest, current)
    return longest


def lag_correlation(values):
    a, b = values[:, :-1].astype(float), values[:, 1:].astype(float)
    a -= a.mean(axis=1, keepdims=True)
    b -= b.mean(axis=1, keepdims=True)
    denom = np.sqrt((a*a).sum(axis=1) * (b*b).sum(axis=1))
    return np.divide((a*b).sum(axis=1), denom, out=np.zeros(len(a)), where=denom > 0)


def histogram_stat(values, pmf):
    counts = (values[..., None] == np.arange(len(pmf))).sum(axis=1)
    expected = values.shape[1] * pmf
    return ((counts-expected)**2 / expected).sum(axis=-1)


def special_constants():
    denom = choose(48, 6)
    adjacent, distance = 0.0, 0.0
    for special in range(1, 50):
        neighbors = int(special > 1) + int(special < 49)
        adjacent += (1-choose(48-neighbors, 6)/denom)/49
        for d in range(49):
            near = min(d, special-1) + min(d, 49-special)
            distance += choose(48-near, 6)/denom/49
    return adjacent, distance


def draw_features(sample, x):
    main, special = sample[..., :6]+1, sample[..., 6]+1
    ordered = np.sort(main, axis=-1)
    consecutive_edges = (np.diff(ordered, axis=-1) == 1).sum(axis=-1)
    current = np.ones(main.shape[:2], dtype=np.int16)
    longest = current.copy()
    for i in range(5):
        current = np.where(ordered[..., i+1] == ordered[..., i]+1, current+1, 1)
        longest = np.maximum(longest, current)
    neighbors = np.zeros_like(x[:, :-1])
    neighbors[..., 1:] |= x[:, :-1, :-1]
    neighbors[..., :-1] |= x[:, :-1, 1:]
    neighbors &= ~x[:, :-1]
    return dict(sums=main.sum(axis=-1), odd=(main % 2).sum(axis=-1),
        large=(main >= 25).sum(axis=-1), special=special,
        repeats=(x[:, :-1] & x[:, 1:]).sum(axis=-1),
        neighbor_count=(neighbors & x[:, 1:]).sum(axis=-1), neighbor_size=neighbors.sum(axis=-1),
        consecutive_edges=consecutive_edges, consecutive_longest=longest,
        special_rank=(main < special[..., None]).sum(axis=-1),
        special_distance=np.abs(main-special[..., None]).min(axis=-1),
        special_adjacent=(np.abs(main-special[..., None]) == 1).any(axis=-1),
        special_in_prev=np.take_along_axis(x[:, :-1], (sample[:, 1:, 6])[..., None], axis=-1)[..., 0],
        prev_special_in_main=np.take_along_axis(x[:, 1:], (sample[:, :-1, 6])[..., None], axis=-1)[..., 0])


def iid_statistics(sample, gap_mean, special_adjacent_mean, special_distance_mean):
    x = indicators(sample)
    n = x.shape[1]
    freq = x.sum(axis=1)
    gaps = longest_gaps(x)
    f = draw_features(sample, x)
    pairs = cross_counts(x, x)[:, UPPER_I, UPPER_J]
    transition = cross_counts(x[:, :-1], x[:, 1:]).astype(float)
    exposure = x[:, :-1].sum(axis=1).astype(float)
    expected = exposure[..., None] * P
    denom = expected * (1-P)
    transition_stat = np.divide((transition-expected)**2, denom,
                               out=np.zeros_like(transition), where=denom > 0).sum(axis=(1, 2))
    special_counts = (sample[..., 6, None] == np.arange(49)).sum(axis=1)
    tails = np.stack([freq[:, mask].sum(axis=1) for mask in TAILS], axis=1)
    sections = np.stack([freq[:, mask].sum(axis=1) for mask in SECTIONS], axis=1)
    tail_e = n*6*np.array([mask.sum() for mask in TAILS])/49
    section_e = n*6*np.array([mask.sum() for mask in SECTIONS])/49
    return dict(
        frequency_pearson=((freq-n*P)**2/(n*P)).sum(axis=1),
        gap_mean_longest=np.abs(gaps.mean(axis=1)-gap_mean), gap_max_longest=gaps.max(axis=1),
        repeat_mean=np.abs(f["repeats"].mean(axis=1)-36/49),
        repeat_histogram=histogram_stat(f["repeats"], hypergeom_pmf(49, 6, 6)),
        neighbor_residual=np.abs((f["neighbor_count"]-P*f["neighbor_size"]).mean(axis=1)),
        sum_mean=np.abs(f["sums"].mean(axis=1)-150),
        sum_variance=np.abs(f["sums"].var(axis=1, ddof=1)-1075),
        sum_lag1=np.abs(lag_correlation(f["sums"])),
        odd_mean=np.abs(f["odd"].mean(axis=1)-150/49),
        odd_histogram=histogram_stat(f["odd"], hypergeom_pmf(49, 25, 6)),
        large_mean=np.abs(f["large"].mean(axis=1)-150/49),
        large_histogram=histogram_stat(f["large"], hypergeom_pmf(49, 25, 6)),
        tail_pearson=((tails-tail_e)**2/tail_e).sum(axis=1),
        section_pearson=((sections-section_e)**2/section_e).sum(axis=1),
        consecutive_edges=np.abs(f["consecutive_edges"].mean(axis=1)-30/49),
        consecutive_longest=f["consecutive_longest"].max(axis=1),
        pair_pearson=((pairs-n*PAIR_P)**2/(n*PAIR_P)).sum(axis=1),
        special_frequency_pearson=((special_counts-n/49)**2/(n/49)).sum(axis=1),
        special_rank_histogram=histogram_stat(f["special_rank"], np.ones(7)/7),
        special_offset=np.abs((f["special"]-f["sums"]/6).mean(axis=1)),
        special_nearest_distance=np.abs(f["special_distance"].mean(axis=1)-special_distance_mean),
        special_adjacent=np.abs(f["special_adjacent"].mean(axis=1)-special_adjacent_mean),
        special_in_previous_main=np.abs(f["special_in_prev"].mean(axis=1)-P),
        previous_special_in_main=np.abs(f["prev_special_in_main"].mean(axis=1)-P),
        markov_fair=transition_stat, odd_lag1=np.abs(lag_correlation(f["odd"])),
        large_lag1=np.abs(lag_correlation(f["large"])))


def permutation_statistics(x, features, weekday, fixed_transition_expectation):
    n = x.shape[1]
    total = x.sum(axis=1)
    association = np.zeros(x.shape[0])
    between = {key: np.zeros(x.shape[0]) for key in ("sums", "odd", "large", "special")}
    for day in sorted(set(weekday)):
        mask = weekday == day
        count = x[:, mask].sum(axis=1)
        expected = mask.sum()*total/n
        association += np.divide((count-expected)**2, expected,
            out=np.zeros_like(expected, dtype=float), where=expected > 0).sum(axis=1)
        for key in between:
            between[key] += mask.sum()*(features[key][:, mask].mean(axis=1)-features[key].mean(axis=1))**2
    transitions = cross_counts(x[:, :-1], x[:, 1:])
    markov = ((transitions-fixed_transition_expectation)**2/(fixed_transition_expectation+1)).sum(axis=(1, 2))
    return dict(weekday_number_association=association, weekday_sum=between["sums"],
        weekday_odd=between["odd"], weekday_large=between["large"], weekday_special=between["special"],
        markov_order_permutation=markov)


def exact_rows(sample, gap_pmf):
    x = indicators(sample)
    freq, gaps = x[0].sum(axis=0), longest_gaps(x)[0]
    special = sample[0, :, 6]
    pair_counts = cross_counts(x, x)[0]
    rows = []
    def append(key, group, value, pmf, expectation, method):
        value = int(value)
        rows.append(dict(key=key, group=group, observed_statistic=value,
            expected_statistic=float(expectation), p=probability_ordered_p(pmf, value),
            method=method, tail="two_sided_probability_ordering", replicates=0,
            extreme_count=None, mc_se=None,
            null_mean=float(np.dot(np.arange(len(pmf)), pmf)),
            null_q025=int(np.searchsorted(np.cumsum(pmf), .025)),
            null_q975=int(np.searchsorted(np.cumsum(pmf), .975))))
    for j in range(49):
        append(f"frequency_{j+1:02d}", "frequency", freq[j], binomial_pmf(69, P), 69*P, "exact_binomial")
        append(f"gap_{j+1:02d}", "gap", gaps[j], gap_pmf, np.dot(np.arange(70), gap_pmf), "exact_longest_zero_run")
        append(f"special_frequency_{j+1:02d}", "special", (special == j).sum(), binomial_pmf(69, 1/49), 69/49, "exact_binomial")
    for i, j in zip(UPPER_I, UPPER_J):
        append(f"pair_{i+1:02d}_{j+1:02d}", "pair", pair_counts[i, j], binomial_pmf(69, PAIR_P), 69*PAIR_P, "exact_binomial")
    for group, masks in [("tail", TAILS), ("section", SECTIONS)]:
        for k, mask in enumerate(masks):
            append(f"{group}_{k}", group, freq[mask].sum(), sum_hypergeom_pmf(69, int(mask.sum())),
                   69*6*mask.sum()/49, "exact_convolution_of_hypergeom")
    features = draw_features(sample, x)
    any_p = 1-choose(44, 6)/choose(49, 6)
    append("any_consecutive_period", "consecutive", (features["consecutive_edges"] > 0).sum(),
           binomial_pmf(69, any_p), 69*any_p, "exact_binomial")
    return rows


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run():
    plan = json.loads(PLAN.read_text())
    rows, days, sample = load_input(REPO / plan["input"])
    if (plan["iid_seed"], plan["permutation_seed"], plan["replicates_per_null"], plan["batch_size"]) != (20261030, 20261031, 100000, 500):
        raise ValueError("Analysis plan constants differ")
    # Exclusive creation prevents accidental reexecution of the real scan.
    OUTPUT.mkdir(exist_ok=False)
    provenance = dict(started_at_utc=utc(), input_sha256=SHA, plan_sha256=digest(PLAN),
        script_sha256=digest(Path(__file__)), numpy=np.__version__, python=platform.python_version(),
        run_count=1, candidate_evaluations=0, prediction_attempts=0, attempts_total_unchanged=14)
    write_json(OUTPUT/"started.json", provenance)
    nrep, batch_size = plan["replicates_per_null"], plan["batch_size"]
    gap_pmf = longest_zero_pmf(69, P)
    constants = (float(np.dot(np.arange(70), gap_pmf)), *special_constants())
    observed_iid = iid_statistics(sample, *constants)
    if set(observed_iid) != {v[0] for v in plan["iid_statistics"]}:
        raise ValueError("Unplanned iid statistic")
    x = indicators(sample)
    features = draw_features(sample, x)
    weekday = np.array([d.weekday() for d in days])
    totals = x.sum(axis=1).astype(float)
    cooccur = cross_counts(x, x).astype(float)
    perm_e = (totals[:, :, None]*totals[:, None, :]-cooccur)/69
    observed_perm = permutation_statistics(x, features, weekday, perm_e)
    if set(observed_perm) != {v[0] for v in plan["conditional_permutation_statistics"]}:
        raise ValueError("Unplanned permutation statistic")
    nulls = {key: np.empty(nrep) for key in [*observed_iid, *observed_perm]}
    rng = np.random.Generator(np.random.PCG64(plan["iid_seed"]))
    for start in range(0, nrep, batch_size):
        stop = min(nrep, start+batch_size)
        statistics = iid_statistics(sample_fair(rng, stop-start, 69), *constants)
        for key, values in statistics.items():
            nulls[key][start:stop] = values
        if stop % 10000 == 0:
            print(f"iid null {stop}/{nrep}", flush=True)
    rng = np.random.Generator(np.random.PCG64(plan["permutation_seed"]))
    for start in range(0, nrep, batch_size):
        stop = min(nrep, start+batch_size)
        permutations = np.array([rng.permutation(69) for _ in range(stop-start)])
        xx = x[0][permutations]
        ff = {key: features[key][0][permutations] for key in ("sums", "odd", "large", "special")}
        statistics = permutation_statistics(xx, ff, weekday, perm_e)
        for key, values in statistics.items():
            nulls[key][start:stop] = values
        if stop % 10000 == 0:
            print(f"conditional permutation {stop}/{nrep}", flush=True)
    tests = exact_rows(sample, gap_pmf)
    for specs, observed, method in [(plan["iid_statistics"], observed_iid, "fair_iid_monte_carlo"),
                                    (plan["conditional_permutation_statistics"], observed_perm, "whole_draw_permutation")]:
        for key, group, description in specs:
            value = float(observed[key][0])
            simulated = nulls[key]
            extreme, p = monte_carlo_p(simulated, value)
            tests.append(dict(key=key, group=group, observed_statistic=value,
                expected_statistic=None, p=p, method=method, tail="upper_of_fixed_statistic",
                replicates=nrep, extreme_count=extreme, mc_se=math.sqrt(p*(1-p)/(nrep+1)),
                null_mean=float(simulated.mean()), null_q025=float(np.quantile(simulated, .025)),
                null_q975=float(np.quantile(simulated, .975))))
    if len(tests) != 1373 or len({t["key"] for t in tests}) != 1373:
        raise ValueError("Fixed multiplicity count differs")
    q = adjust_bh([t["p"] for t in tests])
    harmonic = sum(1/i for i in range(1, len(tests)+1))
    for test, adjusted in zip(tests, q):
        test["q_BH"] = float(adjusted)
        test["q_BY_sensitivity"] = min(1., float(adjusted)*harmonic)
    tests.sort(key=lambda t: t["key"])
    write_csv(OUTPUT/"tests.csv", tests)
    np.savez_compressed(OUTPUT/"null-statistics.npz", **nulls)
    feature_rows = []
    for i, row in enumerate(rows):
        result = dict(issue=row["期數"], date=row["攪珠日期"], weekday=days[i].weekday())
        for key, values in features.items():
            result[key] = int(values[0, i]) if values.shape[1] == 69 else (int(values[0, i-1]) if i else "NA")
        feature_rows.append(result)
    write_csv(OUTPUT/"observed-features.csv", feature_rows)
    transition = cross_counts(x[:, :-1], x[:, 1:])[0]
    exposure = x[0, :-1].sum(axis=0)
    write_csv(OUTPUT/"markov-matrix.csv", [dict(previous_number=i+1, next_number=j+1,
        count=int(transition[i, j]), previous_exposure=int(exposure[i]),
        fair_expected=float(exposure[i]*P), permutation_expected=float(perm_e[0, i, j]),
        individual_cell_p="NA_not_tested", individual_cell_q="NA_not_tested")
        for i in range(49) for j in range(49)])
    groups = {}
    for group in sorted({t["group"] for t in tests}):
        selected = [t for t in tests if t["group"] == group]
        best = min(selected, key=lambda t: t["p"])
        groups[group] = dict(tests=len(selected), minimum_p=best["p"],
            key_at_minimum_p=best["key"], q_BH_at_minimum_p=best["q_BH"],
            minimum_q_BH=min(t["q_BH"] for t in selected))
    descriptive = dict(mean_main_sum=float(features["sums"].mean()),
        sample_variance_main_sum=float(features["sums"].var(ddof=1)),
        mean_repeat=float(features["repeats"].mean()), mean_odd=float(features["odd"].mean()),
        mean_large=float(features["large"].mean()), mean_neighbor=float(features["neighbor_count"].mean()),
        mean_neighbor_null_conditional=float((P*features["neighbor_size"]).mean()),
        mean_special_offset=float((features["special"]-features["sums"]/6).mean()),
        mean_special_nearest_distance=float(features["special_distance"].mean()),
        special_distance_null=constants[2], special_adjacent_null=constants[1],
        mean_consecutive_edges=float(features["consecutive_edges"].mean()),
        maximum_consecutive_run=int(features["consecutive_longest"].max()),
        any_consecutive_periods=int((features["consecutive_edges"] > 0).sum()),
        weekday_counts={str(d): int((weekday == d).sum()) for d in sorted(set(weekday))},
        weekday_means={str(d): {k: float(features[k][0, weekday == d].mean()) for k in ("sums", "odd", "large", "special")}
                       for d in sorted(set(weekday))})
    summary = dict(**provenance, completed_at_utc=utc(), total_tests=len(tests),
        exact_tests=sum(t["replicates"] == 0 for t in tests), iid_statistics=len(observed_iid),
        permutation_statistics=len(observed_perm), replicates_per_null=nrep,
        group_summary=groups, descriptive=descriptive,
        q_BH_below_005=[t for t in tests if t["q_BH"] < .05],
        q_BY_below_005=[t["key"] for t in tests if t["q_BY_sensitivity"] < .05],
        limitations=plan["limitations"], after_scan_no_candidate_id_or_prediction=True)
    write_json(OUTPUT/"summary.json", summary)
    sums = {p.name: digest(p) for p in sorted(OUTPUT.iterdir()) if p.is_file()}
    write_json(OUTPUT/"sealed.json", dict(run_count=1, rerun_allowed=False, files_sha256=sums))
    print(json.dumps(dict(total_tests=len(tests), group_summary=groups,
                         q_BH_below_005=[t["key"] for t in tests if t["q_BH"] < .05]), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    if parser.parse_args().run:
        run()
    else:
        parser.error("Explicit --run required; real output directory must not already exist")
