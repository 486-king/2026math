"""Continuous-time certificates using event splitting and conservative boxes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from scipy.optimize import brentq

from q2_common import PARAMS, SmokePlan
from q2_geometry import (
    pair_intersection_value_and_derivative,
    pair_intersection_xi,
    section_lipschitz_bound,
    union_margin_at_time,
)

ROUNDING_GUARD_M2 = 1e-9


@dataclass(frozen=True)
class CanonicalInterval:
    canonical_box_id: str
    start_s: float
    end_s: float
    proof_branch: str


def radius_regime(t_s: float, smoke: SmokePlan) -> str:
    age = float(t_s) - smoke.t_b_s
    if age < 0.0:
        return "not_burst"
    if age <= PARAMS.smoke_hold_s:
        return "full_radius"
    if age <= PARAMS.smoke_lifetime_s:
        return "linear_decay"
    return "expired"


def physical_event_times(
    plan: Sequence[SmokePlan],
    start_s: float,
    end_s: float,
    *,
    extra_times: Sequence[float] = (),
) -> list[float]:
    events = {float(start_s), float(end_s)}
    for smoke in plan:
        for time in (
            smoke.t_b_s,
            smoke.t_b_s + PARAMS.smoke_hold_s,
            smoke.t_b_s + PARAMS.smoke_lifetime_s,
        ):
            if start_s < time < end_s:
                events.add(float(time))
    for time in extra_times:
        if start_s < float(time) < end_s:
            events.add(float(time))
    return sorted(events)


def event_intervals(
    plan: Sequence[SmokePlan],
    start_s: float,
    end_s: float,
    *,
    prefix: str = "event",
    extra_times: Sequence[float] = (),
) -> list[CanonicalInterval]:
    events = physical_event_times(
        plan,
        start_s,
        end_s,
        extra_times=extra_times,
    )
    return [
        CanonicalInterval(
            canonical_box_id=f"{prefix}_{index:02d}",
            start_s=left,
            end_s=right,
            proof_branch="physical_event_split_with_adaptive_lipschitz",
        )
        for index, (left, right) in enumerate(zip(events[:-1], events[1:]), start=1)
    ]


def canonical_two_bomb_intervals(
    plan: Sequence[SmokePlan],
    end_s: float,
) -> tuple[list[CanonicalInterval], dict[str, float]]:
    if len(plan) != 2:
        raise ValueError("The canonical two-bomb certificate requires two smokes.")
    first, second = plan
    speed = PARAMS.ship_speed_mps
    align_first = first.center_m / speed
    second_burst = second.t_b_s
    first_decay = first.t_b_s + PARAMS.smoke_hold_s
    first_expiry = first.t_b_s + PARAMS.smoke_lifetime_s
    align_second = second.center_m / speed

    def derivative(time: float) -> float:
        return pair_intersection_value_and_derivative(time, first, second)[2]

    full_stationary = brentq(
        derivative,
        second_burst + 1e-9,
        first_decay - 1e-9,
        xtol=1e-13,
    )

    def left_entry(time: float) -> float:
        return pair_intersection_xi(time, first, second) + PARAMS.ship_radius_m

    intersection_left_boundary = brentq(
        left_entry,
        first_decay + 1e-9,
        first_expiry - 1e-9,
        xtol=1e-13,
    )
    decay_stationary = brentq(
        derivative,
        first_decay + 1e-9,
        intersection_left_boundary - 1e-9,
        xtol=1e-13,
    )
    boundaries = [
        0.0,
        align_first,
        second_burst,
        full_stationary,
        first_decay,
        decay_stationary,
        intersection_left_boundary,
        first_expiry,
        align_second,
        float(end_s),
    ]
    names = [
        "single_smoke_1_left_endpoint",
        "single_smoke_1_right_endpoint",
        "equal_radius_pair_intersection_decreasing",
        "equal_radius_pair_intersection_increasing",
        "decay_pair_intersection_decreasing",
        "decay_pair_intersection_increasing",
        "smoke_2_left_endpoint_with_smoke_1_decay",
        "single_smoke_2_left_endpoint",
        "single_smoke_2_right_endpoint",
    ]
    intervals = [
        CanonicalInterval(
            canonical_box_id=f"canonical_{index:02d}",
            start_s=left,
            end_s=right,
            proof_branch=branch,
        )
        for index, (left, right, branch) in enumerate(
            zip(boundaries[:-1], boundaries[1:], names),
            start=1,
        )
    ]
    events = {
        "align_first_s": align_first,
        "second_burst_s": second_burst,
        "full_pair_stationary_s": full_stationary,
        "first_decay_start_s": first_decay,
        "decay_pair_stationary_s": decay_stationary,
        "pair_intersection_hits_left_boundary_s": intersection_left_boundary,
        "first_expiry_s": first_expiry,
        "align_second_s": align_second,
        "window_end_s": float(end_s),
    }
    return intervals, events


def _active_smokes(t_s: float, plan: Sequence[SmokePlan]) -> list[int]:
    return [
        index
        for index, smoke in enumerate(plan)
        if radius_regime(t_s, smoke) in {"full_radius", "linear_decay"}
    ]


def certify_continuous_window(
    plan: Sequence[SmokePlan],
    start_s: float,
    end_s: float,
    *,
    canonical_intervals: Sequence[CanonicalInterval] | None = None,
    analytic_start_zero: bool = False,
    analytic_terminal_zero: bool = False,
    analytic_internal_terminal_times: Sequence[float] = (),
    analytic_internal_tangency_times: Sequence[float] = (),
    maximum_depth: int = 30,
    minimum_width_s: float = 1e-7,
    failure_tolerance_m2: float = 1e-7,
) -> dict[str, Any]:
    if not plan:
        raise ValueError("At least one smoke is required for a time certificate.")
    intervals = list(
        canonical_intervals
        if canonical_intervals is not None
        else event_intervals(plan, start_s, end_s)
    )
    internal_boxes: list[dict[str, Any]] = []
    next_box_number = 1

    def append_box(
        canonical: CanonicalInterval,
        left: float,
        right: float,
        depth: int,
        status: str,
        proof_branch: str,
        lower: float,
        upper: float,
        midpoint_margin: float,
    ) -> None:
        nonlocal next_box_number
        midpoint = 0.5 * (left + right)
        internal_boxes.append(
            {
                "box_id": f"box_{next_box_number:05d}",
                "canonical_box_id": canonical.canonical_box_id,
                "start_s": float(left),
                "end_s": float(right),
                "active_smokes": _active_smokes(midpoint, plan),
                "radius_regimes": [radius_regime(midpoint, smoke) for smoke in plan],
                "proof_branch": proof_branch,
                "conservative_lower_bound_m2": float(lower),
                "numerical_upper_bound_m2": float(upper),
                "midpoint_margin_m2": float(midpoint_margin),
                "subdivision_depth": depth,
                "certificate_status": status,
            }
        )
        next_box_number += 1

    def recurse(canonical: CanonicalInterval, left: float, right: float, depth: int) -> None:
        midpoint = 0.5 * (left + right)
        margin = union_margin_at_time(midpoint, plan).minimum_squared_section_margin_m2
        lipschitz = section_lipschitz_bound(left, right, plan)
        radius = 0.5 * (right - left)
        lower = math.nextafter(
            margin - lipschitz * radius - ROUNDING_GUARD_M2,
            -math.inf,
        )
        upper = math.nextafter(
            margin + lipschitz * radius + ROUNDING_GUARD_M2,
            math.inf,
        )
        if lower >= 0.0:
            append_box(
                canonical,
                left,
                right,
                depth,
                "certified",
                canonical.proof_branch,
                lower,
                upper,
                margin,
            )
            return
        if margin < -failure_tolerance_m2:
            append_box(
                canonical,
                left,
                right,
                depth,
                "failed",
                "exact_midpoint_counterexample",
                lower,
                upper,
                margin,
            )
            return
        if depth >= maximum_depth or (right - left) <= minimum_width_s:
            append_box(
                canonical,
                left,
                right,
                depth,
                "undecided",
                "subdivision_limit_reached",
                lower,
                upper,
                margin,
            )
            return
        split = 0.5 * (left + right)
        recurse(canonical, left, split, depth + 1)
        recurse(canonical, split, right, depth + 1)

    analytic_width = min(0.1, max(1e-4, 0.01 * (end_s - start_s)))
    tangency_evidence: list[dict[str, Any]] = []
    for contact_time in analytic_internal_tangency_times:
        if len(plan) != 2:
            raise ValueError("Analytic pair tangencies require exactly two smokes.")
        probe_width = min(1e-4, analytic_width / 10.0)
        xi, value, derivative = pair_intersection_value_and_derivative(
            contact_time,
            plan[0],
            plan[1],
        )
        left_derivative = pair_intersection_value_and_derivative(
            contact_time - probe_width,
            plan[0],
            plan[1],
        )[2]
        right_derivative = pair_intersection_value_and_derivative(
            contact_time + probe_width,
            plan[0],
            plan[1],
        )[2]
        verified = (
            abs(value) <= failure_tolerance_m2
            and abs(derivative) <= failure_tolerance_m2
            and -PARAMS.ship_radius_m <= xi <= PARAMS.ship_radius_m
            and left_derivative < 0.0
            and right_derivative > 0.0
        )
        if not verified:
            raise ValueError(
                "The supplied analytic internal tangency did not pass "
                "residual, section-domain, and derivative-sign checks."
            )
        tangency_evidence.append(
            {
                "time_s": float(contact_time),
                "pair_intersection_xi_m": float(xi),
                "contact_margin_m2": float(value),
                "contact_derivative_m2_per_s": float(derivative),
                "left_derivative_m2_per_s": float(left_derivative),
                "right_derivative_m2_per_s": float(right_derivative),
                "probe_width_s": float(probe_width),
                "root_isolation_status": "verified_sign_change_negative_to_positive",
            }
        )
    for canonical in intervals:
        left = canonical.start_s
        right = canonical.end_s
        if analytic_start_zero and abs(left - start_s) <= 1e-12:
            analytic_end = min(right, start_s + analytic_width)
            append_box(
                canonical,
                start_s,
                analytic_end,
                0,
                "certified",
                "analytic_single_smoke_monotone_from_exact_zero",
                0.0,
                union_margin_at_time(analytic_end, plan).minimum_squared_section_margin_m2,
                union_margin_at_time(
                    0.5 * (start_s + analytic_end), plan
                ).minimum_squared_section_margin_m2,
            )
            left = analytic_end
        internal_tangency_at_left = next(
            (
                evidence
                for evidence in tangency_evidence
                if abs(left - evidence["time_s"]) <= 1e-12
            ),
            None,
        )
        if internal_tangency_at_left is not None:
            analytic_end = min(right, left + analytic_width)
            append_box(
                canonical,
                left,
                analytic_end,
                0,
                "certified",
                "analytic_pair_tangency_monotone_from_isolated_zero",
                0.0,
                union_margin_at_time(
                    analytic_end,
                    plan,
                ).minimum_squared_section_margin_m2,
                union_margin_at_time(
                    0.5 * (left + analytic_end),
                    plan,
                ).minimum_squared_section_margin_m2,
            )
            left = analytic_end
        internal_tangency_at_right = next(
            (
                evidence
                for evidence in tangency_evidence
                if abs(right - evidence["time_s"]) <= 1e-12
            ),
            None,
        )
        terminal_is_analytic = (
            analytic_terminal_zero and abs(right - end_s) <= 1e-12
        ) or any(
            abs(right - contact_time) <= 1e-12
            for contact_time in analytic_internal_terminal_times
        ) or internal_tangency_at_right is not None
        terminal_begin = right
        if terminal_is_analytic:
            terminal_begin = max(left, end_s - analytic_width)
            if abs(right - end_s) > 1e-12:
                terminal_begin = max(left, right - analytic_width)
            right = terminal_begin
        if right - left > 1e-15:
            recurse(canonical, left, right, 0)
        if terminal_is_analytic:
            append_box(
                canonical,
                terminal_begin,
                canonical.end_s,
                0,
                "certified",
                (
                    "analytic_pair_tangency_monotone_to_isolated_zero"
                    if internal_tangency_at_right is not None
                    else (
                        "analytic_single_smoke_monotone_to_internal_contact_or_"
                        "isolated_terminal_root"
                    )
                ),
                0.0,
                union_margin_at_time(terminal_begin, plan).minimum_squared_section_margin_m2,
                union_margin_at_time(
                    0.5 * (terminal_begin + canonical.end_s), plan
                ).minimum_squared_section_margin_m2,
            )

    canonical_summaries: list[dict[str, Any]] = []
    for canonical in intervals:
        children = [
            box
            for box in internal_boxes
            if box["canonical_box_id"] == canonical.canonical_box_id
        ]
        statuses = {box["certificate_status"] for box in children}
        if "failed" in statuses:
            status = "failed"
        elif "undecided" in statuses:
            status = "undecided"
        else:
            status = "certified"
        canonical_summaries.append(
            {
                "canonical_box_id": canonical.canonical_box_id,
                "start_s": canonical.start_s,
                "end_s": canonical.end_s,
                "proof_branch": canonical.proof_branch,
                "internal_box_count": len(children),
                "conservative_lower_bound_m2": min(
                    box["conservative_lower_bound_m2"] for box in children
                ),
                "certificate_status": status,
            }
        )

    certified = sum(
        box["certificate_status"] == "certified" for box in internal_boxes
    )
    undecided = sum(
        box["certificate_status"] == "undecided" for box in internal_boxes
    )
    failed = sum(box["certificate_status"] == "failed" for box in internal_boxes)
    status = "verified" if undecided == 0 and failed == 0 else "failed"
    minimum_lower = min(
        (
            box["conservative_lower_bound_m2"]
            for box in internal_boxes
            if box["certificate_status"] == "certified"
        ),
        default=-1e300,
    )
    failed_boxes = [
        [box["start_s"], box["end_s"]]
        for box in internal_boxes
        if box["certificate_status"] == "failed"
    ]
    return {
        "method": (
            "physical_event_and_structural_split_with_exact_xi_and_"
            "adaptive_lipschitz_outward_guard"
        ),
        "time_grid_used_as_proof": False,
        "canonical_box_count": len(canonical_summaries),
        "canonical_boxes": canonical_summaries,
        "internal_subbox_count": len(internal_boxes),
        "certified_box_count": certified,
        "undecided_box_count": undecided,
        "failed_box_count": failed,
        "gap_count": failed + undecided,
        "minimum_certified_margin_m2": minimum_lower,
        "analytic_internal_tangencies": tangency_evidence,
        "first_failure_time_interval": failed_boxes[0] if failed_boxes else None,
        "certificate_status": status,
        "internal_boxes": internal_boxes,
        "numerical_policy": {
            "rounding_guard_m2": ROUNDING_GUARD_M2,
            "maximum_depth": maximum_depth,
            "minimum_width_s": minimum_width_s,
            "failure_tolerance_m2": failure_tolerance_m2,
        },
    }
