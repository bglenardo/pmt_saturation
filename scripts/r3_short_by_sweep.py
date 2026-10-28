"""Round 3: short-pulse linearity from the up- and down-sweeps separately (light split drifted between them).

Reads saved files only (runs/saturation_r3); no hardware.
"""
import json
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from ad3pulse.sat_analysis import (ab_ratio, b_measure, light_scale_matched, load_scan,  # noqa: E402
                                   metric_linearity, metric_table)

nb = json.loads((PROJECT / "saturation_r2.ipynb").read_text(encoding="utf-8"))
cells = {c["metadata"]["tags"][0]: "".join(c["source"]) for c in nb["cells"]
         if c["cell_type"] == "code" and c["metadata"].get("tags")}
ns = {}
exec(cells["parameters"], ns)
regime = sys.argv[1] if len(sys.argv) > 1 else "short"
cfg = ns["short_regime"](ns["SHORT_WIDTH_S"]) if regime == "short" else ns["REGIMES"]["long"]
q1 = {1: 0.9353, 2: 1.089}
points, run = load_scan(PROJECT / "runs/saturation_r3", regime, cfg, q1)
for sweep in ("up", "down"):
    pts = [p for p in points if p.sweep == sweep]
    b, be, _ = b_measure(pts)
    r = ab_ratio(pts, ns["MATCH_A_WINDOW"][regime][1], b, be)
    print(f"== {regime} {sweep} ({len(pts)} points): A/B (both linear) = {r['mean']:.2f} ± {r['mean_err']:.2f}, "
          f"{r['use'].sum()} points, chi2/dof {r['chi2_dof']:.2f}")
    try:
        ls = light_scale_matched(pts, b, be, ns["MATCH_A_WINDOW"][regime], b_min=ns["REF_MIN_NPE"])
    except ValueError as exc:
        print("   no matched scale:", exc)
        continue
    print(f"   k_match = {ls['k']:.2f} ± {ls['k_err']:.2f} from {ls['window'].sum()} points")
    for name, (v, e) in metric_table(pts).items():
        if name.startswith("B "):
            continue
        lin = metric_linearity(v, e, ls["light"], ls["light_err"], ls["window"])
        c5, c10 = lin["cross"][0.05], lin["cross"][0.10]
        f = lambda c: "None" if c is None else f"{c:.4g}"
        print(f"   {name:32s}: 5 % low at {f(c5)} PE, 10 % low at {f(c10)} PE")
