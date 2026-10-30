"""HK-MACH-ALT-v2: fixed causal phase proxy, not physical machine inference."""
from __future__ import annotations
import argparse
import csv
from datetime import date,datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
ID='HK-MACH-ALT-v2'
DATA_SHA='653993bd43030f7436a96a171ba98b2e73ed62e26f38108efd334fe3d88c8a5e'
SEED=20261030
SWAP=52
FIRST_S=69
FIRST_ISSUE='26/116'
HORIZON=200
THRESHOLD=43
RANDOM_PATHS=10000
PERMUTATIONS=1000


def canonical(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()


def seed(label,*coordinates):
    if label not in ('TIE','RAND','PERM'):
        raise ValueError('unregistered random namespace')
    raw=json.dumps([label,SEED,*coordinates],ensure_ascii=True,separators=(',',':')).encode('utf-8')
    return int.from_bytes(hashlib.sha256(raw).digest(),'big')


def permutation(label,*coordinates):
    order=list(range(1,50)); random.Random(seed(label,*coordinates)).shuffle(order)
    return order


def phase(s):
    if s<0: raise ValueError('negative valid-draw index')
    return (s if s<SWAP else s+1)%2


def diagnostic_phases(s):
    """Permanent read-only scenarios; no public prediction mode selects these."""
    return {'S1':phase(s) if s<=SWAP else s%2,
            'S2_cyclic3':(s if s<SWAP else s+1)%3,
            'S2_third_even':s%2 if s<SWAP else (2 if s%2==0 else 1)}


def validate_draw(draw):
    if len(draw)!=6 or len(set(draw))!=6 or any(type(n) is not int or not 1<=n<=49 for n in draw):
        raise ValueError('requires six distinct main numbers, special excluded')


def tickets(order):
    if sorted(order)!=list(range(1,50)): raise ValueError('requires bijection 1..49')
    return [sorted(order[i:i+6]) for i in range(0,48,6)]


def forecast_at(draws,s,u,*,exploratory=False):
    if not 0<=s<=len(draws): raise ValueError('unavailable causal history')
    if not exploratory and (not 1<=u<=200 or s!=FIRST_S+u-1):
        raise ValueError('fixed forward index/window')
    history=draws[:s]  # neither target nor future outcomes enter the computation
    counts=[0]*49; nm=0; m=phase(s)
    for t,draw in enumerate(history):
        validate_draw(draw)
        if phase(t)==m:
            nm+=1
            for number in draw: counts[number-1]+=1
    order=permutation('TIE',u)
    order.sort(key=lambda n:-(counts[n-1]+1))  # stable: seeded permutation breaks exact ties
    return dict(model_id=ID,s=s,u=u,phase=m,N_m=nm,k_i=counts,
                weight_numerators=[x+1 for x in counts],weight_denominator=6*nm+49,
                weight_semantics='empirical smoothed ranking weights; not a without-replacement posterior',
                order=order,tickets=tickets(order),excluded=order[48],
                history_indices=[0,s-1],tie_seed_sha256=f'{seed("TIE",u):064x}')


def random_tickets(b,u):
    if not 1<=b<=RANDOM_PATHS or not 1<=u<=200: raise ValueError('fixed Random coordinates')
    return tickets(permutation('RAND',b,u))


def success(draw,allocation):
    validate_draw(draw)
    return int(any(len(set(draw)&set(ticket))>=3 for ticket in allocation))


def fair_p8():
    # Losing polynomial: eight disjoint groups of6 allow at most2; outside one.
    poly=[1]+[0]*6
    for size in [6]*8+[1]:
        updated=[0]*7
        for j,a in enumerate(poly):
            for h in range(min(2 if size==6 else 1,6-j)+1):
                updated[j+h]+=a*math.comb(size,h)
        poly=updated
    return 1-Fraction(poly[6],math.comb(49,6))


def fair_tail():
    q=fair_p8(); p,d=q.numerator,q.denominator
    return Fraction(sum(math.comb(200,k)*p**k*(d-p)**(200-k) for k in range(43,201)),d**200)


def load_snapshot(path=ROOT/'marksix_data.csv'):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA: raise ValueError('snapshot SHA mismatch')
    rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    if len(rows)!=69: raise ValueError('snapshot length')
    draws=[]
    previous=None
    for s,row in enumerate(rows):
        if row['期數']!=f'26/{47+s:03d}': raise ValueError('missing snapshot period')
        day=date.fromisoformat(row['攪珠日期'])
        if previous and day<=previous: raise ValueError('dates not increasing')
        previous=day
        draw=[int(row[f'正選號碼{i}']) for i in range(1,7)]
        validate_draw(draw);draws.append(draw)
    swap=next(s for s,row in enumerate(rows) if row['期數']=='26/099')
    if swap!=SWAP: raise ValueError('swap index differs from prereg; no silent reset')
    return rows,draws


def valid_events(events):
    """Unknown missing events pause; only sourced cancelled/incomplete events skip."""
    valid=[];last_day=None;last_issue=None
    for event in events:
        issue=event['issue'];yy,number=map(int,issue.split('/'))
        day=date.fromisoformat(event['date'])
        if last_issue is not None:
            py,pn=map(int,last_issue.split('/'))
            if not ((yy==py and number==pn+1) or (yy==py+1 and number==1 and event.get('official_year_boundary_url'))):
                raise ValueError('unexplained missing period; NA and pause, no parity advance')
        if last_day and day<=last_day: raise ValueError('event dates out of order')
        last_day,last_issue=day,issue
        if event['status'] in ('cancelled','incomplete'):
            if not event.get('official_source_url'): raise ValueError('skip requires official evidence')
            continue
        if event['status']!='complete' or not event.get('official_source_url'):
            raise ValueError('missing official complete result; NA and pause')
        validate_draw(event['main']); valid.append(event)
    return valid


def evaluate_events(snapshot,events,*,late_issues=(),official_retirement_url=None,
                    prediction_receipts=None,public_before_cutoff_verified=False):
    """Fixed one-shot horizon; no early success, no rule borrowed from H3."""
    if len(snapshot)!=69: raise ValueError('fixed69 historical draws')
    valid=valid_events(events)
    if events and events[0]['issue']!=FIRST_ISSUE: raise ValueError('must start from registered first issue')
    if len(valid)>200: raise ValueError('cannot extend200 valid draws')
    history=list(snapshot);results=[]; late=set(late_issues)
    receipts=prediction_receipts or {}
    for u,event in enumerate(valid,1):
        prediction=forecast_at(history,len(history),u)
        receipt=receipts.get(event['issue'])
        if receipt is None:
            late.add(event['issue'])
        else:
            if (receipt['target_issue']!=event['issue'] or receipt['prediction']!=prediction or
                receipt['prediction_payload_sha256']!=hashlib.sha256(canonical(prediction)).hexdigest()):
                raise ValueError('prediction receipt/content/SHA mismatch; pause')
            made=datetime.fromisoformat(receipt['generated_at_utc'])
            cutoff=datetime.fromisoformat(receipt['official_sales_cutoff_utc'])
            if made.tzinfo is None or cutoff.tzinfo is None: raise ValueError('timezone required')
            if made>=cutoff: late.add(event['issue'])
        results.append(dict(u=u,issue=event['issue'],hit=success(event['main'],prediction['tickets']),
                            late=event['issue'] in late))
        history.append(event['main'])
    k=sum(r['hit'] for r in results)
    nominal=len(valid)==200 and k>=43
    passed=nominal and not late and not official_retirement_url and public_before_cutoff_verified
    return dict(n=len(valid),successes=k,passed=passed,
                statistical_threshold_met=nominal,
                status='archived_regime_interruption' if official_retirement_url else
                ('passed' if passed else 'completed_publication_unverified' if nominal and not late else
                 'archived_not_passed' if len(valid)==200 else 'pending'),
                official_retirement_url=official_retirement_url,late_issues=sorted(late),periods=results)


def permuted_terminal(all_draws,b):
    """Read-only exchangeability diagnostic: permute all269 complete six-sets."""
    if len(all_draws)!=269 or not 1<=b<=1000: raise ValueError('PERM only at completed horizon')
    for draw in all_draws: validate_draw(draw)
    indices=list(range(269));random.Random(seed('PERM',b)).shuffle(indices)
    shuffled=[all_draws[i] for i in indices]
    return sum(success(shuffled[s],forecast_at(shuffled,s,s-69+1)['tickets']) for s in range(69,269))


def random_terminal(all_draws,b):
    if len(all_draws)!=269: raise ValueError('Random terminal diagnostic only at200')
    return sum(success(all_draws[68+u],random_tickets(b,u)) for u in range(1,201))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=('predict-first','explore'))
    args=parser.parse_args()
    rows,draws=load_snapshot()
    if args.operation=='predict-first':
        print(canonical(forecast_at(draws,69,1)).decode(),end='')
    else:
        records=[]
        for s in range(49,69):
            # Signed forward-relative u=-19..0, locked before historical scoring.
            p=forecast_at(draws,s,s-69+1,exploratory=True)
            records.append(dict(issue=rows[s]['期數'],s=s,u=p['u'],tickets=p['tickets'],
                                hit=success(draws[s],p['tickets'])))
        print(canonical(dict(role='in-sample exploratory only; excluded from200',
                             successes=sum(r['hit'] for r in records),n=20,periods=records)).decode(),end='')


if __name__=='__main__': main()
