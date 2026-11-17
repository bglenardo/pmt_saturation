"""Light split A:B from an SPE occupancy scan directory (no hardware).

Every scan point records both PMTs (Ch1 = A, Ch2 = B), so each LED setting gives
an occupancy for both tubes. The split is mu_A / mu_B at the settings where both
are measurable by zero-PE counting.

    python scripts/light_split.py runs/spe_r4b [runs/spe_r4 ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ad3pulse.hardware import FrameSet  # noqa: E402
from ad3pulse.spe import baseline_subtract, integrate_charge, occupancy  # noqa: E402

# Same windows as spe_calibration.ipynb
BASELINE_WINDOW = (-500e-9, -300e-9)
CONTROL_WINDOW = (-280e-9, -80e-9)
SIGNAL_WINDOW = (40e-9, 240e-9)
N_SIGMA = 3.0
MIN_P0 = 0.02          # A: zero-PE counting needs some empty frames
MIN_SIG = 3.0          # B: mu must be this many sigma above zero
Q1_A_PC = 0.9353       # round-3 SPE calibration (2026-10-27), same tube and HV
MAX_CLIP = 0.01        # A's charge is used only where (almost) no frame clips


def mu_err(o) -> float:
    """Statistical error of mu = -ln P0s + ln P0c (binomial on both)."""
    ps, pc = max(o.p0_signal, 1e-9), max(o.p0_control, 1e-9)
    return float(np.sqrt((1 - ps) / (o.n * ps) + (1 - pc) / (o.n * pc)))


def clip_fraction(codes: np.ndarray) -> float:
    """Fraction of frames that touch the lowest code of the run (the PMT pulses are negative)."""
    lo = codes.min()
    return float(np.mean((codes <= lo).any(axis=1))) if (codes <= lo).sum() > 2 else 0.0


def analyse(run_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(run_dir.glob("scan_ch*_*V_*.npz")):
        amp = float(re.search(r"_(\d+\.\d+)V_", path.name).group(1))
        fs = FrameSet.load(path)
        row = {"file": path.name, "amp": amp, "ch3": fs.meta.get("pulser_height_V", np.nan)}
        for ch in (1, 2):
            v = baseline_subtract(fs.volts(ch), fs.time_s, BASELINE_WINDOW, False)
            qs = integrate_charge(v, fs.time_s, SIGNAL_WINDOW)
            qc = integrate_charge(v, fs.time_s, CONTROL_WINDOW)
            o = occupancy(qs, qc, n_sigma=N_SIGMA)
            row[ch] = {"mu": o.mu, "err": mu_err(o), "p0": o.p0_signal, "p0c": o.p0_control,
                       "n": o.n, "qnet": float(np.mean(qs) - np.mean(qc)),
                       "clip": clip_fraction(fs.codes[ch])}
        rows.append(row)
    return sorted(rows, key=lambda r: (r["amp"], r["file"]))


def report(run_dir: Path) -> None:
    rows = analyse(run_dir)
    print(f"\n{run_dir}  ({len(rows)} points)")
    print(" LED V   Ch3 V    mu_A ± err        mu_B ± err        A/B ± err     <Q_A>/<Q_B>  A clipped   (<Q_A>/Q1_A)/mu_B")
    ratios, qsplits = [], []
    for r in rows:
        a, b = r[1], r[2]
        good = a["p0"] >= MIN_P0 and b["mu"] > MIN_SIG * b["err"]
        ratio = err = np.nan
        if good:
            ratio = a["mu"] / b["mu"]
            err = ratio * np.hypot(a["err"] / a["mu"], b["err"] / b["mu"])
            ratios.append((ratio, err))
        qr = a["qnet"] / b["qnet"] if b["qnet"] > 0 else np.nan
        qsplit = np.nan
        if a["clip"] <= MAX_CLIP and b["mu"] > MIN_SIG * b["err"]:
            qsplit = a["qnet"] / Q1_A_PC / b["mu"]
            qsplits.append((qsplit, qsplit * b["err"] / b["mu"]))
        print(f" {r['amp']:.3f}  {r['ch3']:.3f}  {a['mu']:7.3f} ± {a['err']:.3f}   "
              f"{b['mu']:7.4f} ± {b['err']:.4f}   "
              + (f"{ratio:6.1f} ± {err:4.1f}" if good else "     -      ")
              + f"   {qr:7.1f}     {a['clip']:4.0%}      "
              + (f"{qsplit:6.1f}" if np.isfinite(qsplit) else "  -"))
    if ratios:
        r, e = np.array(ratios).T
        w = 1 / e**2
        mean = np.sum(w * r) / np.sum(w)
        chi2 = np.sum(w * (r - mean) ** 2)
        print(f" weighted A/B = {mean:.1f} ± {1 / np.sqrt(np.sum(w)):.1f} "
              f"from {len(r)} points (chi2 {chi2:.1f} / {len(r) - 1})")
    else:
        print(" no setting with both PMTs in the zero-PE counting range")
    if qsplits:
        q, e = np.array(qsplits).T
        w = 1 / e**2
        print(f" weighted (<Q_A>/Q1_A)/mu_B = {np.sum(w * q) / np.sum(w):.1f} ± {1 / np.sqrt(np.sum(w)):.1f} "
              f"from {len(q)} points (B statistics only)")


if __name__ == "__main__":
    for arg in sys.argv[1:] or ["runs/spe_r4b"]:
        report(Path(arg))
