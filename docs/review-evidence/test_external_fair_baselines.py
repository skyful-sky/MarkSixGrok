"""Independent exact arithmetic checks; no candidate backtests."""

from fractions import Fraction
from itertools import combinations
from pathlib import Path
import importlib.util

import pytest

spec = importlib.util.spec_from_file_location(
    "external_fair_baselines", Path(__file__).with_name("external_fair_baselines.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("pool,draw_size,tickets", [
    (9, 4, [(1, 2, 3, 4), (3, 4, 5, 6), (1, 7, 8, 9)]),
    (10, 6, [(1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 6)]),
    (11, 6, [(1, 2, 3, 4, 5, 6), (6, 7, 8, 9, 10, 11)]),
])
def test_grouped_count_matches_independent_exhaustive(pool, draw_size, tickets):
    success, total = module.coverage_count(pool, draw_size, tickets)
    assert total == len(list(combinations(range(1, pool + 1), draw_size)))
    assert success == module.exhaustive_count(pool, draw_size, tickets)


def test_49_matches_independent_disjoint_inclusion_exclusion():
    success, total = module.coverage_count(49, 6, module.rank_template(49))
    assert success == module.disjoint_six_formula(49)
    assert Fraction(success, total) == Fraction(12344, 83237)


def test_relabelling_does_not_change_fair_baseline():
    tickets = module.rank_template(33)
    reflected = [tuple(34 - n for n in ticket) for ticket in reversed(tickets)]
    assert module.coverage_count(33, 6, tickets) == module.coverage_count(33, 6, reflected)


def test_33_matches_complete_independent_enumeration():
    tickets = module.rank_template(33)
    success, total = module.coverage_count(33, 6, tickets)
    assert total == 1107568
    assert success == module.exhaustive_count(33, 6, tickets) == 436186


def test_exact_binomial_small_case():
    assert module.exact_binomial_tail(3, 2, Fraction(1, 2)) == Fraction(1, 2)
    assert module.first_passing_count(3, Fraction(1, 2), Fraction(1, 8)) == 3
