"""A/B light ratio against LED voltage, short and long pulses, from saved scans (no hardware).

    python scripts/ab_ratio_check.py [OUTPUT_DIR] [Q1_A Q1_B] [STAMP_SHORT STAMP_LONG]
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from ad3pulse import sat_plots  # noqa: E402
from ad3pulse.sat_analysis import ab_ratio, b_measure, load_scan  # noqa: E402

nb = json.loads((PROJECT / "saturation_r2.ipynb").read_text(encoding="utf-8"))
cells = {c["metadata"]["tags"][0]: "".join(c["source"]) for c in nb["cells"]
         if c["cell_type"] == "code" and c["metadata"].get("tags")}
ns = {}
exec(cells["parameters"], ns)
out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "runs/saturation_r2"
# short-pulse windows follow the pulse width the files were recorded with (round 2: 100 ns)
from ad3pulse.hardware import FrameSet  # noqa: E402
short_files = sorted(out_dir.glob("short_up_*.npz"))
if short_files:
    width = float(FrameSet.load(short_files[-1]).meta["width_s"])
    if abs(width - ns["REGIMES"]["short"]["width_s"]) > 1e-12:
        ns["REGIMES"]["short"] = ns["short_regime"](width)
q1 = {1: float(sys.argv[2]), 2: float(sys.argv[3])} if len(sys.argv) > 3 else {1: 0.9187, 2: 1.045}
stamps = sys.argv[4:6] if len(sys.argv) > 5 else [None, None]

results = {}
for regime, stamp in zip(("short", "long"), stamps):
    points, run = load_scan(out_dir, regime, ns["REGIMES"][regime], q1, stamp)
    b, be, _ = b_measure(points)
    r = ab_ratio(points, ns["MATCH_A_WINDOW"][regime][1], b, be)
    results[f"{regime} ({run})"] = r
    print(f"{regime} {run}: A/B = {r['mean']:.1f} ± {r['mean_err']:.1f} from {r['use'].sum()} points "
          f"(chi2/dof {r['chi2_dof']:.2f}); slope {r['slope_per_V']:.1f} ± {r['slope_err']:.1f} per V "
          f"= {r['slope_per_V'] / r['mean'] * 100:.0f} %/V")
    for i in sorted(range(len(points)), key=lambda i: points[i].amp):
        if r["use"][i]:
            print(f"   {points[i].sweep:4s} {points[i].amp:.3f} V  A/B {r['ratio'][i]:8.1f} ± {r['ratio_err'][i]:.1f}")
fig = sat_plots.plot_ab_ratio(results, f"A/B light ratio, {out_dir.name}")
dest = PROJECT / "results" / f"ab_ratio_{out_dir.name.split('_')[-1]}"
dest.mkdir(parents=True, exist_ok=True)
fig.savefig(dest / "ab_ratio_vs_led.png", dpi=150)
print("saved", dest / "ab_ratio_vs_led.png")
