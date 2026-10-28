# Changelog

## 2026-10-28: round-3 results (new light geometry, 250 ns short pulses)

**Added**
- **`results/saturation_r3_2026-10-27/`:** A/B light ratio against drive and regime after the geometry change;
  short (250 ns, up-sweep only) and long linearity of PMT A with dynode 8. Main findings: k ≈ 28 short against
  ≈ 10–14 long (regime dependence unchanged), and a one-off shift of the light split during the run.
- **`sat_analysis.ab_ratio()`** (A/B where both PMTs are linear, weighted mean and drive slope) and
  **`sat_plots.plot_ab_ratio()`**, with a synthetic-data test.
- `scripts/ab_ratio_check.py`, `scripts/r3_short_by_sweep.py`, `scripts/r3_writeup.py` (saved data only).
- `run_r2_chain.sh`: `OUT=<dir>` selects the output directory.

**Changed**
- **Short pulses are 250 ns** (`SHORT_WIDTH_S`, `short_regime(w)` in `saturation_r2.ipynb`); windows follow the
  width. The ratio cell no longer hard-codes 100 ns, and `load_scan` refuses files recorded with another width.
- **Ratio-scan zero-PE threshold fixed at 0.25·Q1** (`RATIO_THRESHOLD_Q1`): the 3·MAD σ threshold was at or
  above A's Q1 in the 400 ns window (k 29.5 → 27.8). The k json records the threshold.
- Round-3 LED schedules for the ratio, short and long scans (round-2 ones kept in comments).

## 2026-10-08 (evening): round-2 results

**Added**
- **`results/saturation_r2_2026-10-08/`:**
  - joint occupancy scan (k = 2674 ± 250; A and B charge/Q1 agree with their zero-PE μ);
  - short and long scans of PMT A with Ch4 = dynode 8 at 50 Ω and 1 MΩ;
  - matched light scale; linearity of anode and dynode 8; Ch1/Ch4 shape overlays.
- **`ad3pulse.saturation.smooth_log_spline` and `sat_analysis.light_scale_matched`** (with a pre-knee window
  for long pulses), plus notebook `LIGHT_MODE` / `MATCH_A_WINDOW`.
- `RigolScope.drain()`, `pytest.ini`, `scripts/rigol_replay_check.py`, and `run_r2_chain.sh [Q1_A Q1_B]`.

**Changed**
- **Auto-range:** hysteresis (step down only within 60 % of the finer scale), and it never aborts a run.
- **Scope:** read-back of scale/offset after every change, zero offset at 1 MΩ, and memory depth verified on
  open.

## 2026-10-08: round-2 code (k scan, Ch4 dynode-8 pickoff, finer scans); tested offline only

**Added**
- **`saturation_r2.ipynb`** (round 2; `saturation.ipynb` stays as the round-1 notebook). It records Ch4 = PMT A
  dynode 8 (4.7 nF pickoff) at each LED point, **first at 50 Ω, then at 1 MΩ**.
  - The 1 MΩ recordings stop at `CH4_1M_STOP_V` = 3 V and are skipped at every brighter point. Each new step is
    predicted from the previous one before switching.
  - Cells: `replay_test` (MAX against NORM replay), `ratio` / `ratio_analyze` (joint occupancy scan for k),
    timing, the scan (finer LED steps), and the analysis.
  - Long-pulse window: −5 … +15 µs.
- **`ad3pulse/sat_analysis.py`:**
  - per-recording summaries: anode and dynode charge, peak, FWHM, rise and late/early; the 1 MΩ step; B photon
    counts;
  - the joint occupancy k (`ratio_k`);
  - the smooth light scale (`light_scale`, `b_measure`, `fit_k_prefix`);
  - per-metric linearity.
- **`ad3pulse/sat_plots.py`:**
  - the ratio-scan plot;
  - response against LED voltage (pulse area and height);
  - A against B with the light curve;
  - linearity of all metrics;
  - Ch1/Ch4 shape overlays and the Ch4/Ch1 ratio, plus the 1 MΩ step against ∫anode;
  - shape metrics.
- **`ad3pulse/saturation.py`:** `step_height`, `count_pulses`, `smooth_log_fit` (refit with model weights to
  avoid a low-signal bias), `align_shift` and `rise_time`.
- **`ad3pulse/acquire.py`:**
  - per-channel polarity, with the offset flipped for positive pulses;
  - per-channel impedance with its own V/div ladder; `ScopeSession.set_impedance()` remembers each impedance's
    scale;
  - per-channel peak limits, with `PeakLimitExceeded.channel`;
  - `autorange(channels=...)` and `replay_mode`.
- **`RigolScope.record_frames(mode=...)`:** NORM (default) or MAX.
- **Tests:** 49 in total, including `tests/test_sat_analysis.py` and `tests/test_r2_take_point.py`. The latter
  runs the notebook's `take_point` 1 MΩ stop logic against the fake scope.
- `results/occupancy_2026-10-08/`: both PMTs' occupancy curves from the SPE scans. A's charge above 1.84 V was
  clipped in that scan, so it gives no k.

**Changed**
- `crossing()` needs the final run below the level to have at least 2 points.

## 2026-10-07 (evening): new PMT B, full saturation run

**Added**
- **`results/saturation_2026-10-07_newB/`:** SPE calibration of A and the new B, and the saturation of A against B
  for 100 ns and 10 µs pulses.
  - 100 ns: 5 % low at ~24.5 mA peak; the peak saturates at ~38 mA.
  - 10 µs: linear to ≥ 32 nC per pulse, collapsing after ~55 nC.
- **`scripts/run_saturation_chain.sh`:** unattended calibration → short scan → long scan → HV off (EXIT trap).
- **`ad3pulse.saturation`:**
  - `burst_frames()` rejects pickup bursts and non-LED triggers;
  - `light_scale()` combines the light scale (A at low light, k·B above);
  - `linearity(fit_mask=...)` takes an explicit set of fit points.
- **`saturation.ipynb`:**
  - burst rejection, and subtraction of a same-width control window;
  - low-light points are included in the fit;
  - per-regime pre/control windows;
  - the k fit runs over the lowest-B points up to the first failed linearity cut;
  - the timing cell carries on if the peak guard trips.

**Changed**
- PMT B was replaced by a tube of the same type as A, at −1550 V. Both notebooks were updated (`HV_EXPECTED_V`,
  labels, B scan range).
- `crossing()` returns the point where the deviation stays below the level, ignoring single noisy dips.
- The short-regime B-FWHM check is informational only: the LED's pulse shape changes with drive.
- `run_spe_notebook.py` writes line-buffered stdout, so logs update live.

**Found**
- NORM-mode replay returns only ~1000 screen points, so the long record is sampled at 50 ns.
- A VS Code Jupyter kernel can hold the AD3 lock, even across a USB replug.

## 2026-10-07 (later): saturation studies, code, notebook and first hardware look

**Added**
- **`ad3pulse/acquire.py`:** `ScopeSession` (scope settings, LED amplitude, frame recording with reconnect/retry,
  raw saves with metadata), per-point vertical `autorange()` over a 1-2-5 V/div ladder, and a hard peak guard
  on the 50 Ohm inputs (`check_peaks()` raises `PeakLimitExceeded`).
- **`ad3pulse/saturation.py`:** `peak_current`, `binned_charge`, `fwhm`, `summarize_point`, `linearity`
  (A against reference B), `crossing`, `shape_ratio`, `late_early` (with error) and `flag_reference`.
- **`saturation.ipynb`:** two regimes, short (100 ns, space charge) and long (10 us, base-capacitor depletion),
  at < 5 Hz. Cells: timing, reach (quick guarded ramp), scan (up then down), load_saved, analyze (linearity,
  5 %/10 % points, pulse shapes, A(t)/B(t) droop, PMT B self-check).
- **`scripts/run_spe_notebook.py`:** `--notebook` option and a generic `cells` mode (`--hv-off` optional).
- **Tests:** `tests/test_saturation.py` (synthetic saturation and droop, reference flag, auto-range and peak
  guard against a fake scope).
- **`saturation.ipynb` `lowlight` cell:** 1000 pulses per point at 10 Hz for the A/B slope (user allowed 10 Hz
  where A is far from saturation).
- **`results/saturation_short_2026-10-07/`:**
  - PMT A's peak anode current flat-tops at ~39 mA at −1550 V (not scope clipping);
  - PMT B is too noisy to serve as the reference (~2 mV rms pickup, ~100 MHz bursts). The user is swapping it.

**Changed**
- The peak guard `MAX_PMT_PEAK_V` is 3 V (the user's choice; the 50 Ω input is rated 5 Vrms).

**Fixed**
- **`RigolScope.record_frames()` recorded untriggered frames at slow trigger rates.** After a recording, a bare
  `:RUN` left the scope free-running (status `AUTO`) despite `:TRIG:SWE? NORM`. It now re-sends
  `:TRIG:SWE NORM` + `:RUN` and waits for `WAIT`/`TD` first. The 1 kHz SPE data was unaffected (all scan frames
  contain the LED pulse).

## 2026-10-07: SPE calibration

**Added**
- **`AnalogDiscovery.start_pulse_train(pulse, rate_hz)` and `set_pulse_amplitude()`:** a free-running AD3
  pulse train (one short AWG period plus an AWG wait at 0 V, repeated until stopped). It keeps the 8 ns
  steps at kHz rates, and the amplitude can be changed while it runs.
- **`RigolScope.record_frames()` → `FrameSet`:** hardware frame recording (`:RECord:WRECord`) and per-frame
  readback. `FrameSet` stores raw int16 codes plus preambles, and has `save()`/`load()` for `.npz` and a
  `volts(ch)` helper.
  - Also added: `RigolScope.set_trigger_sweep()` and `max_record_frames()`.
- **`ad3pulse/spe.py`:**
  - `baseline_subtract` (per-frame or per-run) and `integrate_charge` (pC);
  - zero-PE `occupancy` with control-window dark subtraction;
  - `pick_amplitude` (interpolates log μ);
  - `fit_spe` (pedestal + Poisson-weighted n-PE Gaussians, via scipy).
- **`spe_calibration.ipynb`:**
  - tagged cells: parameters, connect, timing, scan, choose, calibrate, load_saved, fit, close, emergency;
  - HV is checked but never changed;
  - the scope reconnects and retries if the LAN connection drops;
  - an optional `load_saved` cell re-fits saved runs without hardware.
- **`scripts/run_spe_notebook.py`:** runs notebook cells headless by tag. Modes: `scan`, `cal`, `final`
  (then HV off), `refit`, `off`.
- **`results/spe_2026-10-07/`:** first SPE calibration.
  - PMT A: Q1 = 0.949 pC, gain 5.9e6.
  - PMT B: Q1 = 0.492 pC, gain 3.1e6.
- **Tests:** `tests/test_spe.py` (synthetic Poisson data), plus frame-recorder and `FrameSet` round-trip tests.
- **Dependency:** `scipy` in `requirements.txt`.

**Changed**
- **The Rigol now defaults to the raw SCPI socket `TCPIP0::<ip>::5555::SOCKET` instead of VXI-11.** VXI-11
  stopped answering after sessions that ended abruptly; the socket is also faster.
- **`RigolScope.arm_single(allow_early=...)`** waits for a real `WAIT`/`TD` after `:SINGle` instead of
  accepting a stale `STOP`.
- **`CLAUDE_CODE_NOTES.md` was renamed to `CLAUDE.md`** and rewritten as the full project handoff.
- **README** rewritten for the current Ethernet / LED / SPE setup.

**Fixed**
- `set_pulse_amplitude()` stopped the AD3 train (AutoConfigure resets the run); it now restarts it.
- Replay frames read before the scope switched frames returned the previous frame; fixed with `*OPC?` after
  each frame selection.
- Fit output crashed on a cp1252 console; the runner reconfigures stdout to UTF-8.

**Hardware settings at this point**
- ISEG ch0 = −1550 V and ch1 = −875 V, both with a 50 µA limit (the stored set values on the supply).
- Rigol Ch1/Ch2 at 50 Ω, Ch3 = pulser.

## 2026-09-29: Ethernet instruments and HV control (commit 75949a7)
- **`IsegHV` rewritten from the iseg SCPI guide:**
  - raw TCP port 10001;
  - `cmd;*OPC?` orders, empty-line skipping, unit-suffixed replies (`parse_iseg_value`);
  - status bits and faults, `wait_stable`, `wait_off`;
  - signed VSET from the channel polarity.
- **`hv set|off|status` CLI**, separate from capture.
- **`RigolScope`:** Ethernet (VXI-11 at the time) with connect retries, `force_trigger`, empty-readout
  check, and the stale-`STOP` fix for `:SINGle`.
- **`rigol-single` CLI:** fire one AD3 pulse and capture Ch1/Ch2 on the Rigol to raw CSV.
- **`pmt_bias_test.ipynb`:** verified −100 V on ch0/ch1, one acquisition, then ramp down.
- Vendor manuals in `Documentation/` are gitignored.

## Initial commit (4f45579)
- AD3 pulse generation and 2-channel capture toolkit: `single`, `sweep`, `repeat`, `gui`, and the overlay
  notebook.
