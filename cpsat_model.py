"""
Stage 2 — OR-Tools CP-SAT Optimization Model
==============================================
Implements constraints C1-C4 from paper Section V.

Correct variable design (final version):
  - d_vars[(tno,0)] lower bound = real scheduled departure time
    This PREVENTS the solver from trivially setting departure=0
    to achieve zero delay. Trains cannot depart earlier than scheduled.
  - d_vars for non-origin stops: lower bound = 0 (free to shift)
  - a_vars: lower bound = 0 (fully free, so C3 can resolve conflicts
    by adjusting arrival times without making the model infeasible)
  - delay_var = d_vars[(tno,0)] - sched_dep  (always >= 0 by construction,
    no MaxEquality needed)

This is the only formulation that simultaneously:
  (a) prevents trivial objective=0 by anchoring origin departures
  (b) avoids infeasibility by leaving arrival times free for conflict resolution
  (c) correctly computes delay as a simple subtraction IntVar

Requires: pip install ortools
Run: py cpsat_model.py
"""

import time
from ortools.sat.python import cp_model
from extract_data import (
    load_corridor_trains,
    select_density_subset,
    tag_fastest_as_premium,
)

DELTA_T_SEP = 2       # Kavach minimum block separation buffer (minutes)
HORIZON     = 1560    # 26 hours, covers overnight wrap-arounds


def build_and_solve(trains_dict, time_limit_s=60):
    """Build and solve the CP-SAT timetable for one density tier.
    Returns (status_name, solve_time_s, objective_value, stats_dict).
    """
    model  = cp_model.CpModel()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers  = 8

    a_vars    = {}
    d_vars    = {}
    sched_dep = {}

    # ── Decision variables ────────────────────────────────────────────────
    for tno, train in trains_dict.items():
        # Real scheduled origin departure (lower bound for d[0])
        first_dep = train.events[0].departure_min
        if first_dep is None:
            first_dep = train.events[0].arrival_min or 0
        sched_dep[tno] = first_dep

        for idx, ev in enumerate(train.events):
            # Arrival: fully free — solver moves arrivals to resolve conflicts
            a_vars[(tno, idx)] = model.NewIntVar(
                0, HORIZON, f"a_{tno}_{idx}"
            )

            # Departure at ORIGIN: lower bound = scheduled time
            # (cannot depart earlier than scheduled — this is what makes
            # delay meaningful and prevents trivial objective=0)
            # Departure at NON-ORIGIN stops: lower bound = 0 (free)
            if idx == 0:
                lo_d = first_dep
            else:
                lo_d = 0
            d_vars[(tno, idx)] = model.NewIntVar(
                lo_d, HORIZON, f"d_{tno}_{idx}"
            )

    # ── C1: Minimum dwell time ────────────────────────────────────────────
    for tno, train in trains_dict.items():
        for idx, ev in enumerate(train.events):
            if ev.arrival_min is not None and ev.departure_min is not None:
                real_dwell = max(0, ev.departure_min - ev.arrival_min)
            else:
                real_dwell = 0
            model.Add(
                d_vars[(tno, idx)] - a_vars[(tno, idx)] >= real_dwell
            )

    # ── C2: Travel time lower bound ───────────────────────────────────────
    for tno, train in trains_dict.items():
        for idx in range(len(train.events) - 1):
            ev_a = train.events[idx]
            ev_b = train.events[idx + 1]
            if ev_a.departure_min is not None and ev_b.arrival_min is not None:
                real_travel = max(1, ev_b.arrival_min - ev_a.departure_min)
            else:
                dist_delta  = max(1.0, abs(ev_b.distance_km - ev_a.distance_km))
                real_travel = max(1, round(dist_delta * 1.3))
            model.Add(
                a_vars[(tno, idx + 1)] - d_vars[(tno, idx)] >= real_travel
            )

    # ── C3: Block mutual exclusion (single-track) ─────────────────────────
    train_list = list(trains_dict.items())
    for i in range(len(train_list)):
        tno_i, train_i = train_list[i]
        for j in range(i + 1, len(train_list)):
            tno_j, train_j = train_list[j]

            blocks_i = [
                (tuple(sorted([train_i.events[k].station_code,
                               train_i.events[k+1].station_code])), k)
                for k in range(len(train_i.events) - 1)
            ]
            blocks_j = [
                (tuple(sorted([train_j.events[k].station_code,
                               train_j.events[k+1].station_code])), k)
                for k in range(len(train_j.events) - 1)
            ]

            for (bi, ki) in blocks_i:
                for (bj, kj) in blocks_j:
                    if bi != bj:
                        continue
                    i_first = model.NewBoolVar(
                        f"if_{tno_i}_{tno_j}_{ki}_{kj}"
                    )
                    model.Add(
                        a_vars[(tno_i, ki+1)] + DELTA_T_SEP <= d_vars[(tno_j, kj)]
                    ).OnlyEnforceIf(i_first)
                    model.Add(
                        a_vars[(tno_j, kj+1)] + DELTA_T_SEP <= d_vars[(tno_i, ki)]
                    ).OnlyEnforceIf(i_first.Not())

    # ── C4: Priority-weighted departure delay (soft objective) ────────────
    # delay_var = d[(tno,0)] - sched_dep[tno]
    # This is always >= 0 because d[(tno,0)] has lower bound = sched_dep[tno]
    # No MaxEquality needed — simple subtraction suffices.
    penalty_terms = []
    for tno, train in trains_dict.items():
        origin_dep_var = d_vars[(tno, 0)]
        sched          = sched_dep[tno]
        delay_var      = model.NewIntVar(0, HORIZON, f"delay_{tno}")
        model.Add(delay_var == origin_dep_var - sched)
        penalty_terms.append(train.priority_weight * delay_var)

    model.Minimize(sum(penalty_terms))

    # ── Solve ─────────────────────────────────────────────────────────────
    t0      = time.perf_counter()
    status  = solver.Solve(model)
    elapsed = time.perf_counter() - t0

    status_name = solver.StatusName(status)
    obj_value   = (
        solver.ObjectiveValue()
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else None
    )

    stats = {
        "status":          status_name,
        "solve_time_s":    elapsed,
        "num_vars":        len(a_vars) + len(d_vars),
        "num_constraints": len(model.Proto().constraints),
        "objective_value": obj_value,
    }

    # Show per-train delays when objective > 0
    if (status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
            and obj_value is not None and obj_value > 0):
        print(f"  Delayed trains:")
        for tno, train in trains_dict.items():
            actual = solver.Value(d_vars[(tno, 0)])
            sched  = sched_dep[tno]
            delay  = actual - sched
            if delay > 0:
                print(f"    {tno:15s} w={train.priority_weight:2d}  "
                      f"sched={sched//60:02d}:{sched%60:02d}  "
                      f"actual={actual//60:02d}:{actual%60:02d}  "
                      f"delay={delay}min  "
                      f"weighted_cost={train.priority_weight*delay}")

    return status_name, elapsed, obj_value, stats


if __name__ == "__main__":
    trains = load_corridor_trains()
    print(f"Loaded {len(trains)} real corridor trains.\n")

    for n in [5, 12, 25, 50]:
        subset = select_density_subset(trains, n)
        tag_fastest_as_premium(subset)
        status, elapsed, obj, stats = build_and_solve(subset)
        print(
            f"N={n:3d}  status={status:10s}  "
            f"solve_time={elapsed:.4f}s  "
            f"vars={stats['num_vars']:4d}  "
            f"constraints={stats['num_constraints']:5d}  "
            f"objective={obj}"
        )
        print()