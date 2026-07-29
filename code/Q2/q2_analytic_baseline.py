from __future__ import annotations

from q2_common import CONSTANTS


def run_baseline() -> dict:
    c = CONSTANTS
    single = c.single_cloud_cover_upper_s
    capacities = []
    for n in (1, 2, 3):
        capacities.append(
            {
                "bomb_count": n,
                "zero_overlap_capacity_s": n * single,
                "covers_M1_lower_window": n * single >= c.m1_detection_lower_s,
                "covers_M1_upper_window": n * single >= c.m1_detection_upper_s,
            }
        )

    chains = []
    for overlap in (0.0, 0.5, 1.0):
        gap = single - overlap
        center_spacing = c.ship_speed_mps * gap
        total = 3.0 * single - 2.0 * overlap
        transition_slack = (
            c.uav_speed_mps * gap - center_spacing
        )
        chains.append(
            {
                "overlap_s": overlap,
                "total_continuous_capacity_s": total,
                "center_spacing_m": center_spacing,
                "drop_time_gap_s": gap,
                "uav_transition_distance_slack_m": transition_slack,
                "passes_1s_drop_interval": gap >= c.min_drop_interval_s,
                "passes_conservative_2s_response_interval": (
                    gap >= c.conservative_response_interval_s
                ),
                "covers_M1_upper_window": total >= c.m1_detection_upper_s,
            }
        )

    return {
        "method_id": "B",
        "role": "usable_baseline",
        "single_cloud_cover_upper_s": single,
        "M1_detection_window_bounds_s": [
            c.m1_detection_lower_s,
            c.m1_detection_upper_s,
        ],
        "capacities": capacities,
        "three_bomb_chains": chains,
        "interpretation": (
            "Legal conservative lower bound: at each time at least one cloud "
            "independently contains the complete ship disk."
        ),
        "absolute_first_drop_status": "blocked_missing_initial_state",
    }
