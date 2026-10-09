from __future__ import annotations

import numpy as np
import pytest

from ad3pulse.hardware import FrameSet, Preamble
from ad3pulse.sat_analysis import (b_measure, light_scale, light_scale_matched, load_scan, metric_linearity,
                                   metric_table, ratio_k,
                                   summarize_frames, summarize_ratio)

Q1 = {1: 0.9, 2: 1.1}
CFG = dict(baseline=(-500e-9, -300e-9), signal=(40e-9, 440e-9), control=(-480e-9, -80e-9),
           pre=(-500e-9, 40e-9), pulser_window=(20e-9, 80e-9), plateau=(450e-9, 495e-9),
           occ_signal=(40e-9, 240e-9), occ_control=(-280e-9, -80e-9))
T = np.arange(-500, 500) * 1e-9
K = 200.0          # A/B light ratio
SAT = 30000.0      # A saturates as N / (1 + N / SAT); dynode 8 stays linear


def _frameset(chans: dict[int, np.ndarray], meta: dict) -> FrameSet:
    codes, pres = {}, {}
    for ch, v in chans.items():
        yinc = max(np.abs(v).max(), 0.01) / 20000
        pres[ch] = Preamble(1, 0, len(T), 1, 1e-9, T[0], 0, yinc, 32768, 0)
        codes[ch] = np.round(v / yinc + 32768).astype(np.uint16)
    return FrameSet(T, codes, pres, meta)


def _pulse(n_pe, q1_pc, t0=100e-9, width=50e-9):
    shape = ((T >= t0) & (T < t0 + width)).astype(float)
    shape /= shape.sum() * 1e-9
    return -np.outer(n_pe, shape) * q1_pc * 1e-12 * 50   # volts into 50 Ohm, negative


def _point(light, rng, n=200, impedance_1m=False):
    na = rng.poisson(light, n).astype(float)
    nb = rng.poisson(light / K, n).astype(float)
    a = _pulse(na / (1 + na / SAT), Q1[1]) + 0.4e-3 * rng.standard_normal((n, len(T)))
    b = _pulse(nb, Q1[2]) + 0.4e-3 * rng.standard_normal((n, len(T)))
    drive = np.where((T > 0) & (T < 100e-9), 1.9, 0.0) * np.ones((n, 1))
    dyn_q = 0.1 * na * Q1[1] * 1e-12                       # dynode 8 carries 10 % of the charge, linear
    if impedance_1m:
        step = np.where(T > 150e-9, 1.0, 0.0)
        d = np.outer(dyn_q / 5e-9, step) + 0.4e-3 * rng.standard_normal((n, len(T)))  # V = Q / 5 nF
        imp = {"1": "FIFTy", "2": "FIFTy", "4": "OMEG"}
    else:
        d = -_pulse(dyn_q / (Q1[1] * 1e-12), Q1[1]) + 0.4e-3 * rng.standard_normal((n, len(T)))
        imp = {"1": "FIFTy", "2": "FIFTy", "4": "FIFTy"}
    return {1: a, 2: b, 3: drive, 4: d}, imp


def test_summarize_signs_and_dynode_step() -> None:
    rng = np.random.default_rng(1)
    ch, imp = _point(500.0, rng)
    r = summarize_frames(_frameset(ch, {"amplitude_V": 2.0, "pmt_impedance": imp}), CFG, Q1)
    a, b, d = r["ch"][1], r["ch"][2], r["ch"][4]
    assert a["pe"] == pytest.approx(500 / (1 + 500 / SAT), rel=0.03)
    assert b["pe"] == pytest.approx(500 / K, rel=0.15)
    assert d["q_pC"] == pytest.approx(0.1 * 500 * Q1[1], rel=0.03)   # positive pickoff -> positive charge
    assert a["peak_mA"] > 0 and d["peak_mA"] > 0
    ch, imp = _point(500.0, rng, impedance_1m=True)
    r1 = summarize_frames(_frameset(ch, {"amplitude_V": 2.0, "pmt_impedance": imp}), CFG, Q1)
    assert r1["ch"][4]["step_V"] == pytest.approx(0.1 * 500 * Q1[1] * 1e-12 / 5e-9, rel=0.03)


def test_scan_light_scale_and_metric_linearity(tmp_path) -> None:
    rng = np.random.default_rng(2)
    amps = np.round(np.linspace(1.8, 3.0, 25), 3)
    lights = 20 * np.exp(6 * (amps - 1.8))          # smooth "LED curve", 20 .. ~27000 PE
    for amp, light in zip(amps, lights):
        for kind, imp1m in (("up", False), ("up1M", True)):
            ch, imp = _point(light, rng, n=300, impedance_1m=imp1m)
            _frameset(ch, {"amplitude_V": float(amp), "pmt_impedance": imp}).save(
                tmp_path / f"short_{kind}_{amp:.3f}V_20261008_000000.npz")
    points, run = load_scan(tmp_path, "short", CFG, Q1)
    assert run == "20261008_000000" and len(points) == 25 and all(p.r1m is not None for p in points)
    ls = light_scale(points, K, 0.02 * K, b_min=0.05)
    u = ls["use_b"]
    assert np.all(np.abs(ls["light"][u] - lights[u]) < 3 * ls["light_err"][u])   # within its errors
    assert np.all(ls["light_err"][u][5:] / ls["light"][u][5:] < 0.05)          # and precise above the edge
    m = metric_table(points)
    assert {"A anode charge (PE)", "dynode 8, 50 Ohm charge (pC)", "dynode 8, 1 MOhm step (V)"} <= set(m)
    fit = (ls["light"] > 100) & (ls["light"] < 500)  # B well measured, A < 2 % low
    lin_a = metric_linearity(*m["A anode charge (PE)"], ls["light"], ls["light_err"], fit)
    lin_d = metric_linearity(*m["dynode 8, 1 MOhm step (V)"], ls["light"], ls["light_err"], fit)
    assert lin_a["dev"][-1] < -0.3                  # anode saturates
    assert abs(lin_d["dev"][-1]) < 0.1              # dynode 8 stays linear
    assert lin_a["cross"][0.05] == pytest.approx(SAT / 19, rel=0.25)


def test_ratio_scan_gives_k() -> None:
    rng = np.random.default_rng(3)
    rows = []
    for amp, light in ((1.9, 20.0), (1.95, 40.0), (2.0, 80.0), (2.05, 160.0)):
        ch, _ = _point(light, rng, n=3000)
        rows.append(summarize_ratio(_frameset({1: ch[1], 2: ch[2]}, {"amplitude_V": amp}), CFG, Q1))
    res = ratio_k(rows, a_max_pe=SAT / 10)
    assert res["use"].sum() >= 3
    assert res["k_mean"] == pytest.approx(K, rel=0.12)


def test_matched_light_scale_is_continuous_and_finds_the_knee(tmp_path) -> None:
    rng = np.random.default_rng(6)
    amps = np.round(np.linspace(1.8, 3.0, 25), 3)
    lights = 20 * np.exp(6 * (amps - 1.8))
    for amp, light in zip(amps, lights):
        ch, imp = _point(light, rng, n=300)
        _frameset(ch, {"amplitude_V": float(amp), "pmt_impedance": imp}).save(
            tmp_path / f"short_up_{amp:.3f}V_20261008_000000.npz")
    points, _ = load_scan(tmp_path, "short", CFG, Q1)
    b, be, _ = b_measure(points)
    ls = light_scale_matched(points, b, be, a_window=(100.0, 600.0), k_ref=K)
    assert ls["k"] == pytest.approx(K, rel=0.1)
    a = np.array([p.r50["ch"][1]["pe"] for p in points])
    np.testing.assert_allclose(ls["light"][~ls["use_b"]], a[~ls["use_b"]])     # A below the hand-over
    u = ls["use_b"]
    assert np.all(np.abs(ls["light"][u] - lights[u]) < 3 * ls["light_err"][u] + 0.05 * lights[u])
    m = metric_table(points)
    lin = metric_linearity(*m["A anode charge (PE)"], ls["light"], ls["light_err"], ls["window"])
    assert lin["cross"][0.05] == pytest.approx(SAT / 19, rel=0.3)
