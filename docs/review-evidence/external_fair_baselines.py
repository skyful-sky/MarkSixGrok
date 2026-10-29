"""Exact uniform-subset coverage arithmetic; no historical data or model execution."""

from collections import Counter, defaultdict
from fractions import Fraction
from itertools import combinations
from math import comb
import json


def rank_template(pool, size=6, count=8):
    if pool < size:
        raise ValueError("pool must contain a full ticket")
    return [tuple((size * b + j) % pool + 1 for j in range(size))
            for b in range(count)]


def coverage_count(pool, draw_size, tickets, threshold=3):
    """Count uniform draw subsets with at least one ticket meeting threshold.

    Partition balls by their ticket-membership vector. For each group choose k
    balls with multiplicity C(group_size,k). Track total selected and each
    ticket's hit count, discarding states already successful. The retained
    degree-draw_size coefficient counts failures exactly (integer arithmetic).
    """
    if not 0 <= draw_size <= pool or threshold <= 0:
        raise ValueError("invalid draw size or threshold")
    ticket_sets = [set(ticket) for ticket in tickets]
    if any(len(ticket) != len(set(ticket)) for ticket in tickets):
        raise ValueError("duplicate ball inside ticket")
    if any(not ticket <= set(range(1, pool + 1)) for ticket in ticket_sets):
        raise ValueError("out-of-range ball")
    groups = Counter(tuple(int(n in ticket) for ticket in ticket_sets)
                     for n in range(1, pool + 1))
    states = {(0, (0,) * len(tickets)): 1}
    for membership, group_size in sorted(groups.items()):
        next_states = defaultdict(int)
        for (selected, hits), ways in states.items():
            for k in range(min(group_size, draw_size - selected) + 1):
                updated = tuple(h + k * member for h, member in zip(hits, membership))
                if all(h < threshold for h in updated):
                    next_states[selected + k, updated] += ways * comb(group_size, k)
        states = next_states
    failures = sum(ways for (selected, _), ways in states.items() if selected == draw_size)
    total = comb(pool, draw_size)
    return total - failures, total


def exhaustive_count(pool, draw_size, tickets, threshold=3):
    """Independent enumeration for small arithmetic checks; not historical scoring."""
    ticket_sets = [set(ticket) for ticket in tickets]
    return sum(any(len(set(draw) & ticket) >= threshold for ticket in ticket_sets)
               for draw in combinations(range(1, pool + 1), draw_size))


def disjoint_six_formula(pool, count=8):
    """Inclusion-exclusion: a six-ball draw can hit at most two disjoint tickets."""
    if pool < 6 * count:
        raise ValueError("tickets are not disjoint")
    one = sum(comb(6, h) * comb(pool - 6, 6 - h) for h in range(3, 7))
    return count * one - comb(count, 2) * comb(6, 3) ** 2


def exact_binomial_tail(n, k, probability):
    """Exact rational upper tail; no estimated or observed success count is input."""
    a, b = probability.numerator, probability.denominator
    numerator = sum(comb(n, h) * a ** h * (b - a) ** (n - h)
                    for h in range(k, n + 1))
    return Fraction(numerator, b ** n)


def first_passing_count(n, probability, alpha):
    for k in range(n + 1):
        if exact_binomial_tail(n, k, probability) <= alpha:
            return k
    raise AssertionError("no threshold found")


def baseline_rows():
    rows = []
    for game, pool in [("UK historical 6/49", 49), ("Japan Loto6", 43),
                       ("Korea Lotto6/45", 45), ("China SSQ red-only", 33)]:
        tickets = rank_template(pool)
        assert len({tuple(sorted(t)) for t in tickets}) == 8
        successes, total = coverage_count(pool, 6, tickets)
        probability = Fraction(successes, total)
        if pool == 49:
            assert successes == disjoint_six_formula(pool)
            assert probability == Fraction(12344, 83237)
        k = first_passing_count(500, probability, Fraction(1, 160))
        rows.append({"game": game, "pool": pool, "draw_size": 6,
                     "tickets_as_rank_positions": tickets,
                     "successes": successes, "total_subsets": total,
                     "probability_fraction": str(probability),
                     "probability": float(probability),
                     "first_submission_alpha_per_lottery": "1/160",
                     "first_submission_min_successes_500_binomial_only": k,
                     "tail_at_k": float(exact_binomial_tail(500, k, probability)),
                     "tail_at_k_minus_1": float(exact_binomial_tail(500, k - 1, probability))})
    return rows


if __name__ == "__main__":
    print(json.dumps({"purpose": "exact fair-configuration arithmetic only",
                      "historical_data_read": False, "candidate_runs": 0,
                      "hong_kong_attempts_used": 14, "new_ids": 0,
                      "method": "integer membership-vector generating-function DP",
                      "games": baseline_rows()}, ensure_ascii=False, sort_keys=True, indent=2))
