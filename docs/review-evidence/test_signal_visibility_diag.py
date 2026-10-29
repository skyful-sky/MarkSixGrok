"""Synthetic diagnostic verification; never loads lottery histories or predictors."""

import importlib.util
from itertools import combinations
from math import comb
from pathlib import Path

import numpy as np
import pytest

path = Path(__file__).with_name("signal_visibility_diag.py")
spec = importlib.util.spec_from_file_location("signal_visibility_diag", path)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_K_law_is_unordered_weighted_subset_not_sequential_weights():
    for w in diag.WEIGHTS:
        counts, probabilities = diag.k_probabilities(w)
        assert counts == [comb(6, k) * comb(43, 6-k) * w**k for k in range(7)]
        assert probabilities.sum() == pytest.approx(1)
    assert sum(diag.k_probabilities(1)[0]) == comb(49, 6)
    assert np.dot(np.arange(7), diag.k_probabilities(1)[1]) == pytest.approx(36/49)


def test_sampler_six_distinct_and_support_count():
    rng = np.random.Generator(np.random.PCG64(diag.SEED))
    masks, k = diag.sample_masks(rng, 10000, 4)
    assert np.all(masks.sum(axis=1) == 6)
    assert np.array_equal(masks[:, :6].sum(axis=1), k)
    expected = np.dot(np.arange(7), diag.k_probabilities(4)[1])
    assert abs(k.mean() - expected) < .05


def test_visibility_order_ties_and_no_outcome_input():
    for visibility in diag.VISIBILITIES:
        rng = np.random.Generator(np.random.PCG64(diag.SEED))
        order, visible = diag.supplied_order(rng, 1000, visibility)
        assert np.all(np.sort(order, axis=1) == np.arange(49))
        assert np.all(order[visible] == np.arange(49))
        if visibility == 0: assert not visible.any()
        if visibility == 1: assert visible.all()
    assert .45 < diag.supplied_order(np.random.Generator(np.random.PCG64(diag.SEED)),1000,.5)[1].mean() < .55


def test_templates_and_once_per_period_success_match_explicit_sets():
    mains = list(combinations(range(9), 6)) + [(0, 1, 2, 30, 31, 32), (0, 6, 12, 18, 24, 48)]
    masks = np.zeros((len(mains),49),bool)
    for i, main in enumerate(mains): masks[i,list(main)]=True
    order = np.broadcast_to(np.arange(49),(len(mains),49))
    a,b,sums = diag.evaluate(masks,order)
    tickets_a = [set(range(6*i,6*i+6)) for i in range(8)]
    tickets_b = [{0,1,2}|set(range(3+3*i,6+3*i)) for i in range(8)]
    for i, main in enumerate(mains):
        assert a[i] == any(len(set(main)&t)>=3 for t in tickets_a)
        assert b[i] == any(len(set(main)&t)>=3 for t in tickets_b)
        assert sums[i] == sum(n+1 for n in main)
    # Relabeling changes no positional geometry when the ranking is relabeled too.
    permutation=np.arange(49)[::-1]
    aa,bb,rr=diag.evaluate(masks[:,permutation],permutation[order])
    assert np.array_equal(a,aa) and np.array_equal(b,bb) and np.array_equal(sums,rr)


def test_paired_error_uses_discordant_pairs_and_shared_outcomes():
    a=np.array([True,True,False,False]);b=np.array([True,False,True,False])
    result=diag.paired_summary(a,b)
    assert result['paired_counts']==dict(A_only=1,B_only=1,both=1,neither=1)
    assert result['paired_MC_SE']==pytest.approx(np.std(b.astype(int)-a.astype(int),ddof=1)/2)
    same=diag.paired_summary(a,a)
    assert same['paired_MC_SE']==same['difference_B_minus_A']==0


def test_analytic_fair_baseline_mixture_and_fixed_p_binomial():
    base=diag.analytic_ideal(1)
    assert base['A'] == diag.Fraction(12344,83237)
    assert 0 < base['B'] < base['A']
    for w in diag.WEIGHTS:
        zero=diag.analytic_cell(w,0);half=diag.analytic_cell(w,.5);full=diag.analytic_cell(w,1)
        for name in ('A','B'):
            assert half['rates'][name] == pytest.approx((zero['rates'][name]+full['rates'][name])/2)
            assert zero['rates'][name] == float(base[name])
    assert diag.binomial_pass(0)==0 and diag.binomial_pass(1)==1
    assert diag.binomial_pass(.5)==pytest.approx(sum(comb(20,k) for k in range(9,21))/2**20)


def test_seed_reproducibility_and_MC_against_exact_calibration():
    cells=diag.run(4000)
    assert cells==diag.run(4000)
    assert len(cells)==9
    for cell in cells:
        assert sum(cell['K_histogram'])==cell['periods']==4000
        assert sum(cell['paired_counts'].values())==4000
        for name in ('A','B'):
            p=cell['analytic']['rates'][name]
            se=(p*(1-p)/4000)**.5
            assert abs(cell['rates'][name]-p)<5*se
