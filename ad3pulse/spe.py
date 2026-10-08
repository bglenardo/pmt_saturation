"""Single-photoelectron (SPE) analysis helpers for LED-pulsed PMT frames.

Kept separate from acquisition: these work on raw frames (volts, seconds)
saved by the acquisition code, so the notebook can re-run them on saved data.

Occupancy uses zero-PE Poisson counting: with mean mu photoelectrons per
pulse, the fraction of pulses with no PE is exp(-mu). The fraction is
measured with a threshold derived from the pedestal in a control window
(same width, before the light arrives), which also corrects for dark counts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

E_CHARGE = 1.602176634e-19  # C


def window_mask(t: np.ndarray, window: tuple[float, float]) -> np.ndarray:
    lo, hi = window
    mask = (t >= lo) & (t < hi)
    if not mask.any():
        raise ValueError(f"window {window} s contains no samples "
                         f"(record spans {t[0]:.3g}..{t[-1]:.3g} s)")
    return mask


def baseline_subtract(v: np.ndarray, t: np.ndarray, window: tuple[float, float],
                      per_frame: bool = True) -> np.ndarray:
    """Subtract the mean over *window* (samples along the last axis).

    per_frame=True removes each frame's own offset (follows slow drifts, but
    adds that window's noise to every frame); per_frame=False subtracts one
    median over all frames, which adds no noise.
    """
    mask = window_mask(t, window)
    if per_frame:
        return v - v[..., mask].mean(axis=-1, keepdims=True)
    return v - np.median(v[..., mask])


def integrate_charge(v: np.ndarray, t: np.ndarray, window: tuple[float, float],
                     r_ohm: float = 50.0) -> np.ndarray:
    """Charge in pC collected in *window*: -integral(V dt) / R.

    PMT anode pulses are negative, so a photoelectron gives a positive charge.
    """
    mask = window_mask(t, window)
    dt = float(t[1] - t[0])
    return -v[..., mask].sum(axis=-1) * dt / r_ohm * 1e12


def robust_sigma(x: np.ndarray) -> float:
    """Gaussian-equivalent sigma from the median absolute deviation."""
    x = np.asarray(x, dtype=float)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


@dataclass
class Occupancy:
    mu: float  # mean PE per pulse, dark-subtracted
    threshold_pC: float
    p0_signal: float  # fraction of pulses below threshold in the signal window
    p0_control: float  # same in the control window (dark counts)
    n: int


def occupancy(q_signal: np.ndarray, q_control: np.ndarray, n_sigma: float = 3.0,
              threshold_pC: float | None = None) -> Occupancy:
    """Mean PE per pulse from zero-PE counting: mu = -ln P0(signal) + ln P0(control).

    The threshold is the control-window pedestal median + n_sigma robust sigmas.
    Photoelectrons whose charge falls below it are counted as zero, so mu is
    slightly low when the SPE peak is not well separated from the pedestal.
    """
    q_signal = np.asarray(q_signal, dtype=float)
    q_control = np.asarray(q_control, dtype=float)
    if threshold_pC is None:
        threshold = float(np.median(q_control) + n_sigma * robust_sigma(q_control))
    else:  # e.g. a fraction of Q1, when the pedestal has non-Gaussian tails
        threshold = float(np.median(q_control) + threshold_pC)
    p0_s = float(np.mean(q_signal < threshold))
    p0_c = float(np.mean(q_control < threshold))
    mu = np.inf if p0_s == 0 else -np.log(p0_s) + np.log(p0_c)
    return Occupancy(float(mu), threshold, p0_s, p0_c, len(q_signal))


def pick_amplitude(amplitudes, mu, target: float) -> float | None:
    """LED amplitude giving *target* mu, interpolating log(mu) between scan points.

    Returns None if the target is outside the scanned range.
    """
    a = np.asarray(amplitudes, dtype=float)
    m = np.asarray(mu, dtype=float)
    ok = np.isfinite(m) & (m > 0)
    a, m = a[ok], m[ok]
    order = np.argsort(a)
    a, logm = a[order], np.log(m[order])
    for i in range(len(a) - 1):
        lo, hi = logm[i], logm[i + 1]
        if min(lo, hi) <= np.log(target) <= max(lo, hi) and lo != hi:
            return float(a[i] + (np.log(target) - lo) / (hi - lo) * (a[i + 1] - a[i]))
    return None


@dataclass
class SpeFit:
    q1_pC: float  # mean SPE charge
    sigma1_pC: float  # SPE charge spread
    mu: float  # mean PE per pulse
    q0_pC: float  # pedestal position
    sigma0_pC: float  # pedestal width
    q1_err_pC: float
    gain: float  # q1 / e
    bin_centers: np.ndarray
    counts: np.ndarray
    model: np.ndarray  # fitted counts per bin

    def __str__(self) -> str:
        return (f"Q1 = {self.q1_pC:.4g} ± {self.q1_err_pC:.2g} pC (σ1 {self.sigma1_pC:.3g} pC), "
                f"gain = {self.gain:.3g}, μ = {self.mu:.3f}, "
                f"pedestal {self.q0_pC:.3g} ± {self.sigma0_pC:.3g} pC")


def spe_model(x, norm, mu, q0, s0, q1, s1, n_pe: int = 3):
    """Pedestal + Poisson-weighted n-PE Gaussians (mean q0 + n q1, var s0² + n s1²)."""
    from math import factorial

    total = np.zeros_like(x, dtype=float)
    for n in range(n_pe + 1):
        weight = np.exp(-mu) * mu ** n / factorial(n)
        sigma = np.sqrt(s0 ** 2 + n * s1 ** 2)
        total += weight * np.exp(-0.5 * ((x - q0 - n * q1) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    return norm * total


def fit_spe(q: np.ndarray, mu_guess: float | None = None, bins: int = 200,
            q_range: tuple[float, float] | None = None, n_pe: int = 3) -> SpeFit:
    """Fit the signal-window charge spectrum with spe_model."""
    from scipy.optimize import curve_fit

    q = np.asarray(q, dtype=float)
    q0 = float(np.median(q))
    s0 = robust_sigma(q)
    thr = q0 + 3 * s0
    above = q[q > thr]
    if mu_guess is None:
        mu_guess = max(-np.log(max(np.mean(q < thr), 1e-6)), 1e-3)
    q1 = float(np.mean(above) - q0) if len(above) else 5 * s0
    if q_range is None:
        q_range = (q0 - 6 * s0, q0 + (n_pe + 1) * q1)
    counts, edges = np.histogram(q, bins=bins, range=q_range)
    centers = 0.5 * (edges[1:] + edges[:-1])
    width = edges[1] - edges[0]

    def f(x, mu, q0, s0, q1, s1):
        return spe_model(x, len(q) * width, mu, q0, s0, q1, s1, n_pe)

    p0 = [mu_guess, q0, s0, q1, 0.4 * q1]
    lower = [0, q0 - 5 * s0, 0.1 * s0, 0.5 * s0, 0.01 * q1]
    upper = [5, q0 + 5 * s0, 10 * s0, 10 * q1, 2 * q1]
    sigma = np.sqrt(np.maximum(counts, 1))
    popt, pcov = curve_fit(f, centers, counts, p0=p0, bounds=(lower, upper), sigma=sigma,
                           absolute_sigma=True, maxfev=20000)
    mu, q0, s0, q1, s1 = popt
    return SpeFit(q1_pC=float(q1), sigma1_pC=float(s1), mu=float(mu), q0_pC=float(q0),
                  sigma0_pC=float(s0), q1_err_pC=float(np.sqrt(pcov[3, 3])),
                  gain=float(q1 * 1e-12 / E_CHARGE), bin_centers=centers,
                  counts=counts, model=f(centers, *popt))


__all__ = [
    "E_CHARGE", "window_mask", "baseline_subtract", "integrate_charge", "robust_sigma",
    "Occupancy", "occupancy", "pick_amplitude", "SpeFit", "spe_model", "fit_spe",
]
