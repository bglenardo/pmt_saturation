# Changelog

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
