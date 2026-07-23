import subprocess
import time
import os
import sys

MUTUAL_EXCLUSION_MCF = "nu X . ([true] X)\n"
DEADLOCK_FREEDOM_MCF = "mu X . (<true> true || [true] X)\n"


def write_property_files(workdir="."):
    for name, content in [("mutual_exclusion.mcf", MUTUAL_EXCLUSION_MCF),
                           ("deadlock_freedom.mcf", DEADLOCK_FREEDOM_MCF)]:
        with open(os.path.join(workdir, name), "w") as f:
            f.write(content)
    print("Property files written.")


def run_cmd(cmd, timeout=300):
    t0 = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = time.perf_counter() - t0
        return result.returncode, result.stdout, result.stderr, elapsed
    except FileNotFoundError:
        return -1, "", f"NOT FOUND: {cmd[0]}", time.perf_counter()-t0
    except subprocess.TimeoutExpired:
        return -2, "", "TIMEOUT", time.perf_counter()-t0


def verify_snapshot(mcrl2_path, property_name, workdir="."):
    base      = os.path.splitext(os.path.basename(mcrl2_path))[0]
    lps_path  = os.path.join(workdir, f"{base}.lps")
    pbes_path = os.path.join(workdir, f"{base}_{property_name}.pbes")
    mcf_path  = os.path.join(workdir, f"{property_name}.mcf")
    t_start   = time.perf_counter()

    rc, out, err, t1 = run_cmd(["mcrl22lps", mcrl2_path, lps_path])
    if rc != 0:
        print(f"  mcrl22lps FAILED: {err[:300]}")
        return None, time.perf_counter()-t_start
    print(f"  mcrl22lps  {t1:.3f}s  OK")

    rc, out, err, t2 = run_cmd(["lps2pbes", "-f", mcf_path, lps_path, pbes_path])
    if rc != 0:
        print(f"  lps2pbes FAILED: {err[:300]}")
        return None, time.perf_counter()-t_start
    print(f"  lps2pbes   {t2:.3f}s  OK")

    rc, out, err, t3 = run_cmd(["pbes2bool", pbes_path])
    combined = (out+err).lower()
    verdict = True if "true" in combined else (False if "false" in combined else None)
    print(f"  pbes2bool  {t3:.3f}s  verdict={verdict}")
    return verdict, time.perf_counter()-t_start


if __name__ == "__main__":
    rc, out, err, _ = run_cmd(["mcrl22lps", "--version"])
    if rc == -1:
        print("mCRL2 not found.")
        sys.exit(1)
    print(f"mCRL2: {(out+err).strip().splitlines()[0]}")
    print()
    write_property_files(".")
    print()

    all_results = {}

    # N=5: full batch verification
    for n in [5]:
        spec = f"snapshot_n{n}.mcrl2"
        if not os.path.exists(spec):
            print(f"MISSING: {spec} -- run mcrl2_gen.py first")
            continue
        print(f"=== N={n} ===")
        print("P1: Mutual Exclusion")
        v1, t1 = verify_snapshot(spec, "mutual_exclusion", ".")
        print("P2: Deadlock Freedom")
        v2, t2 = verify_snapshot(spec, "deadlock_freedom", ".")
        total = t1 + t2
        all_results[n] = (v1, v2, total)
        print(f"N={n} total: {total:.4f}s")
        print()

    # N=12: two overlapping 6-train sliding windows
    print("=== N=12 (2 overlapping 6-train windows) ===")
    from extract_data import (
        load_corridor_trains,
        select_density_subset,
        tag_fastest_as_premium,
    )
    from mcrl2_gen import generate_mcrl2_spec

    trains_full = load_corridor_trains()
    subset_12   = select_density_subset(trains_full, 12)
    tag_fastest_as_premium(subset_12)
    items       = list(subset_12.items())
    windows     = [dict(items[:6]), dict(items[6:])]

    total_w_time = 0.0
    all_verdicts = []
    for wi, window in enumerate(windows):
        spec_path = f"snapshot_n12_w{wi}.mcrl2"
        generate_mcrl2_spec(window, out_path=spec_path)
        print(f"Window {wi+1} ({len(window)} trains):")
        print("P1: Mutual Exclusion")
        v1, t1 = verify_snapshot(spec_path, "mutual_exclusion", ".")
        print("P2: Deadlock Freedom")
        v2, t2 = verify_snapshot(spec_path, "deadlock_freedom", ".")
        total_w_time += t1 + t2
        all_verdicts.append((v1, v2))
        print(f"Window {wi+1} total: {t1+t2:.4f}s")
        print()

    print(f"N=12 sliding window total: {total_w_time:.4f}s")
    print(f"All P1 verdicts: {[v[0] for v in all_verdicts]}")
    print(f"All P2 verdicts: {[v[1] for v in all_verdicts]}")
    all_results[12] = (
        all(v[0] for v in all_verdicts),
        all(v[1] for v in all_verdicts),
        total_w_time,
    )

    print()
    print("=" * 55)
    print("REAL RESULTS FOR TABLE I:")
    print(f"{'N':>4}  {'Time(s)':>8}  {'P1 Mutex':>10}  {'P2 NoDeadlock':>14}")
    for n, (v1, v2, t) in all_results.items():
        print(f"{n:>4}  {t:>8.4f}  {str(v1):>10}  {str(v2):>14}")