"""Exact small-universe checks. Never fit/enumerate either real R3 country."""
from collections import Counter
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from scipy.stats import nbinom

from src import ev_comp_nb_r3 as ev


def reference_features(ticket):
    primes = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47}
    def low_entropy(values):
        probs = np.array(list(Counter(values).values())) / len(values)
        return 1 + float(np.sum(probs * np.log(probs))) / math.log(5)
    return np.array([len(set(ticket) & primes)/6, int(7 in ticket),
        len(set(ticket) & {17,27,37,47})/6, sum(1<=n<=12 for n in ticket)/6,
        sum(13<=n<=31 for n in ticket)/6, low_entropy([n//10 for n in ticket]),
        low_entropy([b-a for a,b in zip(ticket,ticket[1:])])])


def test_seven_feature_definitions_include_big_primes_and_count_seven_once():
    tickets = np.array([[2,7,17,37,41,47], [1,3,5,7,9,11], [1,2,4,7,11,16],
                        [1,2,3,4,10,20], [1,2,3,10,11,12]], dtype=np.uint8)
    actual = ev.decode_features(ev.feature_codes(tickets,49))
    assert np.allclose(actual,np.array([reference_features(t) for t in tickets]),atol=1e-14)
    assert actual[0,0] == 1 and actual[0,2] == .5
    assert actual[1,6] == 1 and actual[2,6] == 0
    # Squared occupancy 18 is shared by partitions 4/1/1 and 3/3, entropy is not.
    assert actual[3,5] != actual[4,5]


@pytest.fixture(scope="module")
def universe():
    return ev.ExactClasses(12)


def test_exact_class_multiplicity_and_nonadditive_normalizer(universe):
    assert universe.omega.sum() == math.comb(12,6)
    theta=np.array([.3,-.2,.1,.4,-.1,.7,-.8])
    expected=sum(math.exp(reference_features(t)@theta) for t in combinations(range(1,13),6))
    actual=universe.omega @ np.exp(universe.features @ theta)
    assert actual == pytest.approx(expected,rel=1e-13)


@pytest.mark.parametrize("main,bonus", [([1,2,3,4,5,6],7),([1,3,5,7,9,12],2)])
def test_exact_prize_projection_matches_full_bruteforce(universe,main,bonus):
    theta=np.array([.3,-.2,.1,.4,-.1,.7,-.8])
    matrix=universe.projection(main,bonus)
    expected=np.zeros(5);z=0
    for ticket in combinations(range(1,13),6):
        w=math.exp(reference_features(ticket)@theta);z+=w
        hits=len(set(ticket)&set(main))
        grade=1 if hits==6 else (2 if bonus in ticket else 3) if hits==5 else 4 if hits==4 else 5 if hits==3 else 0
        if grade:expected[grade-1]+=w
    q=ev.q_and_gradient(theta,universe.features,universe.omega,matrix)[0]
    assert np.allclose(q,expected/z,rtol=1e-12,atol=1e-14)
    assert np.array_equal(np.asarray(matrix.sum(axis=1)).ravel(),universe.expected_sizes)


def test_zero_theta_is_uniform_and_additive_case_matches_esp(universe):
    main,bonus=[1,3,5,7,9,12],2
    matrix=universe.projection(main,bonus)
    q=ev.q_and_gradient(np.zeros(7),universe.features,universe.omega,matrix)[0]
    assert np.allclose(q,ev.r1.uniform_tiers(12),rtol=1e-13)
    theta=np.array([.3,-.2,.1,.4,-.1,0,0])
    # Form the additive per-number weights independently of grouped classes.
    prime={2,3,5,7,11}
    f=np.array([[int(n in prime)/6,int(n==7),int(n in {17,27,37,47})/6,
                 int(n<=12)/6,int(13<=n<=31)/6] for n in range(1,13)])
    weights=np.exp(f@theta[:5])
    exact=ev.q_and_gradient(theta,universe.features,universe.omega,matrix)[0]
    esp=ev.r1.preference_tiers(weights,[main],[bonus])[0]
    assert np.allclose(exact,esp,rtol=1e-12)


def history_fixture(universe,n=9):
    main=[1,3,5,7,9,12];bonus=2
    q=ev.r1.uniform_tiers(12)
    rows=[dict(issue=701+i,date="2012-10-11",main=main,bonus=bonus,
               sales=600,ticket_price=1,counts=np.rint(600*q).tolist()) for i in range(n)]
    rows[0]["counts"][0]=0
    rows[1]["counts"][2]=None
    matrix=ev.sparse.vstack([universe.projection(main,bonus)]*n,format="csr")
    return rows,matrix


@pytest.mark.parametrize("kind",ev.MODELS)
def test_analytic_objective_gradient_matches_independent_central_difference(universe,kind):
    history,matrix=history_fixture(universe)
    objective,d,cells=ev.objective_factory(history,matrix,universe,kind)
    assert cells==len(history)*5-1
    x=np.r_[np.linspace(-.15,.2,d),np.log([5,10,20,30,40])]
    value,g=objective(x)
    assert math.isfinite(value)
    for j in range(len(x)):
        h=1e-5;xp=x.copy();xm=x.copy();xp[j]+=h;xm[j]-=h
        finite=(objective(xp)[0]-objective(xm)[0])/(2*h)
        assert g[j] == pytest.approx(finite,rel=2e-5,abs=2e-7)


def test_nb2_keeps_zero_and_both_analytic_derivatives():
    y=np.array([0.,1,40,4000]);mu=np.array([.2,2,25,5000]);r=np.array([.8,3,12,40])
    ll,dm,dr=ev.nb_values_gradient(y,mu,r)
    assert np.allclose(ll,nbinom.logpmf(y,r,r/(r+mu)),rtol=1e-10,atol=1e-10)
    h=1e-5
    mfinite=(nbinom.logpmf(y,r,r/(r+mu*np.exp(h)))-nbinom.logpmf(y,r,r/(r+mu*np.exp(-h))))/(2*h)
    rp,rm=r*np.exp(h),r*np.exp(-h)
    rfinite=(nbinom.logpmf(y,rp,rp/(rp+mu))-nbinom.logpmf(y,rm,rm/(rm+mu)))/(2*h)
    assert np.allclose(dm,mfinite,rtol=1e-6,atol=1e-7)
    assert np.allclose(dr,rfinite,rtol=1e-5,atol=2e-6)


@pytest.mark.parametrize("kind",ev.MODELS)
def test_single_fixed_optimizer_converges_on_synthetic_only(universe,kind):
    rows,matrix=history_fixture(universe)
    fitted=ev.fit(rows,matrix,universe,kind)
    assert fitted["success"] and fitted["max_training_issue"]==709
    q=ev.frozen_q(fitted,matrix[:5],universe)
    assert np.isfinite(q).all() and np.all(q>0) and q.sum()<=1+1e-12


def test_missing_projection_is_empty_and_not_imputed(universe):
    m=universe.projection(None,None)
    assert m.shape==(5,len(universe.codes)) and m.nnz==0


def test_bootstrap_is_fixed_one_sided_and_negative_gain_cannot_pass(tmp_path):
    result=ev.primary_comparison(np.full(246,-.1),1,tmp_path/'bootstrap.npz')
    assert not result['pass_count'] and result['p_value']==1
    assert result['lower_9875']==pytest.approx(-.1)
    with np.load(tmp_path/'bootstrap.npz',allow_pickle=False) as f:
        assert len(f['centered_bootstrap_mean'])==10000


def test_guard_blocks_hk_sealed_windows_and_aud_artifacts():
    code="""
from src.ev_comp_nb_r3 import install_guard,ROOT
install_guard()
for name in ['marksix_data.csv','data/external/manifest.json','audits/AUD-SERIAL-K6-v1/run/results.json']:
 try:(ROOT/name).read_bytes()
 except PermissionError:pass
 else:raise RuntimeError('Forbidden input read')
"""
    subprocess.run([sys.executable,'-c',code],cwd=ev.ROOT,check=True)


def test_real_result_is_checked_without_refit_or_rerun():
    p=ev.HOME/'run/results.json'
    if not p.exists():pytest.skip('R3 not yet run; this test never starts a run')
    r=json.loads(p.read_text());seal=json.loads((p.parent/'sealed.json').read_text())
    assert r['run_count']==seal['run_count']==1
    assert ev.sha(p)==seal['files_sha256']['results.json']
    assert r['hk_attempts_added']==r['tickets_generated']==r['AUD_SERIAL_reruns']==0
    assert r['hk_attempts_cumulative']==14
    assert set(r['countries'])=={'uk','japan'}
