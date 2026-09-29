import subprocess
import time
import os
import sys

def write_property_files(trains_dict, workdir="."):
    """Generate properties for the blocks and train count in this snapshot.

    P1 forbids a second grant for any block before its free action.
    P2 permits a terminal deadlock only after every train has finished.
    Both describe the untimed process model, not the optimized clock times.
    """
    from mcrl2_gen import all_blocks

    blocks = all_blocks(trains_dict)
    if not blocks or not trains_dict:
        raise ValueError("Verification needs at least one train and block")
    p1 = " &&\n".join(
        f"[true* . grant_{block} . (!free_{block})* . grant_{block}] false"
        for block in blocks
    ) + "\n"
    n = len(trains_dict)
    p2 = (f"nu X(c: Nat = 0). "
          f"((val(c == {n}) || <true>true) && "
          f"[finish] X(c + 1) && [!finish] X(c))\n")
    for name, content in [("mutual_exclusion.mcf", p1),
                          ("deadlock_freedom.mcf", p2)]:
        with open(os.path.join(workdir, name), "w", encoding="utf-8") as f:
            f.write(content)


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
    if rc != 0:
        print(f"  pbes2bool FAILED: {err[:300]}")
        return None, time.perf_counter()-t_start
    answer = out.strip().lower()
    verdict = True if answer == "true" else (False if answer == "false" else None)
    print(f"  pbes2bool  {t3:.3f}s  verdict={verdict}")
    return verdict, time.perf_counter()-t_start


if __name__ == "__main__":
    rc, out, err, _ = run_cmd(["mcrl22lps", "--version"])
    if rc == -1:
        print("mCRL2 not found.")
        sys.exit(1)
    print(f"mCRL2: {(out+err).strip().splitlines()[0]}")
    print()
    all_results = {}

    # N=5: full batch verification
    from extract_data import load_corridor_trains, select_density_subset, tag_fastest_as_premium
    from mcrl2_gen import generate_mcrl2_spec
    trains_full = load_corridor_trains()
    for n in [5]:
        subset = select_density_subset(trains_full, n)
        tag_fastest_as_premium(subset)
        spec = generate_mcrl2_spec(subset, out_path=f"snapshot_n{n}.mcrl2")
        write_property_files(subset, ".")
        print(f"=== N={n} ===")
        print("P1: Mutual Exclusion")
        v1, t1 = verify_snapshot(spec, "mutual_exclusion", ".")
        print("P2: Deadlock Freedom")
        v2, t2 = verify_snapshot(spec, "deadlock_freedom", ".")
        total = t1 + t2
        all_results[n] = (v1, v2, total)
        print(f"N={n} total: {total:.4f}s")
        print()

    # N=12: disjoint partitions; cross-partition interactions are not checked.
    print("=== N=12 (2 disjoint 6-train partitions) ===")
    subset_12   = select_density_subset(trains_full, 12)
    tag_fastest_as_premium(subset_12)
    items       = list(subset_12.items())
    windows     = [dict(items[:6]), dict(items[6:])]

    total_w_time = 0.0
    all_verdicts = []
    for wi, window in enumerate(windows):
        spec_path = f"snapshot_n12_w{wi}.mcrl2"
        generate_mcrl2_spec(window, out_path=spec_path)
        write_property_files(window, ".")
        print(f"Window {wi+1} ({len(window)} trains):")
        print("P1: Mutual Exclusion")
        v1, t1 = verify_snapshot(spec_path, "mutual_exclusion", ".")
        print("P2: Deadlock Freedom")
        v2, t2 = verify_snapshot(spec_path, "deadlock_freedom", ".")
        total_w_time += t1 + t2
        all_verdicts.append((v1, v2))
        print(f"Window {wi+1} total: {t1+t2:.4f}s")
        print()

    print(f"N=12 partition total: {total_w_time:.4f}s")
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
