"""Replay readout check (hardware; run directly, never imported by pytest): can recorder frames be read at full memory depth?

Records 10 dim long-pulse frames (20k depth, -5..+15 us), then reads every frame of the
SAME recording in NORM, MAX and RAW with :WAV:POINts set explicitly, and reports whether
the frames come back distinct (RAW once returned one frame for all) and the readout time.
"""
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from ad3pulse.hardware import RigolScope  # noqa: E402
from ad3pulse.instrument import AnalogDiscovery, PulseSpec  # noqa: E402



def main() -> None:
    N = 10
    s = RigolScope("192.168.0.101").connect()
    for ch in (1, 2):
        s.configure_channel(ch, 0.005, 0.015, impedance="FIFTy")
    s.configure_channel(3, 0.5, -1.5, impedance="OMEG")
    s._write(":RUN"); s.configure_timebase(2e-6, 5e-6, "10k"); time.sleep(0.5)
    s.configure_edge_trigger(3, 0.5, "POS")
    with AnalogDiscovery() as ad3:
        ad3.start_pulse_train(PulseSpec(amplitude=0.5, width=10e-6, pre_delay=100e-9, post_delay=1e-6), 4.0)
        ad3.set_pulse_amplitude(1.70, max_v=3.0)
        time.sleep(0.3)
        s._write(":TRIG:SWE NORM"); s._write(":RUN")
        s._wait_status(("WAIT", "TD"), 5.0)
        s._write(":RECord:WRECord:ENABle ON"); s._write(":RECord:WRECord:PROMpt OFF")
        s._write(f":RECord:WRECord:FRAMes {N}"); s._write(":RECord:WRECord:FINTerval 1e-8")
        s._write(":RECord:WRECord:OPERate RUN")
        t0 = time.monotonic()
        while s._query(":RECord:WRECord:OPERate?").strip().upper() != "STOP":
            time.sleep(0.05)
        print(f"recorded {N} frames in {time.monotonic() - t0:.1f} s; FMAX {s._query(':RECord:WREPlay:FMAX?').strip()}")
        ad3.stop_output(0)

    print("trigger status:", s.trigger_status(), "| memory depth:", s._query(":ACQ:MDEP?").strip(),
          "| sample rate:", s._query(":ACQ:SRAT?").strip())
    s._write(":WAV:FORM WORD")
    s._write(":WAV:SOUR CHAN2")
    for mode, pts in (("NORM", 1000), ("MAX", 10000), ("RAW", 10000)):
        s._write(f":WAV:MODE {mode}")
        s._write(f":WAV:POIN {pts}")
        got = s._query(":WAV:POIN?").strip()
        s._write(":WAV:STAR 1"); s._write(f":WAV:STOP {pts}")
        frames, t0 = [], time.monotonic()
        try:
            for i in range(1, N + 1):
                s._write(f":RECord:WREPlay:FCURrent {i}")
                s._query("*OPC?")
                pre = s.read_preamble()
                frames.append(s._query_codes())
            dt_read = (time.monotonic() - t0) / N
            lens = {len(f) for f in frames}
            distinct = len({f.tobytes() for f in frames})
            v = np.array([pre.volts(f) for f in frames]) if len(lens) == 1 else None
            print(f"{mode}: :WAV:POIN? -> {got}; preamble points {pre.points}, xinc {pre.xincrement:.3g} s; "
                  f"lengths {sorted(lens)}; {distinct}/{N} distinct frames; {dt_read * 1e3:.0f} ms/frame (1 channel)"
                  + (f"; frame-to-frame rms diff {np.std(np.diff(v, axis=0)) * 1e3:.2f} mV" if v is not None else ""))
        except Exception as exc:
            print(f"{mode}: failed: {exc!r}")
    s._write(":WAV:MODE NORM"); s._write(":WAV:POIN 1000")
    s._write(":RECord:WRECord:ENABle OFF")
    s.configure_timebase(100e-9, 0.0, "1k")
    s._write(":RUN")
    s.close()


if __name__ == "__main__":
    main()
