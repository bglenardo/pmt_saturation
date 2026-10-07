# Changelog

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
