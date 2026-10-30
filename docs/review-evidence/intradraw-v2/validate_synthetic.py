"""Reproducible synthetic numerical checks only; historical file IO is blocked."""
from datetime import datetime,timezone
from itertools import combinations
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from src import intradraw_v2 as model


def brute(family,U,a,k,tickets):
    z=0.;included=np.zeros(len(U));success=0.
    for subset in combinations(range(len(U)),k):
        v=U[list(subset)]
        factor=(np.linalg.det(np.eye(k)+v@v.T) if family=='exclusion' else
                math.exp(sum(U[i]@U[j] for i,j in combinations(subset,2))))
        mass=math.exp(float(a[list(subset)].sum()))*factor
        z+=mass;included[list(subset)]+=mass
        if any(len(set(i+1 for i in subset)&set(t))>=3 for t in tickets):success+=mass
    return z,included/z,success/z


def main():
    model.install_no_data_guard(ROOT)
    U=np.array([[.35,.1],[-.3,.2],[.1,-.4],[.25,.3],[-.2,-.35],
                [.1,.15],[-.25,.05],[.3,-.1]])
    tickets=((1,2,3),(2,3,4),(3,4,5),(4,5,6),(5,6,7),(6,7,8),(1,7,8),(1,2,8))
    cases=[]
    for family in ['exclusion','attract2']:
        solved=model.balance(family,U,4);a=solved['log_weights']
        z,pi,reference=brute(family,U,np.asarray(a,float),4,tickets)
        p=model.p8(family,U,a,tickets,4)
        require= model.require
        require(abs(p.value-reference)<=5e-12,'synthetic p8 disagreement')
        require(np.max(np.abs(solved['pi']-pi))<=5e-12,'synthetic marginal disagreement')
        cases.append(dict(family=family,pool=8,k=4,synthetic_U=U.tolist(),
            balanced_log_weights=[float(x) for x in a],inner_steps=solved['iterations'],
            max_equal_marginal_error=solved['max_error'],
            numerical_Z=float(solved['Z']),brute_Z=z,
            max_marginal_difference=float(np.max(np.abs(solved['pi']-pi))),
            joint_p8=p.value,brute_joint_p8=reference,absolute_p8_difference=abs(p.value-reference),
            p8_error_acceptance=p.absolute_error,quadrature_relative_bound=p.quadrature_relative_bound))
    exact=[]
    for family in ['exclusion','attract2']:
        for pool in [49,43]:
            p=model.p8(family,np.zeros((pool,2)),np.zeros(pool),model.original_template(pool))
            exact.append(dict(family=family,pool=pool,k=6,exact_fraction=str(p.exact_fraction),
                              shortcut='known uniform distribution, no numerical integral'))
    record=dict(at_utc=datetime.now(timezone.utc).isoformat(),purpose='synthetic numerical validation only',
                historical_io_guard=True,external_results_read=0,HK_results_read=0,
                real_fits=0,external_scored_periods=0,new_hit_attempts=0,hit_attempts_cumulative=14,
                cases=cases,U_zero_fair_cases=exact,
                GH64_relative_truncation_bound=model.quadrature_bound(U,6,64),
                GH80_relative_truncation_bound=model.quadrature_bound(U,6,80),
                floating_budget_is_engineering_acceptance_not_interval_certificate=True)
    path=Path(__file__).with_name('synthetic-validation.json')
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'synthetic_cases':len(cases),'uniform_exact_cases':len(exact),
                      'max_p8_difference':max(c['absolute_p8_difference'] for c in cases),
                      'external_scored_periods':0},ensure_ascii=False))


if __name__=='__main__':main()
