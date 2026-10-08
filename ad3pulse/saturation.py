"""PMT saturation (linearity) analysis with a reference PMT.

One LED lights both PMTs: PMT A (device under test) gets far more light than
PMT B (reference). While B stays linear, its charge is proportional to the
true light per pulse, so A's departure from proportionality to B is A's
non-linearity. This cancels the LED's own non-linearity and drift.

Two regimes:
- short (~100 ns) pulses: space-charge limit on the peak anode current;
- long (~10 us) pulses: depletion of the charge stored in the base capacitors,
  which shows up as the current drooping *during* the pulse.

Signs for the long-pulse ratio A(t)/B(t) (normalised to low light): A
depleting makes it fall late in the pulse; B depleting makes it rise. B has
fewer base capacitors, so watch for the rise.

Like ``spe.py``, everything works on raw frames (volts, seconds).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spe import integrate_charge, window_mask


def npe(q_pC, q1_pC: float):
    """Photoelectrons from charge, using the SPE charge Q1."""
    return np.asarray(q_pC, dtype=float) / q1_pC


def peak_current(v: np.ndarray, t: np.ndarray, window: tuple[float, float],
                 r_ohm: float = 50.0, smooth: int = 1) -> np.ndarray:
    """Peak anode current per frame in mA (positive for negative pulses).

    *smooth* > 1 applies a moving average of that many samples first, so the
    peak of small pulses is not biased up by noise.
    """
    mask = window_mask(t, window)
    x = v[..., mask]
    if smooth > 1:
        kernel = np.ones(smooth) / smooth
        x = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), -1, x)
    return -x.min(axis=-1) / r_ohm * 1e3


def binned_charge(v: np.ndarray, t: np.ndarray, edges, r_ohm: float = 50.0) -> np.ndarray:
    """Charge in pC in each time bin [edges[i], edges[i+1]); shape (..., n_bins)."""
    return np.stack([integrate_charge(v, t, (lo, hi), r_ohm)
                     for lo, hi in zip(edges[:-1], edges[1:])], axis=-1)


def fwhm(t: np.ndarray, v: np.ndarray) -> float:
    """Full width at half maximum of a negative pulse (e.g. a mean waveform)."""
    v = np.asarray(v, dtype=float)
    i = int(np.argmin(v))
    half = v[i] / 2
    left = i
    while left > 0 and v[left] < half:
        left -= 1
    right = i
    while right < len(v) - 1 and v[right] < half:
        right += 1

    def cross(a, b):  # linear interpolation of the half-level crossing between samples a, b
        if v[b] == v[a]:
            return t[a]
        return t[a] + (half - v[a]) / (v[b] - v[a]) * (t[b] - t[a])

    return float(cross(right - 1, right) - cross(left, left + 1))


@dataclass
class PointSummary:
    """Per-intensity-point means for one PMT channel."""

    amplitude_V: float
    q_mean_pC: float
    q_err_pC: float  # standard error of the mean
    peak_mean_mA: float
    peak_err_mA: float
    n: int


def summarize_point(q_pC: np.ndarray, peak_mA: np.ndarray, amplitude_V: float) -> PointSummary:
    q = np.asarray(q_pC, dtype=float)
    p = np.asarray(peak_mA, dtype=float)
    n = len(q)
    return PointSummary(amplitude_V, float(q.mean()), float(q.std(ddof=1) / np.sqrt(n)),
                        float(p.mean()), float(p.std(ddof=1) / np.sqrt(n)), n)


@dataclass
class Linearity:
    k: float  # test / ref slope in the linear region
    k_err: float
    deviation: np.ndarray  # test / (k ref) - 1 per point
    deviation_err: np.ndarray
    fit_mask: np.ndarray  # points used for k


def linearity(ref, test, fit_range: tuple[float, float] | None = None, ref_err=None, test_err=None,
              fit_mask=None) -> Linearity:
    """Fit test = k * ref (through the origin) on the fit points; return deviations.

    The fit points are those with *ref* inside *fit_range*, or the boolean
    *fit_mask* if given (e.g. "B above threshold and A still far from
    saturation"). Use per-point means (charges in pC, or N_pe).
    """
    ref = np.asarray(ref, dtype=float)
    test = np.asarray(test, dtype=float)
    ref_err = np.zeros_like(ref) if ref_err is None else np.asarray(ref_err, dtype=float)
    test_err = np.zeros_like(test) if test_err is None else np.asarray(test_err, dtype=float)
    if fit_mask is not None:
        mask = np.asarray(fit_mask, dtype=bool)
    else:
        mask = (ref >= fit_range[0]) & (ref <= fit_range[1])
    if mask.sum() < 2:
        raise ValueError(f"need at least 2 fit points, have {mask.sum()}")
    ratio = test[mask] / ref[mask]
    rel = np.hypot(test_err[mask] / test[mask], ref_err[mask] / ref[mask])
    if np.all(rel > 0):
        w = 1 / (ratio * rel) ** 2
        k = float(np.sum(w * ratio) / np.sum(w))
        k_err = float(1 / np.sqrt(np.sum(w)))
        # inflate by the scatter if the points disagree more than their errors
        chi2 = float(np.sum(w * (ratio - k) ** 2))
        if mask.sum() > 1:
            k_err *= max(1.0, np.sqrt(chi2 / (mask.sum() - 1)))
    else:
        k = float(np.mean(ratio))
        k_err = float(np.std(ratio, ddof=1) / np.sqrt(len(ratio)))
    dev = test / (k * ref) - 1
    dev_err = np.abs(dev + 1) * np.sqrt((test_err / test) ** 2 + (ref_err / ref) ** 2 + (k_err / k) ** 2)
    return Linearity(k, k_err, dev, dev_err, mask)


def light_scale(test, ref, k: float, use_ref) -> np.ndarray:
    """True light per point in test-PMT PE: k * ref where *use_ref*, else the test PMT itself.

    Below the reference's useful range the test PMT is assumed linear (its
    deviation is then zero by construction); above it, the reference scaled
    by the fitted slope k measures the light.
    """
    test = np.asarray(test, dtype=float)
    ref = np.asarray(ref, dtype=float)
    return np.where(np.asarray(use_ref, dtype=bool), k * ref, test)


def crossing(x, deviation, level: float, min_run: int = 2) -> float | None:
    """x where the deviation falls to -*level* for good, interpolated (*level* > 0, e.g. 0.05).

    Points are taken in increasing x; the crossing is the last downward pass
    through -*level* after which every point stays below it, so a single
    noisy dip does not count. The final run below must have at least
    *min_run* points (a lone low last point is not a crossing). Returns None
    if the curve does not end below.
    """
    x = np.asarray(x, dtype=float)
    d = np.asarray(deviation, dtype=float)
    order = np.argsort(x)
    x, d = x[order], d[order]
    if not len(d) or d[-1] > -level:
        return None
    above = np.flatnonzero(d > -level)
    if not len(above):
        return float(x[0])
    i = above[-1] + 1  # first point of the final run below -level
    if len(d) - i < min_run:
        return None
    return float(x[i - 1] + (-level - d[i - 1]) / (d[i] - d[i - 1]) * (x[i] - x[i - 1]))


def shape_ratio(test_bins, ref_bins) -> np.ndarray:
    """Mean binned charge of test / ref per time bin (inputs shaped (frames, bins))."""
    return np.asarray(test_bins, dtype=float).mean(axis=0) / np.asarray(ref_bins, dtype=float).mean(axis=0)


def late_early(bins, early: int | slice, late: int | slice) -> tuple[float, float]:
    """Late / early mean charge for one channel, from binned_charge output; (ratio, error).

    The error is the standard error from the frame-to-frame spread, so a
    dim reference gives a noisy ratio rather than a false alarm.
    """
    b = np.asarray(bins, dtype=float)
    e = b[:, early].reshape(len(b), -1).sum(axis=1)
    lt = b[:, late].reshape(len(b), -1).sum(axis=1)
    n = len(b)
    me, ml = e.mean(), lt.mean()
    r = float(ml / me)
    if n < 2:
        return r, float("nan")
    cov = np.cov(lt, e) / n  # [[var_l, cov], [cov, var_e]] of the means
    var = r ** 2 * (cov[0, 0] / ml ** 2 + cov[1, 1] / me ** 2 - 2 * cov[0, 1] / (ml * me))
    return r, float(np.sqrt(max(var, 0.0)))


def flag_reference(ratios, errors=None, reference=None, tolerance: float = 0.02,
                   n_sigma: float = 3.0) -> np.ndarray:
    """True where the reference PMT's late/early (or other shape) ratio has changed.

    *reference* is the expected value: an index into *ratios*, a list of
    indices (error-weighted mean), or None for index 0. A point is flagged
    when it differs by more than *tolerance* (relative) and, if *errors* are
    given, also by more than *n_sigma* combined errors.

    A change means the reference's pulse shape changed with intensity: either
    the reference is depleting (B has fewer base capacitors) or the LED's
    own time profile changed. Points flagged here make the A/B ratio suspect.
    """
    r = np.asarray(ratios, dtype=float)
    err = None if errors is None else np.asarray(errors, dtype=float)
    idx = np.atleast_1d(0 if reference is None else reference)
    if err is None:
        r0, e0 = float(np.mean(r[idx])), 0.0
    else:
        w = 1 / err[idx] ** 2
        r0, e0 = float(np.sum(w * r[idx]) / np.sum(w)), float(1 / np.sqrt(np.sum(w)))
    diff = np.abs(r - r0)
    flag = diff > tolerance * abs(r0)
    if err is not None:
        flag &= diff > n_sigma * np.hypot(err, e0)
    return flag


def burst_frames(v_pre: dict, pulser_height=None, min_pp_v: float = 0.02, n_sigma: float = 10.0,
                 pulser_tolerance: float = 0.10) -> np.ndarray:
    """True for frames hit by a pickup burst; use ``~burst_frames(...)`` to keep the good ones.

    *v_pre* maps channel -> samples (frames, n) from a window before any light
    arrives. A frame is a burst if any channel's peak-to-peak there exceeds
    max(*min_pp_v*, *n_sigma* x the robust spread of all frames' peak-to-peak).
    Single dark pulses (a few mV) stay below *min_pp_v*. With *pulser_height*
    (LED drive per frame), frames whose drive is off by more than
    *pulser_tolerance* from the median are also flagged: some bursts triggered
    the scope themselves.
    """
    bad = None
    for v in v_pre.values():
        pp = np.ptp(np.asarray(v, dtype=float), axis=-1)
        med = np.median(pp)
        spread = 1.4826 * np.median(np.abs(pp - med))
        flag = pp > max(min_pp_v, med + n_sigma * spread)
        bad = flag if bad is None else bad | flag
    if pulser_height is not None:
        h = np.asarray(pulser_height, dtype=float)
        ref = np.median(h)
        flag = np.abs(h - ref) > pulser_tolerance * abs(ref)
        bad = flag if bad is None else bad | flag
    return bad


def step_height(v: np.ndarray, t: np.ndarray, pre: tuple[float, float],
                plateau: tuple[float, float]) -> np.ndarray:
    """Per-frame step height: mean over *plateau* minus mean over *pre* (volts).

    For a pickoff into 1 MOhm the trace integrates the signal charge: it steps
    by ~Q/C and decays only with RC ~ ms, so the step height measures charge.
    """
    return v[..., window_mask(t, plateau)].mean(axis=-1) - v[..., window_mask(t, pre)].mean(axis=-1)


def count_pulses(v: np.ndarray, t: np.ndarray, window: tuple[float, float], threshold_v: float,
                 polarity: int = -1) -> np.ndarray:
    """Number of threshold crossings in the pulse direction per frame (photon counting).

    Counts transitions from below to beyond |threshold| (negative pulses for
    polarity -1). Valid while single-PE pulses don't pile up.
    """
    x = -polarity * np.asarray(v, dtype=float)[..., window_mask(t, window)]
    x = -x  # pulse direction is now positive
    above = x > abs(threshold_v)
    return (above[..., 1:] & ~above[..., :-1]).sum(axis=-1)


@dataclass
class SmoothFit:
    """log y = polynomial(x) fitted with weights; evaluate with value() and error()."""

    coef: np.ndarray
    cov: np.ndarray
    x0: float  # centring of x for numerical stability

    def value(self, x) -> np.ndarray:
        return np.exp(np.polyval(self.coef, np.asarray(x, dtype=float) - self.x0))

    def error(self, x) -> np.ndarray:
        """1-sigma error of value(x) from the coefficient covariance."""
        x = np.asarray(x, dtype=float) - self.x0
        deg = len(self.coef) - 1
        jac = np.stack([x ** (deg - i) for i in range(deg + 1)], axis=-1)
        var_log = np.einsum("...i,ij,...j->...", jac, self.cov, jac)
        return self.value(x + self.x0) * np.sqrt(np.maximum(var_log, 0))


def smooth_log_fit(x, y, yerr, deg: int = 3) -> SmoothFit:
    """Weighted fit of log(y) against x with a polynomial of *deg*.

    Used for the light curve: B's signal against LED voltage, which is smooth
    and monotone, so each point's light comes from all points.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    yerr = np.asarray(yerr, dtype=float)
    ok = (y > 0) & (yerr > 0)
    if ok.sum() < deg + 2:
        raise ValueError(f"need at least {deg + 2} positive points, have {ok.sum()}")
    x0 = float(np.mean(x[ok]))
    w = y[ok] / yerr[ok]  # 1 / sigma of log y
    coef, cov = np.polyfit(x[ok] - x0, np.log(y[ok]), deg, w=w, cov="unscaled")
    # Weighting by the measured y favours upward fluctuations where the signal is
    # small (biasing the fit high there); refit with the fitted value instead.
    w = np.exp(np.polyval(coef, x[ok] - x0)) / yerr[ok]
    coef, cov = np.polyfit(x[ok] - x0, np.log(y[ok]), deg, w=w, cov="unscaled")
    resid = (np.log(y[ok]) - np.polyval(coef, x[ok] - x0)) * w
    dof = ok.sum() - deg - 1
    chi2 = float(np.sum(resid ** 2))
    if dof > 0 and chi2 / dof > 1:
        cov = cov * chi2 / dof  # inflate if points scatter more than their errors
    return SmoothFit(coef, cov, x0)


def align_shift(t: np.ndarray, a: np.ndarray, b: np.ndarray, max_shift_s: float = 50e-9) -> float:
    """Time shift (s) to add to *b*'s time axis so it best matches *a* (cross-correlation)."""
    dt = float(t[1] - t[0])
    n = max(1, int(round(max_shift_s / dt)))
    a = np.asarray(a, dtype=float) - np.mean(a)
    b = np.asarray(b, dtype=float) - np.mean(b)
    best, best_k = -np.inf, 0
    for k in range(-n, n + 1):
        c = float(np.dot(a, np.roll(b, k)))
        if c > best:
            best, best_k = c, k
    return best_k * dt


def rise_time(t: np.ndarray, v: np.ndarray, lo: float = 0.1, hi: float = 0.9) -> float:
    """10-90 % rise time of a pulse (sign-independent) from its start to its extreme."""
    v = np.asarray(v, dtype=float)
    x = v if abs(v.max()) >= abs(v.min()) else -v
    i = int(np.argmax(x))
    peak = x[i]

    def first_cross(level):
        idx = np.flatnonzero(x[: i + 1] >= level * peak)
        j = int(idx[0])
        if j == 0:
            return float(t[0])
        return float(t[j - 1] + (level * peak - x[j - 1]) / (x[j] - x[j - 1]) * (t[j] - t[j - 1]))

    return first_cross(hi) - first_cross(lo)


__all__ = [
    "npe", "peak_current", "binned_charge", "fwhm", "PointSummary", "summarize_point",
    "step_height", "count_pulses", "SmoothFit", "smooth_log_fit", "align_shift", "rise_time",
    "Linearity", "linearity", "light_scale", "crossing", "shape_ratio", "late_early", "flag_reference", "burst_frames",
]
