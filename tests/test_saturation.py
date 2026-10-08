from __future__ import annotations

import numpy as np
import pytest

from ad3pulse.acquire import (PeakLimitExceeded, ScopeSession, ScopeSettings, autorange,
                              choose_scale, screen_range)
from ad3pulse.hardware import FrameSet, Preamble
from ad3pulse.saturation import (binned_charge, burst_frames, crossing, light_scale, flag_reference, fwhm, late_early,
                                 linearity, npe, peak_current, shape_ratio)


# -- analysis ---------------------------------------------------------------

def test_linearity_recovers_saturation_point() -> None:
    n_sat = 5000.0  # test = k N / (1 + N / n_sat): 5 % low at N = n_sat / 19
    n = np.geomspace(5, 20000, 200)
    k_true = 3.0
    ref = n * 0.002
    test = k_true * n / (1 + n / n_sat)
    lin = linearity(ref, test, fit_range=(ref[0], ref[10]))
    assert lin.k == pytest.approx(k_true / 0.002, rel=0.01)
    n5 = crossing(n, lin.deviation, 0.05)
    assert n5 == pytest.approx(n_sat / 19, rel=0.03)
    assert crossing(n, lin.deviation, 0.99) is None
    # an isolated noisy dip before the real bend is ignored
    assert crossing([1, 2, 3, 4, 5, 6], [0, -0.08, 0, -0.04, -0.2, -0.3], 0.05) == pytest.approx(4 + 1 / 16)
    assert crossing([1, 2, 3, 4], [0, 0, 0.01, -0.07], 0.05) is None          # one low last point


def test_linearity_weights_with_errors() -> None:
    ref = np.array([1.0, 2.0, 3.0, 4.0])
    test = np.array([2.0, 4.0, 6.0, 7.0])
    lin = linearity(ref, test, (1, 3), ref_err=np.full(4, 0.01), test_err=np.full(4, 0.01))
    assert lin.k == pytest.approx(2.0)
    assert lin.fit_mask.tolist() == [True, True, True, False]
    assert lin.deviation[-1] == pytest.approx(-0.125)
    with pytest.raises(ValueError):
        linearity(ref, test, (10, 20))


def _pulse_frames(t, amplitude_v, width, droop_tau=None, n_frames=20, noise=0.0, seed=0):
    """Negative rectangular pulses from t=0 to *width*, optionally drooping exponentially."""
    rng = np.random.default_rng(seed)
    shape = ((t >= 0) & (t < width)).astype(float)
    if droop_tau is not None:
        shape *= np.exp(-np.clip(t, 0, None) / droop_tau)
    v = -amplitude_v * shape
    return v + noise * rng.standard_normal((n_frames, len(t)))


def test_peak_current_and_npe() -> None:
    t = np.arange(-500, 500) * 1e-9
    v = _pulse_frames(t, 0.5, 20e-9)  # 0.5 V into 50 Ohm = 10 mA for 20 ns = 200 pC
    np.testing.assert_allclose(peak_current(v, t, (0, 100e-9)), 10.0)
    np.testing.assert_allclose(peak_current(v, t, (0, 100e-9), smooth=5), 10.0)
    q = binned_charge(v, t, [0, 10e-9, 100e-9])
    np.testing.assert_allclose(q.sum(-1), 200.0)
    assert npe(200.0, 0.5) == pytest.approx(400.0)
    assert fwhm(t, v[0]) == pytest.approx(20e-9, abs=1e-9)


def test_long_pulse_droop_ratio_and_reference_flag() -> None:
    t = np.arange(-5000, 25000) * 1e-9
    edges = np.arange(0, 10.01e-6, 1e-6)
    ref_bins = binned_charge(_pulse_frames(t, 0.01, 10e-6), t, edges)
    linear = binned_charge(_pulse_frames(t, 0.5, 10e-6), t, edges)
    depleting = binned_charge(_pulse_frames(t, 0.5, 10e-6, droop_tau=20e-6), t, edges)

    np.testing.assert_allclose(shape_ratio(linear, ref_bins), 50.0)
    r = shape_ratio(depleting, ref_bins) / shape_ratio(linear, ref_bins)
    assert r[0] > r[-1]  # A depleting: the ratio falls late in the pulse
    assert r[-1] == pytest.approx(np.exp(-9.5e-6 / 20e-6), rel=0.01)

    ratios = [late_early(linear, slice(0, 2), slice(8, 10))[0],
              late_early(depleting, slice(0, 2), slice(8, 10))[0]]
    assert ratios[0] == pytest.approx(1.0)
    assert flag_reference(ratios).tolist() == [False, True]


def test_reference_flag_ignores_noisy_points() -> None:
    t = np.arange(-1000, 11000) * 1e-9
    edges = np.arange(0, 10.01e-6, 1e-6)
    early, late = slice(1, 3), slice(7, 9)
    rows = [_pulse_frames(t, 0.01, 10e-6, noise=0.02, n_frames=50, seed=1),   # dim, noisy
            _pulse_frames(t, 0.10, 10e-6, noise=0.02, n_frames=50, seed=2),
            _pulse_frames(t, 0.10, 10e-6, droop_tau=40e-6, noise=0.02, n_frames=50, seed=3)]
    r, e = zip(*(late_early(binned_charge(v, t, edges), early, late) for v in rows))
    assert e[0] > 5 * e[1]
    assert flag_reference(r, e, reference=[0, 1]).tolist() == [False, False, True]


# -- acquisition: auto-range against a fake scope ---------------------------

def test_screen_range_and_choose_scale() -> None:
    assert screen_range(0.01, 0.03) == pytest.approx((-0.07, 0.01))
    # 7 divisions below zero with a 3-division offset; 80 % fill
    assert choose_scale(-0.050, False, 0.01, 3.0) == 0.01
    assert choose_scale(-0.060, False, 0.01, 3.0) == 0.02
    assert choose_scale(-0.003, False, 0.1, 3.0) == 0.002
    assert choose_scale(-0.070, True, 0.01, 3.0) == 0.05  # clipped: two rungs up
    assert choose_scale(-9.0, False, 0.01, 3.0) == 1.0


class FakeAD3:
    def __init__(self) -> None:
        self.amplitudes: list[float] = []

    def set_pulse_amplitude(self, volts, max_v=None) -> None:
        if max_v is not None and volts > max_v:
            raise ValueError("too high")
        self.amplitudes.append(volts)


class FakeScope:
    """Records frames of a negative pulse whose height depends on the LED amplitude."""

    def __init__(self, peaks: dict[int, float], ad3: FakeAD3) -> None:
        self.peaks = peaks  # channel -> volts per LED volt (negative pulse; a negative value = positive pulse)
        self.ad3 = ad3
        self.scale: dict[int, float] = {}
        self.offset: dict[int, float] = {}
        self.recorded: list[int] = []
        self.impedance: dict[int, str] = {}
        self.omeg_gain = 1.0          # signal multiplier while a channel is at 1 MOhm

    def configure_channel(self, ch, scale, offset=0.0, coupling="DC", impedance="OMEG"):
        self.scale[ch], self.offset[ch], self.impedance[ch] = scale, offset, impedance

    def configure_timebase(self, scale, offset=0.0, memory_depth=None):
        if memory_depth is not None:
            self.depth = memory_depth
    def configure_edge_trigger(self, *a, **k): pass
    def set_trigger_sweep(self, *a): pass
    depth = "1k"

    def _write(self, cmd):
        if cmd.startswith(":ACQ:MDEP"):
            self.depth = cmd.split()[1]
        elif cmd.startswith(":CHAN") and ":SCAL " in cmd:
            self.scale[int(cmd[5])] = float(cmd.split()[1])
        elif cmd.startswith(":CHAN") and ":OFFS " in cmd:
            self.offset[int(cmd[5])] = float(cmd.split()[1])

    def _query(self, cmd):
        if cmd.startswith(":CHAN") and cmd.endswith(":SCAL?"):
            return f"{self.scale[int(cmd[5])]:.6E}"
        if cmd.startswith(":CHAN") and cmd.endswith(":OFFS?"):
            return f"{self.offset[int(cmd[5])]:.6E}"
        if cmd == ":ACQ:MDEP?":
            from ad3pulse.acquire import parse_depth
            d = parse_depth(self.depth)
            return f"{d:.4E}" if self.depth in ("1k", "10k", "100k") else "1.0000E+03"   # invalid -> stays 1k
        return "0"
    def close(self): pass

    def record_frames(self, n_frames, channels, timeout_s=60.0, mode="NORM"):
        self.recorded.append(n_frames)
        t = np.arange(-500, 500) * 1e-9
        codes, pres = {}, {}
        for ch in channels:
            yinc = 2e-4  # codes stay inside uint16 for -6..+6 V
            pres[ch] = Preamble(1, 0, len(t), 1, 1e-9, -500e-9, 0, yinc, 0, 0)
            v = np.zeros((n_frames, len(t)))
            if ch in self.peaks:
                gain = self.omeg_gain if self.impedance.get(ch) == "OMEG" else 1.0
                v[:, 600:620] = -self.peaks[ch] * self.ad3.amplitudes[-1] * gain
                lo, hi = screen_range(self.scale[ch], self.offset[ch])
                v = np.clip(v, lo, hi)
            codes[ch] = np.round(v / yinc + 30000).astype(np.uint16)
            pres[ch].yorigin = 30000
        return FrameSet(time_s=t, codes=codes, preambles=pres, meta={})


def _session(tmp_path, peaks):
    ad3 = FakeAD3()
    scope = FakeScope(peaks, ad3)
    settings = ScopeSettings(pmt_scale_v_div={1: 0.01, 2: 0.01})
    s = ScopeSession("fake", settings, ad3, rate_hz=2.0, out_dir=tmp_path,
                     scope_factory=lambda r: scope).open()
    return s, scope


def test_autorange_widens_clipped_channel_and_keeps_dim_one(tmp_path) -> None:
    s, scope = _session(tmp_path, {1: 0.5, 2: 0.02})  # at 2 V: Ch1 -1 V, Ch2 -40 mV
    scales = autorange(s, 2.0, (-500e-9, -300e-9), max_peak_v=2.0)
    assert scales[1] == 0.2   # 1 V needs 7 div x 0.2 V x 0.8 = 1.12 V
    assert scales[2] == 0.01
    assert scope.scale[1] == 0.2 and scope.offset[1] == pytest.approx(0.6)
    fs = s.acquire(2.0, 5, "sat")
    assert fs.meta["pmt_scale_V_div"] == {"1": 0.2, "2": 0.01}
    assert fs.meta["pulser_height_V"] == 0.0
    assert len(list(tmp_path.glob("sat_2.000V_*.npz"))) == 1
    assert not list(tmp_path.glob("probe_*"))  # probes are not saved


def test_autorange_peak_guard(tmp_path) -> None:
    s, _ = _session(tmp_path, {1: 2.0, 2: 0.01})  # Ch1 -4 V at 2 V LED
    with pytest.raises(PeakLimitExceeded):
        autorange(s, 2.0, (-500e-9, -300e-9), max_peak_v=2.0)


def test_burst_frames_flags_pickup_and_bad_triggers() -> None:
    rng = np.random.default_rng(4)
    pre = {1: 0.001 * rng.standard_normal((200, 400)), 2: 0.002 * rng.standard_normal((200, 400))}
    pre[1][10, 50:55] -= 0.005           # a dark pulse: kept
    pre[2][20, 100:300] += 0.03 * np.sin(np.arange(200))  # burst on B only
    pre[1][30, :] += 0.2 * np.sin(np.arange(400) / 3)     # burst on A
    height = np.full(200, 1.9)
    height[40] = 0.6                      # a frame triggered by something other than the LED
    bad = burst_frames(pre, height)
    assert np.flatnonzero(bad).tolist() == [20, 30, 40]
    assert np.flatnonzero(burst_frames(pre)).tolist() == [20, 30]


def test_linearity_fit_mask_and_light_scale() -> None:
    n = np.array([1.0, 5, 20, 50, 200, 1000, 3000])        # true light, A PE
    a = n / (1 + n / 2000)                                  # A saturates
    b = n / 300                                             # B linear, 300x less light
    use_b = b >= 0.05
    fit = use_b & (a < 100)                                 # B usable and A still linear
    lin = linearity(b, a, ref_err=0.05 * b, test_err=0.01 * a, fit_mask=fit)
    assert lin.k == pytest.approx(300, rel=0.03)
    light = light_scale(a, b, lin.k, use_b)
    assert light[0] == a[0] and light[-1] == pytest.approx(3000, rel=0.03)
    dev = a / light - 1
    assert dev[-1] == pytest.approx(-0.6, abs=0.03)


def test_positive_pulse_channel_autorange_and_impedance_switch(tmp_path) -> None:
    from ad3pulse.acquire import ScopeSettings as SS
    ad3 = FakeAD3()
    scope = FakeScope({1: 0.1, 4: -0.4}, ad3)          # Ch4: positive pulses (dynode pickoff)
    settings = SS(pmt_scale_v_div={1: 0.01, 4: 0.01}, polarity={4: +1})
    s = ScopeSession("fake", settings, ad3, rate_hz=2.0, out_dir=tmp_path,
                     scope_factory=lambda r: scope).open()
    assert scope.offset[4] == pytest.approx(-0.03)      # positive pulses: trace shifted down
    assert screen_range(0.01, -0.03) == pytest.approx((-0.01, 0.07))
    scales = autorange(s, 2.0, (-500e-9, -300e-9), max_peak_v={1: 2.0, 4: 2.0})
    assert scales[4] == 0.2 and scales[1] == 0.05       # Ch4 +0.8 V, Ch1 -0.2 V
    s.set_impedance(4, "OMEG")                           # first 1 MOhm use: coarsest 1 MOhm step
    assert scope.impedance[4] == "OMEG" and settings.pmt_scale_v_div[4] == 2.0
    assert scope.offset[4] == 0.0                         # no offset at 1 MOhm (scope ignored it at 2 V/div)
    s.set_scale(4, 0.5)
    s.set_impedance(4, "FIFTy")                          # back to 50 Ohm: its last scale returns
    assert scope.impedance[4] == "FIFTy" and settings.pmt_scale_v_div[4] == 0.2
    s.set_impedance(4, "OMEG")
    assert settings.pmt_scale_v_div[4] == 0.5
    fs = s.acquire(2.0, 3, "x", save=False)
    assert fs.meta["pmt_impedance"]["4"] == "OMEG" and fs.meta["pmt_polarity"]["4"] == 1


def test_per_channel_peak_limit(tmp_path) -> None:
    from ad3pulse.acquire import ScopeSettings as SS
    ad3 = FakeAD3()
    scope = FakeScope({1: 0.1, 4: -2.0}, ad3)           # Ch4 +4 V at 2 V LED
    settings = SS(pmt_scale_v_div={1: 0.05, 4: 1.0}, polarity={4: +1})
    s = ScopeSession("fake", settings, ad3, rate_hz=2.0, out_dir=tmp_path,
                     scope_factory=lambda r: scope).open()
    with pytest.raises(PeakLimitExceeded) as exc:
        autorange(s, 2.0, (-500e-9, -300e-9), max_peak_v={1: 2.0, 4: 3.0})
    assert exc.value.channel == 4
    autorange(s, 2.0, (-500e-9, -300e-9), max_peak_v={1: 2.0})  # Ch4 unlimited: no error


def test_step_height_and_count_pulses() -> None:
    from ad3pulse.saturation import count_pulses, step_height
    t = np.arange(-500, 1500) * 1e-9
    v = np.zeros((3, len(t)))
    v[:, t >= 100e-9] = 0.25                      # 1 MOhm-like step of 0.25 V
    np.testing.assert_allclose(step_height(v, t, (-400e-9, -50e-9), (600e-9, 1400e-9)), 0.25)
    w = np.zeros((2, len(t)))
    for k in (100, 300, 700):                     # three negative SPE-like pulses in frame 0
        w[0, 500 + k:500 + k + 4] = -0.011
    w[1, 500 + 50:500 + 54] = -0.011
    w[1, 200:204] = -0.011                        # outside the window
    n = count_pulses(w, t, (0, 1000e-9), 0.005)
    assert n.tolist() == [3, 1]
    assert count_pulses(-w, t, (0, 1000e-9), 0.005, polarity=+1).tolist() == [3, 1]


def test_smooth_log_fit_recovers_curve() -> None:
    from ad3pulse.saturation import smooth_log_fit
    rng = np.random.default_rng(5)
    x = np.linspace(1.9, 3.0, 25)
    truth = np.exp(3 * (x - 1.9) - 0.8 * (x - 1.9) ** 2) * 0.05
    err = 0.05 * truth
    y = truth + err * rng.standard_normal(len(x))
    fit = smooth_log_fit(x, y, err, deg=3)
    assert np.all(np.abs(fit.value(x) - truth) < 3 * fit.error(x))   # consistent with its own errors
    assert np.all(fit.error(x[3:-3]) < 0.03 * truth[3:-3])          # smoothing beats single-point errors


def test_align_shift_and_rise_time() -> None:
    from ad3pulse.saturation import align_shift, rise_time
    t = np.arange(0, 400) * 1e-9
    a = np.exp(-0.5 * ((t - 150e-9) / 10e-9) ** 2)
    b = np.exp(-0.5 * ((t - 170e-9) / 10e-9) ** 2)
    assert align_shift(t, a, b) == pytest.approx(-20e-9)
    ramp = np.clip((t - 100e-9) / 100e-9, 0, 1)
    assert rise_time(t, -ramp) == pytest.approx(80e-9, abs=2e-9)


def test_memory_depth_is_verified(tmp_path) -> None:
    from ad3pulse.acquire import ScopeSettings as SS, parse_depth
    assert parse_depth("10k") == 1e4 and parse_depth("1.0000E+04") == 1e4 and parse_depth(1000) == 1e3
    ad3 = FakeAD3()
    scope = FakeScope({1: 0.1}, ad3)
    ScopeSession("fake", SS(pmt_scale_v_div={1: 0.01}, memory_depth="10k"), ad3, rate_hz=2.0,
                 out_dir=tmp_path, scope_factory=lambda r: scope).open()
    with pytest.raises(RuntimeError, match="not accepted"):
        ScopeSession("fake", SS(pmt_scale_v_div={1: 0.01}, memory_depth="20k"), ad3, rate_hz=2.0,
                     out_dir=tmp_path, scope_factory=lambda r: FakeScope({1: 0.1}, ad3)).open()


def test_apply_scale_reads_back_and_uses_actual_values(tmp_path) -> None:
    from ad3pulse.acquire import ScopeSettings as SS
    ad3 = FakeAD3()
    scope = FakeScope({1: 0.1}, ad3)
    s = ScopeSession("fake", SS(pmt_scale_v_div={1: 0.01}), ad3, rate_hz=2.0, out_dir=tmp_path,
                     scope_factory=lambda r: scope).open()
    assert s.settings.offset_actual == {}
    real_cfg = scope.configure_channel

    def sticky(ch, scale, offset=0.0, coupling="DC", impedance="OMEG"):   # scope ignores the new offset
        old = scope.offset.get(ch, 0.0)
        real_cfg(ch, scale, offset, coupling, impedance)
        scope.offset[ch] = old

    scope.configure_channel = sticky
    scope._write = lambda cmd: None                                      # and ignores the resend
    s.set_scale(1, 0.1)                                                  # wants +0.3 V, scope keeps +0.03 V
    assert s.settings.offset_actual[1] == pytest.approx(0.03)            # actual offset recorded ...
    assert s.settings.offset_v(1) == pytest.approx(0.03)                 # ... and used for the screen range
