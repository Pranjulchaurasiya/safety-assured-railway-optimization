"""
Baseline Cost Calculator
=========================
Computes the UNOPTIMIZED weighted departure delay cost for N=5 and N=12,
using the exact same penalty formula as the CP-SAT objective function:
  cost = sum(w_i * max(0, actual_dep_i - scheduled_dep_i))

In the baseline scenario (no optimization), when two trains conflict on the
same block, the lower-priority train is delayed by exactly the amount needed
to let the higher-priority train clear first. This matches how a human
dispatcher would manually resolve conflicts without a formal optimizer.
"""

from extract_data import (
    load_corridor_trains,
    select_density_subset,
    tag_fastest_as_premium,
)

DELTA_T_SEP = 2  # same as cpsat_model.py


def compute_baseline_cost(subset):
    """Simulate naive priority-based conflict resolution (no optimization).
    Higher-priority train always goes first. Lower-priority train is delayed
    by exactly enough to let the higher-priority train clear the block.
    Returns total weighted departure delay cost."""

    # Build list of (train, block, dep_time, arr_time) for each block traverse
    traversals = []
    for tno, t in subset.items():
        sched_dep = (t.events[0].departure_min
                     if t.events[0].departure_min is not None
                     else t.events[0].arrival_min or 0)
        for k in range(len(t.events) - 1):
            ev_a = t.events[k]
            ev_b = t.events[k + 1]
            block = tuple(sorted([ev_a.station_code, ev_b.station_code]))
            dep = ev_a.departure_min if ev_a.departure_min is not None else 0
            arr = ev_b.arrival_min if ev_b.arrival_min is not None else dep + 20
            traversals.append({
                "tno":       tno,
                "weight":    t.priority_weight,
                "block":     block,
                "dep":       dep,
                "arr":       arr,
                "sched_dep": sched_dep,
                "actual_dep": sched_dep,  # starts at scheduled, grows if delayed
            })

    # Sort by priority descending, then scheduled departure ascending
    # (highest priority trains go first; within same priority, earlier first)
    traversals.sort(key=lambda x: (-x["weight"], x["dep"]))

    # For each block, track when it was last cleared
    block_clear_time = {}

    # Assign actual departure times greedily
    delays = {tno: 0 for tno in subset}

    for tr in traversals:
        block    = tr["block"]
        last_clr = block_clear_time.get(block, 0)
        # Must wait until block is clear + separation
        earliest_dep = last_clr  # block clear time is when last train ARRIVED
        if tr["dep"] < earliest_dep + DELTA_T_SEP:
            # Forced to delay
            forced_dep = earliest_dep + DELTA_T_SEP
            extra_delay = forced_dep - tr["dep"]
            delays[tr["tno"]] = max(delays[tr["tno"]], extra_delay)
            actual_arr = tr["arr"] + extra_delay
        else:
            actual_arr = tr["arr"]
        block_clear_time[block] = actual_arr

    # Compute weighted cost using same formula as CP-SAT objective
    total_cost = 0
    for tno, t in subset.items():
        sched = (t.events[0].departure_min
                 if t.events[0].departure_min is not None
                 else t.events[0].arrival_min or 0)
        delay = delays[tno]
        total_cost += t.priority_weight * delay

    return total_cost, delays


if __name__ == "__main__":
    trains = load_corridor_trains()

    for n in [5, 12]:
        subset = select_density_subset(trains, n)
        tag_fastest_as_premium(subset)

        baseline_cost, delays = compute_baseline_cost(subset)

        print(f"\nN={n}  baseline_cost={baseline_cost}")
        delayed = {tno: d for tno, d in delays.items() if d > 0}
        if delayed:
            print(f"  Trains delayed in baseline (no optimization):")
            for tno, d in sorted(delayed.items(), key=lambda x: -x[1]):
                t = subset[tno]
                print(f"    {tno:15s} w={t.priority_weight:2d}  "
                      f"delay={d}min  cost={t.priority_weight * d}")
        else:
            print(f"  No delays in baseline (trains naturally non-conflicting)")