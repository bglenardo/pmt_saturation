"""Round-3 write-up plots (results/saturation_r3_2026-10-27/) from saved data; no hardware.

The light split between A and B changed during the short-pulse down-sweep, so the short-pulse linearity
uses the up-sweep only. The long scan (after the change) reproduced between sweeps and uses both.
"""
import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from ad3pulse import sat_plots  # noqa: E402
from ad3pulse.sat_analysis import (ab_ratio, b_measure, light_scale_matched, load_scan,  # noqa: E402
                                   metric_linearity, metric_table)

RUN_DIR = PROJECT / "runs/saturation_r3"
DEST = PROJECT / "results/saturation_r3_2026-10-27"
Q1 = {1: 0.9353, 2: 1.089}
A_CH = 1

nb = json.loads((PROJECT / "saturation_r2.ipynb").read_text(encoding="utf-8"))
cells = {c["metadata"]["tags"][0]: "".join(c["source"]) for c in nb["cells"]
         if c["cell_type"] == "code" and c["metadata"].get("tags")}
ns = {}
exec(cells["parameters"], ns)
cfgs = {"short": ns["short_regime"](ns["SHORT_WIDTH_S"]), "long": ns["REGIMES"]["long"]}
DEST.mkdir(parents=True, exist_ok=True)
shutil.copy(RUN_DIR / "ratio_20261027_131236.png", DEST / "ratio_scan.png")

ab = {}
summary = {}
for regime, sweeps in (("short", ("up",)), ("long", ("up", "down"))):
    cfg = cfgs[regime]
    points, run = load_scan(RUN_DIR, regime, cfg, Q1)
    for sw in ("up", "down"):
        pts = [p for p in points if p.sweep == sw]
        b, be, _ = b_measure(pts)
        ab[f"{regime} {sw}"] = ab_ratio(pts, ns["MATCH_A_WINDOW"][regime][1], b, be)
    pts = [p for p in points if p.sweep in sweeps]
    b, be, _ = b_measure(pts)
    ls = light_scale_matched(pts, b, be, ns["MATCH_A_WINDOW"][regime], b_min=ns["REF_MIN_NPE"])
    metrics = metric_table(pts)
    lins = {n: metric_linearity(v, e, ls["light"], ls["light_err"], ls["window"])
            for n, (v, e) in metrics.items() if not n.startswith("B ")}
    summary[regime] = {"sweeps": sweeps, "k_match": ls["k"], "k_match_err": ls["k_err"],
                       "crossings_true_light_PE": {n: {"5%": l["cross"][0.05], "10%": l["cross"][0.10]}
                                                   for n, l in lins.items()}}
    print(regime, sweeps, f"k_match {ls['k']:.2f} ± {ls['k_err']:.2f}")
    figs = {
        "vs_led": sat_plots.plot_vs_led(pts, metrics, regime),
        "a_vs_b": sat_plots.plot_a_vs_b(pts, ls, ls["k"], regime),
        "linearity": sat_plots.plot_linearity(
            pts, ls, lins, regime,
            ("anode peak current (mA)", metrics["A anode peak (mA)"][0]) if regime == "short"
            else ("expected anode charge, light × Q1 (nC)", ls["light"] * Q1[A_CH] / 1e3)),
        "shapes": sat_plots.plot_shapes_ch1_ch4(pts, ls["light"], cfg, regime),
    }
    for axes in ("linear", "loglog"):
        figs[f"a_vs_b_{axes}"] = sat_plots.plot_a_vs_b(pts, ls, ls["k"], regime, light_axes=axes)
    figs["a_dy8_vs_b"] = sat_plots.plot_a_dy8_vs_b(pts, ls, ls["k"], regime)
    figs["waveforms"] = sat_plots.plot_waveforms(pts, f"{cfg['width_s'] * 1e9:g} ns" if regime == "short" else "10 µs",
                                                 xlim_us=(0.0, 0.6) if regime == "short" else (-1.0, 15.0))
    for name, fig in figs.items():
        if fig is not None:
            fig.savefig(DEST / f"{regime}_{name}.png", dpi=140)

fig = sat_plots.plot_ab_ratio(ab, "A/B light ratio, round 3 (short = 250 ns, long = 10 µs)")
fig.savefig(DEST / "ab_ratio_vs_led.png", dpi=150)
for name, r in ab.items():
    print(f"{name}: A/B = {r['mean']:.2f} ± {r['mean_err']:.2f}, {r['use'].sum()} points, chi2/dof {r['chi2_dof']:.1f}")
(DEST / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if x is None else float(x)))
print("saved to", DEST)
