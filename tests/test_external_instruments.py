from __future__ import annotations

import numpy as np
import pytest

from ad3pulse.hardware import (FrameSet, InstrumentError, IsegHV, Preamble, RigolScope, SiglentSDG,
                               parse_bswv, parse_iseg_value, parse_siglent_value)
from ad3pulse.instrument import PulseSpec


class FakeInstrument:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.responses: dict[str, str] = {}
        self.binary: list[np.ndarray] = []

    def write(self, cmd: str) -> None:
        self.commands.append(cmd)

    def query(self, cmd: str) -> str:
        self.commands.append(cmd)
        key = cmd.strip().upper()
        if key in self.responses:
            return self.responses[key]
        return "0.0"

    def query_binary_values(self, cmd: str, **kwargs) -> np.ndarray:
        self.commands.append(cmd)
        return self.binary.pop(0)

    def close(self) -> None:
        self.commands.append("CLOSE")


class FakeIsegSocket:
    """Mimics the SHR TCP socket: an empty line, then the answer.

    Orders ending in ``;*OPC?`` answer ``1``; queries answer from ``responses``
    (a list is consumed one reply per query); anything else gets no answer,
    like a rejected command on the real device.
    """

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.responses: dict[str, str | list[str]] = {}
        self._lines: list[str] = []

    def write(self, cmd: str) -> None:
        self.commands.append(cmd)
        self._lines.append("")
        if cmd.endswith(";*OPC?"):
            self._lines.append("1")
        elif cmd in self.responses:
            reply = self.responses[cmd]
            self._lines.append(reply.pop(0) if isinstance(reply, list) else reply)

    def read(self) -> str:
        if not self._lines:
            raise TimeoutError("VI_ERROR_TMO")
        return self._lines.pop(0)

    def close(self) -> None:
        self.commands.append("CLOSE")


def test_iseg_hv_commands() -> None:
    fake = FakeIsegSocket()
    fake.responses[":READ:CHAN:STAT? (@0)"] = "1"
    fake.responses[":CONF:OUTP:POL? (@0)"] = "p"
    hv = IsegHV(instrument=fake)
    hv.set_current_limit(1e-4)
    hv.set_voltage(1234.5)
    hv.set_ramp(20)
    hv.output_on()

    orders = [c for c in fake.commands if c.endswith(";*OPC?")]
    assert orders == [
        ":CURR 0.0001,(@0);*OPC?",
        ":VOLT 1234.500,(@0);*OPC?",
        ":CONF:RAMP:VOLT 20,(@0);*OPC?",
        ":VOLT ON,(@0);*OPC?",
    ]


def test_iseg_negative_polarity_sends_signed_voltage() -> None:
    # A negative channel on the real SHR reads back VSET as -1550 V.
    fake = FakeIsegSocket()
    fake.responses[":READ:CHAN:STAT? (@0)"] = "0"
    fake.responses[":CONF:OUTP:POL? (@0)"] = "n"
    assert IsegHV(instrument=fake).set_voltage(1550) == -1550
    assert ":VOLT -1550.000,(@0);*OPC?" in fake.commands


@pytest.mark.parametrize("text, value", [
    ("1.23456E3V", 1234.56),
    ("-4.0E3V", -4000.0),
    ("12.3456E-6A", 12.3456e-6),
    ("1.23456EA", 1.23456),
    ("2.00002V", 2.00002),
    ("0.25000E3V/s", 250.0),
])
def test_parse_iseg_value(text: str, value: float) -> None:
    assert parse_iseg_value(text) == pytest.approx(value)


def test_iseg_wait_stable_waits_for_ramp_end() -> None:
    fake = FakeIsegSocket()
    # on + ramping + positive, then on + constant voltage + positive
    fake.responses[":READ:CHAN:STAT? (@1)"] = ["25", "25", "137"]
    fake.responses[":MEAS:VOLT? (@1)"] = ["0.40000E3V", "0.99000E3V", "0.99990E3V"]
    hv = IsegHV(instrument=fake, channel=1)
    assert hv.wait_stable(1000.0, tolerance_v=1.0, poll_s=0) == pytest.approx(999.9)


def test_iseg_wait_stable_raises_on_trip() -> None:
    fake = FakeIsegSocket()
    fake.responses[":READ:CHAN:STAT? (@0)"] = str(IsegHV.IS_CURRENT_TRIP)
    hv = IsegHV(instrument=fake)
    with pytest.raises(InstrumentError, match="current trip"):
        hv.wait_stable(1000.0, poll_s=0)


def test_iseg_rejected_command_raises() -> None:
    fake = FakeIsegSocket()  # no response configured -> device stays silent
    hv = IsegHV(instrument=fake)
    with pytest.raises(InstrumentError, match="did not answer"):
        hv.read_voltage()


def test_visa_resources_from_ip() -> None:
    assert IsegHV.visa_resource("192.168.0.100") == "TCPIP0::192.168.0.100::10001::SOCKET"
    assert RigolScope.visa_resource("192.168.0.101") == "TCPIP0::192.168.0.101::5555::SOCKET"
    assert RigolScope.visa_resource("TCPIP0::10.0.0.5::5555::SOCKET") == "TCPIP0::10.0.0.5::5555::SOCKET"


def test_iseg_rejects_negative_voltage() -> None:
    hv = IsegHV(instrument=FakeIsegSocket())
    with pytest.raises(ValueError):
        hv.set_voltage(-1000.0)


def test_iseg_close_leaves_hv_on() -> None:
    fake = FakeIsegSocket()
    with IsegHV(instrument=fake) as hv:
        hv.output_on()
    assert fake.commands[-1] == "CLOSE"
    assert not any("OFF" in c for c in fake.commands)


def test_rigol_scope_commands() -> None:
    fake = FakeInstrument()
    scope = RigolScope(instrument=fake)
    scope.configure_channel(1, 0.2, 0.1)
    scope.configure_timebase(50e-9, 150e-9)
    scope.configure_edge_trigger(2, level_v=0.25, slope="NEG")

    assert fake.commands == [
        ":CHAN1:DISP 1",
        ":CHAN1:IMP OMEG",
        ":CHAN1:COUP DC",
        ":CHAN1:SCAL 0.2",
        ":CHAN1:OFFS 0.1",
        ":TIM:MAIN:SCAL 5e-08",
        ":TIM:MAIN:OFFS 1.5e-07",
        ":TRIG:MODE EDGE",
        ":TRIG:EDGE:SOUR CHAN2",
        ":TRIG:EDGE:SLOP NEG",
        ":TRIG:EDGE:LEV 0.25",
    ]


def test_preamble_conversion() -> None:
    # Example reply from the MHO900 programming guide (p.478).
    pre = Preamble.parse("0,0,1000,1,1.000000E-8,-5.000000E-6,0.000000E-12,4.000000E-03,0,128")
    assert pre.points == 1000
    np.testing.assert_allclose(pre.volts(np.array([128, 0x8E])), [0.0, 14 * 4e-3])
    np.testing.assert_allclose(pre.times(3), [-5e-6, -5e-6 + 1e-8, -5e-6 + 2e-8])


def test_rigol_read_channel_chunks() -> None:
    fake = FakeInstrument()
    fake.responses[":WAV:PRE?"] = "1,2,5,1,1e-9,-1e-9,0,1e-3,0,100"
    fake.binary = [np.array([100, 101, 102], dtype=np.uint16),
                   np.array([103, 104], dtype=np.uint16)]
    scope = RigolScope(instrument=fake)
    scope.CHUNK_POINTS = 3
    t, v, _ = scope.read_channel(2)

    np.testing.assert_allclose(v, [0.0, 1e-3, 2e-3, 3e-3, 4e-3])
    np.testing.assert_allclose(t, -1e-9 + np.arange(5) * 1e-9)
    assert fake.commands[:4] == [":WAV:SOUR CHAN2", ":WAV:MODE RAW", ":WAV:FORM WORD", ":WAV:PRE?"]
    assert ":WAV:STAR 4" in fake.commands and ":WAV:STOP 5" in fake.commands


def test_rigol_arm_single_rejects_early_trigger() -> None:
    fake = FakeInstrument()
    fake.responses[":TRIG:STAT?"] = "TD"
    scope = RigolScope(instrument=fake)
    with pytest.raises(Exception, match="triggered before"):
        scope.arm_single(timeout_s=0.1)


def test_rigol_arm_single_ignores_stale_stop() -> None:
    # Right after :SINGle the scope can still report the previous STOP.
    fake = FakeInstrument()
    statuses = iter(["STOP", "STOP", "WAIT"])
    fake.query = lambda cmd: next(statuses) if cmd == ":TRIG:STAT?" else "0"
    scope = RigolScope(instrument=fake)
    assert scope.arm_single(timeout_s=1.0, allow_early=True) == "WAIT"


def test_rigol_capture_rejects_empty_readout() -> None:
    fake = FakeInstrument()
    fake.responses[":WAV:PRE?"] = "1,2,0,1,5e-10,-2.5e-6,0,6.6667e-06,0,32768"
    with pytest.raises(InstrumentError, match="no data"):
        RigolScope(instrument=fake).capture_channels()


def _recorder_fake(n_frames: int) -> FakeInstrument:
    fake = FakeInstrument()
    fake.responses[":RECORD:WRECORD:FMAX?"] = "126976"
    fake.responses[":RECORD:WRECORD:OPERATE?"] = "STOP"
    fake.responses[":RECORD:WREPLAY:FMAX?"] = str(n_frames)
    fake.responses[":TRIG:STAT?"] = "WAIT"
    fake.responses[":WAV:PRE?"] = "1,0,3,1,1e-9,-1e-9,0,1e-3,0,100"
    fake.responses["*OPC?"] = "1"
    # frame-major, Ch1 then Ch2 per frame
    fake.binary = [np.array([100 + 10 * f + ch] * 3, dtype=np.uint16)
                   for f in range(n_frames) for ch in (1, 2)]
    return fake


def test_rigol_record_frames_reads_each_frame(tmp_path) -> None:
    fake = _recorder_fake(3)
    frames = RigolScope(instrument=fake).record_frames(3, channels=(1, 2))

    assert frames.codes[1][:, 0].tolist() == [101, 111, 121]
    assert frames.codes[2][:, 0].tolist() == [102, 112, 122]
    np.testing.assert_allclose(frames.volts(1)[1], [11e-3] * 3)
    assert ":WAV:MODE NORM" in fake.commands
    # normal triggering is re-armed before recording (a bare :RUN free-runs after a recording)
    k = fake.commands.index(":TRIG:SWE NORM")
    assert fake.commands[k + 1] == ":RUN"
    assert k < fake.commands.index(":RECord:WRECord:OPERate RUN")
    for i in (1, 2, 3):  # every frame selection is followed by *OPC?
        k = fake.commands.index(f":RECord:WREPlay:FCURrent {i}", 3)
        assert fake.commands[k + 1] == "*OPC?"

    frames.meta["amplitude_V"] = 1.7
    frames.save(tmp_path / "f.npz")
    loaded = FrameSet.load(tmp_path / "f.npz")
    np.testing.assert_array_equal(loaded.codes[2], frames.codes[2])
    np.testing.assert_allclose(loaded.volts(1), frames.volts(1))
    np.testing.assert_allclose(loaded.time_s, frames.time_s)
    assert loaded.meta["amplitude_V"] == 1.7


def test_rigol_record_frames_max_mode() -> None:
    fake = _recorder_fake(2)
    frames = RigolScope(instrument=fake).record_frames(2, channels=(1, 2), mode="max")
    assert ":WAV:MODE MAX" in fake.commands and ":WAV:MODE NORM" not in fake.commands
    assert frames.meta["replay_mode"] == "MAX"
    with pytest.raises(ValueError, match="RAW"):
        RigolScope(instrument=_recorder_fake(1)).record_frames(1, mode="RAW")


def test_rigol_record_frames_rejects_too_many() -> None:
    fake = _recorder_fake(1)
    with pytest.raises(ValueError, match="holds 126976"):
        RigolScope(instrument=fake).record_frames(200_000)


def test_pulse_fit_to_awg_100ns() -> None:
    pulse = PulseSpec(amplitude=1.0, width=100e-9, pre_delay=100e-9, post_delay=1e-6)
    realised = pulse.fit_to_awg(max_rate=125e6)
    assert pulse.samples == 150  # 1.2 us period at 8 ns/sample
    assert pulse.timing_resolution == pytest.approx(8e-9)
    assert realised == pytest.approx(104e-9)


def test_pulse_fit_to_awg_keeps_long_pulses() -> None:
    pulse = PulseSpec(amplitude=1.0, width=10e-6, pre_delay=5e-6, post_delay=25e-6)
    pulse.fit_to_awg(max_rate=125e6, max_samples=32768)
    assert pulse.samples == 4096


class FakeSiglent:
    """Mimics the SDG2082X socket: set commands change a stored state and get no answer."""

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.wave = {"WVTP": "SQUARE", "FRQ": "1000HZ", "WIDTH": "1e-07", "RISE": "8.4e-09S",
                     "FALL": "8.4e-09S", "HLEV": "1V", "LLEV": "-1V", "DLY": "0"}
        self.out = {"STATE": "OFF", "LOAD": "50", "PLRT": "NOR"}
        self.clamp: dict[str, str] = {}  # parameter -> value the device keeps instead
        self.ignore_off = False
        self.ignore_wvtp = 0  # number of WVTP changes to ignore (seen after a power cycle)

    def write(self, cmd: str) -> None:
        self.commands.append(cmd)
        head, _, args = cmd.partition(" ")
        items = args.split(",")
        if head == "C1:BSWV":
            for k, v in zip(items[0::2], items[1::2]):
                if k == "WVTP" and self.ignore_wvtp > 0:
                    self.ignore_wvtp -= 1
                    continue
                self.wave[k] = self.clamp.get(k, v)
        elif head == "C1:OUTP":
            if items[0] in ("ON", "OFF"):
                if not (items[0] == "OFF" and self.ignore_off):
                    self.out["STATE"] = items[0]
                items = items[1:]
            for k, v in zip(items[0::2], items[1::2]):
                self.out[k] = v

    def query(self, cmd: str) -> str:
        self.commands.append(cmd)
        if cmd == "*IDN?":
            return "Siglent Technologies,SDG2082X,SDG2XFBX7R1421,2.01.01.37R6"
        if cmd == "C1:BSWV?":
            return "C1:BSWV " + ",".join(f"{k},{v}" for k, v in self.wave.items())
        if cmd == "C1:OUTP?":
            return (f"C1:OUTP {self.out['STATE']},LOAD,{self.out['LOAD']},POWERON_STATE,0,"
                    f"PLRT,{self.out['PLRT']}")
        raise TimeoutError("VI_ERROR_TMO")

    def close(self) -> None:
        self.commands.append("CLOSE")


@pytest.mark.parametrize("text, value", [("10HZ", 10.0), ("8.4e-09S", 8.4e-9), ("1.7V", 1.7),
                                         ("1e-07", 1e-7), ("-0.2V", -0.2), ("0", 0.0)])
def test_parse_siglent_value(text: str, value: float) -> None:
    assert parse_siglent_value(text) == pytest.approx(value)


def test_parse_bswv() -> None:
    wave = parse_bswv("C1:BSWV WVTP,PULSE,FRQ,10HZ,PERI,0.1S,HLEV,1.7V,LLEV,0V,WIDTH,1e-07")
    assert wave["WVTP"] == "PULSE" and wave["FRQ"] == "10HZ" and wave["WIDTH"] == "1e-07"


def test_siglent_pulse_train_sequence_and_readback() -> None:
    fake = FakeSiglent()
    sdg = SiglentSDG(instrument=fake).connect()
    width = sdg.start_pulse_train(100e-9, 10.0, 0.5)
    assert width == pytest.approx(100e-9)
    sets = [c for c in fake.commands if not c.endswith("?")]
    assert sets[0] == "C1:OUTP OFF" and sets[-1] == "C1:OUTP ON"
    assert "C1:OUTP LOAD,HZ,PLRT,NOR" in sets and "C1:BSWV WVTP,PULSE" in sets
    assert "C1:BSWV LLEV,0" in sets and "C1:BSWV RISE,8.4e-09" in sets
    assert fake.out["STATE"] == "ON" and fake.wave["HLEV"] == "0.5"
    sdg.set_pulse_amplitude(1.72, max_v=3.0)
    assert fake.wave["HLEV"] == "1.72"
    sdg.stop_output(0)
    assert fake.out["STATE"] == "OFF"
    assert sdg.describe()["wave"]["WVTP"] == "PULSE"


def test_siglent_refuses_fast_rates_and_bad_levels() -> None:
    sdg = SiglentSDG(instrument=FakeSiglent()).connect()
    with pytest.raises(ValueError, match="10 Hz"):
        sdg.start_pulse_train(100e-9, 1000.0, 0.5)
    with pytest.raises(ValueError):
        sdg.start_pulse_train(100e-9, 10.0, 0.0)
    sdg.start_pulse_train(10e-6, 4.0, 0.5)
    with pytest.raises(ValueError, match="limit"):
        sdg.set_pulse_amplitude(3.5, max_v=3.0)
    with pytest.raises(ValueError):
        sdg.set_pulse_amplitude(-1.0)


def test_siglent_clamped_value_raises_and_output_stays_off() -> None:
    fake = FakeSiglent()
    fake.clamp["LLEV"] = "-0.2V"   # what MAX_OUTPUT_AMP did on the real unit
    sdg = SiglentSDG(instrument=fake).connect()
    with pytest.raises(InstrumentError, match="LLEV"):
        sdg.start_pulse_train(100e-9, 10.0, 1.0)
    assert fake.out["STATE"] == "OFF"


def test_siglent_retries_ignored_pulse_mode_change(monkeypatch) -> None:
    monkeypatch.setattr("ad3pulse.hardware.time.sleep", lambda s: None)
    fake = FakeSiglent()
    fake.ignore_wvtp = 1
    sdg = SiglentSDG(instrument=fake).connect()
    sdg.start_pulse_train(100e-9, 10.0, 0.5)
    assert fake.wave["WVTP"] == "PULSE" and fake.out["STATE"] == "ON"
    assert fake.commands.count("C1:BSWV WVTP,PULSE") == 2

    fake = FakeSiglent()
    fake.ignore_wvtp = 99
    with pytest.raises(InstrumentError, match="pulse mode"):
        SiglentSDG(instrument=fake).connect().start_pulse_train(100e-9, 10.0, 0.5)
    assert fake.out["STATE"] == "OFF"


def test_siglent_stop_output_checks_state() -> None:
    fake = FakeSiglent()
    fake.out["STATE"] = "ON"
    fake.ignore_off = True
    with pytest.raises(InstrumentError, match="off"):
        SiglentSDG(instrument=fake).connect().stop_output()


def test_siglent_resource_and_identity() -> None:
    assert SiglentSDG.visa_resource("192.168.0.75") == "TCPIP0::192.168.0.75::5025::SOCKET"
    assert SiglentSDG.visa_resource("TCPIP0::1.2.3.4::INSTR") == "TCPIP0::1.2.3.4::INSTR"
    fake = FakeSiglent()
    fake.query = lambda cmd: "RIGOL TECHNOLOGIES,MHO954"
    with pytest.raises(InstrumentError, match="not a Siglent"):
        SiglentSDG(instrument=fake).connect()
