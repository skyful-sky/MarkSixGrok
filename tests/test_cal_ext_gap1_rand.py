"""Synthetic model/reveal tests plus acquisition checks; no real calibration replay."""

from copy import deepcopy
from fractions import Fraction
import csv
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("calibration", ROOT/"src/cal_ext_gap1_rand.py")
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def synthetic_rows(n=201, pool=49):
    result = []
    for i in range(n):
        main = sorted({(i*3+j) % pool+1 for j in range(6)})
        result.append({"issue": str(701+i), "date": f"fixture-{i}", "status": "observed_backup",
                       "missing_reason": "NA", **{f"n{j+1}": str(x) for j,x in enumerate(main)}})
    return result


def test_gap_exposures_unseen_bin_and_exact_shrinkage():
    state = cal.GapState(49)
    assert state.bins() == [15]*49
    state.observe([1,2,3,4,5,6])
    assert state.exposures[15] == 49 and state.hits[15] == 6
    assert state.bins()[:6] == [0]*6 and state.bins()[6:] == [15]*43
    for _ in range(19):
        state.observe([1,2,3,4,5,6])
    prediction = state.predict(random.Random(20261029))
    assert Fraction(prediction["scores_exact"][0]) == (114+30*Fraction(6,49))/(114+30)
    assert Fraction(prediction["scores_exact"][6]) == (6+30*Fraction(6,49))/(49+19*43+30)
    assert prediction["score_midranks"][:6] == ["7/2"]*6
    assert prediction["score_midranks"][6:] == ["28"]*43


def test_gap_warmup_consumes_exactly_180_shuffles_before_first_score():
    state, rng = cal.GapState(49), random.Random(20261029)
    for local,row in enumerate(synthetic_rows(200),1):
        if local > 20:
            state.predict(rng)
        state.observe([int(row[f"n{i}"]) for i in range(1,7)])
    expected = random.Random(20261029)
    for _ in range(180):
        order = list(range(1,50)); expected.shuffle(order)
    assert rng.getstate() == expected.getstate()
    control = random.Random(20261030)
    control_order = list(range(1,50)); random.Random(20261030).shuffle(control_order)
    assert cal.random_prediction(49,control)["order"] == control_order


@pytest.mark.parametrize("pool", [49,43,45,33])
def test_fixed_ring_template_permutation_and_blue_policy(pool):
    prediction = cal.random_prediction(pool,random.Random(17))
    cal.validate_prediction(prediction,pool)
    assert prediction["tickets"] == [[prediction["order"][(6*b+j)%pool] for j in range(6)] for b in range(8)]
    assert prediction["attached_blue_ball"] == (1 if pool==33 else None)
    bad=deepcopy(prediction);bad["tickets"][0][0]=bad["tickets"][0][1]
    with pytest.raises(ValueError,match="Template"):
        cal.validate_prediction(bad,pool)


def test_binomial_tail_and_one_sided_exact_lower_bound():
    assert cal.binomial_upper(3,2,Fraction(1,2)) == Fraction(1,2)
    assert cal.binomial_upper(5,0,Fraction(1,3)) == 1
    alpha=Fraction(1,160)
    assert cal.cp_lower(5,0,alpha)==0
    assert math.isclose(cal.cp_lower(5,5,alpha),float(alpha)**(1/5),rel_tol=1e-12)
    lower=cal.cp_lower(20,7,alpha)
    tail=sum(math.comb(20,i)*lower**i*(1-lower)**(20-i) for i in range(7,21))
    assert math.isclose(tail,float(alpha),rel_tol=1e-12)


@pytest.fixture
def ready_broker(tmp_path):
    rows=synthetic_rows(22)
    broker=cal.RevealBroker("uk",rows,49,"sourcehash","lockhash",tmp_path)
    state=cal.GapState(49)
    for _ in range(20):
        response=broker.reveal(None);state.observe(response["main"])
    payload={"id":cal.ID,"game":"uk","local_index":21,"target":broker.metadata()[20],
             "through":{"ordinal":720,"issue":"720"},"training_draws":20,
             "history_sha256":broker.history_sha,"source_sha256":"sourcehash","lock_sha256":"lockhash",
             "models":{"gap1":state.predict(random.Random(20261029))}}
    return broker,payload,tmp_path


def saved_proof(path,payload,previous=None):
    envelope={"payload":payload,"payload_sha256":cal.sha(cal.canonical(payload)),
              "previous_chunk_sha256":previous,"saved_at_utc":cal.now()}
    body=cal.canonical(envelope)+b"\n";path.write_bytes(body)
    return {"offset":0,"length":len(body),"sha256":cal.sha(body),"fsync_complete_at_utc":cal.now()}


def test_broker_will_not_reveal_next_draw_before_saved_prediction(ready_broker):
    broker,payload,path=ready_broker
    before=broker.history_sha
    with pytest.raises(ValueError,match="before reveal"):
        broker.reveal(None)
    assert broker.index==20 and broker.history_sha==before
    journal=cal.Journal(path/"warmup-predictions.jsonl")
    proof=journal.append(payload)
    reveal=broker.reveal(proof);journal.close()
    assert reveal["local_index"]==21
    assert reveal["prediction_chunk_sha256"]==proof["sha256"]
    assert reveal["revealed_at_utc"] >= proof["fsync_complete_at_utc"]


@pytest.mark.parametrize("defect", ["target","source","lock","history","through","template","ranks","midrank","chain","bytes","content"])
def test_hash_period_or_template_failure_stops_before_reveal(ready_broker,defect):
    broker,payload,path=ready_broker;before=broker.history_sha
    if defect=="target": payload["target"]["issue"]="999"
    elif defect=="source": payload["source_sha256"]="changed"
    elif defect=="lock": payload["lock_sha256"]="changed"
    elif defect=="history": payload["history_sha256"]="changed"
    elif defect=="through": payload["through"]["ordinal"]=701
    elif defect=="template": payload["models"]["gap1"]["tickets"][0][0]=0
    elif defect=="ranks": payload["models"]["gap1"]["ranks"][0]=0
    elif defect=="midrank": payload["models"]["gap1"]["score_midranks"][0]="0"
    proof=saved_proof(path/"warmup-predictions.jsonl",payload,previous="wrong" if defect=="chain" else None)
    if defect=="bytes":proof["sha256"]="0"*64
    if defect=="content":
        p=path/"warmup-predictions.jsonl";envelope=json.loads(p.read_bytes());envelope["payload_sha256"]="0"*64
        body=cal.canonical(envelope)+b"\n";p.write_bytes(body);proof.update(sha256=cal.sha(body),length=len(body))
    with pytest.raises(ValueError):broker.reveal(proof)
    assert broker.index==20 and broker.history_sha==before


def test_missing_draw_revealed_as_na_not_invented(tmp_path):
    rows=synthetic_rows(1);rows[0].update(status="missing",missing_reason="source absent")
    for i in range(1,7):rows[0][f"n{i}"]="NA"
    broker=cal.RevealBroker("uk",rows,49,"s","l",tmp_path)
    reveal=broker.reveal(None)
    assert reveal["main"] is None and broker.history_sha==cal.sha(b"")


def test_short_series_summary_has_no_fake_rates_or_p_values():
    result=cal.summary([],"korea",Fraction(1,160))
    assert result["n"]==0 and result["gap1"]["rate"] is None
    assert result["gap1"]["binomial_upper_p"] is None and result["gap1"]["lower_bound"] is None
    assert "binomial_upper_p" not in result["random"]
    assert not any(k.startswith("p_") for k in result["paired"])


def test_full_synthetic_loop_rng_schedule_and_descriptive_blocks(tmp_path,monkeypatch):
    monkeypatch.setattr(cal,"OUTPUT",tmp_path)
    rows=synthetic_rows(201)
    class FakeClient:
        def __init__(self,game,directory):
            self.broker=cal.RevealBroker(game,rows,49,"s","l",directory)
            self.metadata=self.broker.metadata()
        def reveal(self,proof):return self.broker.reveal(proof)
        def close(self):pass
    monkeypatch.setattr(cal,"BrokerClient",FakeClient)
    result=cal.run_game("uk",{"rows":201,"main_pool_expected":49,"sha256":"s"},"l")
    assert result["total"]["n"]==1 and result["warmup_slots_used"]==200
    assert result["gap_rng_shuffles"]==181 and result["random_rng_shuffles"]==1
    assert sum(result["total"]["paired"].values())==1
    assert len(result["blocks"])==5 and result["blocks"][0]["n"]==1
    assert all("binomial_upper_p" not in b["gap1"] for b in result["blocks"])
    assert all("binomial_upper_p" not in b["random"] for b in result["blocks"])
    outcomes=[json.loads(s)["payload"] for s in (tmp_path/"uk/outcomes.jsonl").read_text().splitlines()]
    assert len(outcomes)==201 and sum(x["score"] is not None for x in outcomes)==1


def test_guard_blocks_old_sealed_directory_without_reading_it(tmp_path):
    code="""import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('cal',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
fd=m.install_guard(Path(sys.argv[2]))
try:
    (m.ROOT/'data/external/uk.csv').read_bytes()
except PermissionError:
    print('BLOCKED')
else:
    raise SystemExit('sealed read unexpectedly allowed')
"""
    result=subprocess.run([sys.executable,"-B","-c",code,str(ROOT/"src/cal_ext_gap1_rand.py"),str(tmp_path/"guard.jsonl")],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=="BLOCKED"


def test_real_broker_ipc_with_synthetic_data_only(tmp_path,monkeypatch):
    root=tmp_path/"fixture-root";(root/"data/discovery").mkdir(parents=True)
    (root/"archive").mkdir();output=root/"calibration"/cal.ID;output.mkdir(parents=True)
    body=cal.canonical(synthetic_rows(201));(root/"data/discovery/uk.csv").write_bytes(body)
    fixture_lock={"datasets":[{"key":"uk","main_pool_expected":49,"sha256":cal.sha(body)}]}
    lock_bytes=cal.canonical(fixture_lock);(root/"archive"/f"{cal.ID}.lock.json").write_bytes(lock_bytes)
    monkeypatch.setattr(cal,"OUTPUT",output)
    original=cal.subprocess.Popen
    shim="""import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
s=importlib.util.spec_from_file_location('cal',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.ROOT=Path(sys.argv[2]);m.LOCK=m.ROOT/'archive'/f'{m.ID}.lock.json';m.OUTPUT=m.ROOT/'calibration'/m.ID
m.load_access=lambda:SimpleNamespace(load_discovery=lambda game:json.loads((m.ROOT/'data/discovery/uk.csv').read_bytes()))
m.broker_main('uk')
"""
    def launch(args,**kwargs):
        return original([sys.executable,"-B","-c",shim,str(ROOT/"src/cal_ext_gap1_rand.py"),str(root)],**kwargs)
    monkeypatch.setattr(cal.subprocess,"Popen",launch)
    result=cal.run_game("uk",{"rows":201,"main_pool_expected":49,"sha256":cal.sha(body)},cal.sha(lock_bytes))
    assert result["total"]["n"]==1 and result["gap_rng_shuffles"]==181
    assert (output/"uk/broker-stderr.txt").read_bytes()==b""
    opened=[json.loads(x)["path"] for x in (output/"uk/broker-access.jsonl").read_text().splitlines()]
    assert opened and set(opened)=={"data/discovery/uk.csv"}


def test_ssq_discovery_acquisition_and_blue_semantics():
    access=cal.load_access();rows=access.load_discovery("ssq")
    assert len(rows)==92
    assert [(rows[i]["ordinal"],rows[i]["issue"],rows[i]["date"]) for i in [0,-1]]==[
        ("701","2008030","2008-03-16"),("792","2008121","2008-10-14")]
    assert all(r["date"]<"2008-10-16" for r in rows)
    assert all(1<=int(r["extra_ball"])<=16 for r in rows)
    assert [r["ordinal"] for r in access.history_before("ssq",703)]==["701","702"]
    with pytest.raises(ValueError):access.history_before("ssq",2008030)


def test_ssq_csv_matches_source_snapshot_without_opening_old_window():
    spec=importlib.util.spec_from_file_location("ssqprep",ROOT/"docs/review-evidence/prepare_ssq_discovery.py")
    prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
    sources=json.loads((ROOT/"data/discovery/retrievals.json").read_text())
    source=next(r for r in sources if r["kind"]=="ssq")
    body=gzip.decompress((ROOT/source["raw_path"]).read_bytes())
    assert prep.csv_bytes(prep.parse(body,source)) == (ROOT/"data/discovery/ssq.csv").read_bytes()
