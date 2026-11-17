"""Plot the round-4 light split A:B (no hardware).

Left: light per pulse on each PMT against LED drive. Right: A/B per LED setting.
A's light is its charge / Q1 (split run, 50 mV/div, unclipped) or its zero-PE
occupancy (coarse scan, 10 mV/div); B's is always its zero-PE occupancy.

    python scripts/plot_light_split.py [split_dir] [coarse_dir] [morning_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import light_split as L  # noqa: E402

BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#8a8984"   # categorical slots 1-2; gray for the old geometry
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def split_points(rows):
    """(LED V, A PE, B mu, B err, A/B, A/B err) where B is counted and A's charge is unclipped."""
    out = []
    for r in rows:
        a, b = r[1], r[2]
        if a["clip"] <= L.MAX_CLIP and b["mu"] > L.MIN_SIG * b["err"]:
            a_pe = a["qnet"] / L.Q1_A_PC
            out.append((r["amp"], a_pe, b["mu"], b["err"], a_pe / b["mu"], a_pe / b["mu"] * b["err"] / b["mu"]))
    return np.array(out).reshape(-1, 6)


def main(split_dir="runs/spe_r4b/split", coarse_dir="runs/spe_r4b", morning_dir="runs/spe_r4") -> Path:
    split = L.analyse(Path(split_dir))
    coarse = L.analyse(Path(coarse_dir))
    morning = L.analyse(Path(morning_dir))
    sp, mp = split_points(split), split_points(morning)

    plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))

    # ---- light per pulse ------------------------------------------------------------------
    ac = [(r["amp"], r[1]["mu"], r[1]["err"]) for r in coarse
          if r[1]["p0"] >= L.MIN_P0 and r[1]["mu"] > L.MIN_SIG * r[1]["err"] and r["ch3"] > 1.0]
    bc = [(r["amp"], r[2]["mu"], r[2]["err"]) for r in coarse
          if r[2]["mu"] > L.MIN_SIG * r[2]["err"] and r["ch3"] > 1.0]
    ac, bc = np.array(ac), np.array(bc)
    ax1.errorbar(ac[:, 0], ac[:, 1], ac[:, 2], fmt="o", mfc="white", mec=BLUE, ecolor=BLUE, ms=8, mew=2, lw=1.5,
                 capsize=0, label="A, photon counted (10 mV/div)")
    ax1.plot(sp[:, 0], sp[:, 1], "o", color=BLUE, ms=8, label="A, charge / Q1 (50 mV/div)")
    ax1.errorbar(bc[:, 0], bc[:, 1], bc[:, 2], fmt="s", mfc="white", mec=ORANGE, ecolor=ORANGE, ms=8, mew=2,
                 lw=1.5, capsize=0, label="B, photon counted (coarse scan)")
    ax1.errorbar(sp[:, 0], sp[:, 2], sp[:, 3], fmt="s", color=ORANGE, ms=8, lw=1.5, capsize=0,
                 label="B, photon counted (split run)")
    ax1.set_yscale("log")
    ax1.set_ylim(0.05, 3000)                 # headroom for the legend above the data
    ax1.set_xlabel("LED drive, SDG high level (V)")
    ax1.set_ylabel("light per 100 ns pulse (PE)")
    ax1.set_title("Light on each PMT", loc="left", color=INK)
    ax1.text(sp[-1, 0] + 0.02, sp[-1, 1], "A", color=INK, va="center", fontweight="bold")
    ax1.text(sp[-1, 0] + 0.02, sp[-1, 2], "B", color=INK, va="center", fontweight="bold")

    # ---- A/B --------------------------------------------------------------------------------
    w = 1 / sp[:, 5] ** 2
    mean, err = np.sum(w * sp[:, 4]) / np.sum(w), 1 / np.sqrt(np.sum(w))
    chi2 = np.sum(w * (sp[:, 4] - mean) ** 2)
    ax2.axhspan(mean - err, mean + err, color=BLUE, alpha=0.15, lw=0)
    ax2.axhline(mean, color=BLUE, lw=2)
    ax2.errorbar(sp[:, 0], sp[:, 4], sp[:, 5], fmt="o", color=BLUE, ms=8, lw=1.5, capsize=0,
                 label="afternoon geometry (B dimmed)")
    if len(mp):
        ax2.errorbar(mp[:, 0], mp[:, 4], mp[:, 5], fmt="o", mfc="white", mec=GRAY, ecolor=GRAY, ms=8, mew=2,
                     lw=1.5, capsize=0, label="morning geometry")
    ax2.text(1.845, mean, f"A/B = {mean:.0f} ± {err:.0f}\n(χ² {chi2:.1f} / {len(sp) - 1})",
             color=INK, ha="left", va="center")
    ax2.axhline(28, color=GRAY, lw=1, ls=(0, (4, 3)))
    ax2.text(2.21, 30, "round 3 (250 ns): 28", color=INK2, ha="right", va="bottom", fontsize=9)
    ax2.set_ylim(0, max(sp[:, 4] + sp[:, 5]) * 1.2)
    ax2.set_xlabel("LED drive, SDG high level (V)")
    ax2.set_ylabel("A / B  (A charge/Q1 over B occupancy)")
    ax2.set_title("Light split A:B, 100 ns pulses", loc="left", color=INK)

    for ax in (ax1, ax2):
        ax.grid(color=GRID, lw=0.8, which="major")
        ax.set_axisbelow(True)
        leg = ax.legend(fontsize=8.5, frameon=False, loc="upper left" if ax is ax1 else "lower right")
        for t in leg.get_texts():
            t.set_color(INK)
    fig.text(0.01, 0.01, f"Q1_A = {L.Q1_A_PC} pC (round-3 SPE fit). Split run {split_dir}: 400 pulses per point at "
             f"10 Hz. Errors are statistical (B counting).", fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = Path(split_dir) / "light_split.png"
    fig.savefig(out, dpi=150, facecolor="white")
    print(f"weighted A/B = {mean:.1f} ± {err:.1f} (chi2 {chi2:.1f}/{len(sp) - 1}); saved {out}")
    return out


if __name__ == "__main__":
    main(*sys.argv[1:])
