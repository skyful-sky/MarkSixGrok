from fractions import Fraction
import json
import math
from pathlib import Path
import pytest
from src import hk_mach_alt_v2 as m


def test_swap_is_zero_based52_but53rd_valid_draw():
    rows,draws=m.load_snapshot()
    assert len(draws)==69 and rows[52]['期數']=='26/099'
    assert m.SWAP==52 and m.phase(51)==1 and m.phase(52)==1 and m.phase(53)==0


def test_template_exact_uniform_union_and_exact_tail():
    assert m.fair_p8()==Fraction(12344,83237)
    assert float(m.fair_p8())*100==pytest.approx(14.829943414587263)
    assert float(m.fair_tail())==pytest.approx(.007186083900543404,abs=1e-17)
    order=m.permutation('RAND',1,1);t=m.tickets(order)
    assert len(t)==8 and len(set(n for a in t for n in a))==48


def test_future_and_target_changes_cannot_affect_forecast():
    a=[[1,2,3,4,5,6] for _ in range(72)]
    first=m.forecast_at(a,69,1)
    a[69:]=[[40,41,42,43,44,45]]*3
    assert first==m.forecast_at(a,69,1)
    a[0]=[40,41,42,43,44,45]
    assert first['k_i']!=m.forecast_at(a,69,1)['k_i']
    assert first['history_indices']==[0,68]


def test_sha_seed_serialization_and_reproducibility():
    import hashlib
    assert m.seed('TIE',1)==int.from_bytes(hashlib.sha256(b'["TIE",20261030,1]').digest(),'big')
    assert m.random_tickets(1,1)==m.random_tickets(1,1)
    assert m.random_tickets(1,1)!=m.random_tickets(2,1)
    assert m.seed('PERM',1)!=m.seed('RAND',1,1)
    with pytest.raises(ValueError):m.random_tickets(10001,1)


def test_weights_are_exact_counts_with_stable_seeded_ties():
    p=m.forecast_at([[1,2,3,4,5,6]]*69,69,1)
    assert sum(Fraction(a,p['weight_denominator']) for a in p['weight_numerators'])==1
    assert p['tickets'][0]==[1,2,3,4,5,6]
    assert p['order'][6:]==[n for n in m.permutation('TIE',1) if n>6]
    assert 'not a without-replacement posterior' in p['weight_semantics']


def event(issue,day,status='complete',main=None):
    return dict(issue=issue,date=day,status=status,main=main or [1,2,3,4,5,6],official_source_url='https://official.example/event')


def test_cancelled_does_not_advance_valid_index_unknown_missing_pauses():
    rows=[event('26/116','2026-10-31','cancelled'),event('26/117','2026-11-03')]
    p=m.evaluate_events([[1,2,3,4,5,6]]*69,rows)
    assert p['n']==1 and p['periods'][0]['u']==1 and not p['passed']
    rows[0].pop('official_source_url')
    with pytest.raises(ValueError):m.valid_events(rows)
    with pytest.raises(ValueError):m.valid_events([event('26/116','2026-10-31'),event('26/118','2026-11-05')])


def test_no_early_pass_and_regime_stop_no_rephasing():
    snapshot=[[1,2,3,4,5,6]]*69
    rows=[event('26/116','2026-10-31')]
    assert m.evaluate_events(snapshot,rows)['status']=='pending'
    p=m.evaluate_events(snapshot,rows,official_retirement_url='https://official.example/retirement')
    assert p['status']=='archived_regime_interruption' and not p['passed']
    assert m.phase(69)==0


def test_missing_or_tampered_receipts_cannot_be_promoted():
    import hashlib
    snapshot=[[1,2,3,4,5,6]]*69
    rows=[event('26/116','2026-10-31')]
    assert m.evaluate_events(snapshot,rows)['late_issues']==['26/116']
    prediction=m.forecast_at(snapshot,69,1)
    receipt=dict(target_issue='26/116',prediction=prediction,
                 prediction_payload_sha256=hashlib.sha256(m.canonical(prediction)).hexdigest(),
                 generated_at_utc='2026-10-30T12:00:00+00:00',
                 official_sales_cutoff_utc='2026-10-31T13:15:00+00:00')
    result=m.evaluate_events(snapshot,rows,prediction_receipts={'26/116':receipt})
    assert not result['passed'] and not result['late_issues']
    receipt['prediction_payload_sha256']='wrong'
    with pytest.raises(ValueError,match='SHA mismatch'):
        m.evaluate_events(snapshot,rows,prediction_receipts={'26/116':receipt})


def test_diagnostics_never_select_main_phase_or_short_horizon_perm():
    assert m.diagnostic_phases(52)==dict(S1=1,S2_cyclic3=2,S2_third_even=2)
    assert m.diagnostic_phases(53)['S1']==1 and m.phase(53)==0
    with pytest.raises(ValueError):m.permuted_terminal([[1,2,3,4,5,6]]*69,1)
    with pytest.raises(ValueError):m.forecast_at([[1,2,3,4,5,6]]*70,70,1)
