# PMT saturation experiments: `ad3pulse`

Project notes for Claude Code (loaded automatically from the repo root). This file is the
handoff: hardware, how to run things, the hard-won instrument quirks, the user's working
preferences, and current status. Keep it up to date when something changes; record the change
history in `CHANGELOG.md`.

## Purpose
Characterise two PMTs for saturation studies:
- an LED driven by short pulses provides the light;
- the PMT anode pulses are captured on a scope;
- calibration and physics analysis happen in notebooks.

The first milestone, **single-photoelectron (SPE) calibration of both PMTs, is done**
(`results/spe_2026-10-07/`). Saturation studies come next.

## Hardware and wiring

| Device | Role | Connection |
|---|---|---|
| Digilent Analog Discovery 3 | Pulse source only (AWG W1) | USB; needs the WaveForms runtime |
| Rigol MHO954 scope | All waveform capture | Ethernet **192.168.0.101**, raw SCPI socket port **5555** |
| ISEG SHR 40 60 HV (SR040060R4050000200) | PMT bias, 4 ch × 6 kV | Ethernet **192.168.0.100**, raw TCP port **10001** |
| Lab PC | | Ethernet adapter 192.168.0.102 on the instrument LAN |

- **LED drive:** AD3 W1 → tee:
  - one side → 330 Ω in series with the LED (turn-on ~1.6 V);
  - other side → **Rigol Ch3** (1 MΩ). This is the trigger.
- **PMT A** (higher voltage): ISEG **ch0**, negative polarity → **Rigol Ch1**, scope 50 Ω input.
- **PMT B** (lower voltage): ISEG **ch1**, negative polarity → **Rigol Ch2**, scope 50 Ω input.
  **Being replaced (2026-10-07):** the original B was too noisy (base design suspected). The ch1 operating
  point and B's SPE values below refer to the *old* PMT B.
- ISEG ch2/ch3 are positive polarity and unused.

**Operating points** (chosen by the user, 2026-10-06):
- ch0 = −1550 V, draws ~16.9 µA;
- ch1 = −875 V, draws ~14.0 µA (old PMT B);
- current limit **50 µA** on both. 20 µA was too tight: ch0 sat at 85 % of it.

The measured currents imply dividers of ~95 MΩ and ~65 MΩ. The user's first estimate was 200 MΩ; that was
wrong. The supply ramps at 25 V/s, so −1550 V takes about a minute.

## Working preferences (from the user)
- **Reference docs are the PDFs in `Documentation/`.** Don't download manuals from the web; if one is missing,
  ask the user to add it. The PDFs are gitignored (vendor copyright), so copy them by hand to a new PC.
- **HV control is separate from data capture.** Ramps are slow: bias with `hv set`, leave it on across
  captures, and switch off explicitly. Never ramp HV inside a capture command.
- **Before full voltage, confirm the PMTs are dark** (light-tight). Ask about the current limit too.
- **Acquisition code saves raw data only.** Baseline, charge, gain and fits belong in the notebooks and
  `ad3pulse/spe.py`.
- **Don't reintroduce AD3 capture** as the PMT measurement path. AD3 auto-ranging silently jumped to a
  coarse range and buried small signals in quantization noise.
- **When asked to finish unattended, switch the HV off at the end** (see Runbooks), and make the off step
  run even on failure.
- **Commits** go on `main`. The GitHub remote is `origin` = `bglenardo/ad3-pulse-lab`; the user pushes.

## Setting up on a new PC
1. **Python 3.10+.** The current PC runs 3.14.7. From the repo root:
   `python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`.
   For Jupyter, also `pip install ipykernel` and select the `.venv` kernel.
2. **Digilent WaveForms** (runtime 3.25.1 here) for the AD3; `dwf.dll` is loaded via ctypes. **Close the
   WaveForms GUI before running code**, or the device is locked ("Devices are busy").
3. **VISA:** none needed. `pyvisa-py` (pure Python) talks to both instruments over TCP; NI-VISA isn't used.
4. **Network:** give the PC's instrument-LAN adapter a 192.168.0.x address (not .100/.101). Check with
   `python -m ad3pulse hv status` and with `RigolScope().connect()` (prints the IDN).
5. **Data and docs to copy by hand:**
   - `Documentation/*.pdf` (manuals, gitignored);
   - `runs/` (raw data, gitignored; ~92 MB for the SPE runs) if you need to re-fit old data.
6. **Check:** `.venv\Scripts\python -m pytest -q`, which should pass 37 tests with no hardware needed.

## Repository layout
- `ad3pulse/`:
  - `instrument.py`: `PulseSpec` and `AnalogDiscovery`. Covers single pulses, the free-running
    **`start_pulse_train()` / `set_pulse_amplitude()`**, and the legacy AD3 capture code.
  - `hardware.py`: **`RigolScope`** (configure, single-shot, frame recorder `record_frames()` → `FrameSet`)
    and **`IsegHV`** (set/on/off, status bits, `wait_stable()`, `wait_off()`).
  - `spe.py`: analysis. Charge integration, zero-PE occupancy, `pick_amplitude()`, and the SPE fit `fit_spe()`.
  - `acquire.py`: **`ScopeSession`** (scope settings, LED amplitude, retrying frame recording, raw saves),
    per-point vertical **`autorange()`** and the 50 Ω **peak guard** (`check_peaks()` → `PeakLimitExceeded`).
    Used by the saturation notebook; the SPE notebook still has its own `record()`.
  - `saturation.py`: saturation analysis. Peak current, binned charge, `linearity()` against the reference PMT,
    `crossing()`, `shape_ratio()`, `late_early()` with errors, and `flag_reference()`.
  - `cli.py`: `python -m ad3pulse {list, single, sweep, repeat, gui, rigol-single, hv set|off|status}`.
  - `dwfapi.py`: ctypes wrapper for WaveForms (functions resolved by name).
  - `sweep.py`, `repeat.py`, `gui.py`: the legacy AD3-capture workflow.
- `spe_calibration.ipynb`: **the SPE calibration**. Code cells are tagged: `parameters`, `connect`,
  `timing`, `scan`, `choose`, `calibrate`, `load_saved`, `fit`, `close`, `emergency`.
- `pmt_bias_test.ipynb`: bias test. Ramp up, one Rigol acquisition, ramp down (`finally:`).
- `overlay_waveforms.ipynb`: overlays from the legacy AD3 sweep.
- `saturation.ipynb`: **saturation studies** (`REGIME = "short"` or `"long"`). Tags: `parameters`, `helpers`,
  `connect`, `timing`, `reach`, `scan`, `load_saved`, `analyze`, `close`, `emergency`.
- `scripts/run_spe_notebook.py`: runs notebook cells headless by tag (`scan`, `cal`, `final`, `refit`, `off`;
  `--notebook X.ipynb cells TAG,TAG [overrides] [--hv-off]` for any notebook).
- `results/<name>/`: committed summaries and plots (`spe_2026-10-07/` has the first calibration;
  `saturation_short_2026-10-07/` has the first short-pulse saturation look).
- `runs/`: raw data (gitignored). `runs/spe/` and `runs/saturation/` hold `FrameSet` `.npz` files and
  `*.log` run logs.
- `tests/`: pytest with fake instruments, plus synthetic-data tests for `spe.py` and `saturation.py`.

## Runbooks
**Bias the PMTs up** (confirm they're dark first):
```powershell
python -m ad3pulse hv set 1550 --channel 0 --current 50e-6 --no-wait
python -m ad3pulse hv set 875 --channel 1 --current 50e-6     # waits until stable
python -m ad3pulse hv set 1550 --channel 0 --current 50e-6     # confirms ch0 is stable
python -m ad3pulse hv status --channel 0
```
`hv set` takes a **magnitude**; the sign comes from the channel's polarity. It leaves the HV on when it exits.

**Switch HV off:** `python -m ad3pulse hv off --channel 0` (and `--channel 1`), or
`python scripts/run_spe_notebook.py off`, which also stops the AD3 and waits until both channels are below 5 V.

**SPE calibration:** in Jupyter, run `spe_calibration.ipynb` top to bottom. Or headless, with each stage
logged to `runs/spe/`:
```powershell
python scripts/run_spe_notebook.py scan > runs\spe\scan.log 2>&1        # prints the chosen amplitudes
python scripts/run_spe_notebook.py cal "{1: 1.6776, 2: 1.8613}" "CAL_FRAMES = 5000" > runs\spe\cal.log 2>&1
python scripts/run_spe_notebook.py refit                                  # re-fit saved data, no hardware
```
- **Timing:** about 70 s per 500-pulse scan point (3 channels) and about 690 s per 5000-pulse calibration
  chunk (1 channel, ~137 ms/frame).
- **Monitoring:** watch the log with a bounded loop; don't rely only on a completion notification. A crash went
  unnoticed overnight once.

**Saturation** (HV on, PMTs dark), headless, logged to `runs/saturation/`:
```powershell
python scripts/run_spe_notebook.py --notebook saturation.ipynb cells parameters,helpers,connect,timing,reach,close "REGIME = 'short'" > runs\saturation\reach_short.log 2>&1
python scripts/run_spe_notebook.py --notebook saturation.ipynb cells parameters,helpers,connect,scan,analyze,close "REGIME = 'short'" > runs\saturation\scan_short.log 2>&1
python scripts/run_spe_notebook.py --notebook saturation.ipynb cells parameters,helpers,load_saved,analyze "REGIME = 'short'"   # no hardware
```
Overrides run after the parameters cell, e.g. `"REGIME = 'long'; AMPLITUDES_V = [1.6, 1.7]"`; the regime's
settings (`R`) are resolved in the `helpers` cell. Add `--hv-off` for unattended runs.

**One-shot capture:** `python -m ad3pulse rigol-single --amplitude 1.0 --width 100e-9 --plot`
(fires one AD3 pulse and saves Rigol Ch1/Ch2 to CSV).

## SPE method (`ad3pulse/spe.py`, `spe_calibration.ipynb`)
- **Light:** the AD3 free-runs 100 ns pulses (104 ns realised, 8 ns AWG steps) at 1 kHz. The Rigol triggers on
  Ch3 (rising edge, 0.5 V).
- **Record:** 1k points at 1 GS/s, −500…+500 ns. Windows:
  - baseline −500…−300 ns, one median per run (adds no noise);
  - control −280…−80 ns;
  - signal 40…240 ns. The light arrives at ~130–180 ns on Ch1 and ~80–150 ns on Ch2.
- **Charge:** Q = −∫V dt / 50 Ω, in pC.
- **Occupancy (zero-PE Poisson counting):** μ = −ln P0(signal) + ln P0(control), with the threshold at the
  pedestal median + 3·(MAD σ). The control window subtracts dark counts.
- **Amplitude:** interpolate log μ against amplitude for μ = 0.15.
- **The two PMTs need different amplitudes:** ~1.68 V for A, ~1.86 V for B. One LED lights both, and A is far
  more sensitive.
- **Fit:** pedestal Gaussian + Σₙ Poisson(n; μ)·Gauss(n·Q1, √(σ0² + n·σ1²)) for n = 1…3. Gain = Q1/e.
- **Results (2026-10-07, 5k pulses):**
  - PMT A: Q1 = 0.949 pC, gain 5.9e6.
  - PMT B: Q1 = 0.492 pC, gain 3.1e6. Its SPE is only a shoulder; see the results README for caveats.
- **The LED is very steep near turn-on** (μ ×2 per ~20 mV) and drifts. Re-scan near the target before a run.
  PMT A's dark rate is ~200 kHz.

## Instrument quirks (verified on hardware; don't relearn these)

### Rigol MHO954 (`Documentation/MHO900-ProgrammingGuide.pdf`)
- **Use the raw socket `TCPIP0::<ip>::5555::SOCKET`, with `\n` terminators.**
  - `RigolScope` does this by default; any other VISA name passes through unchanged.
  - Don't use VXI-11 (`::INSTR`). After sessions that ended abruptly, VXI-11 accepted links but timed out on
    `*IDN?`, while the socket kept working. The socket is also faster: ~30 vs ~49 ms per 1k-point channel.
- **Single-shot:** `:SINGle` takes ~1.4 s to take effect, and a `STOP` read right after it is the *previous*
  acquisition. `arm_single()` waits for `WAIT`/`TD`. A stale `STOP` once produced a 0-point capture;
  `capture_channels()` now raises on 0 points.
- **Frame recorder** (`:RECord:WRECord:*`, guide §3.19):
  - Holds 126,976 frames at 1k memory depth; recording 5000 triggers at 1 kHz takes ~5 s.
  - **Replay readout must use `:WAV:MODE NORM`.** `RAW` returns the same data for every frame.
  - **After `:RECord:WREPlay:FCURrent i`, send `*OPC?` before reading.** Without it, ~1 in 6 reads returned
    the previous frame.
  - Readout is ~90 ms/frame for 2 channels on small recordings and ~137 ms/frame for 1 channel on 5000-frame
    recordings.
  - Frame timestamps (`FCURrent:TIME?`) read 0.
  - **After a recording the scope is stopped, and a bare `:RUN` free-runs** (trigger status `AUTO`), even though
    `:TRIG:SWE?` still reports `NORM`. At 2 Hz, 19 of 20 frames were untriggered noise and 20 frames recorded in
    0.9 s. `record_frames()` now sends `:TRIG:SWE NORM` + `:RUN` and waits for `WAIT`/`TD` before every
    recording. At 1 kHz real triggers beat the auto timeout: all 15,800 SPE scan frames had the Ch3 pulse.
- **Waveform data:** `WORD` byte order is little-endian (`WORD_BIG_ENDIAN = False`). Volts =
  (code − yorigin − yref) · yinc from `:WAV:PRE?`.
- **Settings:**
  - `:ACQ:MDEP 1k` with 100 ns/div gives 1 GS/s.
  - `:TFORce` forces a trigger.
  - `:TRIG:SWE NORM` ensures frames record only on real triggers, but must be re-sent before each
    recording (see the frame recorder notes above).
- **Network drops:** the scope occasionally drops off the LAN or resets a connection mid-readout. The
  notebook's `record()` reconnects and retries (`SCOPE_RETRIES`).

### ISEG SHR (`Documentation/iseg_manual_iseg_SCPI_general_instruction_set.pdf` v3.3)
- The NHQ RS-232 guide in `Documentation/` is for a different product line and does not apply.
- **Ethernet:** raw TCP port 10001, `\r\n`, no echo. USB/RS-232 *do* echo; that code was removed.
- **Order commands:** the SHR sends an empty line after each one, so orders are sent as `cmd;*OPC?` and empty
  lines are skipped. A rejected command gets no answer at all (timeout → `InstrumentError`).
- **Replies carry units and can omit exponent digits:** `1.23456E3V`, `1.23456EA` = 1.23456 A. Parse with
  `parse_iseg_value()`.
- **Channel syntax:** `:VOLT 1000,(@0)`, `:VOLT ON,(@0)`, `:MEAS:VOLT? (@0)`, `:READ:CHAN:STAT? (@0)`.
- **Signs and status:**
  - VSET is stored **signed** (a negative channel reads −1550 V). `set_voltage()` signs a magnitude from
    `:CONF:OUTP:POL?`.
  - Status bits (§9.2): on = 8, ramping = 16, constant voltage = 128. Faults: input error, emergency off,
    inhibit, trip and arc count; `_check_faults()` raises on these.
- **Set VSET before `:VOLT ON`,** otherwise the channel ramps to the old stored value.
- The current limit can be changed while the channel is on (Kill Enable is off).
- Closing the TCP connection leaves the HV as it is (`IsegHV.__exit__` only closes the connection).

### Analog Discovery 3 (WaveForms SDK)
- **Pulse train:** a custom AWG buffer for one short period (pre + width + post), then
  `FDwfAnalogOutWaitSet(1/rate − period)` at an idle 0 V offset, with `RepeatSet(0)` to repeat until stopped.
- **With AutoConfigure on, any `…Set` call while running stops the AWG** (status → READY), so
  `set_pulse_amplitude()` re-sends `FDwfAnalogOutConfigure(…, 1)`.
- **AWG status codes:** 7 = WAIT (most of a 1 kHz cycle), 3 = running, 0 = ready/stopped.
- **The measured LED drive on Ch3 is ~5 % below the AD3 setting** (e.g. 1.80 V → 1.72 V). Notebook metadata
  records `pulser_height_V`.
- `FDwfAnalogOutNodeDataInfo` returns 0 until `FDwfAnalogOutNodeFunctionSet(…, FUNC_CUSTOM)` has been called.
- **Edge resolution** is period / samples; `fit_to_awg()` caps the rate at 125 MS/s, giving 8 ns steps.
- **Device lock:** only one process (or one handle) can open the AD3. "Devices are busy" means the GUI or
  another Python process has it.
- **Legacy AD3 capture:** `FDwfAnalogInTriggerPositionSet` is a mid-buffer offset. Let the AWG go idle
  before re-arming.

### Windows / environment
- **Console encoding:** printing `σ`/`μ` to a redirected console fails with cp1252. The runner script
  reconfigures stdout to UTF-8.
- **The session scratchpad (temp dir) can be wiped mid-session.** Keep scripts in the repo and logs in `runs/`.
- **No Jupyter kernel in `.venv` yet.** Notebooks were exercised by exec'ing their cells (the runner script).

## Saturation method (`ad3pulse/saturation.py`, `saturation.ipynb`)
- **Two regimes (user's definition):**
  - **short:** ~100 ns LED pulses probe the space-charge limit on peak anode current;
  - **long:** 10 µs pulses probe depletion of the base capacitors (current droops during the pulse).
- **Pulse rate < 5 Hz in both** (default 2 Hz; the notebook asserts it) so the bases recharge between pulses.
  Exception: the `lowlight` cell (A/B slope statistics, A far from saturation) runs at 10 Hz (user's call).
- **Reference:** PMT B is the linear reference and A the device under test. A/B slope k is fitted on the lowest
  points with B ≥ `REF_MIN_NPE`; deviation = A / (k·B) − 1. The A:B light ratio is not yet measured (the
  `reach` cell gives it); if B is too dim to reach `REF_MIN_NPE` before A bends, the method needs rethinking.
- **PMT B has fewer base capacitors** than A and may deplete first, especially with 10 µs pulses. Watch the
  B self-check: B late/early ratio (long; > 2 % and > 3σ from low light) or mean-pulse FWHM (short; > 5 %).
  In A(t)/B(t), *falling* late in the pulse = A depleting; *rising* = B depleting. If B is flagged, stop and
  consider a base with more capacitors for B.
- **Scope safety:** software peak guard only, `MAX_PMT_PEAK_V = 3.0` V (user's choice). The MHO954 50 Ω input
  is rated 5 Vrms with no transient overvoltage (datasheet p. 11). The 50 Ω offset range is ±1 V up to
  136 mV/div and ±4 V above. PMT traces are offset up 3 div so negative pulses get 7 of 8 divisions.
- **Auto-range:** a positive `:CHAN:OFFS` moves the trace up (screen = −offset ± 4 div). This was verified on
  hardware: A's −1.96 V pulses at 0.5 V/div were not clipped.
- **Long-regime record:** 5 µs/div, offset +10 µs, 10k points (200 MS/s), ≈ −15…+35 µs. Readout time per frame
  is not yet measured.
- **Timing (short regime):** a 1000-pulse point at 10 Hz takes ~390 s (3 channels, ~0.29 s/frame readout).
  The reach scan (16 points × 30 pulses at 2 Hz) took ~10 min.

## Status and next steps
**Where things stand (end of 2026-10-07):** the HV is **off** on both channels, and PMT B is being swapped by the user.
Details are in `results/saturation_short_2026-10-07/README.md`.

- **Done:**
  - Ethernet control of the Rigol and ISEG;
  - the AD3 pulse train and the frame recorder (now with re-armed normal triggering);
  - SPE calibration of both PMTs at 5k pulses (`results/spe_2026-10-07/`);
  - the saturation code and notebook. In the short regime, `timing`, `reach` and `lowlight` have run on hardware;
    `scan` and `analyze` have only been tested offline on synthetic data.
- **First saturation result:** **PMT A's peak anode current flat-tops at ~38–39 mA** at −1550 V (verified as
  not scope clipping). Its charge grows only through a longer flat top.
- **Blocker:** PMT B is too noisy to serve as the reference:
  - ~2 mV rms pickup, against a ~5 mV SPE;
  - ~100 MHz bursts every ~20–30 s on both channels;
  - A gets ~250–400× more light than B, so B has < 3 PE while A is linear.

  **The user is replacing PMT B** (base design suspected).
- **After the swap:**
  1. Bias the new B (operating point and current limit are the user's call; confirm the box is dark).
  2. Noise check, i.e. baseline rms on Ch2 and whether the bursts persist. They also hit A, so they may be
     external.
  3. SPE calibration of the new B (`spe_calibration.ipynb`), then update `Q1_PC[2]`, `PMTS` and `HV_EXPECTED_V`
     in `saturation.ipynb`, plus the operating points in this file.
  4. Add burst-frame rejection to the saturation analysis: pre-trigger excursions, or a Ch3 height far from the
     drive.
  5. Re-run `timing` → `reach` → `lowlight` → `scan` → `analyze` (short), then the long (10 µs) regime.
- **Still untested on hardware:**
  - the 10 µs pulse regime: AD3 train, long record and its readout speed;
  - the peak guard actually tripping;
  - `TRIGGER_MODE = "ad3"` in `pmt_bias_test.ipynb`.
- **Not yet decided by the user** (SPE): a 20k-pulse calibration; re-fitting B with a narrower window. Both are
  moot if B is replaced.
- **Uncommitted, user's files:** `.vscode/` and `Untitled-7.ipynb` (a scratch copy of the overlay notebook) are
  left untracked on purpose.
