# Plan: PMT A saturation, round 2 (k from occupancies, finer knee scans, better long-pulse sampling)

## Context
The first full run (`results/saturation_2026-10-07_newB/`) gave PMT A's limits:
- **short (100 ns):** 5 % low at ~24.5 mA;
- **long (10 µs):** linear to ≥ 32 nC, collapsed by ~55 nC.

Weak points of that run:
- **k is poorly known.** The A/B light ratio is k = 1779 ± 11 % (short) and 677 (long). The two disagree and
  come from only 2–3 noisy points.
- **The knees fall in coarse LED gaps.** Long: 1.811 → 1.898 V. Short: 2.0–2.2 V.
- **B is barely measurable** at the points where the slope is fixed.
- **Long pulses read back at 50 ns sampling.** NORM replay returns only the ~1000 screen points, so B can't be
  photon-counted.

**Why A is missing from the occupancy plot:** the combined SPE scan (A, then B) was stopped partway through B.
The restarted scan covered B only, with A's list empty. A's scan files (`runs/spe/scan_ch1_*_20261007_171831.npz`)
still exist.

**User's requests:**
1. Measure the relative occupancies to pin down k before relying on it.
2. Redo both saturation scans with finer LED steps around the knees.
3. Plot each PMT's pulse height and area against LED voltage, as well as A against B.
4. Rely on B more cleverly: put finer steps and more pulses where B's errors are small but A is still linear.
5. For long pulses, keep waveforms with ~5 µs before and ≥ 5 µs after each pulse, for later pulse-model fits.
6. Improve the long-pulse sampling so B's light is measured better.

7. **Added later:** the scope's **Ch4 now picks off dynode 8 through a 4.7 nF capacitor.** Include it in
   acquisition and analysis, to see whether it stays linear further than the anode in both regimes. Measure it
   at **50 Ω and at 1 MΩ**. **Stop the 1 MΩ measurements once Ch4 reaches ~3–4 V in the long-pulse scans:** the
   integrated charge on the pickoff becomes too large for the scope.

The user asked to commit first.

## Steps

### 0. Commit the current state (first)
- One commit on `main`. It contains:
  - `results/saturation_2026-10-07_newB/`;
  - `scripts/run_saturation_chain.sh`;
  - the notebook, analysis and test changes;
  - the `CLAUDE.md`, `CHANGELOG.md` and `README.md` updates.
- `.vscode/` and `Untitled-7.ipynb` stay untracked.

### 1. Occupancy plot with both PMTs (analysis only): DONE 2026-10-08
`results/occupancy_2026-10-08/occupancy_both_pmts.png`. The SPE scan recorded **both channels at every point**, but
**A's charge is clipped above 1.84 V**: the SPE notebook uses a fixed 10 mV/div (±40 mV), so A's charge there isn't
valid and no k can be taken from that scan. **Step 3 must auto-range each channel.**
- **B:** charge/Q1 matches zero-PE μ within a few % (0.30/0.29, 0.46/0.43, 0.95/0.94).
- **A:** charge/Q1 is ~10 % above μ. This is likely SPEs lost below A's zero-PE threshold; step 3 checks it.
- The two μ curves don't overlap in LED voltage and have different log-slopes, so k can't be read off by shifting
  one onto the other.

### 1 (original plan). Occupancy plot with both PMTs
- Re-plot the saved SPE scans with both PMTs on one μ-against-LED-voltage plot:
  - A from `20261007_171831`;
  - B from `20261007_171831` (1.70–1.74 V) and `180248` (1.84–2.10 V).
- Reuse `occupancy()` and `pick_amplitude()` from `ad3pulse/spe.py`.
- Add it to the results folder.

### 2. Hardware check: full-memory replay and the new long window (~15 min)
- **Long window:** 2 µs/div with time offset +5 µs, giving **−5 … +15 µs**. That's 5 µs before the 10 µs pulse
  and 5 µs after it, as requested. At NORM's 1000 points this is already 20 ns sampling.
- **Test `:WAV:MODE MAX` on replay frames.** The guide (§3.28.2) says MAX reads *internal memory* when the scope is
  stopped.
  - Record ~20 dim-light frames with 20k depth, giving 1 ns over 20 µs.
  - Read each frame in MAX and in NORM, and check that the frames differ from each other: RAW once returned
    the same frame every time.
  - Check that MAX decimated agrees with NORM for the same frame, and measure readout time per frame.
- **Code:** a `mode` argument on `RigolScope.record_frames()` (`ad3pulse/hardware.py`; default NORM, so current
  behaviour is unchanged), plus a fake-scope test.
- **Choice:** MAX at 20k points if it works and is fast enough; otherwise NORM with the 20 µs window (20 ns).

### 3. k from a joint occupancy/charge scan (100 ns pulses, 10 Hz; ~1.5–2 h)
- **New `ratio` cell in `saturation.ipynb`.** It sweeps the LED over 1.66–2.06 V with Ch1 and Ch2 recorded at
  every point; Ch3 only on a few frames, to speed up readout. Per point it saves:
  - μ_A from A's zero-PE occupancy (valid at μ ≲ 3) and A's mean charge in PE;
  - μ_B from B's occupancy and B's mean charge.
- **Pulses per point,** chosen so that μ_B is known to ~4–6 %:
  - ~500 where only A is measured (1.66–1.84 V);
  - ~3000–5000 where μ_B ≈ 0.03–0.5 (1.86–2.04 V, 20 mV steps).
- **k = A PE / μ_B** over the points where A ≤ ~500 PE (A still linear). Report a plot of k against LED voltage
  (flat until A bends) and the weighted mean.
- **Cross-checks:**
  - A's charge in PE against μ_A where both are valid. This checks that Q1-based PE agree with photon counting.
  - B's charge against μ_B. Correct μ_B for SPE loss below the threshold using the fitted Q1 and σ1 (≈ 0.5 %
    for the new B).
- **Plot:** the requested two-PMT occupancy plot, with μ and mean PE against LED voltage for A and B.

### 4. Finer saturation scans, both regimes (4 Hz, unattended; ~2.5 h)
- **Short:**
  - LED 1.72–1.90 V in 30 mV steps (A linear, B ~ 0);
  - **1.90–2.20 V in 10 mV steps** (B 0.05–1 PE, plus the knee);
  - 2.20–2.40 in 40 mV;
  - 2.4–3.0 in 0.1 V.
  - 400 pulses per point in the 10 mV band, 200 elsewhere.
- **Long (new window and sampling from step 2):**
  - 1.57–1.74 V coarse;
  - **1.74–1.92 V in 10 mV steps** (knee);
  - 1.92–3.0 coarse.
  - 300 pulses per point in the knee band, 150 elsewhere.
- **Both:** up-sweep plus a down-sweep over every second point; burst rejection; 3 V peak guard.
- **Chain:** an updated `scripts/run_saturation_chain.sh` runs the ratio scan, then short, then long, then HV off
  (EXIT trap). Q1 comes from the 2026-10-07 calibration (0.904 / 1.09 pC), or from a quick re-calibration if
  the user wants one.

### 4b. Ch4: dynode-8 pickoff (4.7 nF), at 50 Ω and 1 MΩ
- **Acquisition** (applies to step 4, and to the ratio scan in step 3 if useful). At each LED point, record twice
  with the same light:
  1. **Ch4 at 50 Ω**, together with Ch1, Ch2 and Ch3;
  2. then switch `:CHAN4:IMP OMEG` and record **Ch4 at 1 MΩ** (Ch1 and Ch2 again, so that every recording has
     its own light reference).
- Interleaving per point avoids LED drift between the two impedances. Switch back to 50 Ω before the next point.
- **Polarity:** the dynode signal is **positive** (opposite to the anode).
  - The auto-range, the peak guard and `screen_range()` (`ad3pulse/acquire.py`) currently assume negative pulses.
  - Add a per-channel polarity to `ScopeSettings`. It flips the offset sign, so a positive pulse gets 7 of 8
    divisions.
  - Burst checks and the peak guard use |V|.
- **Scales:** 50 Ω allows up to 1 V/div (offset ±1 V or ±4 V); 1 MΩ allows up to 10 V/div. Each needs its own
  ladder and offset limits (datasheet p. 11).
- **Safety rules:**
  - **Ch4 at 50 Ω** obeys the same 3 V peak guard as the anodes.
  - **Ch4 at 1 MΩ: once |V| ≥ `CH4_1M_STOP_V` (default 3 V; the user said 3–4 V), skip the 1 MΩ recordings at
    every brighter point** in that sweep and its down-sweep. Apply this in both regimes; the user's concern is
    the long pulses.
  - Probe at 50 Ω first. Predict the 1 MΩ step as V ≈ Q_dyn / C (C = 4.7 nF plus cable and input
    capacitance), from the 50 Ω charge, and don't switch to 1 MΩ if the prediction is above the limit.
- **The 1 MΩ trace** is a step that decays slowly: RC ≈ 1 MΩ × ~5 nF ≈ 5 ms, well within the 250 ms between
  pulses at 4 Hz.
  - Its observable is the **step height** ΔV: the mean over a plateau window after the pulse, minus the
    pre-pulse baseline. ΔV ∝ dynode charge.
  - For long pulses the record must reach ≥ 5 µs after the pulse; the new window ends at +15 µs, which is enough.
- **Analysis:**
  - **Ch4 at 50 Ω:** charge (+∫V dt / 50 Ω) and peak.
  - **Ch4 at 1 MΩ:** ΔV.
  - Each metric gets its own linearity curve against the light scale (k·B_fit), using
    `linearity(fit_mask=...)` with the scale fitted at low light.
  - Compare the deviation curves of the anode, Ch4 at 50 Ω and Ch4 at 1 MΩ. Show where each departs by 5 % and
    10 %, in both regimes.
- **Code:** `ScopeSettings` (polarity, per-channel impedance), a `ScopeSession` impedance switch and the
  1 MΩ-stop logic, plus fake-scope tests for both.
- **Dynode-8 analysis and plots (user's request):**
  - **Linearity plots:** the dynode-8 metrics go on the same plots as the anode. These are Ch4 50 Ω charge,
    Ch4 50 Ω peak and Ch4 1 MΩ step ΔV, each normalised by its own low-light scale factor.
    - The panels show deviation against true light, and against anode peak current (short) or charge (long).
    - Each metric gets its own marker and colour, with up- and down-sweeps distinguished.
    - The 5 %/10 % crossings for each metric are printed and tabulated in the README.
  - **Response against LED voltage:** the per-PMT pulse-height and pulse-area plots (step 5) also get the Ch4
    curves.
  - **Pulse shapes, Ch1 against Ch4:** overlay A's anode (Ch1) and dynode-8 (Ch4, 50 Ω) mean waveforms for
    selected light levels, in both regimes.
    - Use one panel per light level: about 6 levels from linear, through the knee, to deep saturation.
    - Plot the anode current and the dynode current, each normalised to its own peak, or to the area of the
      low-light shape. The dynode signal is positive and the anode negative, so flip the sign for the comparison.
    - Align the two in time with the cross-correlation at low light, since the cables differ.
    - Also include one summary panel of the ratio Ch4(t) / Ch1(t) against time at each level. If the dynode stays
      linear while the anode saturates, the ratio will grow where the anode flat-tops (short) or collapses (long).
    - For 1 MΩ, also overlay the step shape, normalised, against the integral of Ch1's current.
  - **Pulse-shape metrics** against light: FWHM (short), late/early (long) and rise time. Plot them for Ch1 and
    Ch4 side by side.

### 5. Analysis upgrades (`ad3pulse/saturation.py`, `saturation.ipynb`)
- **Fixed k:** use k from step 3 (`K_FIXED` parameter, with its error) instead of re-fitting it on noisy scan
  points.
- **Smooth light curve:** where B is significant, fit log B(V) with a smooth monotone function of LED voltage
  (e.g. a cubic in V, or a monotone spline). Light = k·B_fit(V), and A is assumed linear below the B threshold.
  This uses every point, which is the "smarter" way to rely on B. The up- and down-sweeps check that the LED
  didn't drift.
- **Long pulses, B photon counting:** where sampling allows (step 2), count B's SPE pulses in 0–10.5 µs (threshold
  ~5 mV, against an SPE of ~11 mV and noise of 1.4 mV). Subtract a scaled pre-window count. Use charge above
  ~100 PE, where pulses pile up.
- **Pedestal:** with only a 5 µs pre-window, scale the pre-window charge to the signal width instead of using a
  same-width control.
- **New plots** for each PMT and regime:
  - pulse height (peak mA) against LED voltage;
  - pulse area (PE) against LED voltage;
  - plus A against B, and the deviation against light, peak current or charge.
- Raw waveforms for every point are already saved in full (`FrameSet` `.npz`); nothing changes there.

### 6. Write-up
- `results/saturation_<date>/README.md` with the new k, the knee positions, and the plots.
- Update `CLAUDE.md` and `CHANGELOG.md`, then commit.

## Critical files
- **Changed:**
  - `ad3pulse/hardware.py` (`record_frames(mode=...)`);
  - `ad3pulse/saturation.py` (smooth light curve, photon counting, scaled pedestal);
  - `saturation.ipynb` (ratio cell, new long window, plots, fixed k);
  - `scripts/run_saturation_chain.sh`;
  - tests in `tests/`.
- **Reused:**
  - `occupancy`, `pick_amplitude`, `baseline_subtract` and `integrate_charge` (`ad3pulse/spe.py`);
  - `burst_frames`, `linearity`, `light_scale` and `crossing` (`ad3pulse/saturation.py`);
  - `ScopeSession` and `autorange` (`ad3pulse/acquire.py`).

## Outcome (2026-10-08 evening)
**Round 2 is done.** See `results/saturation_r2_2026-10-08/README.md`.
- The plan was carried out, with two changes:
  - the light scale is **matched** (B spline × k fitted where A is linear), not the fixed ratio-scan k;
  - long pulses use NORM 1000-point replay at 20 ns (full-depth replay isn't possible), so B is measured by
    charge, not counting.

## Progress (2026-10-08)
- **Steps 0–1:** done.
- **Code for steps 2–5:** written and tested offline in `saturation_r2.ipynb`, `ad3pulse/sat_analysis.py` and
  `ad3pulse/sat_plots.py`.
- **Next, on hardware** (HV on, box dark):
  1. `replay_test`, to choose MAX/20k or NORM/1k for long pulses;
  2. then the unattended chain: SPE calibration → ratio scan → short scan → long scan → analysis → HV off.

## Decisions (user, 2026-10-08)
- **Ch4 is PMT A's dynode 8.**
- **1 MΩ stops at 3 V** (`CH4_1M_STOP_V = 3.0`).
- **1 MΩ is recorded at every LED point** (until the stop).
- **SPE re-calibration of both PMTs first**, at the start of the run.

## Hardware prerequisites
- **HV is off now.** Before step 2: confirm the box is dark, then ramp both channels to −1550 V with
  `python -m ad3pulse hv set 1550 --channel 0/1 --current 50e-6`.
- Close the VS Code Jupyter kernel if it has the AD3 open.

## Verification
- `pytest`: the existing 39 tests plus new ones for MAX-mode recording, photon counting, the smooth light fit
  and the scaled pedestal.
- **Step 2:** MAX frames differ from frame to frame and agree with NORM after decimation. Readout time is noted.
- **Step 3:** k is flat against LED voltage below A's knee. A's PE (charge) agree with μ_A (occupancy) within a
  few %, and so do B's charge and μ_B.
- **Step 4:** the down-sweep reproduces the up-sweep, and the knee positions now have uncertainties.
- **HV off** at the end, confirmed by `hv status`.
