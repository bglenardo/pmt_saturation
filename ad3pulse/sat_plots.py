"""Plots for the round-2 saturation analysis (``ad3pulse.sat_analysis``).

Each function returns its matplotlib Figure; the notebook saves and shows it.
"""

from __future__ import annotations

import numpy as np

from .saturation import align_shift
from .spe import window_mask

COLORS = {"A anode charge (PE)": "C0", "A anode peak (mA)": "C9",
          "dynode 8, 50 Ohm charge (pC)": "C3", "dynode 8, 50 Ohm peak (mA)": "C1",
          "dynode 8, 1 MOhm step (V)": "C2",
          "B anode charge (PE)": "C4", "B anode peak (mA)": "C6"}
MARKERS = {"up": "o", "down": "s", "low": "^"}


def _plt():
    import matplotlib.pyplot as plt
    return plt


def plot_ratio_scan(rows: list[dict], kres: dict, title: str = ""):
    """Both PMTs' zero-PE mu and mean PE against LED voltage, and k against LED voltage."""
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    amp = np.array([r["amplitude_V"] for r in rows])
    ax = axes[0]
    for ch, name, col in ((1, "PMT A", "C0"), (2, "PMT B", "C1")):
        mu = np.array([r[ch]["mu"] for r in rows]); me = np.array([r[ch]["mu_err"] for r in rows])
        pe = np.array([r[ch]["pe"] for r in rows]); pee = np.array([r[ch]["pe_err"] for r in rows])
        ok = np.isfinite(mu) & np.isfinite(me) & (mu > 2 * me) & (mu < 4)
        ax.errorbar(amp[ok], mu[ok], yerr=me[ok], fmt="o", ms=4, capsize=2, color=col, label=f"{name}: zero-PE μ")
        okp = pe > 2 * pee
        ax.errorbar(amp[okp], pe[okp], yerr=pee[okp], fmt="s", ms=4, mfc="none", capsize=2, color=col,
                    label=f"{name}: mean charge / Q1")
    ax.set_yscale("log"); ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel("photoelectrons per pulse")
    ax.set_title(title or "joint occupancy scan", fontsize=9); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    ax = axes[1]
    k_err = np.abs(kres["k_err"])  # a negative k (B below zero) gives a negative propagated error
    ok = np.isfinite(kres["k"]) & np.isfinite(k_err) & (kres["k"] > 0) & (k_err < kres["k"])
    kres = {**kres, "k_err": k_err}
    use = kres["use"] & ok
    ax.errorbar(amp[ok & ~use], kres["k"][ok & ~use], yerr=kres["k_err"][ok & ~use], fmt="o", ms=4, mfc="none",
                color="0.5", capsize=2, label="not used (B too dim or A too bright)")
    ax.errorbar(amp[use], kres["k"][use], yerr=kres["k_err"][use], fmt="o", ms=4, color="C3", capsize=2, label="used")
    ax.axhline(kres["k_mean"], color="k", ls="--", lw=0.8,
               label=f"k = {kres['k_mean']:.0f} ± {kres['k_mean_err']:.0f} (χ²/dof {kres['chi2_dof']:.2f})")
    ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel("A PE (charge) / B zero-PE μ")
    ax.set_title("light ratio k", fontsize=9); ax.grid(alpha=.3); ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def plot_vs_led(points, metrics: dict, regime: str):
    """Pulse area and pulse height against LED voltage for A, B and dynode 8."""
    plt = _plt()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    amp = np.array([p.amp for p in points]); sweep = np.array([p.sweep for p in points])
    groups = [(axes[0, 0], ("A anode charge (PE)", "B anode charge (PE)"), "pulse area (PE)"),
              (axes[0, 1], ("A anode peak (mA)", "B anode peak (mA)"), "pulse height (mA into 50 Ω)"),
              (axes[1, 0], ("dynode 8, 50 Ohm charge (pC)", "dynode 8, 1 MOhm step (V)"), "dynode 8: area (pC) / 1 MΩ step (V)"),
              (axes[1, 1], ("dynode 8, 50 Ohm peak (mA)",), "dynode 8 pulse height (mA into 50 Ω)")]
    for ax, names, ylabel in groups:
        for name in names:
            if name not in metrics:
                continue
            val, err = metrics[name]
            for sw in ("up", "down"):
                sel = (sweep == sw) & np.isfinite(val) & (val > 0)
                ax.errorbar(amp[sel], val[sel], yerr=err[sel], fmt=MARKERS[sw], ms=4, capsize=2,
                            color=COLORS.get(name), mfc="none" if sw == "down" else None,
                            label=f"{name} ({sw})")
        ax.set_yscale("log"); ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel(ylabel)
        ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    fig.suptitle(f"{regime} pulses: response against LED voltage", fontsize=10)
    fig.tight_layout()
    return fig


def plot_a_vs_b(points, ls: dict, k: float, regime: str, light_axes: str = "semilogy"):
    """A against B, and B against LED voltage with the smooth light-curve fit.

    *light_axes* sets the light-curve panel's axes: "semilogy" (log B, the default), "linear" or "loglog".
    """
    if light_axes not in ("semilogy", "linear", "loglog"):
        raise ValueError(f"light_axes must be 'semilogy', 'linear' or 'loglog', not {light_axes!r}")
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    amp = ls["amp"]; sweep = np.array([p.sweep for p in points])
    a = np.array([p.r50["ch"][1]["pe"] for p in points]); ae = np.array([p.r50["ch"][1]["pe_err"] for p in points])
    ax = axes[0]
    for sw in ("up", "down"):
        sel = sweep == sw
        ax.errorbar(ls["b"][sel], a[sel], xerr=ls["b_err"][sel], yerr=ae[sel], fmt=MARKERS[sw], ms=4, capsize=2, label=sw)
    xx = np.geomspace(max(np.nanmin(ls["b"][ls["b"] > 0]), 1e-3), np.nanmax(ls["b"]), 50)
    ax.plot(xx, k * xx, "k--", lw=0.8, label=f"linear, k = {k:.0f}")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("B per pulse"); ax.set_ylabel("A (PE per pulse)")
    ax.set_title(f"{regime}: A against the B reference", fontsize=9); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    ax = axes[1]
    sig = ls["b_sig"]
    ax.errorbar(amp[sig], ls["b"][sig], yerr=ls["b_err"][sig], fmt="o", ms=4, capsize=2, label="B (significant)")
    floor = 1e-4 if light_axes != "linear" else -np.inf
    ax.errorbar(amp[~sig], np.maximum(ls["b"][~sig], floor), yerr=ls["b_err"][~sig], fmt="o", ms=4, mfc="none",
                color="0.6", capsize=2, label="B (not used)")
    vv = np.linspace(ls["v_on"], amp.max(), 100)
    f = ls["fit"]
    ax.plot(vv, f.value(vv), "C3", lw=1, label="smooth fit (light curve / k)")
    ax.fill_between(vv, f.value(vv) - f.error(vv), f.value(vv) + f.error(vv), color="C3", alpha=0.2)
    if light_axes != "linear":
        ax.set_yscale("log")
    if light_axes == "loglog":
        from matplotlib.ticker import FormatStrFormatter, MultipleLocator
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(MultipleLocator(0.2)); ax.xaxis.set_minor_locator(MultipleLocator(0.05))
        ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f")); ax.xaxis.set_minor_formatter(FormatStrFormatter(""))
    ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel("B per pulse")
    ax.set_title(f"light curve from B ({'linear' if light_axes == 'linear' else light_axes.replace('semilogy', 'log y')} axes)",
                 fontsize=9); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def plot_linearity(points, ls: dict, lins: dict, regime: str, x2: tuple[str, np.ndarray]):
    """Deviation from linear of every metric, against true light and against *x2* (anode peak or charge)."""
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sweep = np.array([p.sweep for p in points])
    for ax, (xname, x) in zip(axes, (("true light (A PE per pulse)", ls["light"]), x2)):
        for name, lin in lins.items():
            if not np.isfinite(lin["scale"]):
                continue
            for sw in ("up", "down"):
                sel = (sweep == sw) & np.isfinite(lin["dev"]) & (x > 0)
                c5 = lin["cross"][0.05]
                lab = f"{name}" + (f" (5 % at {c5:.3g})" if c5 and sw == "up" and xname.startswith("true") else "")
                ax.errorbar(x[sel], 100 * lin["dev"][sel], yerr=100 * lin["dev_err"][sel], fmt=MARKERS[sw], ms=3.5,
                            capsize=2, color=COLORS.get(name), mfc="none" if sw == "down" else None,
                            label=lab if sw == "up" else None)
        for lv in (-5, -10):
            ax.axhline(lv, color="0.6", ls=":", lw=0.8)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xscale("log"); ax.set_ylim(-100, 40)
        ax.set_xlabel(xname); ax.set_ylabel("deviation from linear (%)")
        ax.grid(alpha=.3, which="both")
    axes[0].legend(fontsize=7)
    fig.suptitle(f"{regime} pulses: linearity of the anode and the dynode-8 pickoff (open = down-sweep)", fontsize=10)
    fig.tight_layout()
    return fig


def _levels(light, n):
    order = np.argsort(light)
    idx = np.unique(np.linspace(0, len(order) - 1, n).round().astype(int))
    return [int(order[i]) for i in idx]


def plot_shapes_ch1_ch4(points, light, cfg: dict, regime: str, n_levels: int = 6):
    """Anode (Ch1) and dynode-8 (Ch4, 50 Ohm) mean pulses overlaid, one panel per light level,
    plus Ch4(t)/Ch1(t) for all levels and (if present) the 1 MOhm step against Ch1's integral."""
    plt = _plt()
    up = [i for i, p in enumerate(points) if p.sweep == "up" and 4 in p.r50["ch"]]
    if not up:
        return None
    sel = [up[i] for i in _levels(np.array([light[i] for i in up]), n_levels)]
    ncol = 3
    nrow = int(np.ceil(len(sel) / ncol)) + 1
    fig, axes = plt.subplots(nrow, ncol, figsize=(15, 3.3 * nrow), squeeze=False)
    t = points[sel[0]].r50["t"]
    unit, ts = ("µs", 1e6) if regime == "long" else ("ns", 1e9)
    sig = window_mask(t, (cfg["signal"][0] - (t[1] - t[0]) * 20, cfg["signal"][1]))
    ref = points[sel[0]].r50
    shift = align_shift(t[sig], -ref["ch"][1]["mean_v"][sig], ref["ch"][4]["mean_v"][sig],
                        max_shift_s=50e-9 if regime == "short" else 500e-9)
    cmap = plt.get_cmap("viridis")
    ratio_ax = axes[-1, 0]
    for j, i in enumerate(sel):
        p = points[i]
        a = -p.r50["ch"][1]["mean_v"]; d = p.r50["ch"][4]["mean_v"]
        d_al = np.roll(d, int(round(shift / (t[1] - t[0]))))
        ax = axes.flat[j]
        ax.plot(t * ts, a / np.max(a[sig]), color="C0", lw=1, label="anode Ch1 (−V)")
        ax.plot(t * ts, d_al / np.max(d_al[sig]), color="C3", lw=1, label="dynode 8 Ch4, 50 Ω (aligned)")
        ax.set_xlim(cfg["signal"][0] * ts - (2 if regime == "long" else 20), cfg["signal"][1] * ts)
        ax.set_title(f"LED {p.amp:.3f} V, light ≈ {light[i]:.3g} PE", fontsize=9)
        ax.set_xlabel(f"time ({unit})"); ax.set_ylabel("normalised to peak"); ax.grid(alpha=.3)
        if j == 0:
            ax.legend(fontsize=7)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(a > 0.05 * np.max(a[sig]), d_al / a, np.nan)
        ratio_ax.plot(t * ts, ratio / np.nanmedian(ratio[sig]) if np.isfinite(ratio[sig]).any() else ratio,
                      color=cmap(j / max(len(sel) - 1, 1)), lw=1, label=f"{light[i]:.3g} PE")
    for k in range(len(sel), (nrow - 1) * ncol):
        axes.flat[k].set_visible(False)
    ratio_ax.set_title("Ch4(t) / Ch1(t), each normalised to its median", fontsize=9)
    ratio_ax.set_xlabel(f"time ({unit})"); ratio_ax.grid(alpha=.3); ratio_ax.legend(fontsize=6)
    ratio_ax.set_xlim(cfg["signal"][0] * ts, cfg["signal"][1] * ts)
    ax = axes[-1, 1]
    have1m = [i for i in sel if points[i].r1m is not None and 4 in points[i].r1m["ch"]]
    for j, i in enumerate(have1m):
        p = points[i]
        a = -p.r1m["ch"][1]["mean_v"]
        cum = np.cumsum(a); cum /= np.max(np.abs(cum)) if np.max(np.abs(cum)) > 0 else 1
        step = p.r1m["ch"][4]["mean_v"]; step = step / np.max(np.abs(step)) if np.max(np.abs(step)) > 0 else step
        col = cmap(j / max(len(have1m) - 1, 1))
        ax.plot(t * ts, step, color=col, lw=1, label=f"1 MΩ step, {light[i]:.3g} PE")
        ax.plot(t * ts, cum, color=col, lw=0.8, ls="--")
    ax.set_title("1 MΩ step (solid) vs ∫ anode current (dashed), normalised", fontsize=9)
    ax.set_xlabel(f"time ({unit})"); ax.grid(alpha=.3)
    if have1m:
        ax.legend(fontsize=6)
    axes[-1, 2].set_visible(False)
    fig.suptitle(f"{regime} pulses: anode vs dynode-8 pulse shapes", fontsize=10)
    fig.tight_layout()
    return fig


def plot_shape_metrics(points, light, regime: str):
    """Pulse-shape metrics against light for the anode (Ch1) and dynode 8 (Ch4, 50 Ohm)."""
    plt = _plt()
    names = (("late_early", "late / early charge"),) if regime == "long" else \
            (("fwhm_s", "FWHM (ns)"), ("rise_s", "10–90 % rise (ns)"))
    fig, axes = plt.subplots(1, len(names), figsize=(6.5 * len(names), 4.3), squeeze=False)
    sweep = np.array([p.sweep for p in points])
    for ax, (key, label) in zip(axes[0], names):
        for ch, name, col in ((1, "anode Ch1", "C0"), (4, "dynode 8 Ch4", "C3")):
            v = np.array([p.r50["ch"].get(ch, {}).get(key, np.nan) for p in points], dtype=float)
            if regime == "short":
                v = v * 1e9
            for sw in ("up", "down"):
                sel = sweep == sw
                ax.plot(light[sel], v[sel], MARKERS[sw], ms=4, color=col, mfc="none" if sw == "down" else None,
                        label=f"{name} ({sw})")
        ax.set_xscale("log"); ax.set_xlabel("true light (A PE per pulse)"); ax.set_ylabel(label)
        ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    fig.suptitle(f"{regime} pulses: pulse-shape metrics", fontsize=10)
    fig.tight_layout()
    return fig


__all__ = ["plot_ratio_scan", "plot_vs_led", "plot_a_vs_b", "plot_linearity", "plot_shapes_ch1_ch4",
           "plot_shape_metrics"]


def plot_ab_ratio(results: dict, title: str = ""):
    """A/B light ratio against LED voltage for several regimes on one axis.

    *results* maps a regime name to ab_ratio() output. Filled markers are the points with both
    PMTs linear; dashed lines their weighted means. Proportional PMTs give one flat line.
    """
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for i, (name, r) in enumerate(results.items()):
        col = f"C{i}"
        ok = np.isfinite(r["ratio"]) & (r["ratio"] > 0) & np.isfinite(r["ratio_err"]) & (r["ratio_err"] < r["ratio"])
        for sw in ("up", "down"):
            sel = ok & (r["sweep"] == sw)
            u, n = sel & r["use"], sel & ~r["use"]
            ax.errorbar(r["amp"][u], r["ratio"][u], yerr=r["ratio_err"][u], fmt=MARKERS[sw], ms=4, capsize=2, color=col,
                        label=f"{name} ({sw})" if u.any() else None)
            ax.errorbar(r["amp"][n], r["ratio"][n], yerr=r["ratio_err"][n], fmt=MARKERS[sw], ms=4, capsize=2,
                        color=col, mfc="none", alpha=0.4)
        ax.axhline(r["mean"], color=col, ls="--", lw=0.8,
                   label=f"{name}: A/B = {r['mean']:.4g} ± {r['mean_err']:.2g}, "
                         f"slope {r['slope_per_V']:.3g} ± {r['slope_err']:.2g} /V")
    ax.set_yscale("log"); ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel("A / B (PE / PE)")
    ax.set_title(title or "A/B light ratio (open: B insignificant, or A past its linear range)", fontsize=9)
    ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def plot_waveforms(points, regime: str, sweep: str = "up", xlim_us: tuple[float, float] | None = None,
                   n_legend: int = 10, titles: dict | None = None):
    """Mean anode current of A (Ch1) and B (Ch2) against time, one curve per LED amplitude.

    Colours run along viridis from the dimmest to the brightest point of *sweep*; the legend lists about
    *n_legend* of the amplitudes.
    """
    plt = _plt()
    pts = sorted((p for p in points if p.sweep == sweep), key=lambda p: p.amp)
    if not pts:
        raise ValueError(f"no {sweep}-sweep points")
    cmap = plt.get_cmap("viridis")
    titles = titles or {1: "PMT A (Ch1)", 2: "PMT B (Ch2)"}
    labelled = set(np.unique(np.round(np.linspace(0, len(pts) - 1, min(n_legend, len(pts)))).astype(int)))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    for ax, ch in zip(axes, (1, 2)):
        for j, p in enumerate(pts):
            t_us = p.r50["t"] * 1e6
            i_ma = -p.r50["ch"][ch]["mean_v"] / 50.0 * 1e3
            ax.plot(t_us, i_ma, lw=0.9, color=cmap(j / max(len(pts) - 1, 1)),
                    label=f"{p.amp:.2f} V" if j in labelled else None)
        if xlim_us is not None:
            ax.set_xlim(*xlim_us)
        ax.set_xlabel("time from trigger (µs)"); ax.set_ylabel("mean anode current (mA)")
        ax.set_title(f"{titles[ch]}: {regime} pulses, {sweep}-sweep", fontsize=9)
        ax.grid(alpha=.3)
    axes[0].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    return fig


def plot_a_dy8_vs_b(points, ls: dict, k: float, regime: str, sweep: str = "up"):
    """Like plot_a_vs_b, with PMT A's dynode-8 (Ch4, 50 Ohm) charge next to its anode charge.

    The dynode charge is scaled to anode PE by the weighted mean anode/dynode ratio on the light-scale
    window (``ls["window"]``), so both sit on k*B where A is linear. Only *sweep* points are drawn.
    """
    from .sat_analysis import metric_table
    plt = _plt()
    m = metric_table(points)
    a, ae = m["A anode charge (PE)"]
    d, de = m["dynode 8, 50 Ohm charge (pC)"]
    sel = np.array([p.sweep == sweep for p in points])
    win = ls["window"] & np.isfinite(d) & (d > 0)
    r = a[win] / d[win]
    re = r * np.hypot(ae[win] / a[win], de[win] / d[win])
    w = 1 / re ** 2
    s = float(np.sum(w * r) / np.sum(w))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    b, be = ls["b"], ls["b_err"]
    ax.errorbar(b[sel], a[sel], xerr=be[sel], yerr=ae[sel], fmt="o", ms=7, capsize=2, color=COLORS["A anode charge (PE)"], alpha=0.6,
                label="anode charge (Ch1)")
    ax.errorbar(b[sel], s * d[sel], xerr=be[sel], yerr=s * de[sel], fmt="D", ms=4, capsize=2, mfc="none",
                color=COLORS["dynode 8, 50 Ohm charge (pC)"],
                label=f"dynode 8 charge (Ch4, 50 Ω) × {s:.3g} PE/pC")
    ok = b[sel][b[sel] > 0]
    xx = np.geomspace(max(np.nanmin(ok), 1e-3), np.nanmax(ok), 50)
    ax.plot(xx, k * xx, "k--", lw=0.8, label=f"linear, k = {k:.3g}")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("B per pulse"); ax.set_ylabel("A (PE per pulse)")
    ax.set_title(f"{regime}: A anode and dynode 8 against B ({sweep}-sweep)", fontsize=9)
    ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    ax = axes[1]
    sig = ls["b_sig"] & sel
    amp = ls["amp"]
    ax.errorbar(amp[sig], b[sig], yerr=be[sig], fmt="o", ms=4, capsize=2, label="B (significant)")
    ns = ~ls["b_sig"] & sel
    ax.errorbar(amp[ns], np.maximum(b[ns], 1e-4), yerr=be[ns], fmt="o", ms=4, mfc="none", color="0.6", capsize=2,
                label="B (not used)")
    vv = np.linspace(ls["v_on"], amp.max(), 100)
    f = ls["fit"]
    ax.plot(vv, f.value(vv), "C3", lw=1, label="smooth fit (light curve / k)")
    ax.fill_between(vv, f.value(vv) - f.error(vv), f.value(vv) + f.error(vv), color="C3", alpha=0.2)
    ax.set_yscale("log"); ax.set_xlabel("LED amplitude (V)"); ax.set_ylabel("B per pulse")
    ax.set_title("light curve from B", fontsize=9); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    fig.tight_layout()
    return fig
