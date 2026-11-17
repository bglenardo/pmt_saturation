"""Siglent pulse check (hardware; run directly, never imported by pytest): what reaches the LED tee?

With the HV OFF, plays 100 ns pulses at 10 Hz and 10 us pulses at 4 Hz from the SDG2082X (CH1),
at two levels each, records ~20 frames of Rigol Ch3 (the tee, 1 MOhm) and reports the measured
baseline, height/setting, 50 % width and 10-90 % rise/fall. The output is switched off at the end.

    .venv\\Scripts\\python scripts/sdg_check.py [--levels 1.0,2.0] [--frames 20]
"""
import argparse
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from ad3pulse.hardware import IsegHV, RigolScope, SiglentSDG  # noqa: E402

# (label, width, rate, timebase s/div, time offset s, memory depth)
CASES = [("100 ns", 100e-9, 10.0, 50e-9, 150e-9, "1k"),
         ("10 us", 10e-6, 4.0, 2e-6, 5e-6, "10k")]


def crossing(t, v, level, rising, start=0):
    """First interpolated time after index *start* where *v* crosses *level*."""
    above = v >= level if rising else v <= level
    idx = np.flatnonzero(above[start + 1:] & ~above[start:-1])
    if not len(idx):
        return np.nan, len(v) - 1
    i = start + idx[0]
    return float(t[i] + (level - v[i]) * (t[i + 1] - t[i]) / (v[i + 1] - v[i])), i + 1


def shape(t, v, width):
    base = float(np.median(v[t < -20e-9]))
    plateau = (t > 0.25 * width) & (t < 0.75 * width)
    top = float(np.median(v[plateau]))
    amp = top - base
    t50r, i = crossing(t, v, base + 0.5 * amp, True)
    t50f, _ = crossing(t, v, base + 0.5 * amp, False, i)
    t10, j = crossing(t, v, base + 0.1 * amp, True)
    t90, _ = crossing(t, v, base + 0.9 * amp, True, j)
    # fall: the last 90 % crossing before the falling 50 % point, then the next 10 % crossing
    k = int(np.searchsorted(t, t50f)) if np.isfinite(t50f) else len(t) - 1
    hi = np.flatnonzero(v[:k] >= base + 0.9 * amp)
    f90 = float(t[hi[-1]]) if len(hi) else np.nan
    f10, _ = crossing(t, v, base + 0.1 * amp, False, k)
    after = v[t > t50f + 0.3 * width] if np.isfinite(t50f) else v[-50:]
    return dict(base=base, top=top, width=t50f - t50r, rise=t90 - t10, fall=f10 - f90,
                t50=t50r, overshoot=float(v[plateau | (t < t50r + 0.25 * width)].max() - top),
                after=float(np.median(after) - base) if len(after) else np.nan)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--levels", default="1.0,2.0", help="SDG high levels (V, open circuit)")
    ap.add_argument("--frames", type=int, default=20)
    a = ap.parse_args()
    levels = [float(x) for x in a.levels.split(",")]

    with IsegHV() as hv:
        for ch in (0, 1):
            hv.channel = ch
            if abs(hv.read_voltage()) > 5.0:
                raise SystemExit(f"HV ch{ch} is at {hv.read_voltage():.1f} V: run this check with the HV off")

    scope = RigolScope().connect()
    sdg = SiglentSDG().connect()
    print(f"{sdg.idn}\n{scope.idn}")
    try:
        scope.configure_channel(3, 0.5, -1.5, impedance="OMEG")
        scope.configure_edge_trigger(3, 0.5, "POS")
        for label, width, rate, tdiv, toff, depth in CASES:
            scope._write(":RUN")
            scope.configure_timebase(tdiv, toff, depth)
            time.sleep(0.5)
            got_w = sdg.start_pulse_train(width, rate, levels[0], max_v=3.0)
            print(f"\n{label} at {rate:g} Hz (read-back width {got_w * 1e9:g} ns, depth "
                  f"{scope._query(':ACQ:MDEP?').strip()})")
            for lev in levels:
                sdg.set_pulse_amplitude(lev, max_v=3.0)
                time.sleep(0.5)
                fs = scope.record_frames(a.frames, (3,), timeout_s=a.frames / rate + 30)
                v, t = fs.volts(3), fs.time_s
                m = shape(t, np.median(v, axis=0), width)
                per = [shape(t, x, width) for x in v]
                jit = np.nanstd([p["t50"] for p in per])
                hs = np.array([p["top"] - p["base"] for p in per])
                print(f"  set {lev:.3f} V: base {m['base'] * 1e3:+.1f} mV, height {m['top'] - m['base']:.3f} V "
                      f"({(m['top'] - m['base']) / lev:.3f} of setting, frame rms {hs.std() * 1e3:.1f} mV), "
                      f"width {m['width'] * 1e9:.1f} ns, rise {m['rise'] * 1e9:.1f} ns, "
                      f"fall {m['fall'] * 1e9:.1f} ns, overshoot {m['overshoot'] * 1e3:.0f} mV, "
                      f"after {m['after'] * 1e3:+.1f} mV, edge jitter {jit * 1e9:.2f} ns, "
                      f"dt {(t[1] - t[0]) * 1e9:g} ns, {fs.n_frames} frames")
    finally:
        sdg.stop_output()
        print("\nSiglent output off")
        sdg.close()
        scope.close()


if __name__ == "__main__":
    main()
