"""Round-2 saturation analysis: per-point summaries, light scale and plots.

Works on raw ``FrameSet`` files saved by ``saturation_r2.ipynb``:

- ``<regime>_<sweep>_<amp>V_<stamp>.npz``: Ch1 (PMT A anode), Ch2 (PMT B anode),
  Ch3 (LED drive) and Ch4 (PMT A dynode 8 through 4.7 nF) at 50 Ohm;
- ``<regime>_<sweep>1M_<amp>V_<stamp>.npz``: the same LED point with Ch4 at 1 MOhm;
- ``ratio_<amp>V_<stamp>.npz``: the joint occupancy scan for the A/B light ratio k.

Conventions: anode pulses are negative, the dynode pickoff positive. Charges
are in pC (or PE with the SPE charge Q1), currents in mA into 50 Ohm, the
1 MOhm observable is the step height in V.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .hardware import FrameSet
from .saturation import (binned_charge, burst_frames, count_pulses, crossing, fwhm, late_early,
                         peak_current, rise_time, smooth_log_fit, step_height)
from .spe import baseline_subtract, integrate_charge, occupancy, window_mask

ANODES = (1, 2)
DYNODE = 4
PULSER = 3


def _mean_err(x) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("nan")


def _width(w) -> float:
    return w[1] - w[0]


def summarize_frames(fs: FrameSet, cfg: dict, q1_pc: dict, reject_bursts: bool = True) -> dict:
    """Per-point summary of one recording (any of the file kinds above).

    *cfg* holds the regime's windows (seconds from the trigger): baseline, signal,
    control (pedestal; scaled to the signal width), pre (burst check),
    pulser_window, plateau (1 MOhm step), and optionally time_bins/early/late,
    count_window/count_control/count_threshold_v/count_max_dt (B photon counting).
    """
    t = fs.time_s
    dt = float(t[1] - t[0])
    imp = {int(k): v for k, v in fs.meta.get("pmt_impedance", {}).items()}
    volts = {ch: fs.volts(ch) for ch in (*ANODES, DYNODE) if ch in fs.codes}
    keep = np.ones(fs.n_frames, dtype=bool)
    if reject_bursts:
        pre = window_mask(t, cfg["pre"])
        height = None
        if PULSER in fs.codes:
            height = np.median(fs.volts(PULSER)[:, window_mask(t, cfg["pulser_window"])], axis=1)
        # the 1 MOhm dynode trace carries a slow step; leave it out of the pickup check
        checked = {ch: v[:, pre] for ch, v in volts.items() if not (ch == DYNODE and imp.get(ch) == "OMEG")}
        keep = ~burst_frames(checked, height)
    row = {"amplitude_V": fs.meta["amplitude_V"], "label": fs.meta.get("label", ""), "t": t, "dt": dt,
           "n_frames": fs.n_frames, "n_rejected": int((~keep).sum()), "impedance": imp,
           "pulser_height_V": fs.meta.get("pulser_height_V"), "ch": {}}
    scale = _width(cfg["signal"]) / _width(cfg["control"])
    for ch, v_all in volts.items():
        v = baseline_subtract(v_all[keep], t, cfg["baseline"], False)
        mean_v = v.mean(axis=0)
        c = {"mean_v": mean_v, "impedance": imp.get(ch, "FIFTy")}
        if ch == DYNODE and c["impedance"] == "OMEG":
            dv = step_height(v, t, cfg["baseline"], cfg["plateau"])
            c["step_V"], c["step_err_V"] = _mean_err(dv)
            c["peak_V"], c["peak_err_V"] = _mean_err(v[:, window_mask(t, (cfg["signal"][0], cfg["plateau"][1]))].max(axis=1))
        else:
            # make every pulse negative (anodes already are; the dynode pickoff is positive)
            # so the negative-pulse helpers apply unchanged
            x = v if ch in ANODES else -v
            q = integrate_charge(x, t, cfg["signal"]) - scale * integrate_charge(x, t, cfg["control"]).mean()
            pk = peak_current(x, t, cfg["signal"], smooth=5)  # mA into 50 Ohm
            c["q_pC"], c["q_err_pC"] = _mean_err(q)
            c["peak_mA"], c["peak_err_mA"] = _mean_err(pk)
            if ch in q1_pc and ch in ANODES:
                c["pe"], c["pe_err"] = c["q_pC"] / q1_pc[ch], c["q_err_pC"] / q1_pc[ch]
            sig = window_mask(t, cfg["signal"])
            mx = x.mean(axis=0)
            c["fwhm_s"] = fwhm(t[sig], mx[sig])
            c["rise_s"] = rise_time(t[sig], mx[sig])
            if cfg.get("time_bins") is not None:
                bins = binned_charge(x, t, cfg["time_bins"])
                c["late_early"], c["late_early_err"] = late_early(bins, cfg["early"], cfg["late"])
        if ch == 2 and cfg.get("count_window") is not None and dt <= cfg.get("count_max_dt", 2e-9):
            n = count_pulses(v, t, cfg["count_window"], cfg["count_threshold_v"], polarity=-1)
            nc = count_pulses(v, t, cfg["count_control"], cfg["count_threshold_v"], polarity=-1)
            cs = _width(cfg["count_window"]) / _width(cfg["count_control"])
            m, e = _mean_err(n)
            mc, ec = _mean_err(nc)
            c["count"], c["count_err"] = m - cs * mc, float(np.hypot(e, cs * ec))
        row["ch"][ch] = c
    return row


def summarize_ratio(fs: FrameSet, cfg: dict, q1_pc: dict, n_sigma: float = 3.0) -> dict:
    """Joint occupancy point: zero-PE mu and mean PE for both anodes (100 ns pulses)."""
    t = fs.time_s
    volts = {ch: fs.volts(ch) for ch in ANODES if ch in fs.codes}
    pre = window_mask(t, cfg["pre"])
    keep = ~burst_frames({ch: v[:, pre] for ch, v in volts.items()})
    out = {"amplitude_V": fs.meta["amplitude_V"], "n": int(keep.sum()), "n_rejected": int((~keep).sum())}
    for ch, v_all in volts.items():
        v = baseline_subtract(v_all[keep], t, cfg["baseline"], False)
        s = integrate_charge(v, t, cfg["occ_signal"])
        c = integrate_charge(v, t, cfg["occ_control"])
        o = occupancy(s, c, n_sigma=n_sigma)
        mu_err = np.sqrt((1 - o.p0_signal) / (o.n * o.p0_signal)) if o.p0_signal > 0 else np.inf
        m, e = _mean_err(s - c.mean())
        out[ch] = {"mu": o.mu, "mu_err": float(mu_err), "pe": m / q1_pc[ch], "pe_err": e / q1_pc[ch],
                   "threshold_pC": o.threshold_pC}
    return out


def ratio_k(rows: list[dict], a_max_pe: float, b_min_mu: float = 0.02, b_max_mu: float = 2.0,
            spe_loss_b: float = 0.0) -> dict:
    """k = A PE (charge) / B zero-PE mu, per point and weighted mean over the usable points.

    Usable: B's mu significant (> 3 sigma) and inside [b_min_mu, b_max_mu], A below
    *a_max_pe* (still linear). *spe_loss_b* corrects B's mu for single PEs below
    the zero-PE threshold (fraction lost).
    """
    amp = np.array([r["amplitude_V"] for r in rows])
    a = np.array([r[1]["pe"] for r in rows]); ae = np.array([r[1]["pe_err"] for r in rows])
    mu = np.array([r[2]["mu"] for r in rows]) / (1 - spe_loss_b)
    mue = np.array([r[2]["mu_err"] for r in rows]) / (1 - spe_loss_b)
    use = (mu > 3 * mue) & (mu >= b_min_mu) & (mu <= b_max_mu) & (a <= a_max_pe) & (a > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = a / mu
        ke = k * np.hypot(ae / a, mue / mu)
    if use.sum() < 1:
        raise ValueError("no usable points for k")
    w = 1 / ke[use] ** 2
    kmean = float(np.sum(w * k[use]) / np.sum(w))
    kerr = float(1 / np.sqrt(np.sum(w)))
    chi2 = float(np.sum(w * (k[use] - kmean) ** 2))
    dof = int(use.sum() - 1)
    if dof > 0 and chi2 / dof > 1:
        kerr *= np.sqrt(chi2 / dof)
    return {"amp": amp, "k": k, "k_err": ke, "use": use, "k_mean": kmean, "k_mean_err": kerr,
            "chi2_dof": chi2 / dof if dof > 0 else float("nan")}


# -- scan analysis ----------------------------------------------------------

@dataclass
class ScanPoint:
    sweep: str
    amp: float
    r50: dict
    r1m: dict | None = None


def load_scan(out_dir, regime: str, cfg: dict, q1_pc: dict, stamp: str | None = None) -> tuple[list[ScanPoint], str]:
    """Load and summarize every point of the newest (or given) round-2 scan of *regime*."""
    out_dir = Path(out_dir)
    files = sorted(out_dir.glob(f"{regime}_up_*.npz")) + sorted(out_dir.glob(f"{regime}_down_*.npz"))
    if not files:
        raise FileNotFoundError(f"no {regime}_up/down files in {out_dir}")
    run = stamp or max("_".join(f.stem.split("_")[-2:]) for f in files)
    points = []
    for f in files:
        if not f.stem.endswith(run):
            continue
        sweep = "up" if f"{regime}_up_" in f.name else "down"
        r50 = summarize_frames(FrameSet.load(f), cfg, q1_pc)
        f1m = f.with_name(f.name.replace(f"{regime}_{sweep}_", f"{regime}_{sweep}1M_"))
        r1m = summarize_frames(FrameSet.load(f1m), cfg, q1_pc) if f1m.exists() else None
        points.append(ScanPoint(sweep, r50["amplitude_V"], r50, r1m))
    points.sort(key=lambda p: (p.sweep == "down", p.amp * (-1 if p.sweep == "down" else 1)))
    return points, run


def b_measure(points: list[ScanPoint], count_max: float = 100.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """B per pulse in PE: the photon count where present and below *count_max* (no pile-up),
    else charge / Q1. Returns (value, error, used_count)."""
    b, be, used = [], [], []
    for p in points:
        c = p.r50["ch"][2]
        if "count" in c and np.isfinite(c["count"]) and c["count"] < count_max:
            b.append(c["count"]); be.append(c["count_err"]); used.append(True)
        else:
            b.append(c["pe"]); be.append(c["pe_err"]); used.append(False)
    return np.array(b, float), np.array(be, float), np.array(used)


def fit_k_prefix(points: list[ScanPoint], b, b_err, b_min: float = 0.05, n_points: int = 3,
                 min_late_early: float | None = None) -> tuple[float, float, np.ndarray]:
    """A/B slope from the lowest-light up-sweep points with a significant B, stopping at the
    first point whose A pulse has collapsed (late/early < *min_late_early*, long pulses)."""
    a = np.array([p.r50["ch"][1]["pe"] for p in points]); ae = np.array([p.r50["ch"][1]["pe_err"] for p in points])
    ok = np.ones(len(points), bool)
    if min_late_early is not None:
        ok &= np.array([p.r50["ch"][1].get("late_early", 1.0) >= min_late_early for p in points])
    cand = np.flatnonzero((b >= b_min) & (b > 3 * b_err) & np.array([p.sweep == "up" for p in points]))
    cand = cand[np.argsort(b[cand])]
    fail = np.flatnonzero(~ok[cand])
    cand = cand[:fail[0]] if len(fail) else cand
    idx = cand[:n_points]
    if len(idx) < 1:
        raise ValueError("no fit points for k")
    r = a[idx] / b[idx]
    re = r * np.hypot(ae[idx] / a[idx], b_err[idx] / b[idx])
    w = 1 / re ** 2
    return float(np.sum(w * r) / np.sum(w)), float(1 / np.sqrt(np.sum(w))), idx


def light_scale(points: list[ScanPoint], k: float, k_err: float, b_min: float = 0.05,
                deg: int = 3, b_key: str = "pe", b=None, b_err=None) -> dict:
    """True light per point in A photoelectrons.

    Above the point where B becomes significant (>= *b_min* and > 3 sigma), the
    light is k times a smooth fit of B against LED voltage (all points, both
    sweeps); below it, A is assumed linear and its own PE are the light.
    *b_key* selects B's measure: "pe" (charge / Q1) or "count" (photon count), unless
    arrays *b*, *b_err* are given (e.g. from b_measure()).
    """
    amp = np.array([p.amp for p in points])
    a = np.array([p.r50["ch"][1]["pe"] for p in points])
    ae = np.array([p.r50["ch"][1]["pe_err"] for p in points])
    if b is None:
        b = np.array([p.r50["ch"][2].get(b_key, np.nan) for p in points])
        be = np.array([p.r50["ch"][2].get(b_key + "_err", np.nan) for p in points])
    else:
        b, be = np.asarray(b, float), np.asarray(b_err, float)
    sig = (b >= b_min) & (b > 3 * be)
    fit = smooth_log_fit(amp[sig], b[sig], be[sig], deg=deg)
    v_on = float(amp[sig].min())  # B is used from here up
    use_b = amp >= v_on
    b_fit, b_fit_err = fit.value(amp), fit.error(amp)
    light = np.where(use_b, k * b_fit, a)
    light_err = np.where(use_b, light * np.hypot(b_fit_err / b_fit, k_err / k), ae)
    return {"amp": amp, "light": light, "light_err": light_err, "use_b": use_b, "fit": fit,
            "b": b, "b_err": be, "b_sig": sig, "v_on": v_on}


def metric_table(points: list[ScanPoint]) -> dict:
    """Per-point arrays (value, error) of every response metric that is present."""
    def arr(getter):
        vals, errs = [], []
        for p in points:
            try:
                v, e = getter(p)
            except (KeyError, TypeError):
                v, e = np.nan, np.nan
            vals.append(v); errs.append(e)
        return np.array(vals, dtype=float), np.array(errs, dtype=float)

    m = {
        "A anode charge (PE)": arr(lambda p: (p.r50["ch"][1]["pe"], p.r50["ch"][1]["pe_err"])),
        "A anode peak (mA)": arr(lambda p: (p.r50["ch"][1]["peak_mA"], p.r50["ch"][1]["peak_err_mA"])),
        "B anode charge (PE)": arr(lambda p: (p.r50["ch"][2]["pe"], p.r50["ch"][2]["pe_err"])),
        "B anode peak (mA)": arr(lambda p: (p.r50["ch"][2]["peak_mA"], p.r50["ch"][2]["peak_err_mA"])),
        "dynode 8, 50 Ohm charge (pC)": arr(lambda p: (p.r50["ch"][4]["q_pC"], p.r50["ch"][4]["q_err_pC"])),
        "dynode 8, 50 Ohm peak (mA)": arr(lambda p: (p.r50["ch"][4]["peak_mA"], p.r50["ch"][4]["peak_err_mA"])),
        "dynode 8, 1 MOhm step (V)": arr(lambda p: (p.r1m["ch"][4]["step_V"], p.r1m["ch"][4]["step_err_V"])),
    }
    return {k: v for k, v in m.items() if np.isfinite(v[0]).any()}


def metric_linearity(value, err, light, light_err, fit_mask, levels=(0.05, 0.10)) -> dict:
    """Scale a metric to the light on *fit_mask* points (low light) and return its deviation."""
    value, err = np.asarray(value, float), np.asarray(err, float)
    ok = fit_mask & np.isfinite(value) & (value > 0) & (light > 0)
    if ok.sum() < 2:
        return {"scale": np.nan, "dev": np.full_like(value, np.nan), "dev_err": np.full_like(value, np.nan),
                "cross": {lv: None for lv in levels}, "n_fit": int(ok.sum())}
    ratio = value[ok] / light[ok]
    rerr = ratio * np.hypot(err[ok] / value[ok], light_err[ok] / light[ok])
    w = 1 / rerr ** 2
    s = float(np.sum(w * ratio) / np.sum(w))
    s_err = float(1 / np.sqrt(np.sum(w)))
    with np.errstate(divide="ignore", invalid="ignore"):
        dev = value / (s * light) - 1
        dev_err = np.abs(dev + 1) * np.sqrt((err / value) ** 2 + (light_err / light) ** 2 + (s_err / s) ** 2)
    good = np.isfinite(dev) & (light > 0)
    cross = {lv: crossing(light[good], dev[good], lv) for lv in levels}
    return {"scale": s, "scale_err": s_err, "dev": dev, "dev_err": dev_err, "cross": cross, "n_fit": int(ok.sum())}


__all__ = [
    "ANODES", "DYNODE", "PULSER", "summarize_frames", "summarize_ratio", "ratio_k", "ScanPoint",
    "load_scan", "b_measure", "fit_k_prefix", "light_scale", "metric_table", "metric_linearity",
]
