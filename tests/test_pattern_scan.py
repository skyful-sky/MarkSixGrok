"""Synthetic statistical calibration fixtures; never executes the real scan."""

import importlib.util
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "docs/review-evidence/pattern_scan_26047_26115.py"
spec = importlib.util.spec_from_file_location("pattern_scan", SCRIPT)
SCAN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SCAN)


def test_bh_known_vector_ties_and_invalid_pvalues():
    assert SCAN.adjust_bh([.01, .04, .03, .002]) == pytest.approx([.02, .04, .04, .008])
    assert SCAN.adjust_bh([.005]*10) == pytest.approx([.005]*10)
    assert SCAN.adjust_bh([0, 1]) == pytest.approx([0, 1])
    for invalid in ([float("nan")], [-.01], [1.1]):
        with pytest.raises(ValueError):
            SCAN.adjust_bh(invalid)


def test_exact_discrete_two_sided_uses_probability_ordering():
    pmf = np.array([.1, .2, .4, .2, .1])
    assert SCAN.probability_ordered_p(pmf, 0) == pytest.approx(.2)
    assert SCAN.probability_ordered_p(pmf, 1) == pytest.approx(.6)
    assert SCAN.probability_ordered_p(pmf, 2) == pytest.approx(1)


def test_mc_plus_one_never_zero_and_includes_floating_ties():
    assert SCAN.monte_carlo_p([0, 1, 2], 10) == (0, .25)
    assert SCAN.monte_carlo_p([0, 1, 2], 1) == (2, .75)
    assert SCAN.monte_carlo_p([0, 1, 2], 0) == (3, 1)
    assert SCAN.monte_carlo_p([1-1e-14], 1) == (1, 1)


def test_longest_zero_distribution_against_exhaustive_small_sequences():
    n, p = 5, .3
    masses = np.zeros(n+1)
    for sequence in itertools.product((0, 1), repeat=n):
        current = longest = 0
        for value in sequence:
            current = 0 if value else current+1
            longest = max(longest, current)
        ones = sum(sequence)
        masses[longest] += p**ones*(1-p)**(n-ones)
    assert SCAN.longest_zero_pmf(n, p) == pytest.approx(masses)


def test_hypergeom_and_convolution_against_independent_support():
    expected = np.array([math.comb(3, k)*math.comb(5, 2-k)/math.comb(8, 2) for k in range(3)])
    assert SCAN.hypergeom_pmf(8, 3, 2) == pytest.approx(expected)
    pmf = SCAN.sum_hypergeom_pmf(3, 4)
    assert pmf.sum() == pytest.approx(1)
    assert np.dot(np.arange(len(pmf)), pmf) == pytest.approx(3*6*4/49)
    assert np.flatnonzero(pmf)[-1] == 12


@pytest.mark.parametrize("periods", [5, 64, 65, 69])
def test_bitpacked_pairs_and_one_lag_match_explicit_matrix_products(periods):
    sample = SCAN.sample_fair(np.random.Generator(np.random.PCG64(7)), 3, periods)
    x = SCAN.indicators(sample)
    pair = SCAN.cross_counts(x, x)
    lag = SCAN.cross_counts(x[:, :-1], x[:, 1:])
    for i in range(3):
        matrix = x[i].astype(int)
        assert np.array_equal(pair[i], matrix.T @ matrix)
        assert np.array_equal(lag[i], matrix[:-1].T @ matrix[1:])
        assert np.array_equal(np.diag(pair[i]), matrix.sum(axis=0))


def test_uniform_sampler_support_special_exclusion_and_reproducibility():
    def sample():
        return SCAN.sample_fair(np.random.Generator(np.random.PCG64(19)), 10, 69)
    a = sample()
    assert np.array_equal(a, sample())
    assert np.all((a >= 0) & (a < 49))
    assert np.all(np.diff(np.sort(a, axis=-1), axis=-1) > 0)
    assert np.all(SCAN.indicators(a).sum(axis=-1) == 6)


def test_neighbor_edges_do_not_wrap_and_previous_numbers_are_excluded():
    # Main1..6 / special7, followed by main44..49 / special43.
    sample = np.array([[[0, 1, 2, 3, 4, 5, 6], [43, 44, 45, 46, 47, 48, 42]]])
    f = SCAN.draw_features(sample, SCAN.indicators(sample))
    assert f["neighbor_size"].tolist() == [[1]]  # Only7, never49.
    assert f["neighbor_count"].tolist() == [[0]]
    assert f["repeats"].tolist() == [[0]]
    assert f["consecutive_edges"].tolist() == [[5, 5]]
    assert f["consecutive_longest"].tolist() == [[6, 6]]
    assert f["special_rank"].tolist() == [[6, 0]]
    assert f["special_distance"].tolist() == [[1, 1]]


def test_permutation_expected_transition_matrix_matches_all_orders():
    sample = np.array([[[0, 1, 2, 3, 4, 5, 6], [0, 1, 2, 3, 7, 8, 9],
                        [0, 1, 2, 10, 11, 12, 13], [0, 1, 14, 15, 16, 17, 18]]])
    x = SCAN.indicators(sample)
    total = x.sum(axis=1).astype(float)
    formula = (total[:, :, None]*total[:, None, :]-SCAN.cross_counts(x, x))/4
    all_orders = np.array(list(itertools.permutations(range(4))))
    xx = x[0][all_orders]
    empirical = SCAN.cross_counts(xx[:, :-1], xx[:, 1:]).mean(axis=0)
    assert empirical == pytest.approx(formula[0])
    assert formula[0, 0, 0] == 3  # i=j is included.


def test_plan_statistic_set_and_total_multiplicity_on_synthetic_data():
    plan = json.loads(SCAN.PLAN.read_text())
    sample = SCAN.sample_fair(np.random.Generator(np.random.PCG64(3)), 1, 69)
    gap_pmf = SCAN.longest_zero_pmf(69, SCAN.P)
    iid = SCAN.iid_statistics(sample, np.dot(np.arange(70), gap_pmf), *SCAN.special_constants())
    assert set(iid) == {r[0] for r in plan["iid_statistics"]}
    x = SCAN.indicators(sample)
    total = x.sum(axis=1).astype(float)
    expected = (total[:, :, None]*total[:, None, :]-SCAN.cross_counts(x, x))/69
    perm = SCAN.permutation_statistics(x, SCAN.draw_features(sample, x), np.arange(69) % 7, expected)
    assert set(perm) == {r[0] for r in plan["conditional_permutation_statistics"]}
    exact = SCAN.exact_rows(sample, gap_pmf)
    assert len(exact) == 1339 and len(iid) == 28 and len(perm) == 6
    assert len(exact)+len(iid)+len(perm) == 1373
    assert all(np.all(np.isfinite(v)) for v in [*iid.values(), *perm.values()])
    assert all(0 <= r["p"] <= 1 for r in exact)


def test_repeated_synthetic_null_statistics_are_identical():
    sample = SCAN.sample_fair(np.random.Generator(np.random.PCG64(99)), 8, 69)
    pmf = SCAN.longest_zero_pmf(69, SCAN.P)
    args = (np.dot(np.arange(70), pmf), *SCAN.special_constants())
    first = SCAN.iid_statistics(sample, *args)
    second = SCAN.iid_statistics(sample, *args)
    assert all(np.array_equal(first[k], second[k]) for k in first)


def test_changed_csv_fails_before_parsing_or_analysis(tmp_path):
    path = tmp_path/"altered.csv"
    path.write_text("invalid data")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        SCAN.load_input(path)


def test_sealed_real_scan_has_one_run_and_unchanged_plan_script_hashes():
    # Verification of stored artifacts only; does not run the scan or simulator.
    sealed = json.loads((SCAN.OUTPUT/"sealed.json").read_text())
    summary = json.loads((SCAN.OUTPUT/"summary.json").read_text())
    assert sealed["run_count"] == summary["run_count"] == 1
    assert sealed["rerun_allowed"] is False
    assert summary["input_sha256"] == SCAN.SHA
    assert summary["plan_sha256"] == SCAN.digest(SCAN.PLAN)
    assert summary["script_sha256"] == SCAN.digest(SCRIPT)
    assert summary["total_tests"] == 1373
    for name, expected in sealed["files_sha256"].items():
        assert SCAN.digest(SCAN.OUTPUT/name) == expected


def test_stored_mc_p_and_global_bh_can_be_verified_without_resimulation():
    import csv
    with (SCAN.OUTPUT/"tests.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({r["key"] for r in rows}) == 1373
    q = SCAN.adjust_bh([float(r["p"]) for r in rows])
    assert q == pytest.approx([float(r["q_BH"]) for r in rows])
    with np.load(SCAN.OUTPUT/"null-statistics.npz", allow_pickle=False) as saved:
        mc = [r for r in rows if r["replicates"] != "0"]
        assert len(mc) == len(saved.files) == 34
        for row in mc:
            null = saved[row["key"]]
            assert null.shape == (100000,)
            extreme, p = SCAN.monte_carlo_p(null, float(row["observed_statistic"]))
            assert extreme == int(row["extreme_count"])
            assert p == float(row["p"])
