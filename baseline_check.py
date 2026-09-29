"""Priority-ordered greedy baseline using consistent whole-train shifts.

Each train retains its scheduled travel and dwell pattern. When its next
block occupation conflicts with a previously placed train, all of its
events are shifted together. The resulting origin delay is costed with
the same priority weights as CP-SAT. This is a feasible heuristic, not
an operating-rule dispatcher or an optimal solution.
"""

from extract_data import (
    load_corridor_trains,
    select_density_subset,
    tag_fastest_as_premium,
)

DELTA_T_SEP = 2


def train_intervals(train):
    """Return scheduled block intervals, rejecting missing/invalid times."""
    result = []
    for first, second in zip(train.events, train.events[1:]):
        departure = first.departure_min
        arrival = second.arrival_min
        if departure is None or arrival is None or arrival <= departure:
            raise ValueError(
                f"Cannot construct a baseline block interval for {train.train_no}"
            )
        block = tuple(sorted((first.station_code, second.station_code)))
        result.append((block, departure, arrival))
    return result


def compute_baseline_cost(subset):
    """Place trains in descending priority, shifting entire routes on conflict."""
    placed = {}
    delays = {}
    trains = sorted(
        subset.items(),
        key=lambda item: (-item[1].priority_weight,
                          item[1].events[0].departure_min or 0,
                          str(item[0])),
    )
    for train_id, train in trains:
        intervals = train_intervals(train)
        delay = 0
        while True:
            new_delay = delay
            for block, departure, arrival in intervals:
                for occupied_start, occupied_end in placed.get(block, ()):
                    shifted_start = departure + delay
                    shifted_end = arrival + delay
                    if (shifted_start < occupied_end + DELTA_T_SEP
                            and occupied_start < shifted_end + DELTA_T_SEP):
                        new_delay = max(new_delay,
                                        occupied_end + DELTA_T_SEP - departure)
            if new_delay == delay:
                break
            delay = new_delay
        delays[train_id] = delay
        for block, departure, arrival in intervals:
            placed.setdefault(block, []).append(
                (departure + delay, arrival + delay)
            )

    return sum(subset[train_id].priority_weight * delay
               for train_id, delay in delays.items()), delays


if __name__ == "__main__":
    trains = load_corridor_trains()
    for n in (5, 12):
        subset = select_density_subset(trains, n)
        tag_fastest_as_premium(subset)
        cost, delays = compute_baseline_cost(subset)
        print(f"N={n} baseline_cost={cost}")
        for train_id, delay in delays.items():
            if delay:
                print(f"  {train_id}: +{delay} min")
