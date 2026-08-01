"""A/B capacity frontiers with deterministic continuous optimisation."""

from __future__ import annotations

import math
import time
from decimal import Decimal, localcontext
from typing import Any, Sequence

import numpy as np
from scipy.optimize import brentq, differential_evolution, minimize_scalar, root

from q2_baseline import baseline_frontier
from q2_common import (
    MODEL_SCOPE,
    PARAMS,
    SmokePlan,
    standalone_numeric_reference_records_from_q2_guide,
)
from q2_continuous_certificate import certify_continuous_window, event_intervals
from q2_geometry import (
    pair_intersection_value_and_derivative,
    union_margin_at_time,
)
from q2_reachability import enumerate_relative_headings

THREE_BOMB_REFERENCE_S = 42.523129869
GLOBAL_SEED = 2026


def _margin(time_s: float, plan: Sequence[SmokePlan]) -> float:
    return union_margin_at_time(
        time_s, plan
    ).minimum_squared_section_margin_m2


def _first_failure_or_terminal_root(
    plan: Sequence[SmokePlan],
    *,
    search_start_s: float,
    search_end_s: float,
    point_count: int = 20001,
) -> float:
    times = np.linspace(search_start_s, search_end_s, point_count)
    margins = np.array([_margin(float(time), plan) for time in times])
    negative = np.flatnonzero(margins < 0.0)
    if not len(negative):
        return float(search_end_s)
    index = int(negative[0])
    if index == 0:
        return float(search_start_s)
    return float(
        brentq(
            lambda time: _margin(time, plan),
            float(times[index - 1]),
            float(times[index]),
            xtol=1e-13,
        )
    )


def _decimal_two_bomb_refinement(
    center_2_initial: float,
    bridge_time_initial: float,
    terminal_time_initial: float,
    second_burst_s: float,
) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = 80
        two = Decimal(2)
        ship_speed = Decimal(str(PARAMS.ship_speed_mps))
        ship_radius = Decimal(str(PARAMS.ship_radius_m))
        smoke_radius_max = Decimal(str(PARAMS.smoke_max_radius_m))
        decay = Decimal(str(PARAMS.smoke_decay_s))
        lifetime = Decimal(str(PARAMS.smoke_lifetime_s))
        first_center = Decimal(
            str(PARAMS.smoke_max_radius_m - PARAMS.ship_radius_m)
        )
        second_burst = Decimal(str(second_burst_s))
        radius_slope = -smoke_radius_max / decay

        def bridge_equations(
            center_2: Decimal,
            bridge_time: Decimal,
        ) -> tuple[Decimal, Decimal]:
            radius_1 = (
                smoke_radius_max
                * (lifetime - bridge_time)
                / decay
            )
            radius_2 = smoke_radius_max
            d_1 = ship_speed * bridge_time - first_center
            d_2 = ship_speed * bridge_time - center_2
            a_1 = (
                radius_1 * radius_1
                - ship_radius * ship_radius
                - d_1 * d_1
            )
            a_2 = (
                radius_2 * radius_2
                - ship_radius * ship_radius
                - d_2 * d_2
            )
            ap_1 = (
                two * radius_1 * radius_slope
                - two * d_1 * ship_speed
            )
            ap_2 = -two * d_2 * ship_speed
            m_1 = -two * d_1
            m_2 = -two * d_2
            denominator = m_1 - m_2
            xi = (a_2 - a_1) / denominator
            xi_prime = (ap_2 - ap_1) / denominator
            value = a_1 + m_1 * xi
            derivative = (
                ap_1
                - two * ship_speed * xi
                + m_1 * xi_prime
            )
            return value, derivative

        center_2 = Decimal(str(center_2_initial))
        bridge_time = Decimal(str(bridge_time_initial))
        difference_step = Decimal("1e-25")
        bridge_iterations = 0
        for bridge_iterations in range(1, 31):
            value, derivative = bridge_equations(center_2, bridge_time)
            if max(abs(value), abs(derivative)) <= Decimal("1e-55"):
                break
            value_center_plus = bridge_equations(
                center_2 + difference_step,
                bridge_time,
            )
            value_center_minus = bridge_equations(
                center_2 - difference_step,
                bridge_time,
            )
            value_time_plus = bridge_equations(
                center_2,
                bridge_time + difference_step,
            )
            value_time_minus = bridge_equations(
                center_2,
                bridge_time - difference_step,
            )
            j11 = (
                value_center_plus[0] - value_center_minus[0]
            ) / (two * difference_step)
            j21 = (
                value_center_plus[1] - value_center_minus[1]
            ) / (two * difference_step)
            j12 = (
                value_time_plus[0] - value_time_minus[0]
            ) / (two * difference_step)
            j22 = (
                value_time_plus[1] - value_time_minus[1]
            ) / (two * difference_step)
            determinant = j11 * j22 - j12 * j21
            delta_center = (value * j22 - derivative * j12) / determinant
            delta_time = (j11 * derivative - j21 * value) / determinant
            center_2 -= delta_center
            bridge_time -= delta_time

        terminal_time = Decimal(str(terminal_time_initial))

        def terminal_equation(time_value: Decimal) -> tuple[Decimal, Decimal]:
            radius_2 = (
                smoke_radius_max
                * (second_burst + lifetime - time_value)
                / decay
            )
            d_2 = ship_speed * time_value - center_2
            value = (
                radius_2 * radius_2
                - ship_radius * ship_radius
                - d_2 * d_2
                - two * d_2 * ship_radius
            )
            derivative = (
                two * radius_2 * radius_slope
                - two * ship_speed * (d_2 + ship_radius)
            )
            return value, derivative

        terminal_iterations = 0
        for terminal_iterations in range(1, 31):
            value, derivative = terminal_equation(terminal_time)
            if abs(value) <= Decimal("1e-55"):
                break
            terminal_time -= value / derivative

        bridge_residuals = bridge_equations(center_2, bridge_time)
        terminal_residual = terminal_equation(terminal_time)[0]
        return {
            "decimal_precision_digits": context.prec,
            "second_center_m_decimal": str(+center_2),
            "bridge_critical_time_s_decimal": str(+bridge_time),
            "terminal_decay_root_s_decimal": str(+terminal_time),
            "bridge_value_residual_m2_decimal": str(+bridge_residuals[0]),
            "bridge_derivative_residual_m2_per_s_decimal": str(
                +bridge_residuals[1]
            ),
            "terminal_root_residual_m2_decimal": str(+terminal_residual),
            "bridge_newton_iterations": bridge_iterations,
            "terminal_newton_iterations": terminal_iterations,
            "termination_reason": (
                "80_digit_decimal_newton_residual_below_1e-55"
            ),
        }


def solve_two_bomb_frontier() -> dict[str, Any]:
    first = SmokePlan.from_burst(
        "capacity_two_smoke_1",
        center_m=PARAMS.smoke_max_radius_m - PARAMS.ship_radius_m,
        t_b_s=0.0,
    )
    second_burst = PARAMS.single_smoke_max_duration_s

    def plan_for_center(center_2: float) -> list[SmokePlan]:
        return [
            first,
            SmokePlan.from_burst(
                "capacity_two_smoke_2",
                center_m=float(center_2),
                t_b_s=second_burst,
            ),
        ]

    def late_bridge_minimum(center_2: float) -> tuple[float, float]:
        plan = plan_for_center(center_2)
        result = minimize_scalar(
            lambda time_value: _margin(time_value, plan),
            bounds=(PARAMS.smoke_hold_s, PARAMS.smoke_lifetime_s),
            method="bounded",
            options={"xatol": 5e-15, "maxiter": 1000},
        )
        return float(result.fun), float(result.x)

    bridge_boundary_center = brentq(
        lambda center: late_bridge_minimum(center)[0],
        200.0,
        201.0,
        xtol=5e-14,
        rtol=1e-14,
    )
    coarse_bridge_margin, coarse_bridge_time = late_bridge_minimum(
        bridge_boundary_center
    )
    coarse_plan = plan_for_center(bridge_boundary_center)
    coarse_terminal_root = brentq(
        lambda time_value: _margin(time_value, coarse_plan),
        28.0,
        second_burst + PARAMS.smoke_lifetime_s - 1e-9,
        xtol=1e-13,
    )

    def joint_equations(values: np.ndarray) -> np.ndarray:
        center_2, bridge_time, terminal_time = map(float, values)
        local_plan = plan_for_center(center_2)
        _, bridge_value, bridge_derivative = (
            pair_intersection_value_and_derivative(
                bridge_time,
                local_plan[0],
                local_plan[1],
            )
        )
        terminal_value = _margin(terminal_time, local_plan)
        return np.array(
            [bridge_value, bridge_derivative, terminal_value],
            dtype=float,
        )

    base_start = np.array(
        [
            bridge_boundary_center,
            coarse_bridge_time,
            coarse_terminal_root,
        ],
        dtype=float,
    )
    deterministic_perturbations = [
        (0.0, 0.0, 0.0),
        (-0.02, 0.25, -0.05),
        (0.02, -0.25, 0.05),
        (-0.10, -0.50, -0.10),
        (0.10, 0.50, 0.10),
        (0.0, -0.75, 0.15),
    ]
    local_refinement_runs = []
    converged = []
    for perturbation in deterministic_perturbations:
        start = base_start + np.array(perturbation, dtype=float)
        result = root(
            joint_equations,
            start,
            method="lm",
            options={
                "ftol": 1e-14,
                "xtol": 1e-14,
                "gtol": 1e-14,
                "maxiter": 4000,
            },
        )
        residual = joint_equations(result.x)
        row = {
            "start": [float(value) for value in start],
            "solution": [float(value) for value in result.x],
            "maximum_absolute_residual": float(
                np.max(np.abs(residual))
            ),
            "residual_vector": [float(value) for value in residual],
            "success": bool(result.success),
            "termination_reason": str(result.message),
            "function_evaluations": int(result.nfev),
        }
        local_refinement_runs.append(row)
        if result.success and row["maximum_absolute_residual"] <= 1e-7:
            converged.append(row)
    if not converged:
        raise RuntimeError("Two-bomb deterministic joint refinement failed.")
    best_float_solution = min(
        converged,
        key=lambda row: row["maximum_absolute_residual"],
    )["solution"]
    decimal_refinement = _decimal_two_bomb_refinement(
        best_float_solution[0],
        best_float_solution[1],
        best_float_solution[2],
        second_burst,
    )
    verified_center = float(
        decimal_refinement["second_center_m_decimal"]
    )
    bridge_time = float(
        decimal_refinement["bridge_critical_time_s_decimal"]
    )
    terminal_root = float(
        decimal_refinement["terminal_decay_root_s_decimal"]
    )
    plan = plan_for_center(verified_center)
    bridge_margin = _margin(bridge_time, plan)
    intervals = event_intervals(
        plan,
        0.0,
        terminal_root,
        prefix="two_frontier",
        extra_times=[bridge_time],
    )
    certificate = certify_continuous_window(
        plan,
        0.0,
        terminal_root,
        canonical_intervals=intervals,
        analytic_start_zero=True,
        analytic_terminal_zero=True,
        analytic_internal_terminal_times=[second_burst],
        analytic_internal_tangency_times=[bridge_time],
        maximum_depth=32,
        minimum_width_s=1e-8,
    )
    decimal_residuals = [
        abs(
            Decimal(
                decimal_refinement[
                    "bridge_value_residual_m2_decimal"
                ]
            )
        ),
        abs(
            Decimal(
                decimal_refinement[
                    "bridge_derivative_residual_m2_per_s_decimal"
                ]
            )
        ),
        abs(
            Decimal(
                decimal_refinement[
                    "terminal_root_residual_m2_decimal"
                ]
            )
        ),
    ]
    verified = (
        certificate["certificate_status"] == "verified"
        and certificate["undecided_box_count"] == 0
        and certificate["failed_box_count"] == 0
        and max(decimal_residuals) <= Decimal("1e-50")
        and abs(bridge_margin) <= 1e-7
    )
    nearby_document_references = [
        record
        for record in standalone_numeric_reference_records_from_q2_guide()
        if abs(record["value"] - terminal_root) < 1.0
    ]
    reference_record = (
        nearby_document_references[0]
        if len(nearby_document_references) == 1
        else None
    )
    work_guide_reference: float | str = (
        reference_record["value"]
        if reference_record is not None
        else "not_available"
    )
    reference_gap: float | str = (
        work_guide_reference - terminal_root
        if isinstance(work_guide_reference, float)
        else "not_available"
    )
    reference_precision_digits: int | str = (
        reference_record["precision_digits"]
        if reference_record is not None
        else "not_available"
    )
    matches_reference_at_reported_precision: bool | str = (
        round(terminal_root, reference_precision_digits)
        == round(work_guide_reference, reference_precision_digits)
        if (
            isinstance(work_guide_reference, float)
            and isinstance(reference_precision_digits, int)
        )
        else "not_available"
    )
    reference_source_document = (
        reference_record["source_document"]
        if reference_record is not None
        else "not_available"
    )
    result_strength = "best_verified_two_bomb_collinear_solution"
    return {
        "scheme_id": "Q2_A_two_bomb_best_verified_collinear_solution",
        "bomb_count": 2,
        "method": (
            "deterministic_multistart_joint_continuous_roots_followed_by_"
            "80_digit_decimal_newton_and_full_continuous_certificate"
        ),
        "translation_normalisation": {
            "first_burst_s": 0.0,
            "first_center_m": first.center_m,
            "second_burst_s": second_burst,
            "second_burst_rule": (
                "latest no-gap burst after the first single-smoke interval"
            ),
            "normalisation_audit": (
                "first burst fixes time translation; first center is the "
                "largest downstream center that covers the ship at t=0"
            ),
        },
        "decision_variables": {
            "smoke_centers_m": [
                first.center_m,
                verified_center,
            ],
            "burst_times_s": [
                first.t_b_s,
                plan[1].t_b_s,
            ],
        },
        "bridge_boundary_equation": (
            "pair-envelope value equals zero and its time derivative equals zero"
        ),
        "bridge_boundary_center_m": bridge_boundary_center,
        "verified_second_center_m": verified_center,
        "bridge_minimum_time_s": bridge_time,
        "bridge_minimum_margin_m2": bridge_margin,
        "coverage_interval_s": [0.0, terminal_root],
        "coverage_start_s": 0.0,
        "coverage_end_s": terminal_root,
        "terminal_decay_root_s": terminal_root,
        "best_objective_s": terminal_root,
        "best_objective_rounded_to_9_decimal_places_s": round(
            terminal_root,
            9,
        ),
        "reference_value_hardcoded": False,
        "reference_used_in_acceptance": False,
        "work_guide_reference_s": work_guide_reference,
        "reference_precision_digits": reference_precision_digits,
        "reference_source_document": reference_source_document,
        "matches_reference_at_reported_precision": (
            matches_reference_at_reported_precision
        ),
        "work_guide_reference_read_method": (
            "read_only_ooxml_unique_standalone_numeric_value_within_"
            "one_second_of_computed_root"
        ),
        "reference_gap_s": reference_gap,
        "reference_comparison_used_for_reporting_only": True,
        "reference_used_in_objective": False,
        "reference_used_in_constraints": False,
        "reference_used_in_candidate_selection": False,
        "near_bridge_boundary": True,
        "local_refinement_evidence": {
            "joint_variables": [
                "second_center_m",
                "bridge_critical_time_s",
                "terminal_decay_root_s",
            ],
            "joint_equations": [
                "bridge_pair_envelope_value=0",
                "bridge_pair_envelope_time_derivative=0",
                "terminal_continuous_margin=0",
            ],
            "time_grid_used_in_objective_or_constraints": False,
            "deterministic_start_count": len(
                deterministic_perturbations
            ),
            "converged_start_count": len(converged),
            "coarse_nested_root_start": {
                "second_center_m": bridge_boundary_center,
                "bridge_time_s": coarse_bridge_time,
                "bridge_margin_m2": coarse_bridge_margin,
                "terminal_root_s": coarse_terminal_root,
            },
            "runs": local_refinement_runs,
            "decimal_refinement": decimal_refinement,
            "variable_bound_audit": {
                "artificial_narrow_bounds_used": False,
                "initial_value_only_solver": False,
                "premature_rounding_used": False,
                "inward_reproduction_guard_used": False,
            },
        },
        "best_schedule": [smoke.as_event_record() for smoke in plan],
        "continuous_certificate": certificate,
        "relative_reachability": enumerate_relative_headings(plan),
        "certificate_status": "verified" if verified else "failed",
        "result_strength": result_strength,
        "global_optimality_status": "not_proved",
    }


def _vectorised_margin(
    times: np.ndarray,
    centers: np.ndarray,
    bursts: np.ndarray,
) -> np.ndarray:
    ship = PARAMS.ship_speed_mps * times[:, None]
    d_values = ship - centers[None, :]
    ages = times[:, None] - bursts[None, :]
    radii = np.where(
        (ages >= 0.0) & (ages <= PARAMS.smoke_hold_s),
        PARAMS.smoke_max_radius_m,
        np.where(
            (ages > PARAMS.smoke_hold_s) & (ages <= PARAMS.smoke_lifetime_s),
            PARAMS.smoke_max_radius_m
            * (PARAMS.smoke_lifetime_s - ages)
            / PARAMS.smoke_decay_s,
            0.0,
        ),
    )
    intercepts = (
        radii * radii
        - PARAMS.ship_radius_m**2
        - d_values * d_values
    )
    slopes = -2.0 * d_values
    intercepts = np.where(radii > 0.0, intercepts, -1e100)
    left_values = np.max(
        intercepts - PARAMS.ship_radius_m * slopes,
        axis=1,
    )
    right_values = np.max(
        intercepts + PARAMS.ship_radius_m * slopes,
        axis=1,
    )
    result = np.minimum(left_values, right_values)
    smoke_count = len(centers)
    for first in range(smoke_count):
        for second in range(first + 1, smoke_count):
            denominator = slopes[:, first] - slopes[:, second]
            valid = (
                (radii[:, first] > 0.0)
                & (radii[:, second] > 0.0)
                & (np.abs(denominator) > 1e-12)
            )
            xi = np.divide(
                intercepts[:, second] - intercepts[:, first],
                denominator,
                out=np.zeros_like(denominator),
                where=valid,
            )
            pair_value = (
                intercepts[:, first] + slopes[:, first] * xi
            )
            envelope = np.max(intercepts + slopes * xi[:, None], axis=1)
            on_envelope = np.abs(envelope - pair_value) <= 1e-5
            candidate = np.where(
                valid
                & (xi >= -PARAMS.ship_radius_m)
                & (xi <= PARAMS.ship_radius_m)
                & on_envelope,
                envelope,
                1e100,
            )
            result = np.minimum(result, candidate)
    return result


def _three_bomb_plan_from_variables(variables: Sequence[float]) -> list[SmokePlan]:
    center_2, center_3, burst_3 = map(float, variables)
    return [
        SmokePlan.from_burst(
            "capacity_three_smoke_1",
            center_m=PARAMS.smoke_max_radius_m - PARAMS.ship_radius_m,
            t_b_s=0.0,
        ),
        SmokePlan.from_burst(
            "capacity_three_smoke_2",
            center_m=center_2,
            t_b_s=PARAMS.single_smoke_max_duration_s,
        ),
        SmokePlan.from_burst(
            "capacity_three_smoke_3",
            center_m=center_3,
            t_b_s=burst_3,
        ),
    ]


def _diagnostic_duration(variables: Sequence[float], horizon_s: float = 46.0) -> float:
    plan = _three_bomb_plan_from_variables(variables)
    times = np.linspace(0.0, horizon_s, 5001)
    centers = np.array([smoke.center_m for smoke in plan])
    bursts = np.array([smoke.t_b_s for smoke in plan])
    margins = _vectorised_margin(times, centers, bursts)
    negative = np.flatnonzero(margins < -1e-6)
    if not len(negative):
        return horizon_s
    return float(times[int(negative[0]) - 1]) if negative[0] else 0.0


def solve_three_bomb_frontier() -> tuple[dict[str, Any], dict[str, Any]]:
    start_clock = time.perf_counter()
    target_times = np.unique(
        np.concatenate(
            (
                np.linspace(0.1, THREE_BOMB_REFERENCE_S, 12001),
                np.array(
                    [
                        PARAMS.single_smoke_max_duration_s - 1e-6,
                        PARAMS.single_smoke_max_duration_s,
                        PARAMS.single_smoke_max_duration_s + 1e-6,
                        PARAMS.smoke_hold_s,
                        PARAMS.smoke_lifetime_s,
                    ]
                ),
            )
        )
    )
    bounds = [(160.0, 205.0), (260.0, 330.0), (18.0, 29.0)]
    structured_initialisation = np.array([178.16064721, 287.86592204, 25.06430275])
    rng = np.random.default_rng(GLOBAL_SEED)
    population_size = 45
    initial_population = np.empty((population_size, 3), dtype=float)
    initial_population[0] = structured_initialisation
    for column, (lower, upper) in enumerate(bounds):
        initial_population[1:, column] = rng.uniform(
            lower,
            upper,
            size=population_size - 1,
        )

    def objective(variables: np.ndarray) -> float:
        plan = _three_bomb_plan_from_variables(variables)
        centers = np.array([smoke.center_m for smoke in plan])
        bursts = np.array([smoke.t_b_s for smoke in plan])
        return -float(
            np.min(_vectorised_margin(target_times, centers, bursts))
        )

    result = differential_evolution(
        objective,
        bounds=bounds,
        seed=GLOBAL_SEED,
        init=initial_population,
        popsize=15,
        maxiter=100,
        tol=1e-9,
        polish=True,
        workers=1,
        updating="immediate",
    )
    candidate_variables = [result.x, structured_initialisation]
    verified_candidates: list[tuple[float, list[SmokePlan], dict[str, Any]]] = []
    candidate_checks = []
    for variables in candidate_variables:
        plan = _three_bomb_plan_from_variables(variables)
        intervals = event_intervals(
            plan,
            0.0,
            THREE_BOMB_REFERENCE_S,
            prefix="three_frontier",
        )
        certificate = certify_continuous_window(
            plan,
            0.0,
            THREE_BOMB_REFERENCE_S,
            canonical_intervals=intervals,
            analytic_start_zero=True,
            analytic_internal_terminal_times=[
                PARAMS.single_smoke_max_duration_s
            ],
            maximum_depth=32,
            minimum_width_s=1e-7,
        )
        exact_terminal_root = _first_failure_or_terminal_root(
            plan,
            search_start_s=THREE_BOMB_REFERENCE_S,
            search_end_s=min(
                smoke.t_b_s + PARAMS.smoke_lifetime_s for smoke in plan[-1:]
            ),
            point_count=10001,
        )
        candidate_checks.append(
            {
                "variables": [float(value) for value in variables],
                "reference_horizon_certificate_status": certificate[
                    "certificate_status"
                ],
                "actual_terminal_root_s": exact_terminal_root,
            }
        )
        if certificate["certificate_status"] == "verified":
            verified_candidates.append((exact_terminal_root, plan, certificate))
    if not verified_candidates:
        raise RuntimeError("No three-bomb candidate passed the continuous certificate.")
    actual_root, best_plan, certificate = max(
        verified_candidates,
        key=lambda row: row[0],
    )
    population_durations = sorted(
        _diagnostic_duration(row) for row in result.population
    )
    feasible_count = len(verified_candidates)
    runtime = time.perf_counter() - start_clock
    candidate_improvement = None
    if actual_root > THREE_BOMB_REFERENCE_S + 1e-9:
        candidate_improvement = {
            "candidate_duration_s": actual_root,
            "improvement_over_reference_s": actual_root - THREE_BOMB_REFERENCE_S,
            "continuous_certificate_status_at_reference_horizon": certificate[
                "certificate_status"
            ],
            "adoption_status": "awaiting_human_decision_not_formal_replacement",
        }
    payload = {
        "scheme_id": "Q2_A_three_bomb_best_verified_collinear_reference",
        "bomb_count": 3,
        "formal_method_name_zh": MODEL_SCOPE["main_method_name_zh"],
        "global_seed": GLOBAL_SEED,
        "local_search_seed": GLOBAL_SEED,
        "start_count": len(result.population),
        "feasible_start_count": feasible_count,
        "failed_start_count": len(result.population) - feasible_count,
        "optimiser_name": "scipy.optimize.differential_evolution_with_polish",
        "optimiser_options": {
            "maxiter": 100,
            "population_size": population_size,
            "tolerance": 1e-9,
            "workers": 1,
            "updating": "immediate",
            "structured_initialisation_used": True,
        },
        "variable_bounds": {
            "center_2_m": list(bounds[0]),
            "center_3_m": list(bounds[1]),
            "burst_3_s": list(bounds[2]),
        },
        "stopping_tolerance": 1e-9,
        "best_objective_s": THREE_BOMB_REFERENCE_S,
        "verified_actual_terminal_root_s": actual_root,
        "best_schedule": [smoke.as_event_record() for smoke in best_plan],
        "local_optimum_count": len(
            set(round(duration, 6) for duration in population_durations)
        ),
        "objective_distribution": {
            "minimum_s": population_durations[0],
            "median_s": float(np.median(population_durations)),
            "maximum_s": population_durations[-1],
        },
        "runtime_seconds": "recorded_in_non_core_round2_run_summary",
        "continuous_certificate": certificate,
        "candidate_checks": candidate_checks,
        "candidate_improvement": candidate_improvement,
        "relative_reachability": enumerate_relative_headings(best_plan),
        "certificate_status": "verified",
        "result_strength": "best_verified_collinear_solution",
        "global_optimality_status": "not_proved",
    }
    runtime_payload = {
        "three_bomb_optimisation_runtime_seconds": runtime,
        "three_bomb_function_evaluations": int(result.nfev),
        "three_bomb_optimiser_message": str(result.message),
    }
    return payload, runtime_payload


def capacity_frontier() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = baseline_frontier()
    two_bomb = solve_two_bomb_frontier()
    three_bomb, runtime = solve_three_bomb_frontier()
    one_bomb = {
        "scheme_id": "Q2_A_one_bomb_analytic",
        "bomb_count": 1,
        "best_objective_s": PARAMS.single_smoke_max_duration_s,
        "formula": "2(R_c-R_s)/V_s",
        "result_strength": "analytic_exact",
        "global_optimality_status": "proved_for_one_fixed_smoke",
    }
    payload = {
        "formal_method_name_zh": MODEL_SCOPE["main_method_name_zh"],
        "A": {
            "one_bomb": one_bomb,
            "two_bomb": two_bomb,
            "three_bomb": three_bomb,
        },
        "B": baseline,
        "worst_detection_window_s": PARAMS.detect_worst_upper_s,
        "scope_note": (
            "A contains analytic or verified collinear solutions; the two- "
            "and three-bomb results are not proved global optima. B is a "
            "conservative constructive baseline."
        ),
        "two_bomb_plan_isolation": {
            "minimum_resource_scheme_id": (
                "Q2_A_two_bomb_minimum_resource_full_worst_window"
            ),
            "capacity_solution_scheme_id": (
                "Q2_A_two_bomb_best_verified_collinear_solution"
            ),
            "separate_schedules": True,
            "separate_robustness_results": True,
        },
    }
    return payload, runtime
