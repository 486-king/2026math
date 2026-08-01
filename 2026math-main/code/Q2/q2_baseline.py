"""Constructive B baseline based on individually complete smoke intervals."""

from __future__ import annotations

from typing import Any

from q2_common import PARAMS, SmokePlan
from q2_reachability import enumerate_relative_headings


def merge_intervals(intervals: list[list[float]], tolerance: float = 1e-12) -> dict[str, Any]:
    if not intervals:
        return {
            "union": [],
            "gap_count": 0,
            "longest_continuous_component_s": 0.0,
        }
    ordered = sorted(([float(a), float(b)] for a, b in intervals), key=lambda row: row[0])
    merged = [ordered[0]]
    gaps = []
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + tolerance:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            gaps.append([merged[-1][1], start])
            merged.append([start, end])
    return {
        "union": merged,
        "gaps": gaps,
        "gap_count": len(gaps),
        "longest_continuous_component_s": max(end - start for start, end in merged),
    }

def construct_baseline(bomb_count: int) -> dict[str, Any]:
    if bomb_count not in (1, 2, 3):
        raise ValueError("The B baseline supports one to three bombs.")
    segment = PARAMS.single_smoke_max_duration_s
    plans: list[SmokePlan] = []
    intervals: list[list[float]] = []
    records: list[dict[str, Any]] = []
    for index in range(bomb_count):
        start = index * segment
        end = (index + 1) * segment
        midpoint = 0.5 * (start + end)
        center = PARAMS.ship_speed_mps * midpoint
        smoke = SmokePlan.from_burst(
            smoke_id=f"B{bomb_count}_{index + 1}",
            center_m=center,
            t_b_s=start,
        )
        plans.append(smoke)
        intervals.append([start, end])
        records.append(
            {
                **smoke.as_event_record(),
                "independent_full_coverage_interval_s": [start, end],
                "interval_duration_s": end - start,
                "next_interval_contact_margin_s": 0.0 if index < bomb_count - 1 else None,
            }
        )
    union = merge_intervals(intervals)
    reachability = enumerate_relative_headings(plans)
    return {
        "scheme_id": f"Q2_B_{bomb_count}_bomb_constructive_baseline",
        "method": "B_independent_single_smoke_interval_continuation",
        "bomb_count": bomb_count,
        "smokes": records,
        "coverage_intervals_s": intervals,
        "continuation_times_s": [interval[1] for interval in intervals[:-1]],
        "robustness_margin_s": 0.0,
        "zero_margin_contact": True,
        "time_interval_union": union,
        "gap_count": union["gap_count"],
        "longest_continuous_component_s": union["longest_continuous_component_s"],
        "relative_reachability": reachability,
        "result_strength": "conservative_constructive_baseline",
        "global_optimality_status": "not_claimed",
    }


def baseline_frontier() -> dict[str, Any]:
    plans = [construct_baseline(count) for count in (1, 2, 3)]
    return {
        "method": "B_conservative_constructive_baseline",
        "plans": plans,
        "capacities_s": {
            str(plan["bomb_count"]): plan["longest_continuous_component_s"]
            for plan in plans
        },
    }
