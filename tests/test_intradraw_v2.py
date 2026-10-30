"""Small-universe enumeration and synthetic checks; no historical outcomes."""
from fractions import Fraction
from itertools import combinations
import math
import subprocess
import sys

import numpy as np
import pytest

from src import intradraw_v2 as m


SMALL_TICKETS=((1,2,3),(2,3,4),(3,4,5),(4,5,6),
               (5,6,7),(6,7,8),(1,7,8),(1,2,8))


def synthetic():
    U=np.array([[.35,.1],[-.3,.2],[.1,-.4],[.25,.3],[-.2,-.35],
                [.1,.15],[-.25,.05],[.3,-.1]])
    a=np.array([.1,-.15,.2,-.05,.15,-.1,.05,-.2]);a-=a.mean()
    return U,a


def brute(family,U,a,k,tickets=SMALL_TICKETS):
    z=0.;nums=np.zeros(len(U));event=0.
    for S in combinations(range(len(U)),k):
        v=U[list(S)]
        if family=='exclusion':
            # Independent full principal determinant, not the rank2 recurrence.
            factor=np.linalg.det(np.eye(k)+v@v.T)
        else:
            factor=math.exp(sum(float(U[i]@U[j]) for i,j in combinations(S,2)))
        mass=math.exp(sum(a[i] for i in S))*factor
        z+=mass;nums[list(S)]+=mass
        if any(len(set(i+1 for i in S)&set(T))>=3 for T in tickets):event+=mass
    return z,nums/z,event/z


def test_rank2_moment_product_has_identity_and_nonzero_high_order_mass():
    U,a=synthetic()
    p=m.dpp_polynomial(U,a,6)
    z,_,_=brute('exclusion',U,a,6)
    assert float(m.determinant_mass(p[6]))==pytest.approx(z,rel=1e-13)
    assert z>0   # rank(U)=2 does not eliminate six-by-six I+UU^T minors


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_normalizer_marginals_and_joint_p8_match_small_exhaustive(family):
    U,a=synthetic()
    z,pi=m.normalizer_marginals(family,U,a,3)
    expected,pp,coverage=brute(family,U,a,3)
    assert float(z)==pytest.approx(expected,rel=2e-13)
    assert np.allclose(pi,pp,rtol=2e-12,atol=2e-13)
    result=m.p8(family,U,a,SMALL_TICKETS,3)
    assert result.value==pytest.approx(coverage,abs=2e-12)
    assert result.absolute_error>0
    if family=='attract2':assert result.quadrature_relative_bound>0


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_cap3_keeps_cross_ticket_overlap_and_does_not_sum_events(family):
    U,a=synthetic()
    # Some draws succeed in multiple tickets; exact union differs from sum.
    p=m.p8(family,U,a,SMALL_TICKETS,4)
    assert p.value==pytest.approx(brute(family,U,a,4)[2],abs=2e-12)
    count=sum(any(len(set(S)&set(T))>=3 for T in SMALL_TICKETS)
              for S in combinations(range(1,9),4))
    individual=sum(sum(len(set(S)&set(T))>=3 for T in SMALL_TICKETS)
                   for S in combinations(range(1,9),4))
    assert individual>count
    assert m.uniform_p8(8,4,SMALL_TICKETS)==Fraction(count,math.comb(8,4))


@pytest.mark.parametrize('family',['exclusion','attract2'])
@pytest.mark.parametrize('pool,q',[(49,Fraction(12344,83237)),(43,Fraction(1221091,6096454))])
def test_zero_U_returns_exact_original_fair_fraction(family,pool,q):
    result=m.p8(family,np.zeros((pool,2)),np.zeros(pool),m.original_template(pool))
    assert result.exact_fraction==q
    assert result.absolute_error==0   # exact combinatorial shortcut, not GH claim
    assert result.value==float(q)


@pytest.mark.parametrize('family',['exclusion','attract2'])
@pytest.mark.parametrize('pool',[43,49])
def test_full_pool_synthetic_uniform_normalizer_and_marginals(family,pool):
    for row in [(0.,0.),(.2,.1)]:
        U=np.tile(row,(pool,1));a=np.zeros(pool)
        z,pi=m.normalizer_marginals(family,U,a,6)
        square=sum(x*x for x in row)
        multiplier=1+6*square if family=='exclusion' else math.exp(15*square)
        assert float(z)==pytest.approx(math.comb(pool,6)*multiplier,rel=3e-13)
        assert np.max(np.abs(pi-6/pool))<1e-10


def test_japan_template_and_frozen_permutation_generation():
    tickets=m.original_template(43)
    assert tickets[7]==(1,2,3,4,5,43)
    assert len(set(tickets[0])&set(tickets[7]))==5
    permutations=m.fixed_permutations(43)
    assert len(permutations)==64 and permutations==m.fixed_permutations(43)
    assert all(sorted(p)==list(range(1,44)) for p in permutations)


@pytest.mark.parametrize('family',['exclusion','attract2'])
@pytest.mark.parametrize('pool',[43,49])
def test_all_64_uniform_candidates_tie_and_first_is_selected(family,pool):
    permutations=m.fixed_permutations(pool)
    index,tickets,values=m.select_template(family,np.zeros((pool,2)),np.zeros(pool),permutations)
    assert index==0 and tickets==m.original_template(pool,permutations[0])
    assert len(values)==64 and all(v.exact_fraction==values[0].exact_fraction for v in values)


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_equal_marginal_inner_solve_uses_gauge_and_disk(family):
    U,_=synthetic()
    solved=m.balance(family,U,3)
    assert abs(solved['log_weights'].sum())<=1e-12
    assert np.max(np.abs(solved['pi']-3/8))+solved['marginal_error_budget']<=1e-10
    assert solved['iterations']<=100


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_rotation_and_reflection_preserve_set_distribution(family):
    U,a=synthetic();angle=.731
    R=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    p=m.p8(family,U,a,SMALL_TICKETS,3)
    rotated=m.p8(family,U@R,a,SMALL_TICKETS,3)
    mirrored=m.p8(family,U*np.array([-1,1]),a,SMALL_TICKETS,3)
    assert rotated.value==pytest.approx(p.value,abs=3e-12)
    assert mirrored.value==pytest.approx(p.value,abs=3e-12)


def test_quadrature_order_and_nonzero_error_upper_bound_are_fixed():
    U,_=synthetic()
    assert 0<m.quadrature_bound(U,6)<1e-12
    assert m.quadrature_bound(U,6,80)<m.quadrature_bound(U,6,64)
    with pytest.raises(m.NumericalFailure,match='order'):
        m.gaussian_nodes(32)


def test_hermite_rule_is_standard_normal_and_weights_positive():
    grid,weights=m.gaussian_nodes(64)
    assert len(weights)==64**2 and np.all(weights>0)
    assert float(weights.sum())==pytest.approx(1,abs=1e-15)
    assert float(weights@(grid[:,0]**2))==pytest.approx(1,abs=1e-14)
    assert float(weights@(grid[:,1]**4))==pytest.approx(3,abs=1e-13)


def test_unresolved_template_comparison_fails_instead_of_fake_exact_tie():
    a=m.Estimate(.2,1e-5,1e-7);b=m.Estimate(.20000001,1e-5,1e-7)
    with pytest.raises(m.NumericalFailure,match='unresolved'):
        m.choose_estimates([a,b])
    assert m.choose_estimates([m.Estimate(.1,0,0,Fraction(1,10)),
                               m.Estimate(.1,0,0,Fraction(1,10))])==0
    assert m.choose_estimates([m.Estimate(.1,1e-12,0),m.Estimate(.2,1e-12,0)])==1


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_profiled_joint_loss_is_finite_and_penalized_on_synthetic_sets(family):
    U,_=synthetic();draws=[(1,2,3),(3,4,5),(6,7,8)]
    solved=m.balance(family,U,3)
    z=brute(family,U,np.asarray(solved['log_weights'],float),3)[0]
    logweights=[]
    for S in draws:
        ix=np.array(S)-1;v=U[ix]
        factor=(np.linalg.det(np.eye(3)+v@v.T) if family=='exclusion' else
                math.exp(sum(U[i]@U[j] for i,j in combinations(ix,2))))
        logweights.append(float(solved['log_weights'][ix].sum())+math.log(factor))
    expected=len(draws)*math.log(z)-sum(logweights)+np.sum(U*U)/2
    assert m.profiled_objective(family,U,draws,3)==pytest.approx(expected,abs=1e-10)


def test_outer_solver_enforces_row_norm_without_box_and_single_start():
    target=np.array([[2.,0.],[.3,-.2]])
    def objective(U,probe):return float(np.sum((U-target)**2)/2)
    result=m.projected_optimize(objective,np.zeros((2,2)))
    assert result['success'] and result['iterations']<=1000
    assert np.all(np.linalg.norm(result['U'],axis=1)<=1)
    assert np.allclose(result['U'],[[1,0],[.3,-.2]],atol=1e-4)
    with pytest.raises(m.NumericalFailure,match='row L2'):
        m.p8('exclusion',np.full((8,2),.8),np.zeros(8),SMALL_TICKETS,3)


def test_disk_projection_handles_float_norm_rounding_at_boundary():
    raw=np.array([[math.sqrt(.5),math.sqrt(.5)],[.6,.8],[2.,2.],[.2,.3]])
    projected=m.project_rows(raw)
    assert np.all((projected.astype(np.longdouble)**2).sum(axis=1)<=1)
    assert np.array_equal(projected[-1],raw[-1])
    with pytest.raises(m.NumericalFailure,match='nonfinite'):
        m.project_rows([[math.inf,0]])


def test_synthetic_process_cannot_open_historical_files():
    code="""
from src.intradraw_v2 import install_no_data_guard
from pathlib import Path
install_no_data_guard()
for p in ['marksix_data.csv','data/discovery/uk.csv','data/external/manifest.json','ev/EV-COMP-NB-R3/run/results.json']:
 try:Path(p).read_bytes()
 except PermissionError:pass
 else:raise RuntimeError('historical input permitted')
"""
    subprocess.run([sys.executable,'-c',code],check=True)


@pytest.mark.parametrize('family',['exclusion','attract2'])
def test_equal_marginal_pair_deviations_compensate(family):
    U,_=synthetic();a=m.balance(family,U,3)['log_weights']
    matrix=np.zeros((8,8));z=0.
    for S in combinations(range(8),3):
        v=U[list(S)]
        factor=(np.linalg.det(np.eye(3)+v@v.T) if family=='exclusion' else
                math.exp(sum(U[i]@U[j] for i,j in combinations(S,2))))
        mass=math.exp(float(a[list(S)].sum()))*factor;z+=mass
        for i,j in combinations(S,2):matrix[i,j]+=mass;matrix[j,i]+=mass
    matrix/=z
    assert np.allclose(matrix.sum(axis=1),np.full(8,6/8),atol=1e-10)
    fair=np.full((8,8),6/56);np.fill_diagonal(fair,0)
    assert np.allclose((matrix-fair).sum(axis=1),0,atol=1e-10)
    assert (matrix-fair).max()>0 and (matrix-fair).min()<0
    assert m.p8(family,U,a,SMALL_TICKETS,3).value==pytest.approx(brute(family,U,a,3)[2],abs=2e-12)


def test_future_fit_entry_locks_warmup_and_single_start_without_running_fit(monkeypatch):
    starts=[]
    def fake_optimizer(objective,initial):
        starts.append(initial.copy())
        return dict(U=initial,iterations=0,success=True)
    def fake_balance(family,U,k):
        return dict(log_weights=np.zeros(len(U)),iterations=0,pi=np.full(len(U),k/len(U)))
    monkeypatch.setattr(m,'projected_optimize',fake_optimizer)
    monkeypatch.setattr(m,'balance',fake_balance)
    fixture=[(1,2,3,4,5,6)]*200
    result=m.fit_once('exclusion',fixture,49)
    assert result['success'] and len(starts)==1
    assert np.array_equal(starts[0],m.initial_U(49))
    assert result['outer']['iterations']==result['inner']['iterations']==0
    with pytest.raises(m.NumericalFailure,match='200'):
        m.fit_once('attract2',fixture[:-1],49)
    with pytest.raises(m.NumericalFailure,match='pools'):
        m.fit_once('attract2',fixture,45)


def test_prereg_artifacts_pin_candidates_alpha_and_parameters():
    import hashlib,json
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    folder=root/'prereg/intradraw-v2'
    lock=json.loads((folder/'lock.json').read_text())
    candidates=json.loads((folder/'permutations.json').read_text())
    assert [x['external_j'] for x in lock['models']]==[2,3]
    assert [x['alpha_fraction'] for x in lock['models']]==['1/480','1/960']
    for name,digest in lock['documents_sha256'].items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
    assert candidates['uk']==m.fixed_permutations(49)
    assert candidates['japan']==m.fixed_permutations(43)
    assert lock['candidate_count']==64 and not lock['polar_sorting'] and not lock['box_constraint']
    assert lock['row_l2_max']==1 and lock['external_scores']==lock['real_fits']==0
