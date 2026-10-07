"""Frame acquisition shared by the LED-pulsed PMT notebooks.

A ``ScopeSession`` owns the Rigol connection and its settings, records frames
with the waveform recorder (reconnecting if the scope drops off the LAN), and
saves them raw. Nothing here computes charges: analysis lives in ``spe.py``
and ``saturation.py``.

The vertical auto-range (``autorange``) picks each PMT channel's V/div from a
few probe frames, so bright pulses are not clipped and dim ones are not
buried in quantization. It also enforces a hard peak limit on the 50 Ohm
inputs: ``PeakLimitExceeded`` means stop the light now.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from .hardware import FrameSet, RigolScope

SCOPE_DIVISIONS = 8  # vertical divisions on screen
# 1-2-5 V/div steps used by the auto-range (50 Ohm inputs).
SCALE_LADDER_V_DIV = (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)


class PeakLimitExceeded(RuntimeError):
    """A PMT pulse came too close to (or beyond) the safe input limit."""


@dataclass
class ScopeSettings:
    pmt_scale_v_div: dict[int, float]  # Rigol channel -> V/div (50 Ohm)
    pulser_channel: int = 3
    pulser_scale_v_div: float = 0.5
    pulser_offset_v: float = -1.5
    # Shift the PMT traces up by this many divisions so negative pulses get
    # 4 + offset_div of the 8 divisions (offset_v = offset_div * scale).
    pmt_offset_div: float = 3.0
    timebase_s_div: float = 100e-9
    time_offset_s: float = 0.0
    memory_depth: str = "1k"
    trig_level_v: float = 0.5

    @property
    def pmt_channels(self) -> tuple[int, ...]:
        return tuple(self.pmt_scale_v_div)


def screen_range(scale_v_div: float, offset_v: float) -> tuple[float, float]:
    """Voltage span shown on screen; a positive offset moves the trace up."""
    half = SCOPE_DIVISIONS / 2 * scale_v_div
    return -offset_v - half, -offset_v + half


def choose_scale(peak_v: float, clipped: bool, current: float, offset_div: float,
                 ladder=SCALE_LADDER_V_DIV, fill: float = 0.8) -> float:
    """V/div for a negative pulse of |peak_v| volts (smallest that keeps it within *fill*).

    If the probe was clipped the true peak is unknown, so step two rungs above
    *current* and probe again.
    """
    ladder = sorted(ladder)
    if clipped:
        above = [s for s in ladder if s > current]
        return above[min(1, len(above) - 1)] if above else ladder[-1]
    span_div = SCOPE_DIVISIONS / 2 + offset_div  # divisions below 0 V
    for s in ladder:
        if abs(peak_v) <= fill * span_div * s:
            return s
    return ladder[-1]


@dataclass
class ScopeSession:
    """Rigol connection + LED amplitude control for frame-recorder runs."""

    resource: str
    settings: ScopeSettings
    ad3: object  # AnalogDiscovery with a running pulse train (or a fake)
    rate_hz: float
    out_dir: Path
    stamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    max_led_v: float = 3.0
    retries: int = 3
    run_meta: dict = field(default_factory=dict)  # added to every saved file (HV state, ...)
    pulser_window: tuple[float, float] = (20e-9, 80e-9)  # where Ch3 shows the drive height
    scope_factory: Callable[[str], RigolScope] | None = None
    reconnect_wait_s: float = 10.0

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.scope: RigolScope | None = None
        self.amplitude: float | None = None

    # -- scope -------------------------------------------------------------
    def open(self) -> "ScopeSession":
        s = self.settings
        factory = self.scope_factory or (lambda r: RigolScope(r).connect())
        self.scope = factory(self.resource)
        for ch, scale in s.pmt_scale_v_div.items():
            self._apply_scale(ch, scale)
        self.scope.configure_channel(s.pulser_channel, s.pulser_scale_v_div, s.pulser_offset_v,
                                     impedance="OMEG")
        self.scope.configure_timebase(s.timebase_s_div, s.time_offset_s, s.memory_depth)
        self.scope.configure_edge_trigger(s.pulser_channel, s.trig_level_v, "POS")
        self.scope.set_trigger_sweep("NORM")
        self.scope._write(":RUN")
        return self

    def close(self) -> None:
        if self.scope is not None:
            self.scope.close()
            self.scope = None

    def _apply_scale(self, ch: int, scale: float) -> None:
        self.scope.configure_channel(ch, scale, self.settings.pmt_offset_div * scale,
                                     impedance="FIFTy")
        self.settings.pmt_scale_v_div[ch] = scale

    def channel_setting(self, ch: int) -> tuple[float, float]:
        """(V/div, offset V) as the scope reports them."""
        return (float(self.scope._query(f":CHAN{ch}:SCAL?")),
                float(self.scope._query(f":CHAN{ch}:OFFS?")))

    def set_scale(self, ch: int, scale: float) -> None:
        self._apply_scale(ch, scale)

    # -- LED ---------------------------------------------------------------
    def set_amplitude(self, volts: float) -> None:
        if volts != self.amplitude:
            self.ad3.set_pulse_amplitude(volts, max_v=self.max_led_v)
            self.amplitude = volts
            time.sleep(0.2)

    # -- recording ---------------------------------------------------------
    def record(self, n_frames: int, channels: tuple[int, ...] | None = None) -> FrameSet:
        """Record *n_frames* triggers, reconnecting if the scope drops the LAN link."""
        import pyvisa

        channels = channels or (*self.settings.pmt_channels, self.settings.pulser_channel)
        for attempt in range(1, self.retries + 1):
            try:
                return self.scope.record_frames(n_frames, channels,
                                                timeout_s=n_frames / self.rate_hz + 30)
            except (OSError, pyvisa.errors.VisaIOError) as exc:
                print(f"    scope connection lost ({exc!r}); reconnecting, attempt {attempt}")
                try:
                    self.close()
                except Exception:
                    pass
                time.sleep(self.reconnect_wait_s)
                self.open()
        raise RuntimeError(f"scope readout failed {self.retries} times")

    def acquire(self, amplitude: float, n_frames: int, label: str,
                channels: tuple[int, ...] | None = None, meta: dict | None = None,
                save: bool = True) -> FrameSet:
        """Set the LED amplitude, record, attach metadata and save raw frames."""
        self.set_amplitude(amplitude)
        fs = self.record(n_frames, channels)
        s = self.settings
        fs.meta.update(
            label=label, amplitude_V=amplitude, rate_Hz=self.rate_hz,
            pmt_scale_V_div={str(ch): s.pmt_scale_v_div[ch] for ch in s.pmt_channels},
            pmt_offset_div=s.pmt_offset_div, timebase_s_div=s.timebase_s_div,
            time_offset_s=s.time_offset_s, memory_depth=s.memory_depth,
            recorded_at=datetime.now().isoformat(), **self.run_meta, **(meta or {}))
        if s.pulser_channel in fs.codes:
            t = fs.time_s
            window = (t > self.pulser_window[0]) & (t < self.pulser_window[1])
            fs.meta["pulser_height_V"] = float(np.median(fs.volts(s.pulser_channel)[:, window]))
        if save:
            fs.save(self.out_dir / f"{label}_{amplitude:.3f}V_{self.stamp}.npz")
        return fs


@dataclass
class ChannelCheck:
    peak_v: float  # most negative sample over all frames (baseline-corrected)
    clipped: bool
    screen_v: tuple[float, float]


def check_peaks(fs: FrameSet, settings: ScopeSettings, baseline_window: tuple[float, float],
                max_peak_v: float) -> dict[int, ChannelCheck]:
    """Peak and clipping per PMT channel; raise PeakLimitExceeded above *max_peak_v*.

    A clipped trace whose screen already reaches *max_peak_v* also raises:
    its real peak is unknown and could be beyond the limit.
    """
    t = fs.time_s
    base = (t >= baseline_window[0]) & (t < baseline_window[1])
    out = {}
    for ch in settings.pmt_channels:
        if ch not in fs.codes:
            continue
        v = fs.volts(ch)
        scale = settings.pmt_scale_v_div[ch]
        lo, hi = screen_range(scale, settings.pmt_offset_div * scale)
        v_min = float(v.min())
        clipped = v_min <= lo + 0.01 * SCOPE_DIVISIONS * scale
        peak = v_min - float(np.median(v[:, base]))
        out[ch] = ChannelCheck(peak, clipped, (lo, hi))
        if abs(v_min) > max_peak_v or (clipped and abs(lo) >= max_peak_v):
            raise PeakLimitExceeded(
                f"Ch{ch}: peak {v_min:.3g} V{' (clipped)' if clipped else ''} at "
                f"{scale:g} V/div; limit {max_peak_v:g} V")
    return out


def autorange(session: ScopeSession, amplitude: float, baseline_window: tuple[float, float],
              max_peak_v: float, n_probe: int = 10, max_steps: int = 6,
              ladder=SCALE_LADDER_V_DIV, fill: float = 0.8) -> dict[int, float]:
    """Pick each PMT channel's V/div at *amplitude* from short probe recordings.

    Probe frames are not saved. Returns the chosen scales (also applied to the
    session). Raises PeakLimitExceeded if a probe exceeds *max_peak_v*.
    """
    s = session.settings
    for _ in range(max_steps):
        fs = session.acquire(amplitude, n_probe, "probe", channels=s.pmt_channels, save=False)
        checks = check_peaks(fs, s, baseline_window, max_peak_v)
        changed = False
        for ch, c in checks.items():
            new = choose_scale(c.peak_v, c.clipped, s.pmt_scale_v_div[ch], s.pmt_offset_div,
                               ladder, fill)
            if new != s.pmt_scale_v_div[ch]:
                session.set_scale(ch, new)
                changed = True
        if not changed:
            return dict(s.pmt_scale_v_div)
    raise RuntimeError(f"auto-range did not settle in {max_steps} steps: {s.pmt_scale_v_div}")


__all__ = [
    "SCOPE_DIVISIONS", "SCALE_LADDER_V_DIV", "PeakLimitExceeded", "ScopeSettings",
    "screen_range", "choose_scale", "ScopeSession", "ChannelCheck", "check_peaks", "autorange",
]
