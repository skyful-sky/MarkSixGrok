"""Runner mechanics only: no historical fit, no replay of a sealed run."""
from fractions import Fraction
import json

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
