"""
statistical_runs.py — correct version using real cpsat_model.py
Excludes Run 1 as a solver warm-up/JIT cost (empirically ~3-6x slower
than subsequent runs in the same process — see three prior sessions).
"""
import statistics
import time
from extract_data import load_corridor_trains, select_density_subset, tag_fastest_as_premium
from cpsat_model import build_and_solve

trains = load_corridor_trains()

WARMUP_RUNS = 1
MEASURED_RUNS = 10
TOTAL_RUNS = WARMUP_RUNS + MEASURED_RUNS

for n in [5, 12]:
    times = []
    objectives = []
    subset = select_density_subset(trains, n)
    tag_fastest_as_premium(subset)

    print(f"\nRunning {TOTAL_RUNS}x for N={n} ({WARMUP_RUNS} warm-up + {MEASURED_RUNS} measured)...")
    for i in range(TOTAL_RUNS):
        status, elapsed, obj, stats = build_and_solve(subset)
        tag = "WARMUP" if i < WARMUP_RUNS else "measured"
        print(f"  Run {i+1:2d}: {elapsed:.4f}s  status={status}  obj={obj}  [{tag}]")
        if i >= WARMUP_RUNS:
            times.append(elapsed)
            objectives.append(obj if obj is not None else 0)

    print(f"\nN={n} STATISTICS ({MEASURED_RUNS} runs, excluding warm-up):")
    print(f"  Mean:   {statistics.mean(times):.4f}s")
    print(f"  Median: {statistics.median(times):.4f}s")
    print(f"  Stdev:  {statistics.stdev(times):.4f}s")
    print(f"  Min:    {min(times):.4f}s")
    print(f"  Max:    {max(times):.4f}s")
    print(f"  Obj mean: {statistics.mean(objectives):.1f}")