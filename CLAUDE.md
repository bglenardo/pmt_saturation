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
- **Ch4 (added 2026-10-08):** PMT A's dynode-8 pickoff through 4.7 nF.
  - At 50 Ω it gives a positive pulse (19.5 pC at A ≈ 31 PE; 446 pC at A ≈ 700 PE, short pulses).
  - At 1 MΩ it gives a positive charge *step*, ~30 mV at 19.5 pC (C_eff ≈ 0.65 nF), with ~16 MHz ringing. Its signal is
  positive. Run it at 50 Ω and at 1 MΩ, and stop 1 MΩ once it reaches ~3–4 V.
- **PMT B:** ISEG **ch1**, negative polarity → **Rigol Ch2**, scope 50 Ω input. **Replaced on 2026-10-07**
  by a tube of the same type as A (the original B was too noisy; base design suspected). B's SPE values in
  `results/spe_2026-10-07/` and the 875 V figures below refer to the *old* B.
- ISEG ch2/ch3 are positive polarity and unused.

**Operating points** (chosen by the user, 2026-10-06):
- ch0 = −1550 V, draws ~16.9 µA;
- ch1 = −1550 V for the new B (same type as A), draws ~16.8 µA. The user set it on the ISEG front panel.
  The old B ran at −875 V and drew ~14.0 µA.
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
- `saturation_r2.ipynb`: **round 2** (k scan, dynode-8 Ch4 at 50 Ω and 1 MΩ, finer scans). Its analysis is in
  `ad3pulse/sat_analysis.py` and `ad3pulse/sat_plots.py`.
- `saturation.ipynb`: **saturation studies, round 1** (`REGIME = "short"` or `"long"`). Tags: `parameters`, `helpers`,
  `connect`, `timing`, `reach`, `scan`, `load_saved`, `analyze`, `close`, `emergency`.
- `scripts/run_saturation_chain.sh`: unattended chain. SPE calibration → short and long saturation scans → HV off,
  with the HV-off step in an EXIT trap. Its processes survive stopping the Claude background task.
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
python -m ad3pulse hv set 1550 --channel 1 --current 50e-6    # waits until stable
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
    **NORM returns only the ~1000 screen points**, whatever the memory depth. At 1k depth (short regime) nothing
    is lost. The long-regime record (10k depth, 50 µs) comes back at 50 ns spacing (20 MS/s): A's 10 µs
    envelope is fine, but B's few-ns SPE pulses are mostly lost, so B can't be photon-counted (2026-10-07).
  - **After `:RECord:WREPlay:FCURrent i`, send `*OPC?` before reading.** Without it, ~1 in 6 reads returned
    the previous frame.
  - Readout is ~90 ms/frame for 2 channels on small recordings and ~137 ms/frame for 1 channel on 5000-frame
    recordings.
  - Frame timestamps (`FCURrent:TIME?`) read 0.
  - **After a recording the scope is stopped, and a bare `:RUN` free-runs** (trigger status `AUTO`), even though
    `:TRIG:SWE?` still reports `NORM`. At 2 Hz, 19 of 20 frames were untriggered noise and 20 frames recorded in
    0.9 s. `record_frames()` now sends `:TRIG:SWE NORM` + `:RUN` and waits for `WAIT`/`TD` before every
    recording. At 1 kHz real triggers beat the auto timeout: all 15,800 SPE scan frames had the Ch3 pulse.
- **Memory depth** must be a listed value (`1k`, `10k`, `100k`, ...); **`20k` is silently ignored**. It is also
  ignored if set while stopped. `ScopeSession.open()` now sends `:RUN` first and verifies `:ACQ:MDEP?`.
  Round 1's long record was really sampled at 1k depth (20–50 MS/s). With 10k over 20 µs it's 500 MS/s.
- **Replay at full depth is not possible.** In frame replay, `:WAV:MODE MAX`/`RAW` with `:WAV:POIN 10000` return
  10k points, but the *same record for every frame*. That record is not the replayed frame: its correlation with
  frame N is ~0. Only NORM (1000 screen points) is frame-correct (`scripts/rigol_replay_test.py`, 2026-10-08).
  Peak-detect acquisition (`:ACQ:TYPE PEAK`) didn't make B photon-countable.
- **Offsets:**
  - `:CHANx:OFFS -0` is not accepted; the old offset stays, and the scope rescales it with the V/div.
  - At 1 MΩ and 2 V/div, a −6 V offset was reported as applied but not applied, so the preamble showed a fake
    +6 V.
  - The code writes clean values, uses **zero offset at 1 MΩ**, and reads back scale and offset after every
    change (`ScopeSession._apply_scale`). The scope also once kept 0.031 V/div when 0.01 was asked.
- **Waveform data:** `WORD` byte order is little-endian (`WORD_BIG_ENDIAN = False`). Volts =
  (code − yorigin − yref) · yinc from `:WAV:PRE?`.
- **Settings:**
  - `:ACQ:MDEP 1k` with 100 ns/div gives 1 GS/s.
  - `:TFORce` forces a trigger.
  - `:TRIG:SWE NORM` ensures frames record only on real triggers, but must be re-sent before each
    recording (see the frame recorder notes above).
- **Stuck socket, replies one command late (2026-10-08).** After a session was broken by a second connection,
  the raw socket held back every reply until the *next* command arrived: `*IDN?` returned the previous answer.
  Draining found nothing, and VXI-11 timed out as well. **Power-cycling the scope** is the fix.
  `RigolScope.connect()` now drains stale replies and re-asks `*IDN?` if the first answer isn't Rigol's, but
  that can't fix the stuck state.
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
- **Never open a second scope connection while a run is in progress.** On 2026-10-08 two pytest runs imported
  `scripts/rigol_replay_test.py`, a hardware script whose name matched pytest's pattern, and a diagnostic
  connection followed. This broke the chain's scope session: timeouts, then a stray `*IDN?` reply read as the
  memory depth. The ratio scan was lost after 1.86 V and the chain fell through to HV off.
  - The script is now `scripts/rigol_replay_check.py`, guarded by `__main__`.
  - `pytest.ini` limits collection to `tests/`.
  - The memory-depth read-back retries on a stray reply.
- **Device lock:** only one process (or one handle) can open the AD3. "Devices are busy" means the GUI or
  another Python process has it.
  - **A VS Code Jupyter kernel on the `.venv` can hold it** (2026-10-07). Unplugging the USB did not help, and
    `python -m ad3pulse list` showed "(in use)". Killing the kernel (`ipykernel_launcher`, the
    `pythoncore-3.14` child process) freed it. Check `Get-CimInstance Win32_Process` for python processes first.
  - **Stopping a background run kills the shell, not necessarily the AD3 output.** Afterwards, open the AD3 and
    call `stop_output(0)` to make sure the LED is off.
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
- **Reference:** PMT B is the linear reference and A the device under test.
  - **Light scale (user's choice):** where B ≥ `REF_MIN_NPE` (0.05 PE) and > 3σ, k·B is the true light; at lower
    light A is assumed linear.
  - **k fit:** k is fitted on the `FIT_POINTS` lowest-B significant points, stopping at the first one that fails a
    linearity cut. For long pulses that cut is A late/early ≥ 0.5: a depleted A gives *less* charge, so charge
    cuts can't exclude it.
  - **Deviation** = A / light − 1. The light ratio is A:B ≈ 1800 (short) and ≈ 680 (long) with the new B.
- **PMT B has fewer base capacitors** than A and may deplete first, especially with 10 µs pulses. Watch the
  B self-check: B late/early ratio (long; > 2 % and > 3σ from low light) or mean-pulse FWHM (short; > 5 %).
  In A(t)/B(t), *falling* late in the pulse = A depleting; *rising* = B depleting. If B is flagged, stop and
  consider a base with more capacitors for B.
- **Scope safety:** software peak guard only, `MAX_PMT_PEAK_V = 3.0` V (user's choice). The MHO954 50 Ω input
  is rated 5 Vrms with no transient overvoltage (datasheet p. 11). The 50 Ω offset range is ±1 V up to
  136 mV/div and ±4 V above. PMT traces are offset up 3 div so negative pulses get 7 of 8 divisions.
- **Auto-range:** a positive `:CHAN:OFFS` moves the trace up (screen = −offset ± 4 div). This was verified on
  hardware: A's −1.96 V pulses at 0.5 V/div were not clipped.
- **Long-regime record:** 5 µs/div, offset +10 µs, −15…+35 µs. It reads back as 1000 points at 50 ns (see the
  Rigol notes) and takes ~1.5 min per 150-pulse point at 4 Hz.
- **Timing (short regime):** a 1000-pulse point at 10 Hz takes ~390 s (3 channels, ~0.29 s/frame readout).
  The reach scan (16 points × 30 pulses at 2 Hz) took ~10 min.

## Status and next steps
**Where things stand (end of 2026-10-07, ~21:00):** the HV is **off** on both channels. The full saturation
characterisation of PMT A is done in both regimes, against the new PMT B; see
**`results/saturation_2026-10-07_newB/README.md`**. Earlier, noisy-B results are in `results/saturation_short_2026-10-07/`.

- **Done:**
  - Ethernet control of the Rigol and ISEG;
  - the AD3 pulse train and the frame recorder (with re-armed triggering);
  - SPE calibration of A and of the new B. A: Q1 = 0.904 pC (`results/spe_2026-10-07/` has the morning
    0.949 pC). New B: Q1 = 1.09 pC, gain 6.8e6;
  - saturation, short and long, run unattended with `scripts/run_saturation_chain.sh`.
- **Results (PMT A at −1550 V):**
  - **100 ns pulses:** 5 % low at ~1,180 PE (≈ 24.5 mA peak), 10 % low at ~1,510 PE (≈ 27 mA). Peak current
    saturates at ~38 mA.
  - **10 µs pulses:** linear to at least ~36,000 PE (≈ 32 nC per pulse). By ~150,000 PE it is 60 % low, and the
    current collapses after the base has delivered ~55 nC.
  - The new B is clean up to ~9 nC per pulse in 10 µs.
- **Approved plan for the next round: `NEXT_STEPS.md`.** It covers k from a joint occupancy scan, finer knee
  scans, better long-pulse sampling, and the **Ch4 dynode-8 pickoff** (4.7 nF, at 50 Ω and 1 MΩ, with 1 MΩ
  stopped at ~3 V). Ch4 was added by the user on 2026-10-08.
- **Open questions and next steps** (see that README):
  - finer amplitude steps around the knees: 1.81–1.90 V (long) and 2.0–2.2 V (short);
  - more statistics on the A/B slope k;
  - why k differs between regimes (1779 short vs 677 long). Candidates are B's long-window afterpulses, and
    B's long-window noise, which comes from the 50 ns sampling;
  - a better long-pulse readout. NORM replay gives only 1000 screen points;
  - optionally, characterise B with the roles swapped.
- **Still untested on hardware:** the peak guard actually tripping; `TRIGGER_MODE = "ad3"` in
  `pmt_bias_test.ipynb`.
- **Uncommitted, user's files:** `.vscode/` and `Untitled-7.ipynb` are left untracked on purpose.
