"""PMT saturation tools: LAN instrument wrappers, acquisition and analysis.

The Siglent SDG2082X drives the LED (since 2026-11-14; the Analog Discovery 3
before that, kept for the legacy tools). The Rigol MHO954 scope and ISEG HV
supply are the measurement/control devices for the PMT setup.
"""

from .dwfapi import DwfError, dwf
from .hardware import FrameSet, IsegHV, InstrumentError, RigolScope, RigolScopeCapture, SiglentSDG
from .instrument import AnalogDiscovery, Capture, PulseSpec, ScopeSpec
from .repeat import capture_repeats
from .sweep import run_sweep, summarize

__all__ = [
    "AnalogDiscovery",
    "Capture",
    "PulseSpec",
    "ScopeSpec",
    "DwfError",
    "dwf",
    "IsegHV",
    "RigolScope",
    "RigolScopeCapture",
    "SiglentSDG",
    "FrameSet",
    "InstrumentError",
    "run_sweep",
    "summarize",
    "capture_repeats",
]
