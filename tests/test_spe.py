from __future__ import annotations

import numpy as np
import pytest

from ad3pulse.spe import (E_CHARGE, baseline_subtract, fit_spe, integrate_charge,
                          occupancy, pick_amplitude)

MU, Q1, S1, S0 = 0.15, 1.0, 0.35, 0.05  # PE/pulse, pC, pC, pC


def synthetic_charges(n: int, mu: float, seed: int = 1):
    rng = np.random.default_rng(seed)
    npe = rng.poisson(mu, n)
    signal = rng.normal(npe * Q1, np.sqrt(S0 ** 2 + npe * S1 ** 2))
    control = rng.normal(0.0, S0, n)
    return signal, control


def test_integrate_charge_of_rectangular_pulse() -> None:
    t = np.arange(1000) * 1e-9
    v = np.full((2, 1000), 0.01)  # 10 mV offset
    v[:, 500:520] -= 0.05  # -50 mV for 20 ns into 50 Ohm -> 20 pC
    v = baseline_subtract(v, t, (0, 400e-9))
    np.testing.assert_allclose(integrate_charge(v, t, (480e-9, 560e-9)), [20.0, 20.0])


def test_occupancy_recovers_mu() -> None:
    signal, control = synthetic_charges(50_000, MU)
    occ = occupancy(signal, control)
    assert occ.mu == pytest.approx(MU, abs=0.01)
    assert occ.threshold_pC == pytest.approx(3 * S0, rel=0.1)


def test_occupancy_subtracts_dark_counts() -> None:
    signal, control = synthetic_charges(50_000, MU)
    rng = np.random.default_rng(2)
    dark = rng.random(len(signal)) < 0.02  # 2% dark-count pulses in both windows
    signal = signal + dark * Q1
    control = control + (rng.random(len(control)) < 0.02) * Q1
    assert occupancy(signal, control).mu == pytest.approx(MU, abs=0.01)


def test_fit_spe_recovers_gain() -> None:
    signal, _ = synthetic_charges(50_000, MU)
    fit = fit_spe(signal)
    assert fit.q1_pC == pytest.approx(Q1, rel=0.05)
    assert fit.mu == pytest.approx(MU, rel=0.1)
    assert fit.gain == pytest.approx(Q1 * 1e-12 / E_CHARGE, rel=0.05)


def test_pick_amplitude_interpolates_log_mu() -> None:
    amps = [1.6, 1.7, 1.8, 1.9]
    mu = [0.01, 0.05, 0.25, 1.25]  # x5 per step
    assert pick_amplitude(amps, mu, 0.05) == pytest.approx(1.7)
    assert pick_amplitude(amps, mu, np.sqrt(0.05 * 0.25)) == pytest.approx(1.75)
    assert pick_amplitude(amps, mu, 5.0) is None
