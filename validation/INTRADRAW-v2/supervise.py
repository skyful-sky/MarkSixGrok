"""Detached one-shot continuation, then tests/commit/push; never restarts fits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.intradraw_external_validation import BASE, digest, now, save_new, preflight

PYTHON='/tmp/marksix-commit-venv/bin/python'
REPORT=ROOT/'docs/intradraw-v2-external-validation.md'
TESTS=[PYTHON,'-m','pytest','tests/','docs/review-evidence/test_signal_visibility_diag.py',
       'docs/review-evidence/test_external_fair_baselines.py',
       'docs/review-evidence/test_external_holdout_windows.py',
       '--no-sealed-results','-q','-p','no:cacheprovider']


def command(args):
    return subprocess.run(args,cwd=ROOT,check=True,text=True,capture_output=True).stdout.strip()


def main():
    preflight()
    start=dict(at_utc=now(),pid=os.getpid(),run_count=1,kind='interruption_continuation',
               head=command(['git','rev-parse','HEAD']),
               adapter_sha256=digest(ROOT/'src/intradraw_external_validation.py'),
               original_kernel_sha256=digest(ROOT/'src/intradraw_v2.py'),
               tag_refs=command(['git','show-ref','--tags']))
    save_new(BASE/'supervisor-start.json',start)
    jobs=[]
    for family in ('exclusion','attract2'):
        for country in ('uk','japan'):
            output=open(f'/tmp/marksix-intradraw-{family}-{country}.log','x')
            child=subprocess.Popen([PYTHON,'-u','-m','src.intradraw_external_validation',
                                    family,country,'--resume'],cwd=ROOT,
                                   stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                                   start_new_session=True)
            jobs.append((family,country,child))
    print(json.dumps(dict(event='launched',at_utc=now(),jobs=[dict(family=f,country=c,pid=p.pid)
                                                            for f,c,p in jobs])),flush=True)
    while any(p.poll() is None for _,_,p in jobs):
        progress=[]
        for family,country,p in jobs:
            file=BASE/'run'/f'{family}-{country}'/'resume-events.jsonl'
            latest=file.read_text().splitlines()[-1] if file.exists() else 'launching'
            progress.append(dict(family=family,country=country,pid=p.pid,exit=p.poll(),latest=latest))
        print(json.dumps(dict(at_utc=now(),progress=progress)),flush=True)
        time.sleep(30)
    if any(p.returncode!=0 for _,_,p in jobs):
        raise RuntimeError('A worker exited without a terminal record; no restart and no automatic commit')
    command([PYTHON,str(BASE/'finalize.py')])
    result=json.loads((BASE/'results.json').read_text())
    lines=['# INTRADRAW-v2 外部預驗結果','',
           '依 cce71b9 原規格，j2 α=1/480、j3 α=1/960、增幅至少2pp；沒有更改原核、起點、求解器或門檻。',
           '上輪 bridge 中斷在首輪梯度，沒有接受步／已擬合模型／評分；原始紀錄完整保留。',
           '續算只重播已完成的確定性目標函數浮點值，逐個核對其鎖定輸入，未完成探針接續原求解器。run_count仍1。','',
           '| 案／國家 | 命中／評分 | 成功率 | 公平基準 | p | 下界 | 判定 |',
           '|---|---|---|---|---|---|---|']
    for r in result['records']:
        lines.append(f"| {r['model_id']}／{r['country']} | {r['successes'] if r['successes'] is not None else 'NA'}/{r['n']} | {r['rate']} | {r.get('fair_q','NA')} | {r['p_value']} | {r.get('lower_bound','NA')} | {r['status']} |")
        if r.get('failure'):
            lines.extend(['',f"{r['model_id']}／{r['country']} 技術停止：`{r['failure_type']}: {r['failure']}`。NA不等於0命中；沒有重跑。"])
        if r.get('paired'):
            lines.extend(['',f"{r['model_id']}／{r['country']} 配對：`{json.dumps(r['paired'])}`；固定區塊：`{json.dumps(r['blocks'])}`。"])
    lines.extend(['','## 同配置 Random（只描述）',''])
    for country,r in result['random'].items():
        lines.append(f"- {country}：{r['successes']}/{r['n']} = {r['rate']:.8%}；第1套固定置換，不選對照p值。")
    lines.extend(['','日本只稱246期篩選；資料未曝光資格仍未核實，不能作盲測或確認性通過。',
                  '未有兩國完整500期及全部資料／穩定性資格，整體封存，不申請香港回測。',
                  '未讀取香港資料，H3、prereg-r2/r3、CSV、26/116、舊registry、tags、sealed windows與舊結果保持不變；香港嘗試仍14。',
                  '',f"執行起點：{start['head']}；原始預鎖：cce71b92ecc174bb7fad6085d0a863d5c248ab26。",''])
    with REPORT.open('x') as stream: stream.write('\n'.join(lines))
    completed=subprocess.run(TESTS,cwd=ROOT,text=True,capture_output=True)
    save_new(BASE/'test-results.json',dict(at_utc=now(),command=TESTS,exit_code=completed.returncode,
                                         stdout=completed.stdout,stderr=completed.stderr))
    if completed.returncode:
        raise RuntimeError('Tests failed; results retained but not committed or pushed')
    preflight()
    if command(['git','show-ref','--tags'])!=start['tag_refs']:
        raise RuntimeError('Tag refs changed; stop without commit')
    allowed=('src/intradraw_external_validation.py','tests/test_intradraw_external_validation.py',
             'validation/INTRADRAW-v2/','docs/intradraw-v2-external-validation.md')
    changed=command(['git','diff','--name-only','cce71b9']).splitlines()
    if any(not any(p==a or a.endswith('/') and p.startswith(a) for a in allowed) for p in changed):
        raise RuntimeError('Unexpected tracked change; stop without commit')
    REPORT.with_name(REPORT.name+'.sha256').write_text(digest(REPORT)+'  '+REPORT.name+'\n')
    files=sorted(p for p in BASE.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (BASE/'SHA256SUMS').write_text(''.join(digest(p)+'  '+str(p.relative_to(ROOT))+'\n' for p in files))
    command(['git','diff','--check'])
    command(['git','add','src/intradraw_external_validation.py','tests/test_intradraw_external_validation.py',
             'validation/INTRADRAW-v2',str(REPORT.relative_to(ROOT)),str(REPORT.relative_to(ROOT))+'.sha256'])
    command(['git','-c','user.name=Codex','-c','user.email=codex@openai.com','commit','-m',
             'Archive one-shot intradraw v2 external validation and all terminal outcomes'])
    commit=command(['git','rev-parse','HEAD'])
    pushed=subprocess.run(['git','push','origin','main'],cwd=ROOT,text=True,capture_output=True)
    outcome=dict(at_utc=now(),commit=commit,push_exit_code=pushed.returncode,
                 push_stdout=pushed.stdout,push_stderr=pushed.stderr,
                 tests_summary=completed.stdout.splitlines()[-1],report_sha256=digest(REPORT))
    Path('/tmp/marksix-intradraw-completion.json').write_text(json.dumps(outcome,indent=2))
    print(json.dumps(outcome),flush=True)
    if pushed.returncode: raise RuntimeError('Push rejected; no force/rebase/tag changes')


if __name__=='__main__':
    try: main()
    except BaseException as exc:
        import traceback
        Path('/tmp/marksix-intradraw-supervisor-error.json').write_text(json.dumps(
            dict(at_utc=now(),error=str(exc),traceback=traceback.format_exc()),indent=2))
        raise
