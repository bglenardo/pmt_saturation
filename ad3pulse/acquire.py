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
# 1-2-5 V/div steps used by the auto-range. 50 Ohm inputs go up to 1 V/div,
# 1 MOhm up to 10 V/div (MHO900 datasheet p. 11).
SCALE_LADDER_V_DIV = (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0)
SCALE_LADDER_1M_V_DIV = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0)
LADDERS = {"FIFTy": SCALE_LADDER_V_DIV, "OMEG": SCALE_LADDER_1M_V_DIV}


class PeakLimitExceeded(RuntimeError):
    """A PMT pulse came too close to (or beyond) the safe input limit."""

    def __init__(self, message: str, channel: int | None = None) -> None:
        super().__init__(message)
        self.channel = channel


@dataclass
class ScopeSettings:
    pmt_scale_v_div: dict[int, float]  # Rigol channel -> V/div
    pulser_channel: int = 3
    pulser_scale_v_div: float = 0.5
    pulser_offset_v: float = -1.5
    # Shift the PMT traces by this many divisions so pulses get 4 + offset_div
    # of the 8 divisions: up for negative (anode) pulses, down for positive
    # (dynode pickoff) ones. offset_v = -polarity * offset_div * scale.
    pmt_offset_div: float = 3.0
    polarity: dict[int, int] = field(default_factory=dict)  # channel -> -1 (default) or +1
    impedance: dict[int, str] = field(default_factory=dict)  # channel -> "FIFTy" (default) or "OMEG"
    timebase_s_div: float = 100e-9
    time_offset_s: float = 0.0
    memory_depth: str = "1k"
    trig_level_v: float = 0.5

    @property
    def pmt_channels(self) -> tuple[int, ...]:
        return tuple(self.pmt_scale_v_div)

    def pol(self, ch: int) -> int:
        return self.polarity.get(ch, -1)

    def imp(self, ch: int) -> str:
        return self.impedance.get(ch, "FIFTy")

    def offset_v(self, ch: int) -> float:
        return -self.pol(ch) * self.pmt_offset_div * self.pmt_scale_v_div[ch]


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
    replay_mode: str = "NORM"  # record_frames() readout mode; "MAX" = full memory (if it works)
    reconnect_wait_s: float = 10.0

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.scope: RigolScope | None = None
        self.amplitude: float | None = None
        self._scale_memory: dict[tuple[int, str], float] = {}

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
        s = self.settings
        s.pmt_scale_v_div[ch] = scale
        self.scope.configure_channel(ch, scale, s.offset_v(ch), impedance=s.imp(ch))
        self._scale_memory[(ch, s.imp(ch))] = scale

    def set_impedance(self, ch: int, impedance: str, scale: float | None = None) -> None:
        """Switch *ch* to "FIFTy" or "OMEG"; restore that impedance's last V/div unless *scale* is given.

        Without a remembered scale the coarsest step of that impedance's ladder
        is used, so the first probe can't be overdriven on screen.
        """
        if impedance not in LADDERS:
            raise ValueError(f"impedance {impedance!r}: use FIFTy or OMEG")
        if scale is None:
            scale = self._scale_memory.get((ch, impedance), LADDERS[impedance][-1])
        self.settings.impedance[ch] = impedance
        self._apply_scale(ch, scale)

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
                                                timeout_s=n_frames / self.rate_hz + 30,
                                                mode=self.replay_mode)
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
            pmt_impedance={str(ch): s.imp(ch) for ch in s.pmt_channels},
            pmt_polarity={str(ch): s.pol(ch) for ch in s.pmt_channels},
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
    peak_v: float  # most extreme sample in the pulse direction over all frames (baseline-corrected)
    clipped: bool
    screen_v: tuple[float, float]


def check_peaks(fs: FrameSet, settings: ScopeSettings, baseline_window: tuple[float, float],
                max_peak_v) -> dict[int, ChannelCheck]:
    """Peak and clipping per PMT channel; raise PeakLimitExceeded above the limit.

    *max_peak_v* is one limit for all channels or a dict channel -> limit (a
    channel missing from the dict is not limited). Pulses are negative or
    positive per ``settings.pol(ch)``. A clipped trace whose screen edge already
    reaches the limit also raises: its real peak is unknown and could be beyond.
    """
    t = fs.time_s
    base = (t >= baseline_window[0]) & (t < baseline_window[1])
    out = {}
    for ch in settings.pmt_channels:
        if ch not in fs.codes:
            continue
        v = fs.volts(ch)
        pol = settings.pol(ch)
        scale = settings.pmt_scale_v_div[ch]
        lo, hi = screen_range(scale, settings.offset_v(ch))
        margin = 0.01 * SCOPE_DIVISIONS * scale
        if pol < 0:
            extreme = float(v.min())
            edge, clipped = lo, extreme <= lo + margin
        else:
            extreme = float(v.max())
            edge, clipped = hi, extreme >= hi - margin
        peak = extreme - float(np.median(v[:, base]))
        out[ch] = ChannelCheck(peak, clipped, (lo, hi))
        limit = max_peak_v.get(ch) if isinstance(max_peak_v, dict) else max_peak_v
        if limit is not None and (abs(extreme) > limit or (clipped and abs(edge) >= limit)):
            raise PeakLimitExceeded(
                f"Ch{ch} ({settings.imp(ch)}): peak {extreme:.3g} V{' (clipped)' if clipped else ''} "
                f"at {scale:g} V/div; limit {limit:g} V", channel=ch)
    return out


def autorange(session: ScopeSession, amplitude: float, baseline_window: tuple[float, float],
              max_peak_v, n_probe: int = 10, max_steps: int = 6,
              ladder=None, fill: float = 0.8,
              channels: tuple[int, ...] | None = None) -> dict[int, float]:
    """Pick each PMT channel's V/div at *amplitude* from short probe recordings.

    Probe frames are not saved. Returns the chosen scales (also applied to the
    session). *ladder* is one ladder for all channels, or None for the ladder of
    each channel's impedance. *channels* limits the ranging to a subset.
    Raises PeakLimitExceeded if a probe exceeds the limit (see check_peaks).
    """
    s = session.settings
    channels = channels or s.pmt_channels
    for _ in range(max_steps):
        fs = session.acquire(amplitude, n_probe, "probe", channels=channels, save=False)
        checks = check_peaks(fs, s, baseline_window, max_peak_v)
        changed = False
        for ch, c in checks.items():
            lad = ladder if ladder is not None else LADDERS[s.imp(ch)]
            new = choose_scale(c.peak_v, c.clipped, s.pmt_scale_v_div[ch], s.pmt_offset_div,
                               lad, fill)
            if new != s.pmt_scale_v_div[ch]:
                session.set_scale(ch, new)
                changed = True
        if not changed:
            return dict(s.pmt_scale_v_div)
    raise RuntimeError(f"auto-range did not settle in {max_steps} steps: {s.pmt_scale_v_div}")


__all__ = [
    "SCOPE_DIVISIONS", "SCALE_LADDER_V_DIV", "SCALE_LADDER_1M_V_DIV", "LADDERS",
    "PeakLimitExceeded", "ScopeSettings",
    "screen_range", "choose_scale", "ScopeSession", "ChannelCheck", "check_peaks", "autorange",
]
