"""Run spe_calibration.ipynb cells headless (no Jupyter kernel needed).

Cells are selected by their tag (cell metadata "tags"). Parameter overrides are
Python statements executed right after the parameters cell. Output goes to
stdout; redirect it to a log file in runs/spe/ for long runs.

    python scripts/run_spe_notebook.py scan  [overrides]
        timing check is NOT included; runs parameters, connect, scan, choose, close
    python scripts/run_spe_notebook.py cal   "{1: 1.6776, 2: 1.8613}" [overrides]
        calibration runs at those LED amplitudes + SPE fit; HV is left on
    python scripts/run_spe_notebook.py final "{1: 1.6776, 2: 1.8613}" [overrides]
        same as cal, then switches HV ch0/ch1 off and waits until they are down
    python scripts/run_spe_notebook.py refit [overrides]
        re-fit the newest saved calibration run (no hardware)
    python scripts/run_spe_notebook.py off
        stop the AD3 output and switch HV ch0/ch1 off

Example: python scripts/run_spe_notebook.py cal "{1: 1.68}" "CAL_FRAMES = 5000" > runs/spe/cal.log 2>&1
"""

import json
import os
import pickle
import sys
import traceback
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # fit results print σ/μ; the Windows console default can't
sys.stderr.reconfigure(encoding="utf-8")
PROJECT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

NOTEBOOK = PROJECT / "spe_calibration.ipynb"
CELLS = {c["metadata"]["tags"][0]: "".join(c["source"])
         for c in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
         if c["cell_type"] == "code" and c["metadata"].get("tags")}


def run(tags, overrides=""):
    ns = {"__name__": "__main__"}
    for tag in tags:
        print(f"--- cell: {tag}", flush=True)
        exec(compile(CELLS[tag], f"<cell {tag}>", "exec"), ns)
        if tag == "parameters" and overrides:
            exec(overrides, ns)
    return ns


def ad3_off():
    try:
        from ad3pulse.instrument import AnalogDiscovery
        with AnalogDiscovery() as dev:
            dev.stop_output(0)
        print("AD3 output stopped", flush=True)
    except Exception as exc:  # still held by this process: the notebook cells stop it themselves
        print(f"AD3 stop: {exc!r}", flush=True)


def hv_off(channels=(0, 1)):
    from ad3pulse.hardware import IsegHV
    with IsegHV() as hv:
        for ch in channels:
            hv.channel = ch
            hv.output_off()
            print(f"HV ch{ch}: off command sent", flush=True)
        for ch in channels:
            hv.channel = ch
            v = hv.wait_off(threshold_v=5.0, timeout_s=300)
            st = hv.read_status()
            print(f"HV ch{ch}: down at {v:.2f} V, status {st} "
                  f"({', '.join(hv.describe_status(st)) or 'off'})", flush=True)


def print_fits(ns):
    for ch, fit in ns["fits"].items():
        print(f"RESULT ch{ch}: {fit}", flush=True)


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    mode = argv[1]
    if mode == "scan":
        try:
            ns = run(["parameters", "connect", "scan", "choose", "close"], argv[2] if len(argv) > 2 else "")
            out = {"scan": {ch: [(a, h, o.__dict__) for a, h, o in rows] for ch, rows in ns["scan"].items()},
                   "cal": ns["CAL_AMPLITUDE_V"]}
            with open(PROJECT / ns["OUTPUT_DIR"] / f"scan_result_{ns['stamp']}.pkl", "wb") as f:
                pickle.dump(out, f)
            print("SCAN DONE", ns["CAL_AMPLITUDE_V"], flush=True)
        finally:
            ad3_off()
    elif mode in ("cal", "final"):
        overrides = f"CAL_AMPLITUDE_V = {eval(argv[2])!r}\n" + (argv[3] if len(argv) > 3 else "")
        try:
            print_fits(run(["parameters", "connect", "calibrate", "fit", "close"], overrides))
        except Exception:
            if mode == "cal":
                raise
            traceback.print_exc()
        finally:
            ad3_off()
            if mode == "final":
                hv_off()
            print("CAL DONE" + (" (HV off)" if mode == "final" else " (HV left on)"), flush=True)
    elif mode == "refit":
        print_fits(run(["parameters", "load_saved", "fit"], argv[2] if len(argv) > 2 else ""))
    elif mode == "off":
        ad3_off()
        hv_off()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
