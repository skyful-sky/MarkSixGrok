"""Collect four terminal records; no fits and no model re-scoring."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.intradraw_external_validation import BASE, PREREG, digest, now, preflight, reveal, save_new, hit
from src.intradraw_v2 import original_template, require


def main():
    preflight()
    records=[]
    for family in ('exclusion','attract2'):
        for country in ('uk','japan'):
            path=BASE/'run'/f'{family}-{country}'/'results.json'
            record=json.loads(path.read_text())
            require(record['stage']=='terminal' and record['run_count']==1,'unfinished or repeated run')
            record.update(result_path=str(path.relative_to(ROOT)),result_sha256=digest(path))
            records.append(record)
    # A frozen Random-only receipt provides an independently described comparator
    # even if a model failed before it could freeze a template. It never enters a fit.
    permutations=json.loads((PREREG/'permutations.json').read_text())
    random={}
    for country,pool in [('uk',49),('japan',43)]:
        path=BASE/'run'/f'random-{country}.json'
        tickets=original_template(pool,permutations[country][0])
        sha=save_new(path,dict(stage='frozen_before_reveal',frozen_at_utc=now(),
                              country=country,tickets=tickets,source='preregistered first permutation',
                              no_model_fit=True))
        draws=reveal(country,pool,path,sha)
        successes=sum(hit(d,tickets) for d in draws)
        random[country]=dict(n=len(draws),successes=successes,rate=successes/len(draws),
                             receipt_sha256=sha,descriptive_only=True)
        for r in records:
            if r['country']==country and r['n']:
                require(r['random_successes']==successes,'Random mismatch; stop')
    save_new(BASE/'results.json',dict(run_count=1,prereg_commit=records[0]['prereg_commit'],
             finished_at_utc=now(),records=records,random=random,HK_attempts_cumulative=14,
             confirmatory_qualification=False,
             status='archived_no_HK_qualification',
             note='Japan246 only; source nonexposure not established; failures are NA, not zero hits'))
    ledger=BASE/'ledger.jsonl'
    with ledger.open('x') as stream:
        for record in records:
            stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')
    for path in (BASE/'results.json',ledger):
        path.with_name(path.name+'.sha256').write_text(digest(path)+'  '+path.name+'\n')
    files=sorted(p for p in BASE.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (BASE/'SHA256SUMS').write_text(''.join(digest(p)+'  '+str(p.relative_to(ROOT))+'\n' for p in files))


if __name__=='__main__':
    main()
