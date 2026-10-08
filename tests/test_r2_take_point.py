"""The 1 MOhm Ch4 stop logic of saturation_r2.ipynb's take_point(), run against the fake scope."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ad3pulse.acquire import PeakLimitExceeded, ScopeSession, ScopeSettings, autorange, check_peaks
from ad3pulse.sat_analysis import summarize_frames

from test_saturation import FakeAD3, FakeScope

NB = Path(__file__).resolve().parents[1] / "saturation_r2.ipynb"


def _take_point_source() -> str:
    cells = json.loads(NB.read_text(encoding="utf-8"))["cells"]
    src = "".join(next(c for c in cells if c["metadata"].get("tags") == ["connect"])["source"])
    return src[src.index("one_m = "):]


def test_take_point_stops_1mohm_and_skips_brighter(tmp_path) -> None:
    ad3 = FakeAD3()
    scope = FakeScope({1: 0.05, 2: 0.01, 4: -0.8}, ad3)   # Ch4 positive: +0.8 V per LED volt at 50 Ohm
    scope.omeg_gain = 2.0                                   # ... and 1.6 V per LED volt at 1 MOhm
    settings = ScopeSettings(pmt_scale_v_div={1: 0.01, 2: 0.01, 4: 0.01}, polarity={4: +1})
    session = ScopeSession("fake", settings, ad3, rate_hz=4.0, out_dir=tmp_path, scope_factory=lambda r: scope).open()
    cfg = dict(baseline=(-500e-9, -300e-9), signal=(40e-9, 440e-9), control=(-480e-9, -80e-9),
               pre=(-500e-9, 40e-9), pulser_window=(20e-9, 80e-9), plateau=(450e-9, 495e-9))
    ns = dict(session=session, cfg=cfg, autorange=autorange, check_peaks=check_peaks,
              PeakLimitExceeded=PeakLimitExceeded, summarize_frames=summarize_frames, np=np,
              REGIME="short", A_CH=1, B_CH=2, DYN_CH=4, Q1_PC={1: 0.9, 2: 1.1},
              MAX_PEAK_V={1: 3.0, 2: 3.0, 4: 3.0}, CH4_1M_STOP_V=3.0, PROBE_FRAMES=3)
    exec(compile(_take_point_source(), "take_point", "exec"), ns)
    take_point = ns["take_point"]
    results = {amp: take_point(amp, 4, "up") for amp in (1.0, 1.5, 2.25, 3.0)}
    # 1 MOhm: 1.6 V (ok), 2.4 V (ok), 3.6 V (stop), 4.8 V (skipped: brighter than the stop)
    assert results[1.0][1] is not None and results[1.5][1] is not None
    assert results[2.25][1] is None and results[3.0][1] is None
    assert ns["one_m"]["stop_amp"] == 2.25
    assert scope.impedance[4] == "FIFTy"                 # always returned to 50 Ohm
    names = sorted(p.name.split("_1M")[0] for p in tmp_path.glob("short_up1M_*.npz"))
    assert len(names) == 2                               # only the two allowed 1 MOhm recordings saved
    assert results[1.0][1]["ch"][4]["impedance"] == "OMEG"
