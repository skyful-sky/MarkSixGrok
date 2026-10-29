"""Synthetic checks for warmup gates, conditional models and forward-only Borda."""

from dataclasses import replace
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import marksix_r2 as r2
import marksix_shadow_gates as gates
import marksix_meta_borda as meta


def fixtures(n=24):
    draws = []
    for t in range(n):
        main = tuple(sorted((t * 5 + k * 7) % 49 + 1 for k in range(6)))
        special = next(j for j in range(1, 50) if j not in main)
        draws.append(r2.Draw(f"26/{47+t:03}", date(2026, 5, 5) + timedelta(days=t), main, special))
    return draws


def test_pearson_is_lagged_pearson_not_full_series_acf():
    x = np.array([2, 5, 1, 7, 3, 8, 4], float)
    assert float(gates.lag_pearson(x)) == pytest.approx(np.corrcoef(x[:-1], x[1:])[0, 1])
    assert float(gates.lag_pearson(np.ones(20))) == 0


def test_gate_permutation_pairs_and_plus_one_match_direct_reconstruction():
    warm = gates.common.main_masks(fixtures(20))[0]
    output = gates.gate_test(warm)
    rng = np.random.default_rng(20261029)
    indices = np.stack([rng.permutation(20) for _ in range(10000)])
    odd = np.array(output["warmup"]["odd_counts"])
    high = np.array(output["warmup"]["high_counts"])
    expected_S = gates.lag_pearson(odd[indices]) + gates.lag_pearson(high[indices])
    assert np.array_equal(expected_S, output["permutation_statistics"]["paired_S"])
    S = output["models"]["SH-COMPREV-v1"]["S"]
    assert output["models"]["SH-COMPREV-v1"]["p_lower"] == (1 + int(np.count_nonzero(expected_S <= S))) / 10001
    D = np.array([np.std(draw.main, ddof=1) for draw in fixtures(20)])
    assert output["warmup"]["D_sample_std"] == pytest.approx(D)
    observed = output["models"]["SH-DISPREG-v1"]["r1"]
    assert output["models"]["SH-DISPREG-v1"]["p_upper"] == (1 + int(np.count_nonzero(gates.lag_pearson(D[indices]) >= observed))) / 10001
    with pytest.raises(ValueError): gates.gate_test(warm[:19])


def test_gate_requires_all_sign_and_p_conditions_and_constant_fails():
    warm = np.zeros((20, 49), bool); warm[:, :6] = True
    result = gates.gate_test(warm)
    assert all(not entry["passed"] for entry in result["models"].values())
    for entry in result["models"].values():
        assert entry.get("p_upper", entry.get("p_lower")) == 1


def test_candidate_rank_exception_M_and_regime_tickets():
    masks = gates.common.main_masks(fixtures(24))
    output = gates.run_paths(masks, gates.MODELS, True)
    for model, records in output["records"].items():
        assert len(records) == 4
        for record in records:
            M = max(len(set(ticket).intersection(record["main"])) for ticket in record["tickets"])
            assert record["M"] == M and record["success"] == (M >= 3)
            if model == "SH-DISPREG-v1":
                assert record["mean_main_rank"] is None
                expected = record["EWM_D"] < record["historical_median_D"]
                assert (record["regime"] == "clustered") == expected
                assert sorted(sum(record["tickets"], [])) == list(range(1, 49))


def test_comprev_cells_unclipped_exact_scores_and_midrank():
    draws = [replace(d, main=(1, 3, 5, 7, 9, 11), special=49) for d in fixtures(21)]
    record = gates.run_paths(gates.common.main_masks(draws), ("SH-COMPREV-v1",), True)["records"]["SH-COMPREV-v1"][0]
    for n in range(1, 50):
        cell = int(n >= 25) * 2 + int(n % 2 == 0)
        size = (12, 12, 13, 12)[cell]
        count = 6 if cell == 0 else 0
        e = Fraction(6 * size, 49)
        expected = (e - Fraction(1, 2) * (count - e)) / size
        assert Fraction(record["score_keys"][n - 1], record["score_denominator"]) == expected
    assert record["score_keys"][0] < 0  # Negative predictions are not silently clipped.
    assert record["mean_main_rank"] == 43.5


def test_no_lookahead_special_exclusion_and_unpassed_not_runnable():
    draws = fixtures(24); masks = gates.common.main_masks(draws)
    original = gates.run_paths(masks, gates.MODELS, True)
    changed = masks.copy(); changed[0, 21] = False; changed[0, 21, :6] = True
    alternate = gates.run_paths(changed, gates.MODELS, True)
    for model in gates.MODELS:
        a = original["records"][model][1]; b = alternate["records"][model][1]
        assert a["tickets"] == b["tickets"]
    changed_special = [replace(d, special=next(n for n in range(49, 0, -1) if n not in d.main)) for d in draws]
    assert np.array_equal(gates.common.main_masks(changed_special), masks)
    with pytest.raises(ValueError, match="passed"): gates.run_paths(masks, ())


def test_borda_all_ten_equal_weight_and_seeded_aggregate_ties():
    components = {}
    for i, model in enumerate(meta.COMPONENTS):
        ranks = list(range(1, 50)) if i < 5 else list(range(49, 0, -1))
        components[model] = {"ranks": ranks}
    output = meta.aggregate_ranks(components)
    assert output["rank_sum_keys"] == [250] * 49
    expected = list(range(1, 50)); random.Random(20261029).shuffle(expected)
    assert output["order"] == expected
    assert output["tickets"] == [expected[i:i + 6] for i in range(0, 48, 6)]
    with pytest.raises(ValueError): meta.aggregate_ranks(dict(list(components.items())[:-1]))


def test_meta_forward_components_and_weekday_formula_use_only_past():
    history = fixtures(24); target = '26/071'; target_date = history[-1].day + timedelta(days=1)
    output = meta.predict(history, target, target_date)
    assert list(output["components"]) == list(meta.COMPONENTS)
    assert output["through"] == history[-1].issue and output["shadow_only"]
    for record in output["components"].values(): assert sorted(record["ranks"]) == list(range(1, 50))
    same_day = [d for d in history if d.day.weekday() == target_date.weekday()]
    for j in range(1, 50):
        b = (sum(j in d.main for d in history) + 20 * 6 / 49) / (len(history) + 20)
        expected = round((sum(j in d.main for d in same_day) + 20 * b) / (len(same_day) + 20) - b, 12)
        assert float(output["components"]["SH-WDAY20-v1"]["scores"][j - 1]) == expected
    changed = [replace(d, special=next(n for n in range(49, 0, -1) if n not in d.main)) for d in history]
    assert meta.predict(changed, target, target_date) == output
    assert output["historical_screening_performed"] is False


def test_component_rng_continues_existing_stream_without_old_predictions():
    rng = random.Random(20261029)
    for _ in range(4):
        x = list(range(1, 50)); rng.shuffle(x)
    expected = list(range(1, 50)); rng.shuffle(expected)
    actual = list(range(1, 50)); meta.seeded_component_rng(24).shuffle(actual)
    assert actual == expected


def test_gate_and_forward_records_are_not_same_window_attempts(tmp_path):
    p = tmp_path / 'attempts.csv'
    p.write_text('attempt_id\nSH-EXISTING-v1\nGATE-SH-DISPREG-v1\nGATE-SH-COMPREV-v1\nFORWARD-SH-META-BORDA-v1\n')
    assert gates.common.attempt_budget(p)["used"] == 1


def test_locks_match_code_and_meta_dependencies():
    lock, digest = gates.verify_lock()
    assert lock["implementation_sha256"] == hashlib.sha256(Path(gates.__file__).read_bytes()).hexdigest()
    assert len(digest) == 64
    lock, digest = meta.verify_lock()
    assert lock["specification"]["historical_screening"] is False
    assert len(digest) == 64


def test_meta_cli_serializes_prediction_and_checksum_before_rejecting_overwrite(tmp_path, monkeypatch, capsys):
    history = fixtures(24)
    protocol_hash = 'a' * 64
    monkeypatch.setattr(meta, 'ROOT', tmp_path)
    monkeypatch.setattr(meta, 'verify_lock', lambda: ({'file_sha256': {'prereg/round3.yaml': protocol_hash}}, 'b' * 64))
    monkeypatch.setattr(meta.r2, 'load_training', lambda: history)
    monkeypatch.setattr(meta, 'predict', lambda *args: {'model': 'UNIT-TEST-META', 'target': '26/116', 'tickets': [[1,2,3,4,5,6]]})
    monkeypatch.setattr(meta.subprocess, 'check_output', lambda *args, **kwargs: 'unit-test-commit\n')
    monkeypatch.setattr(sys, 'argv', ['marksix_meta_borda.py'])
    meta.main()
    files = list((tmp_path / 'forward/meta-borda').glob('26-116.prediction.*.json'))
    assert len(files) == 1
    payload = json.loads(files[0].read_bytes())
    audit = payload.pop('audit')
    assert hashlib.sha256(meta.canonical_json(payload).encode()).hexdigest() == audit['deterministic_payload_sha256']
    assert hashlib.sha256(files[0].read_bytes()).hexdigest() == Path(str(files[0])+'.sha256').read_text().split()[0]
    with pytest.raises(SystemExit) as error:
        meta.main()
    assert error.value.code == 2
