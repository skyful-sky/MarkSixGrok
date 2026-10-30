"""Frozen-receipt integrity; do not rerun the historical exploration."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from src import hk_mach_alt_v2 as m

ROOT=Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preregistered_fingerprints_still_match():
    lock=json.loads((ROOT/'prereg/hk-mach-alt-v2/lock.json').read_text())
    for name,expected in lock['fingerprints'].items():
        assert sha(ROOT/name)==expected
    assert lock['swap']['zero_based_s']==52 and lock['swap']['one_based_valid_ordinal']==53
    assert lock['alpha']=='1/100' and lock['shared_family_reserved_alpha']=='2/75'


def test_frozen_prediction_and_tickets_hashes_and_causal_reproduction():
    file=next((ROOT/'forward/hk-mach-alt-v2').glob('*.json'))
    frame=json.loads(file.read_text())
    assert sha(file)==file.with_name(file.name+'.sha256').read_text().split()[0]
    assert hashlib.sha256(m.canonical(frame['tickets'] if 'tickets' in frame else frame['prediction']['tickets'])).hexdigest()==frame['tickets_sha256']
    assert hashlib.sha256(m.canonical(frame['prediction'])).hexdigest()==frame['prediction_payload_sha256']
    _,draws=m.load_snapshot()
    assert frame['prediction']==m.forecast_at(draws,69,1)
    assert frame['target_issue']=='26/116' and frame['history_last_issue']=='26/115'
    assert datetime.fromisoformat(frame['generated_at_utc'])<datetime.fromisoformat(frame['official_sales_cutoff_utc'])
    assert frame['publication_before_cutoff_verified'] is False


def test_exploration_is_once_after_freeze_and_excluded():
    record=json.loads((ROOT/'archive/hk-mach-alt-v2/exploration-26096-26115.json').read_text())
    file=next((ROOT/'forward/hk-mach-alt-v2').glob('*.json'))
    frame=json.loads(file.read_text())
    assert record['run_count']==1 and record['forward_counted']==0 and not record['parameters_changed']
    assert record['prediction_frozen_first_sha256']==sha(file)
    assert datetime.fromisoformat(record['completed_at_utc'])>datetime.fromisoformat(frame['generated_at_utc'])
    assert len(record['periods'])==20 and record['n']==20
    assert record['periods'][0]['u']==-19 and record['periods'][-1]['u']==0


def test_attempt15_is_a_supplement_existing_registry_unchanged():
    import csv
    with (ROOT/'registry/hk-mach-alt-v2.csv').open() as stream: rows=list(csv.DictReader(stream))
    assert len(rows)==1 and rows[0]['attempt_id']==m.ID and rows[0]['hk_attempt_number']=='15'
    assert rows[0]['shared_H3_nonindependent']=='True'
    assert rows[0]['lock_sha256']==sha(ROOT/rows[0]['lock_path'])
