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
| Siglent SDG2082X | LED pulse source (CH1), since 2026-11-14 | Ethernet **192.168.0.75**, raw SCPI socket port **5025** |
| Digilent Analog Discovery 3 | Retired pulse source (AWG W1); legacy tools only | USB; needs the WaveForms runtime |
| Rigol MHO954 scope | All waveform capture | Ethernet **192.168.0.101**, raw SCPI socket port **5555** |
| ISEG SHR 40 60 HV (SR040060R4050000200) | PMT bias, 4 ch × 6 kV | Ethernet **192.168.0.100**, raw TCP port **10001** |
| Lab PC | | Ethernet adapter 192.168.0.102 on the instrument LAN |

- **LED drive:** Siglent CH1 (AD3 W1 until 2026-11-13) → tee:
  - one side → 330 Ω in series with the LED (turn-on ~1.6 V). **A Kim wipe over the LED diffuses the light
    (2026-11-14),** and the mounting was made more rigid;
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
- **LED pulse rate ≤ 10 Hz whenever data are taken** (user, 2026-11-14), so the bases recharge. This
  includes SPE calibration, which ran at 1 kHz up to round 3. `SiglentSDG` refuses faster rates.
- **Acquisition code saves raw data only.** Baseline, charge, gain and fits belong in the notebooks and
  `ad3pulse/spe.py`.
- **Don't reintroduce AD3 capture** as the PMT measurement path. AD3 auto-ranging silently jumped to a
  coarse range and buried small signals in quantization noise.
- **When asked to finish unattended, switch the HV off at the end** (see Runbooks), and make the off step
  run even on failure.
- **Commits** go on `main`. The GitHub remote is `origin` = `bglenardo/pmt_saturation` (renamed from `ad3-pulse-lab` on 2026-11-16; the Python package is still `ad3pulse`); the user pushes.

## Setting up on a new PC
1. **Python 3.10+.** The current PC runs 3.14.7. From the repo root:
   `python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt`.
   For Jupyter, also `pip install ipykernel` and select the `.venv` kernel.
2. **Digilent WaveForms** (runtime 3.25.1 here) for the AD3; `dwf.dll` is loaded via ctypes. **Close the
   WaveForms GUI before running code**, or the device is locked ("Devices are busy").
3. **VISA:** none needed. `pyvisa-py` (pure Python) talks to both instruments over TCP; NI-VISA isn't used.
4. **Network:** give the PC's instrument-LAN adapter a 192.168.0.x address (not .100/.101). Check with
   `python -m ad3pulse hv status`, `python -m ad3pulse sdg status` and `RigolScope().connect()` (prints the IDN).
5. **Data and docs to copy by hand:**
   - `Documentation/*.pdf` (manuals, gitignored);
   - `runs/` (raw data, gitignored; ~92 MB for the SPE runs) if you need to re-fit old data.
6. **Check:** `.venv\Scripts\python -m pytest -q`, which should pass 70 tests with no hardware needed.

## Repository layout
- `ad3pulse/`:
  - `instrument.py` (legacy, AD3): `PulseSpec` and `AnalogDiscovery`. Covers single pulses, the free-running
    **`start_pulse_train()` / `set_pulse_amplitude()`**, and the legacy AD3 capture code.
  - `hardware.py`: **`RigolScope`** (configure, single-shot, frame recorder `record_frames()` → `FrameSet`)
    **`IsegHV`** (set/on/off, status bits, `wait_stable()`, `wait_off()`) and **`SiglentSDG`** (the LED pulser:
    `start_pulse_train(width, rate, high_v)`, `set_pulse_amplitude()`, `stop_output()`, all checked by read-back).
  - `spe.py`: analysis. Charge integration, zero-PE occupancy, `pick_amplitude()`, and the SPE fit `fit_spe()`.
  - `acquire.py`: **`ScopeSession`** (scope settings, LED amplitude, retrying frame recording, raw saves),
    per-point vertical **`autorange()`** and the 50 Ω **peak guard** (`check_peaks()` → `PeakLimitExceeded`).
    Used by the saturation notebook; the SPE notebook still has its own `record()`.
  - `saturation.py`: saturation analysis. Peak current, binned charge, `linearity()` against the reference PMT,
    `crossing()`, `shape_ratio()`, `late_early()` with errors, and `flag_reference()`.
  - `cli.py`: `python -m ad3pulse {list, single, sweep, repeat, gui, rigol-single, hv set|off|status, sdg status|off}`.
  - `dwfapi.py`: ctypes wrapper for WaveForms (functions resolved by name).
  - `sweep.py`, `repeat.py`, `gui.py`: the legacy AD3-capture workflow.
- `spe_calibration.ipynb`: **the SPE calibration**. Code cells are tagged: `parameters`, `connect`,
  `timing`, `scan`, `choose`, `calibrate`, `load_saved`, `fit`, `close`, `emergency`.
- `pmt_bias_test.ipynb`: bias test. Ramp up, one Rigol acquisition, ramp down (`finally:`).
- `overlay_waveforms.ipynb`: overlays from the legacy AD3 sweep.
- `saturation_r4_writeup.ipynb`: **round-4 write-up** (saved data only; run from the repo root). Headless:
  `pip install nbclient` and execute with `nbclient.NotebookClient(nb, kernel_name="python3")`.
- `saturation_r2.ipynb`: **rounds 2–4** (round 4 = Siglent pulser, `OUTPUT_DIR = runs/saturation_r4`; k scan, dynode-8 Ch4 at 50 Ω and 1 MΩ, finer scans). Its analysis is in
  `ad3pulse/sat_analysis.py` and `ad3pulse/sat_plots.py`.
- `saturation.ipynb`: **saturation studies, round 1** (`REGIME = "short"` or `"long"`). Tags: `parameters`, `helpers`,
  `connect`, `timing`, `reach`, `scan`, `load_saved`, `analyze`, `close`, `emergency`.
- `scripts/run_saturation_chain.sh`: unattended chain. SPE calibration → short and long saturation scans → HV off,
  with the HV-off step in an EXIT trap. Its processes survive stopping the Claude background task.
- `scripts/run_spe_notebook.py`: runs notebook cells headless by tag (`scan`, `cal`, `final`, `refit`, `off`;
  `--notebook X.ipynb cells TAG,TAG [overrides] [--hv-off]` for any notebook).
- `results/<name>/`: committed summaries and plots (`spe_2026-10-07/` has the first calibration;
  `saturation_short_2026-10-07/` has the first short-pulse saturation look).
- `scripts/run_r2_chain.sh`: the round-2/3/4 chain (`OUT=<dir>` picks the output directory).
  `scripts/ab_ratio_check.py`, `r3_short_by_sweep.py` and `r3_writeup.py` re-analyse saved scans.
- `scripts/sdg_check.py`: bench check of the Siglent pulses on Ch3 (HV off; width, edges, height against setting).
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
`python scripts/run_spe_notebook.py off`, which also switches the Siglent output off and waits until both
channels are below 5 V. **LED off:** `python -m ad3pulse sdg off`.

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
- **Light:** the Siglent free-runs 100 ns pulses at **10 Hz** (round 4 on; until round 3 the AD3 ran 104 ns
  pulses at 1 kHz). The Rigol triggers on
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

### Siglent SDG2082X (`Documentation/SDG_Programming-Guide_PG02-E05C.pdf`, `SDG2000X_UserManual_EN.pdf`)
- **Raw socket `TCPIP0::192.168.0.75::5025::SOCKET`, `
` terminators.** IDN
  `Siglent Technologies,SDG2082X,SDG2XFBX7R1421,2.01.01.37R6`.
- **Set commands get no answer, and out-of-range values are clamped silently** (`FRQ,0` became 1 µHz). Every
  setting is read back with `C1:BSWV?` (`WVTP,PULSE,FRQ,10HZ,...,HLEV,1V,LLEV,0V,...,WIDTH,1e-07,RISE,8.4e-09S,...`;
  `parse_bswv()`), and `SiglentSDG` raises on a mismatch. A read-back takes ~8 ms.
- **Pulse mode:** `C1:BSWV WVTP,PULSE`, `FRQ`, `WIDTH`, `RISE`/`FALL` (minimum **8.4 ns**), `HLEV`, `LLEV,0`.
  The pulse starts at the period start; the scope triggers on its rising edge on Ch3 as before.
- **Output impedance is always 50 Ω.** `OUTP LOAD,HZ` only rescales the displayed values, so HLEV is the
  open-circuit voltage. On Ch3 (2026-11-14, HV off): 10 µs pulses reach 1.00–1.01 × HLEV; 100 ns pulses show a
  fast (~5 ns) step to about half height and a cable echo ~30 ns later, ringing on the top (median over the
  pulse ≈ 0.91 × HLEV), width 102.6 ns at 50 %, edge jitter 0.2 ns.
- **After a power cycle it comes up in SINE, and the first `WVTP,PULSE` was ignored** while the following FRQ/level
  commands were applied. `start_pulse_train()` now repeats WVTP until the read-back says PULSE.
- **A 50 Ω terminator on the tee halves the drive** (50 Ω source): during one point (1.775 V, 2026-11-14) the user tried
  one and Ch3 read 0.86 V instead of ~1.55 V, below LED turn-on. Without it Ch3 is ~0.87 × HLEV for 100 ns pulses.
- **Don't use `MAX_OUTPUT_AMP`.** Setting it to 3 V moved the levels to HLEV 1.5 V / LLEV −0.2 V (reverse bias
  on the LED). It is left at 20 V; the 3 V limit is in software (`max_v`).
- Closing the socket leaves the output as it is. `stop_output()` sends `C1:OUTP OFF` and checks `C1:OUTP?`.
- **One socket at a time, and the SCPI server can lock up (2026-11-14).** While a run held the SDG, a second
  connection (`sdg status`) timed out. When the run closed its socket, a fresh connection was reset at once,
  and from then on ports 5025/5024 and VXI-11 refused every connection (ping still answered) for 30+ min.
  The output was already confirmed OFF. **Never open a second SDG connection during a run, and don't reconnect
  straight after one closes.** `pulser_off()` now skips the reconnect when the run confirmed OFF, and
  `connect()` retries with 3 s pauses. Recovery: power-cycle the SDG (or LAN reset on its front panel).

### Analog Discovery 3 (WaveForms SDK, retired as the pulser on 2026-11-14)
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
  - **short:** ~100 ns LED pulses probe the space-charge limit on peak anode current. **From round 3 on they are
    250 ns** (`SHORT_WIDTH_S` in `saturation_r2.ipynb`; the AD3's 100 ns squares are badly shaped). The windows
    follow the width (`short_regime(w)`), and `load_scan` refuses files recorded with another width: pass
    `SHORT_WIDTH_S = 100e-9` to re-analyse round-2 short data;
  - **long:** 10 µs pulses probe depletion of the base capacitors (current droops during the pulse).
- **Pulse rate < 5 Hz in both** (default 2 Hz; the notebook asserts it) so the bases recharge between pulses.
  Exception: the `lowlight` cell (A/B slope statistics, A far from saturation) runs at 10 Hz (user's call).
- **Reference:** PMT B is the linear reference and A the device under test.
  - **Light scale (user's choice):** where B ≥ `REF_MIN_NPE` (0.05 PE) and > 3σ, k·B is the true light; at lower
    light A is assumed linear.
  - **k fit:** k is fitted on the `FIT_POINTS` lowest-B significant points, stopping at the first one that fails a
    linearity cut. For long pulses that cut is A late/early ≥ 0.5: a depleted A gives *less* charge, so charge
    cuts can't exclude it.
  - **Deviation** = A / light − 1. The light ratio A:B was ≈ 1800–2400 (short) and ≈ 680–1100 (long) in rounds
    1–2; with the round-3 geometry it is ≈ 28 (short) and ≈ 10–14 (long).
  - **Ratio-scan occupancy threshold:** fixed at `RATIO_THRESHOLD_Q1` = 0.25·Q1. The 3·MAD σ threshold sat at or
    above A's Q1 in the 400 ns window of 250 ns pulses and made k ~6 % high.
- **PMT B's base:** the *original* B was thought to have fewer base capacitors. The current B holds far more
  charge than A for 10 µs pulses (~84 nC against ~38 nC), but its late/early rises from ~3 nC on, so it is a
  clean long-pulse reference only up to ~1.9–2.0 V LED (round 3). Watch the
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
**Round 4 (2026-11-14, Siglent pulser, 100 ns + 10 µs):** chain 16:22–21:36, HV off at the end
(`OUT=runs/saturation_r4 bash scripts/run_r2_chain.sh 1.81 2.055`, log `runs/saturation_r4/chain.log`).
**Written up in `saturation_r4_writeup.ipynb`** (repo root, runs in ~20 s from saved data; figures and `summary.json`
in `results/saturation_r4_2026-11-14/`).
- **SPE:** A Q1 = 0.904 ± 0.013 pC, B Q1 = 1.080 ± 0.014 pC. **Ratio scan k = 137.5 ± 2.4** (B counted; 140.4 ± 2.1
  against B's charge/Q1, which the scans use). Split run: 132 ± 6.
- **First point of each scan was bad** (100 ns up 2.000 V, 10 µs up 1.700 V): the timing cell left
  `ScopeSession.amplitude` at the same value, the scan restarted the SDG at 0.5 V, and `set_amplitude()` skipped
  the "unchanged" value. Fixed (amplitude always sent; test). Both points are excluded.
- **100 ns:** k_match 142.5 ± 0.8 (0.9σ from k_q). A linear to ~1 % up to ~1000 PE; charge 5 % low at ~1500–1730 PE,
  10 % at ~2100–2250 PE (matched / direct scale), 41 % low at 6200 PE (5 V); peak flattens at ~34 mA.
- **10 µs:** A(t)/B(t) through the pulse is flat at 1.88–1.98 V (A 2.8–11 k PE) and *rises during the pulse* from
  ~2.0 V on: A's gain grows as charge leaves its base (supralinear), not a light-split change. Light scale fitted on
  A = 2500–11 000 PE: **k = 57.4 ± 0.5** (default window 5–30 k gives 63.2, biased by the supralinearity).
  A is 5 % high from ~12 000 PE, 10 % from ~21 000, +37 % at ~35 000; delivered charge tops out at 58 700 PE
  (53 nC, 2.24 V), then falls (29 000 PE at 4 V, true light ~380 000). B's late/early drops ~10 % above ~1 nC, then
  stays flat (probably LED shape; ≤ 5 % on the true light).
- **Setup changes:** Kim wipe over the LED; the user dimmed B further (afternoon); **Ch4 (dynode 8) is unplugged**
  (`USE_DYN = False` in `saturation_r2.ipynb`). **LED limit 5 V for 100 ns (user)**, 10 µs up to 4 V;
  Ch3 at 1 V/div.
- **Light split (100 ns), afternoon geometry:** A/B = 127 ± 6 from B counted (μ 0.1–0.5) against A's charge/Q1 at
  2.0–2.2 V (`runs/spe_r4b/split`, `scripts/light_split.py`, A at 50 mV/div via `PMT_SCALE_BY_CH`). Zero-PE counting
  at 50 mV/div loses 20–30 % of A's SPEs (higher threshold); at 10 mV/div charge/Q1 and counting agree.
  The morning value (≈ 13) was poorly determined (11–35; B at μ ≈ 0.05).
- **μ = 0.15:** A ~1.81 V, B ~2.055 V (`runs/spe_r4b/scan_coarse.log`).
- **Reach (`runs/saturation_r4/reach`):** 100 ns: A 61 PE at 2.2 V, 340 at 2.6, 850 at 3.0 V (14.5 mA). 10 µs: A peaks
  at ~55 900 PE (52 nC) at 2.3 V and falls to 42 100 at 3.0 V while B rises to ~3 040 PE; A/B ≈ 54–72 at 1.9–2.1 V.

**Round 3 status (2026-10-28):** the HV is **off** on both channels. **Round 3 is done:**
`results/saturation_r3_2026-10-27/README.md` (raw data `runs/saturation_r3/`). Round 2 is in
`results/saturation_r2_2026-10-08/`, round 1 in `results/saturation_2026-10-07_newB/`.

- **Round 3 geometry (user, 2026-10-27):** A and B at about the same position relative to the LED, B's
  attenuator hole enlarged. Short pulses are now 250 ns. SPE: A Q1 = 0.9353 pC, B Q1 = 1.089 pC.
- **Round 3 results (PMT A at −1550 V; light in A PE per pulse):**
  - **k = A/B ≈ 28 for 250 ns** (ratio scan 27.8 ± 0.5, k_match 27.86 ± 0.19) and **≈ 10–14 for 10 µs**.
    The regime dependence (long/short ≈ 0.49) is the same as in round 2 (0.46), so it is an LED property.
  - **The light split changed once during the run** (short down-sweep: A −21 %, B +28 %), very likely the
    mounting shifting. Data on either side reproduce. The user will make the mounting rigid. Analyse the short
    sweeps separately (`scripts/r3_short_by_sweep.py`); the chain's mixed-sweep short result is wrong.
  - **250 ns:** anode charge 5 % low at ~2960 PE, 10 % at ~4480 PE (100 ns, round 2: 1330/1590). The peak still
    flattens at ~38 mA. Dynode 8 is ~3 % more linear.
  - **10 µs:** 5 % low at ~42 800 PE, but uncertain at the 10–15 % level: long-pulse A/B varies with drive
    (7.8–11.8; A's late/early rises 1.00 → 1.14 before depletion while B's stays flat). A's delivered charge
    tops out at ~38 nC, as in round 2.
- **Round 2 (100 ns):** anode charge 5 % low at ~1330 PE, 10 % at ~1590 PE, peak saturating at ~39 mA; 10 µs:
  5 % low at ~33 400 PE. Dynode 8 collapses with the anode in both regimes.
- **B is not a drive-independent light reference** across regimes. The analysis uses a "matched" light scale
  (B spline × k fitted where A is linear), and `ab_ratio()` / `plot_ab_ratio()` show A/B against LED drive.
- **Limitations:**
  - 50 Ω dynode-8 "charge" for 10 µs pulses is high-passed (RC 235 ns), so it follows the current, not the
    charge;
  - 1 MΩ data stop at 3 V.
- **Next (proposals):**
  - rigid mounting, then repeat the low-light ratio scan a few times to check k stays at ~28;
  - an independent light reference (ND filter on A, a second LED for A + B = AB, or a photodiode);
  - attenuating the 1 MΩ pickoff so long-pulse dynode-8 charge can be followed through depletion;
  - pulse-model fits of the saved waveforms.
- **Still untested on hardware:** the peak guard actually tripping; `TRIGGER_MODE = "ad3"` in
  `pmt_bias_test.ipynb`.
- **Uncommitted, user's files:** `.vscode/` and `Untitled-7.ipynb` are left untracked on purpose.
