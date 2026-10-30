"""Runner mechanics only: no historical fit, no replay of a sealed run."""
from fractions import Fraction
import json
import numpy as np

import pytest

from src import intradraw_external_validation as runner
from src.intradraw_v2 import NumericalFailure


def row(issue=701, date='2000-01-01'):
    return dict(issue=str(issue), date=date, main_pool_expected='49', status='observed_backup',
                **{f'n{i}':str(i) for i in range(1,7)})


def test_period_or_matrix_missing_does_not_fill_or_shift():
    with pytest.raises(NumericalFailure): runner.parse_rows([],701,1,49)
    with pytest.raises(NumericalFailure): runner.parse_rows([row(702)],701,1,49)
    with pytest.raises(NumericalFailure): runner.parse_rows([row()],701,1,43)
    assert runner.parse_rows([row()],701,1,49)==[[1,2,3,4,5,6]]


def test_no_duplicate_ball_or_bad_date():
    bad=row(); bad['n6']='1'
    with pytest.raises(NumericalFailure): runner.parse_rows([bad],701,1,49)
    with pytest.raises(NumericalFailure): runner.parse_rows([row(),row(702)],701,2,49)


def test_artifacts_exclusive_and_hash_checked_before_reveal(tmp_path):
    receipt=tmp_path/'receipt.json'
    sha=runner.save_new(receipt,{'stage':'frozen_before_reveal'})
    assert sha==runner.digest(receipt)
    with pytest.raises(FileExistsError): runner.save_new(receipt,{})
    with pytest.raises(NumericalFailure): runner.reveal('uk',49,receipt,'wrong')
    receipt.write_text(json.dumps({'stage':'unfrozen'}))
    with pytest.raises(NumericalFailure): runner.reveal('uk',49,receipt,runner.digest(receipt))


def test_joint_success_once_and_paired_table():
    tickets=((1,2,3,4,5,6),)*8
    random=((7,8,9,10,11,12),)*8
    draws=[[1,2,3,20,21,22],[7,8,9,20,21,22],[1,2,3,7,8,9],[30,31,32,33,34,35]]
    result=runner.summarize(draws,tickets,random,float(Fraction(12344,83237)),1/480)
    assert result['successes']==2 and result['random_successes']==2
    assert result['paired']==dict(both=1,model_only=1,random_only=1,neither=1)
    assert result['confirmatory_qualification'] is False


def test_uk_stability_and_two_pp_are_conjunctions():
    tickets=((1,2,3,4,5,6),)*8
    draws=[[1,2,3,4,5,6]]*400+[[30,31,32,33,34,35]]*100
    result=runner.summarize(draws,tickets,tickets,.148299434146,1/480)
    assert result['p_value']<1/480 and result['rate']>.148299434146+.02
    assert not result['nominal_screen_pass']  # final100 block fails, no OR gate


def test_interrupted_gradient_replay_requires_exact_input_and_no_accepted_steps(tmp_path):
    events=[dict(event='warmup_read_start'),dict(event='warmup_validated',n=200),
            dict(event='objective_start',call=1),dict(event='objective_end',call=1,value=100.),
            dict(event='objective_start',call=2)]
    (tmp_path/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    values,check=runner.recovery_prefix(tmp_path,49)
    initial=runner.model.project_rows(runner.model.initial_U(49))
    assert values==[100.]
    check(1,initial,False)
    with pytest.raises(NumericalFailure): check(1,initial+1e-6,False)
    with pytest.raises(NumericalFailure): check(1,initial,True)
    (tmp_path/'fit.json').write_text('{}')
    with pytest.raises(NumericalFailure): runner.recovery_prefix(tmp_path,49)


def test_resume_rejects_receipts_changed_after_audit_before_fit(tmp_path,monkeypatch):
    work=tmp_path/'run'/'exclusion-uk'; work.mkdir(parents=True)
    (work/'start.json').write_text('{}')
    (work/'events.jsonl').write_text('changed')
    (tmp_path/'recovery-audit.json').write_text(json.dumps(dict(records=[dict(
        family='exclusion',country='uk',original_events_sha256='wrong',
        start_sha256='wrong',completed_objectives=0,accepted_steps=0)])))
    monkeypatch.setattr(runner,'BASE',tmp_path)
    monkeypatch.setattr(runner,'preflight',lambda:dict(models=[dict(family='exclusion',id='test')]))
    monkeypatch.setattr(runner,'recovery_prefix',lambda *args:([],lambda *a:None))
    monkeypatch.setattr(runner.model,'fit_once',lambda *a:pytest.fail('must not fit altered receipts'))
    with pytest.raises(NumericalFailure,match='changed after recovery audit'):
        runner.execute('exclusion','uk',True)
    assert not (work/'resume-start.json').exists()
