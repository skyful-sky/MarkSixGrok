"""One-shot execution adapter; imports the unmodified cce71b9 numerical kernel.

No model choices live here. Training reads only the first 200 rows. Outcome
parsing is permitted only after a durable frozen-template receipt is saved.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np
import scipy
from scipy.stats import beta, binom

from src import intradraw_v2 as model

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'validation/INTRADRAW-v2'
PREREG = ROOT / 'prereg/intradraw-v2'
LOCK_COMMIT = 'cce71b92ecc174bb7fad6085d0a863d5c248ab26'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    """Exclusive creation forbids replacing any existing execution artifact."""
    path = Path(path)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return digest(path)


def append(path, value):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def preflight():
    lock = json.loads((PREREG/'lock.json').read_text())
    for relative, expected in lock['implementation_sha256'].items():
        model.require(digest(ROOT/relative) == expected, 'locked implementation hash: '+relative)
    for relative, expected in lock['documents_sha256'].items():
        model.require(digest(PREREG/relative) == expected, 'locked document hash: '+relative)
    for key, field in [('initialization', 'initialization_file'),
                       ('candidate_permutations', 'candidate_permutations_file')]:
        model.require(digest(PREREG/lock[field]) == lock[key+'_sha256'], 'locked '+key)
    snapshot = lock['external_ledger_snapshot']
    model.require(digest(ROOT/snapshot['path']) == snapshot['sha256'], 'external j ledger changed')
    model.require(digest(PREREG/snapshot['new_reservations_file']) ==
                  lock['external_reservations_sha256'], 'reserved slots changed')
    meta = lock['source_metadata']
    model.require(digest(ROOT/meta['manifest_path']) == meta['manifest_sha256'], 'source manifest changed')
    for dataset in meta['datasets']:
        model.require(digest(ROOT/'data/discovery'/dataset['path']) == dataset['sha256'], 'source CSV changed')
    env = lock['float_environment']
    model.require(platform.python_version() == env['python'] and np.__version__ == env['numpy']
                  and scipy.__version__ == env['scipy'], 'locked software environment')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS'):
        model.require(os.environ.get(name) == '1', 'locked single-thread '+name)
    return lock


def parse_rows(rows, start, count, pool):
    model.require(len(rows) == count, 'missing periods; NA, no filling')
    draws = []
    previous = None
    for expected, row in zip(range(start, start+count), rows):
        model.require(int(row['issue']) == expected and int(row['main_pool_expected']) == pool,
                      'issue/matrix mismatch; NA, no shifting')
        date = datetime.strptime(row['date'], '%Y-%m-%d')
        model.require(previous is None or date > previous, 'non-increasing dates')
        previous = date
        draw = [int(row['n'+str(i)]) for i in range(1, 7)]
        model.require(row['status'].startswith('observed') and len(set(draw)) == 6
                      and all(1 <= n <= pool for n in draw), 'missing/invalid complete six-set')
        draws.append(draw)
    return draws


def load_warmup(country, pool):
    with (ROOT/'data/discovery'/f'{country}.csv').open() as stream:
        rows = list(itertools.islice(csv.DictReader(stream), 200))
    return parse_rows(rows, 701, 200, pool)


def reveal(country, pool, receipt, receipt_sha):
    model.require(digest(receipt) == receipt_sha, 'frozen receipt hash changed')
    frozen = json.loads(Path(receipt).read_text())
    model.require(frozen['stage'] == 'frozen_before_reveal', 'missing durable prediction freeze')
    with (ROOT/'data/discovery'/f'{country}.csv').open() as stream:
        rows = list(itertools.islice(csv.DictReader(stream), 200, 700 if pool == 49 else 446))
    return parse_rows(rows, 901, 500 if pool == 49 else 246, pool)


def hit(draw, tickets):
    return max(len(set(draw)&set(ticket)) for ticket in tickets) >= 3


def summarize(draws, tickets, random_tickets, q, alpha):
    m = [hit(draw, tickets) for draw in draws]
    r = [hit(draw, random_tickets) for draw in draws]
    n, k = len(m), sum(m)
    p = float(binom.sf(k-1, n, q))
    lower = float(beta.ppf(alpha, k, n-k+1)) if k else 0.
    blocks = [{'n': len(m[i:i+100]), 'successes': sum(m[i:i+100])}
              for i in range(0, n, 100)]
    nominal = p <= alpha and lower > q and k/n >= q+.02
    if n == 500:
        nominal = nominal and all(b['successes']/b['n'] > q for b in blocks)
    return dict(n=n, successes=k, rate=k/n, random_successes=sum(r), random_rate=sum(r)/n,
                paired=dict(both=sum(a and b for a,b in zip(m,r)),
                            model_only=sum(a and not b for a,b in zip(m,r)),
                            random_only=sum(b and not a for a,b in zip(m,r)),
                            neither=sum(not a and not b for a,b in zip(m,r))),
                fair_q=q, gain_over_fair=k/n-q, p_value=p, alpha=alpha,
                lower_bound=lower, blocks=blocks, nominal_screen_pass=bool(nominal),
                confirmatory_qualification=False,
                period_hits=[dict(issue=901+i, model=int(a), random=int(b))
                             for i,(a,b) in enumerate(zip(m,r))])


def recovery_prefix(work, pool):
    """Only recover an interrupted first gradient; no accepted step is reset."""
    for name in ('fit.json','predictions.json','results.json','resume-start.json'):
        model.require(not (work/name).exists(), 'not an untouched interrupted first gradient: '+name)
    events=[json.loads(line) for line in (work/'events.jsonl').read_text().splitlines()]
    model.require(events[:2] and events[0]['event']=='warmup_read_start'
                  and events[1]['event']=='warmup_validated' and events[1]['n']==200,
                  'invalid original warmup receipt')
    completed=[]
    pending=False
    for event in events[2:]:
        if event['event']=='objective_start':
            model.require(not pending and event['call']==len(completed)+1, 'nonsequential original calls')
            pending=True
        elif event['event']=='objective_end':
            model.require(pending and event['call']==len(completed)+1
                          and math.isfinite(event['value']), 'invalid original objective result')
            completed.append(event['value']);pending=False
        else:
            raise model.NumericalFailure('unsupported prior execution state')
    model.require(pending and len(completed)<1+4*pool, 'not an interrupted first gradient')
    initial=model.project_rows(model.initial_U(pool))
    def check(call, U, probe):
        expected=initial.copy()
        if call>1:
            coordinate=(call-2)//2
            expected.flat[coordinate] += 1e-4 if (call-2)%2==0 else -1e-4
        model.require(probe==(call>1) and np.array_equal(U,expected), 'replay input differs from locked trajectory')
    return completed,check


def execute(family, country, resume=False):
    lock = preflight()
    pool = 49 if country == 'uk' else 43
    identity = next(item for item in lock['models'] if item['family'] == family)
    work = BASE/'run'/f'{family}-{country}'
    if resume:
        completed,check_replay=recovery_prefix(work,pool)
        started=json.loads((work/'start.json').read_text())
        audit=json.loads((BASE/'recovery-audit.json').read_text())
        prior=next(r for r in audit['records'] if r['family']==family and r['country']==country)
        model.require(digest(work/'events.jsonl')==prior['original_events_sha256']
                      and digest(work/'start.json')==prior['start_sha256']
                      and len(completed)==prior['completed_objectives'] and prior['accepted_steps']==0,
                      'original interruption receipts changed after recovery audit')
        model.require(started['model_id']==identity['id'] and started['country']==country
                      and started['prereg_commit']==LOCK_COMMIT and started['run_count']==1
                      and started['source_sha256']==digest(ROOT/'data/discovery'/f'{country}.csv')
                      and started['j']==identity['external_j']
                      and started['alpha_fraction']==identity['alpha_fraction'], 'prior start differs')
        save_new(work/'resume-start.json', dict(at_utc=now(),run_count=1,
                 original_events_sha256=digest(work/'events.jsonl'), replay_completed_calls=len(completed),
                 prior_accepted_steps=0, reason='Manager-authorized deterministic continuation after bridge interruption'))
    else:
        work.mkdir(parents=True, exist_ok=False)  # one start per model/country
    new_start = dict(model_id=identity['id'], family=family, country=country, run_count=1,
                   prereg_commit=LOCK_COMMIT, started_at_utc=now(), stage='started',
                   source_sha256=digest(ROOT/'data/discovery'/f'{country}.csv'),
                   j=identity['external_j'], alpha_fraction=identity['alpha_fraction'],
                   hk_attempt_cost=0)
    if not resume:
        started=new_start
        save_new(work/'start.json', started)
    event_path=work/('resume-events.jsonl' if resume else 'events.jsonl')
    append(event_path, dict(at_utc=now(), event='warmup_read_start'))
    receipt = None
    try:
        draws = load_warmup(country, pool)
        append(event_path, dict(at_utc=now(), event='warmup_validated', n=200))
        # Telemetry delegates every call unchanged to the hash-pinned kernel.
        original = model.profiled_objective
        calls = 0
        def observed(*args, **kwargs):
            nonlocal calls
            calls += 1
            if resume and calls<=len(completed):
                check_replay(calls,args[1],args[4] if len(args)>4 else kwargs.get('probe',False))
                append(event_path,dict(at_utc=now(),event='objective_replayed',call=calls,
                                      value=completed[calls-1]))
                return completed[calls-1]
            before = time.monotonic()
            append(event_path, dict(at_utc=now(), event='objective_start', call=calls))
            value = original(*args, **kwargs)
            append(event_path, dict(at_utc=now(), event='objective_end', call=calls,
                                            seconds=time.monotonic()-before, value=value))
            return value
        model.profiled_objective = observed
        fitted = model.fit_once(family, draws, pool)
        model.profiled_objective = original
        saved = dict(U=np.asarray(fitted['U'], float).tolist(),
                     log_weights=[str(x) for x in fitted['log_weights']],
                     outer={key:value for key,value in fitted['outer'].items() if key != 'U'},
                     inner={key:([str(x) for x in value] if isinstance(value,np.ndarray)
                                 else str(value) if isinstance(value,np.longdouble) else value)
                            for key,value in fitted['inner'].items()}, fitted_at_utc=now())
        save_new(work/'fit.json', saved)
        permutations = json.loads((PREREG/'permutations.json').read_text())[country]
        index, tickets, estimates = model.select_template(family, fitted['U'], fitted['log_weights'], permutations)
        receipt = work/'predictions.json'
        receipt_sha = save_new(receipt, dict(stage='frozen_before_reveal', frozen_at_utc=now(),
            model_id=identity['id'], country=country, fit_sha256=digest(work/'fit.json'),
            data_sha256=started['source_sha256'], template_index_zero_based=index,
            tickets=tickets, random_tickets=model.original_template(pool, permutations[0]),
            candidates=[dict(value=e.value, absolute_error=e.absolute_error,
                             quadrature_relative_bound=e.quadrature_relative_bound) for e in estimates],
            score_issues=lock['windows'][country]['score']))
        outcomes = reveal(country, pool, receipt, receipt_sha)
        result = summarize(outcomes, tickets, model.original_template(pool, permutations[0]),
                           float(Fraction(lock['fair_q'][country])), float(Fraction(identity['alpha_fraction'])))
        result['status'] = ('partial_screen_pass' if country=='japan' else 'nominal_screen_pass') if result['nominal_screen_pass'] else 'archived_screen_failed'
        result['prediction_sha256'] = receipt_sha
    except Exception as exc:
        result = dict(status='archived_execution_failure', n=0, successes=None, rate=None,
                      random_successes=None, random_rate=None, p_value=None,
                      nominal_screen_pass=False, confirmatory_qualification=False,
                      failure_type=type(exc).__name__, failure=str(exc),
                      traceback=traceback.format_exc(), score_outcomes_revealed=False)
    result.update(started)
    result.update(stage='terminal', finished_at_utc=now(), fit_available=(work/'fit.json').exists(),
                  predictions_available=receipt is not None and receipt.exists(),
                  source_eligibility='exposed discovery; not confirmatory holdout', hk_attempts_cumulative=14)
    save_new(work/'results.json', result)
    append(event_path, dict(at_utc=now(), event='terminal', status=result['status']))
    print(json.dumps(dict(country=country, family=family, status=result['status'],
                          successes=result['successes'], n=result['n'], failure=result.get('failure'))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('family', choices=['exclusion','attract2'])
    parser.add_argument('country', choices=['uk','japan'])
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    execute(args.family, args.country, args.resume)
