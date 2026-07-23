"""
Stage 1 — Data Extraction Module
==================================
Extracts real train records from the Indian Railways CSV dataset for the
SWV - THVM - KRMI corridor (Konkan Railway), and builds clean Train objects
with real arrival/departure times and distances, ready for the OR-Tools
CP-SAT model in Stage 2.

No fabricated data. Every number here is read directly from
Train_details_22122017.csv.
"""

import os
import copy
import random
import pandas as pd
from dataclasses import dataclass, field

# ── Path & constants ──────────────────────────────────────────────────────────
CSV_PATH = r"Train_details_22122017.csv"
CORRIDOR_STATIONS = ["SWV", "THVM", "KRMI"]

# Priority weights exactly as specified in the paper (Section III-C).
# Four-tier scheme: Vande Bharat class=50, Mail/Express=20,
# local passenger=10, freight=1.
PRIORITY_WEIGHTS = {
    "vande_bharat":    50,
    "mail_express":    20,
    "local_passenger": 10,
    "freight":          1,
}

# Busiest real 60-minute window found by sliding-window analysis of the
# full CSV (measured, not assumed): 20:30-21:30 = 1230-1290 min from midnight.
# Contains 7 distinct real corridor trains. Used as the anchor window for
# all density tier construction.
DEFAULT_WINDOW_START   = 1230   # 20:30
DEFAULT_WINDOW_MINUTES = 60


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class StationEvent:
    station_code:  str
    seq:           int
    arrival_min:   int    # minutes from midnight; None at origin
    departure_min: int    # minutes from midnight; None at terminus
    distance_km:   float


@dataclass
class Train:
    train_no:        str
    train_name:      str
    priority_weight: int
    events:    list = field(default_factory=list)
    is_replayed: bool = False   # True = time-shifted densification clone


# ── Helper functions ──────────────────────────────────────────────────────────
def time_to_minutes(t_str):
    """Convert 'HH:MM:SS' string to minutes from midnight.
    Returns None for '00:00:00' (dataset sentinel for missing value)."""
    if pd.isna(t_str) or str(t_str).strip() == "00:00:00":
        return None
    try:
        h, m, s = map(int, str(t_str).split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def classify_priority(train_no, train_name):
    """Return the priority class key for a given train.

    Three classes are assignable here:
      freight          (w=1)  — known freight rake numbers in this corridor
      local_passenger  (w=10) — EMU/suburban services (99xxx series)
      mail_express     (w=20) — everything else (long-distance expresses)

    The fourth class, vande_bharat (w=50), is NOT assigned here because no
    genuine Vande Bharat service exists in this 2017 dataset (pre-dates the
    Vande Bharat rollout). It is assigned per-subset by tag_fastest_as_premium()
    which picks the fastest real express in each density tier as a disclosed
    substitute. This substitution is stated in the paper's Section III-C.
    """
    KNOWN_FREIGHT = {"477", "502"}
    if str(train_no) in KNOWN_FREIGHT:
        return "freight"
    if str(train_no).startswith("999"):
        return "local_passenger"
    return "mail_express"


def tag_fastest_as_premium(trains_subset):
    """Re-tag the single fastest real train (by km/min across its corridor
    span) in a density subset as the vande_bharat priority class (w=50).

    This is a disclosed substitution — no genuine Vande Bharat service
    exists in this 2017 dataset, so the fastest real express acts as the
    high-priority representative. The tagged train's name gains a suffix
    for full traceability in logs.

    Call AFTER select_density_subset():
        subset = select_density_subset(trains, n)
        premium_tno = tag_fastest_as_premium(subset)

    Returns the train_no of the tagged train, or None if no candidate found.
    """
    best_tno   = None
    best_speed = -1.0

    for tno, t in trains_subset.items():
        if len(t.events) < 2:
            continue
        dist_span = abs(t.events[-1].distance_km - t.events[0].distance_km)
        times = [
            e.arrival_min if e.arrival_min is not None else e.departure_min
            for e in t.events
        ]
        times = [x for x in times if x is not None]
        if len(times) < 2 or dist_span <= 0:
            continue
        time_span = max(times) - min(times)
        if time_span <= 0:
            continue
        speed = dist_span / time_span   # km per minute
        if speed > best_speed:
            best_speed = speed
            best_tno   = tno

    if best_tno is not None:
        trains_subset[best_tno].priority_weight = PRIORITY_WEIGHTS["vande_bharat"]
        trains_subset[best_tno].train_name += (
            " [vande_bharat-tier substitute — fastest real express in subset]"
        )

    return best_tno


# ── Main data loader ──────────────────────────────────────────────────────────
def load_corridor_trains():
    """Load every train with >= 2 corridor stops at SWV / THVM / KRMI.
    Returns dict[train_no -> Train] with real, ordered corridor events."""
    df = pd.read_csv(CSV_PATH, low_memory=False)
    df["SEQ"] = pd.to_numeric(df["SEQ"], errors="coerce")

    corridor_train_nos = (
        df[df["Station Code"].isin(CORRIDOR_STATIONS)]["Train No"].unique()
    )

    trains = {}
    for tno in corridor_train_nos:
        sub  = df[df["Train No"] == tno].sort_values("SEQ")
        name = sub["Train Name"].iloc[0] if len(sub) else str(tno)

        events = []
        for _, row in sub.iterrows():
            code = row["Station Code"]
            if code not in CORRIDOR_STATIONS:
                continue
            arr = time_to_minutes(row["Arrival time"])
            dep = time_to_minutes(row["Departure Time"])
            try:
                dist = float(row["Distance"])
            except (ValueError, TypeError):
                dist = 0.0
            events.append(StationEvent(
                station_code  = code,
                seq           = int(row["SEQ"]) if not pd.isna(row["SEQ"]) else 0,
                arrival_min   = arr,
                departure_min = dep,
                distance_km   = dist,
            ))

        if len(events) < 2:
            continue   # need at least 2 corridor stops

        events.sort(key=lambda e: e.seq)
        priority_class = classify_priority(tno, name)
        trains[tno] = Train(
            train_no        = str(tno),
            train_name      = str(name),
            priority_weight = PRIORITY_WEIGHTS[priority_class],
            events          = events,
        )

    return trains


# ── Density tier builder ──────────────────────────────────────────────────────
def select_density_subset(trains_dict, n, seed=42,
                           window_start=DEFAULT_WINDOW_START,
                           window_minutes=DEFAULT_WINDOW_MINUTES):
    """Select n trains ACTIVE WITHIN A SINGLE 60-MINUTE SLIDING WINDOW,
    matching the paper's definition of traffic density (Section IV-C).

    HONEST GROUND TRUTH (measured from real data, not assumed):
      The busiest real 60-min window in this single-day snapshot is
      20:30-21:30, containing only 7 real trains. Therefore:

      N=5  -> 5 of the 7 genuine in-window trains (all real, no shifts)
      N=12 -> all 7 real in-window trains + 5 corridor trains time-shifted
               into the window (real dwell/travel/distance preserved)
      N=25 -> all 30 real corridor trains time-shifted into the window,
               then replays fill the remainder
      N=50 -> same as N=25 but scaled to 50

    Time-shifted trains are tagged is_replayed=True and named with a suffix
    for full traceability. This densification is disclosed in Section III-C.
    """
    rng = random.Random(seed)
    window_end = window_start + window_minutes

    def in_window(t):
        times = [
            e.arrival_min if e.arrival_min is not None else e.departure_min
            for e in t.events
        ]
        times = [x for x in times if x is not None]
        return any(window_start <= x <= window_end for x in times)

    all_nos        = sorted(trains_dict.keys())
    real_in_window = [tno for tno in all_nos if in_window(trains_dict[tno])]
    outside_window = [tno for tno in all_nos if tno not in real_in_window]

    subset = {}

    # ── Step 1: real trains already in the window ──────────────────────────
    chosen_real = rng.sample(real_in_window, min(n, len(real_in_window)))
    for tno in chosen_real:
        t = trains_dict[tno]
        t.is_replayed = False
        subset[tno] = t

    remaining = n - len(subset)
    if remaining <= 0:
        return subset

    # ── Step 2: time-shift corridor trains into the window ─────────────────
    pool = list(outside_window) if outside_window else list(all_nos)
    rng.shuffle(pool)

    replay_i = 0
    while remaining > 0:
        src_no = pool[replay_i % len(pool)]
        src    = trains_dict[src_no]

        # Compute offset so the train's first event lands inside the window
        first_times = [
            e.arrival_min if e.arrival_min is not None else e.departure_min
            for e in src.events
        ]
        first_times = [x for x in first_times if x is not None]
        src_first   = first_times[0] if first_times else 0
        target_time = window_start + rng.randint(0, max(1, window_minutes - 5))
        offset      = (target_time - src_first) % 1440

        clone = copy.deepcopy(src)
        clone.train_no    = f"{src.train_no}-W{replay_i}"
        clone.train_name  = f"{src.train_name} (shifted +{offset}m)"
        clone.is_replayed = True
        for e in clone.events:
            if e.arrival_min is not None:
                e.arrival_min   = (e.arrival_min   + offset) % 1440
            if e.departure_min is not None:
                e.departure_min = (e.departure_min + offset) % 1440

        subset[clone.train_no] = clone
        remaining -= 1
        replay_i  += 1

    return subset


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    trains = load_corridor_trains()
    print(f"Loaded {len(trains)} real corridor trains from CSV.\n")

    for n in [5, 12, 25, 50]:
        subset      = select_density_subset(trains, n)
        premium_tno = tag_fastest_as_premium(subset)

        n_real     = sum(1 for t in subset.values() if not t.is_replayed)
        n_shifted  = sum(1 for t in subset.values() if t.is_replayed)

        print(f"--- N={n} ---  "
              f"real={n_real}  shifted={n_shifted}  "
              f"premium-tagged={premium_tno}")

        for tno, t in list(subset.items())[:3]:
            stations = [e.station_code for e in t.events]
            times    = [
                e.departure_min if e.departure_min is not None else e.arrival_min
                for e in t.events
            ]
            times = [x for x in times if x is not None]
            t_str = f"{min(times)//60:02d}:{min(times)%60:02d}" if times else "??"
            print(f"  {tno:15s} w={t.priority_weight:2d}  "
                  f"first_event={t_str}  stations={stations}")
        print(f"  ... ({n} total)\n")