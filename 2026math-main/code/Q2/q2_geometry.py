"""Exact fixed-time collinear union geometry and independent area diagnostics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from typing import Any, Sequence

from q2_common import (
    PARAMS,
    Q2Parameters,
    SmokePlan,
    ship_center_m,
    smoke_radius,
    smoke_radius_derivative,
)


@dataclass(frozen=True)
class FixedTimeSectionResult:
    minimising_xi_m: float
    minimum_squared_section_margin_m2: float
    active_smoke_indices: tuple[int, ...]
    candidate_count: int
    pairwise_intersections: tuple[dict[str, Any], ...]
    numerical_tolerance: float
    valid_smoke_count: int

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["active_smoke_indices"] = list(self.active_smoke_indices)
        payload["pairwise_intersections"] = list(self.pairwise_intersections)
        return payload


def exact_collinear_section(
    ship_center: float,
    smoke_centers: Sequence[float],
    smoke_radii: Sequence[float],
    *,
    ship_radius: float = PARAMS.ship_radius_m,
    tolerance: float = 1e-10,
) -> FixedTimeSectionResult:
    if len(smoke_centers) != len(smoke_radii):
        raise ValueError("Smoke centers and radii must have the same length.")
    lines: list[tuple[int, float, float]] = []
    for index, (center, radius) in enumerate(zip(smoke_centers, smoke_radii)):
        radius = float(radius)
        if radius <= 0.0:
            continue
        d_value = float(ship_center) - float(center)
        intercept = radius * radius - ship_radius * ship_radius - d_value * d_value
        slope = -2.0 * d_value
        lines.append((index, intercept, slope))
    if not lines:
        return FixedTimeSectionResult(
            minimising_xi_m=0.0,
            minimum_squared_section_margin_m2=-1e300,
            active_smoke_indices=(),
            candidate_count=0,
            pairwise_intersections=(),
            numerical_tolerance=tolerance,
            valid_smoke_count=0,
        )

    candidates: list[float] = [-float(ship_radius), float(ship_radius)]
    intersections: list[dict[str, Any]] = []
    for left in range(len(lines)):
        for right in range(left + 1, len(lines)):
            i, a_i, m_i = lines[left]
            j, a_j, m_j = lines[right]
            denominator = m_i - m_j
            if abs(denominator) <= tolerance:
                intersections.append(
                    {
                        "smoke_indices": [i, j],
                        "status": "parallel_or_nearly_parallel",
                        "xi_m": None,
                    }
                )
                continue
            xi = (a_j - a_i) / denominator
            in_domain = -ship_radius - tolerance <= xi <= ship_radius + tolerance
            intersections.append(
                {
                    "smoke_indices": [i, j],
                    "status": "candidate" if in_domain else "outside_ship_section",
                    "xi_m": float(xi),
                }
            )
            if in_domain:
                candidates.append(min(float(ship_radius), max(-float(ship_radius), float(xi))))

    unique_candidates: list[float] = []
    for value in sorted(candidates):
        if not unique_candidates or abs(value - unique_candidates[-1]) > tolerance:
            unique_candidates.append(value)

    evaluations: list[tuple[float, float, tuple[int, ...]]] = []
    for xi in unique_candidates:
        line_values = [(index, intercept + slope * xi) for index, intercept, slope in lines]
        envelope = max(value for _, value in line_values)
        active = tuple(
            index
            for index, value in line_values
            if abs(value - envelope) <= max(tolerance, tolerance * abs(envelope))
        )
        evaluations.append((float(envelope), float(xi), active))
    minimum, xi_min, active = min(evaluations, key=lambda row: (row[0], row[1]))
    return FixedTimeSectionResult(
        minimising_xi_m=xi_min,
        minimum_squared_section_margin_m2=minimum,
        active_smoke_indices=active,
        candidate_count=len(unique_candidates),
        pairwise_intersections=tuple(intersections),
        numerical_tolerance=tolerance,
        valid_smoke_count=len(lines),
    )


def plan_state(
    t_s: float,
    plan: Sequence[SmokePlan],
    *,
    parameters: Q2Parameters = PARAMS,
    ship_speed_mps: float | None = None,
    max_radius_m: float | None = None,
    longitudinal_drift_mps: float = 0.0,
) -> tuple[float, list[float], list[float]]:
    speed = parameters.ship_speed_mps if ship_speed_mps is None else float(ship_speed_mps)
    ship = ship_center_m(t_s, speed)
    centers: list[float] = []
    radii: list[float] = []
    for smoke in plan:
        age = float(t_s) - smoke.t_b_s
        center = smoke.center_m
        if age > 0.0:
            center += float(longitudinal_drift_mps) * age
        centers.append(center)
        radii.append(smoke_radius(t_s, smoke.t_b_s, max_radius_m=max_radius_m))
    return ship, centers, radii


def union_margin_at_time(
    t_s: float,
    plan: Sequence[SmokePlan],
    *,
    parameters: Q2Parameters = PARAMS,
    ship_speed_mps: float | None = None,
    max_radius_m: float | None = None,
    longitudinal_drift_mps: float = 0.0,
    tolerance: float = 1e-10,
) -> FixedTimeSectionResult:
    ship, centers, radii = plan_state(
        t_s,
        plan,
        parameters=parameters,
        ship_speed_mps=ship_speed_mps,
        max_radius_m=max_radius_m,
        longitudinal_drift_mps=longitudinal_drift_mps,
    )
    return exact_collinear_section(
        ship,
        centers,
        radii,
        ship_radius=parameters.ship_radius_m,
        tolerance=tolerance,
    )


def pair_intersection_xi(
    t_s: float,
    first: SmokePlan,
    second: SmokePlan,
    *,
    ship_speed_mps: float = PARAMS.ship_speed_mps,
    max_radius_m: float = PARAMS.smoke_max_radius_m,
) -> float:
    ship = ship_speed_mps * float(t_s)
    d_1 = ship - first.center_m
    d_2 = ship - second.center_m
    r_1 = smoke_radius(t_s, first.t_b_s, max_radius_m=max_radius_m)
    r_2 = smoke_radius(t_s, second.t_b_s, max_radius_m=max_radius_m)
    a_1 = r_1 * r_1 - PARAMS.ship_radius_m**2 - d_1 * d_1
    a_2 = r_2 * r_2 - PARAMS.ship_radius_m**2 - d_2 * d_2
    denominator = -2.0 * d_1 + 2.0 * d_2
    if abs(denominator) <= 1e-14:
        raise ZeroDivisionError("Parallel section lines have no unique intersection.")
    return (a_2 - a_1) / denominator


def pair_intersection_value_and_derivative(
    t_s: float,
    first: SmokePlan,
    second: SmokePlan,
    *,
    ship_speed_mps: float = PARAMS.ship_speed_mps,
    max_radius_m: float = PARAMS.smoke_max_radius_m,
) -> tuple[float, float, float]:
    ship = ship_speed_mps * float(t_s)
    d_1 = ship - first.center_m
    d_2 = ship - second.center_m
    r_1 = smoke_radius(t_s, first.t_b_s, max_radius_m=max_radius_m)
    r_2 = smoke_radius(t_s, second.t_b_s, max_radius_m=max_radius_m)
    rp_1 = smoke_radius_derivative(t_s, first.t_b_s, max_radius_m=max_radius_m)
    rp_2 = smoke_radius_derivative(t_s, second.t_b_s, max_radius_m=max_radius_m)
    a_1 = r_1 * r_1 - PARAMS.ship_radius_m**2 - d_1 * d_1
    a_2 = r_2 * r_2 - PARAMS.ship_radius_m**2 - d_2 * d_2
    ap_1 = 2.0 * r_1 * rp_1 - 2.0 * d_1 * ship_speed_mps
    ap_2 = 2.0 * r_2 * rp_2 - 2.0 * d_2 * ship_speed_mps
    m_1 = -2.0 * d_1
    m_2 = -2.0 * d_2
    mp_value = -2.0 * ship_speed_mps
    denominator = m_1 - m_2
    xi = (a_2 - a_1) / denominator
    xi_prime = (ap_2 - ap_1) / denominator
    value = a_1 + m_1 * xi
    derivative = ap_1 + mp_value * xi + m_1 * xi_prime
    return float(xi), float(value), float(derivative)


def section_lipschitz_bound(
    start_s: float,
    end_s: float,
    plan: Sequence[SmokePlan],
    *,
    ship_speed_mps: float = PARAMS.ship_speed_mps,
    max_radius_m: float = PARAMS.smoke_max_radius_m,
    longitudinal_drift_mps: float = 0.0,
) -> float:
    if end_s < start_s:
        raise ValueError("Invalid time box.")
    bounds: list[float] = []
    for smoke in plan:
        midpoint = 0.5 * (start_s + end_s)
        if smoke_radius(midpoint, smoke.t_b_s, max_radius_m=max_radius_m) <= 0.0:
            continue
        for time in (start_s, end_s):
            age = time - smoke.t_b_s
            radius = smoke_radius(time, smoke.t_b_s, max_radius_m=max_radius_m)
            radius_prime = smoke_radius_derivative(
                time, smoke.t_b_s, max_radius_m=max_radius_m
            )
            center_velocity = longitudinal_drift_mps if age > 0.0 else 0.0
            center = smoke.center_m + max(age, 0.0) * longitudinal_drift_mps
            d_value = ship_speed_mps * time - center
            d_prime = ship_speed_mps - center_velocity
            for xi in (-PARAMS.ship_radius_m, PARAMS.ship_radius_m):
                derivative = 2.0 * radius * radius_prime - 2.0 * d_prime * (
                    d_value + xi
                )
                bounds.append(abs(derivative))
    return max(bounds, default=0.0)


def _area_breakpoints(
    t_s: float,
    plan: Sequence[SmokePlan],
    ship_center: float,
    centers: Sequence[float],
    radii: Sequence[float],
) -> list[float]:
    radius = PARAMS.ship_radius_m
    points = [-radius, radius]
    for center, smoke_radius_value in zip(centers, radii):
        relative = center - ship_center
        for point in (relative - smoke_radius_value, relative + smoke_radius_value):
            if -radius < point < radius:
                points.append(point)
    valid = [
        (center, smoke_radius_value)
        for center, smoke_radius_value in zip(centers, radii)
        if smoke_radius_value > 0.0
    ]
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            c_i, r_i = valid[i]
            c_j, r_j = valid[j]
            d_i = ship_center - c_i
            d_j = ship_center - c_j
            denominator = -2.0 * d_i + 2.0 * d_j
            if abs(denominator) <= 1e-14:
                continue
            a_i = r_i * r_i - d_i * d_i
            a_j = r_j * r_j - d_j * d_j
            xi = (a_j - a_i) / denominator
            if -radius < xi < radius:
                points.append(xi)
    return sorted(set(float(value) for value in points))


def high_precision_uncovered_area(
    t_s: float,
    plan: Sequence[SmokePlan],
    *,
    precision_digits: int = 60,
    repeat_precision_digits: int = 120,
    area_tolerance_m2: float = 1e-30,
) -> dict[str, Any]:
    ship, centers, radii = plan_state(t_s, plan)
    fixed_time_section = exact_collinear_section(
        ship,
        centers,
        radii,
    )
    exact_fixed_time_coverage = (
        fixed_time_section.minimum_squared_section_margin_m2 >= 0.0
    )
    breakpoints = _area_breakpoints(t_s, plan, ship, centers, radii)

    def integrate(digits: int) -> tuple[Decimal, Decimal]:
        with localcontext() as context:
            context.prec = digits
            zero = Decimal(0)
            two = Decimal(2)
            four = Decimal(4)
            six = Decimal(6)
            fifteen = Decimal(15)
            ship_decimal = Decimal(str(ship))
            rs_decimal = Decimal(str(PARAMS.ship_radius_m))
            centers_decimal = [Decimal(str(value)) for value in centers]
            radii_decimal = [Decimal(str(value)) for value in radii]
            # Arithmetic uses 50+ digits, while the quadrature tolerance is tied
            # to the formal 1e-8 m^2 area decision threshold rather than to every
            # available Decimal digit.
            integration_tolerance = Decimal("1e-12")

            def uncovered_length(xi: Decimal) -> Decimal:
                ship_height_sq = max(zero, rs_decimal * rs_decimal - xi * xi)
                ship_height = ship_height_sq.sqrt()
                smoke_height = zero
                x_absolute = ship_decimal + xi
                for center_decimal, radius_decimal in zip(
                    centers_decimal, radii_decimal
                ):
                    height_sq = radius_decimal * radius_decimal - (
                        x_absolute - center_decimal
                    ) ** 2
                    if height_sq > 0:
                        smoke_height = max(smoke_height, height_sq.sqrt())
                return two * max(zero, ship_height - smoke_height)

            def simpson(
                left: Decimal,
                right: Decimal,
                f_left: Decimal,
                f_mid: Decimal,
                f_right: Decimal,
            ) -> Decimal:
                return (right - left) * (f_left + four * f_mid + f_right) / six

            def adaptive(
                left: Decimal,
                right: Decimal,
                f_left: Decimal,
                f_mid: Decimal,
                f_right: Decimal,
                whole: Decimal,
                tolerance: Decimal,
                depth: int,
            ) -> tuple[Decimal, Decimal]:
                midpoint = (left + right) / two
                left_midpoint = (left + midpoint) / two
                right_midpoint = (midpoint + right) / two
                f_left_midpoint = uncovered_length(left_midpoint)
                f_right_midpoint = uncovered_length(right_midpoint)
                left_area = simpson(
                    left, midpoint, f_left, f_left_midpoint, f_mid
                )
                right_area = simpson(
                    midpoint, right, f_mid, f_right_midpoint, f_right
                )
                refined = left_area + right_area
                if depth <= 0 or abs(refined - whole) <= fifteen * tolerance:
                    correction = (refined - whole) / fifteen
                    return refined + correction, abs(correction)
                left_result, left_error = adaptive(
                    left,
                    midpoint,
                    f_left,
                    f_left_midpoint,
                    f_mid,
                    left_area,
                    tolerance / two,
                    depth - 1,
                )
                right_result, right_error = adaptive(
                    midpoint,
                    right,
                    f_mid,
                    f_right_midpoint,
                    f_right,
                    right_area,
                    tolerance / two,
                    depth - 1,
                )
                return left_result + right_result, left_error + right_error

            total = zero
            total_error_bound = zero
            for left_float, right_float in zip(breakpoints[:-1], breakpoints[1:]):
                if right_float <= left_float:
                    continue
                left = Decimal(str(left_float))
                right = Decimal(str(right_float))
                midpoint = (left + right) / two
                f_left = uncovered_length(left)
                f_mid = uncovered_length(midpoint)
                f_right = uncovered_length(right)
                whole = simpson(left, right, f_left, f_mid, f_right)
                estimate, error_bound = adaptive(
                    left,
                    right,
                    f_left,
                    f_mid,
                    f_right,
                    whole,
                    integration_tolerance,
                    24,
                )
                total += estimate
                total_error_bound += error_bound
            return +total, +total_error_bound

    first, first_error_bound = integrate(precision_digits)
    second, second_error_bound = integrate(repeat_precision_digits)
    if first < 0 or second < 0:
        raise ArithmeticError(
            "The nonnegative uncovered-area integrand produced a negative result."
        )
    difference = abs(second - first)
    numerical_upper = second + second_error_bound + difference
    conservative_upper = (
        Decimal(0)
        if exact_fixed_time_coverage
        else numerical_upper
    )
    no_area_detected = (
        exact_fixed_time_coverage
        or conservative_upper <= Decimal(str(area_tolerance_m2))
    )
    return {
        "time_s": float(t_s),
        "raw_uncovered_area_m2": float(second),
        "conservative_area_upper_bound_m2": float(conservative_upper),
        "integration_precision_digits": precision_digits,
        "repeated_precision_digits": repeat_precision_digits,
        "precision_doubling_difference_m2": float(difference),
        "convergence_difference_m2": float(difference),
        "initial_quadrature_error_bound_m2": float(first_error_bound),
        "repeated_quadrature_error_bound_m2": float(second_error_bound),
        "area_tolerance_m2": area_tolerance_m2,
        "clipping_applied": False,
        "negative_value_clamped": False,
        "geometric_positive_part_applied": True,
        "fixed_time_exact_section_margin_m2": (
            fixed_time_section.minimum_squared_section_margin_m2
        ),
        "fixed_time_exact_coverage_proved": exact_fixed_time_coverage,
        "breakpoint_count": len(breakpoints),
        "verified_no_uncovered_area": no_area_detected,
        "proof_or_diagnostic_status": (
            "exact_zero_from_fixed_time_analytic_section"
            if exact_fixed_time_coverage
            else (
                "no_uncovered_area_detected_above_tolerance"
                if no_area_detected
                else "positive_uncovered_area_detected"
            )
        ),
        "upper_bound_construction": (
            "exact_zero_from_necessary_and_sufficient_fixed_time_"
            "collinear_section"
            if exact_fixed_time_coverage
            else (
                "raw_repeated_precision_area_plus_repeated_adaptive_simpson_"
                "error_estimate_plus_precision_doubling_difference"
            )
        ),
        "method": "decimal_adaptive_simpson_vertical_cross_section_integration",
    }


def assert_geometry_identity_example() -> None:
    result = exact_collinear_section(
        ship_center=0.0,
        smoke_centers=[0.0],
        smoke_radii=[PARAMS.smoke_max_radius_m],
    )
    expected = PARAMS.smoke_max_radius_m**2 - PARAMS.ship_radius_m**2
    if not math.isclose(
        result.minimum_squared_section_margin_m2,
        expected,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise RuntimeError("Fixed-time collinear section identity failed.")
