# OVR Framework — Real Working System

This is the real, working implementation of the Optimize–Verify–Repair
pipeline described in your paper, built on your actual
`Train_details_22122017.csv` dataset. Every number this system produces
is genuinely measured — no fabricated data.

---

## 1. What's in this folder

| File | What it does | Status |
|---|---|---|
| `Train_details_22122017.csv` | Your real dataset | ✅ included |
| `extract_data.py` | Pulls real SWV/THVM/KRMI trains, builds N=5/12/25/50 tiers | ✅ tested, works |
| `cpsat_model.py` | Real OR-Tools CP-SAT model (constraints C1–C4) | ⚠️ needs OR-Tools installed |
| `mcrl2_gen.py` | Writes real `.mcrl2` process specification files | ✅ tested, works |
| `run_mcrl2.py` | Runs the real mCRL2 toolchain (mcrl22lps → lps2pbes → pbes2bool) | ⚠️ needs mCRL2 installed |
| `repair_adapter.py` | Algorithm 1 loop — orchestrates Optimize→Verify | ⚠️ partial (see Known Gaps) |
| `run_all.py` | Runs all 4 density tiers, writes real `table_I_real_results.csv` | ⚠️ needs both tools installed |

---

## 2. IMPORTANT — An honest finding about your dataset

When building the density tiers, I discovered your CSV contains only
**30 distinct real trains** with valid stops at SWV/THVM/KRMI on this
single-day snapshot (22-Dec-2017) — not 50+.

- **N=5 and N=12** → 100% real, distinct trains from your CSV.
- **N=25 and N=50** → all 30 real trains, plus additional trains built by
  **time-shifting copies** of real trains (same real dwell times, same
  real travel times, same real distances — only the clock-start shifts).
  Each is labeled clearly, e.g. `10103-R0`.

**You must add one sentence to your paper's Section III-C disclosing this.**
Suggested text:

> *"For density tiers exceeding the 30 distinct real corridor trains present
> in the single-day dataset snapshot (N=25, N=50), additional train
> instances were constructed by time-shifting real corridor trains'
> complete event sequences (preserving all real dwell times, travel times,
> and distances) to simulate higher traffic density, consistent with
> standard scheduler stress-testing practice [3]."*

---

## 3. Setup — Step by Step

### Step 3.1 — Install Python dependencies

Open a terminal on **your own machine** (not this chat) in this folder, and run:

```bash
pip install pandas ortools
```

If you're on Linux and get a "externally managed environment" error:

```bash
pip install pandas ortools --break-system-packages
```

### Step 3.2 — Install mCRL2

Download the installer for your OS from:
**https://www.mcrl2.org/web/user_manual/download.html**

- **Windows/macOS:** run the installer, it adds mCRL2 to PATH automatically.
- **Linux (Debian/Ubuntu):**
  ```bash
  sudo apt update
  sudo apt install mcrl2
  ```

### Step 3.3 — Verify both installs worked

```bash
python3 -c "import ortools; print('OR-Tools OK')"
mcrl22lps --version
```

If both print without error, you're ready.

---

## 4. Running the System — In Order

Run each stage individually first, to confirm each one works before
running the full pipeline.

### Stage 1 — Test data extraction (no external tools needed)

```bash
python3 extract_data.py
```

**Expected output:** Lists of real trains for N=5, 12, 25, 50, with station
sequences and priority weights. This should work immediately since it
only needs pandas.

### Stage 2 — Test OR-Tools CP-SAT (needs OR-Tools installed)

```bash
python3 cpsat_model.py
```

**Expected output:** A line per density tier showing solver status,
real solve time, variable count, and objective value:

```
N=  5  status=OPTIMAL    solve_time=0.0XXXs  vars=...  constraints=...  objective=...
N= 12  status=OPTIMAL    solve_time=0.0XXXs  ...
```

These solve times are your **real** "OR-Tools (s)" column for Table I.

### Stage 3 — Test mCRL2 spec generation (no external tools needed)

```bash
python3 mcrl2_gen.py
```

**Expected output:** Writes `snapshot_n5.mcrl2` and prints the first
2000 characters of it. This should work immediately.

### Stage 4 — Test the real mCRL2 toolchain (needs mCRL2 installed)

```bash
python3 run_mcrl2.py
```

**Expected output:** mCRL2 version detected, then real verdict and timing
from running `mcrl22lps` → `lps2pbes` → `pbes2bool` on the N=5 snapshot.

**If this fails:** the error message will tell you exactly which mCRL2
binary wasn't found — that means mCRL2 isn't correctly on your PATH yet.
Re-check Step 3.2.

### Stage 5 — Test the repair loop orchestration

```bash
python3 repair_adapter.py
```

**Expected output:** A JSON dump showing OR-Tools time, mCRL2 time, and
verdict for N=5, run through the actual loop structure from Algorithm 1.

### Stage 6 — Run everything, get your real Table I

```bash
python3 run_all.py
```

**Expected output:** Runs all four density tiers end-to-end and writes
`table_I_real_results.csv` with your genuinely measured numbers, plus
prints a clean summary table to paste into your paper.

---

## 5. Known Gaps — What's NOT Fully Automated Yet

Being upfront about exactly what still needs work, so you don't
accidentally present incomplete pieces as finished:

1. **Trace extraction via `lpsxsim`** (Algorithm 1, lines 6–9) is a
   marked integration point in `repair_adapter.py`. The exact CLI flags
   for non-interactive trace extraction differ across mCRL2 versions.
   **Once you run `lpsxsim --help` on your installed version, send me
   the output and I will complete this so the repair loop runs
   end-to-end automatically.**

2. **State Transitions Explored** column is not yet computed — needs
   parsing `pbes2bool -v`'s verbose output for state-space size. Marked
   with instructions in `run_all.py`'s bottom comment block.

3. **Weighted Delay Cost (Baseline vs OVR)** columns are not yet wired
   up — the calculation logic is described in `run_all.py`'s comments;
   it needs about 15 lines of code to compute baseline cost from raw CSV
   times vs. the CP-SAT objective value already computed in
   `cpsat_model.py`.

**Do not copy old fabricated numbers for these three columns into your
final paper.** Either complete the wiring (I can help — send results from
Stage 6 first) or omit those columns and report only what this system
actually measures: OR-Tools time, mCRL2 time, total pipeline time, and
repair iteration count.

---

## 6. What To Send Me Next

Run Stages 1 through 6 in order. At whichever stage something fails,
**copy-paste the exact error message** back to me — don't try to debug
silently, since some failures (especially Stage 4) depend on your
specific mCRL2 version's exact CLI behavior, which I can't predict
without seeing the real output from your machine.

Once Stage 6 succeeds, send me `table_I_real_results.csv` and I will
help you write the corrected, fully honest Table I and Table II for
your paper, plus the corrected Abstract/Section VI language to match.