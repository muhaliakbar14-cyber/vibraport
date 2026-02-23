# config.py
"""
Global configuration and simulation parameters for Vibraport.
"""

from dataclasses import dataclass, field
import numpy as np


# ── Channel definitions ────────────────────────────────────────────────────────
VELOCITY_CHANNELS = {
    'Vertical (mm/s)':     '#00897B',
    'Longitudinal (mm/s)': '#E53935',
    'Transversal (mm/s)':  '#5C6BC0',
}

ACCEL_CHANNELS = {
    'A_Vert (mm/s²)': '#00897B',
    'A_Long (mm/s²)': '#E53935',
    'A_Tran (mm/s²)': '#5C6BC0',
}

DISP_CHANNELS = {
    'D_Vert (mm)': '#00897B',
    'D_Long (mm)': '#E53935',
    'D_Tran (mm)': '#5C6BC0',
}

SOUND_CHANNEL = {
    'Channel 4 (Pa)': '#FFB300',
}

CHANNEL_RENAME = {
    'Channel 1 (mm/s)': 'Vertical (mm/s)',
    'Channel 2 (mm/s)': 'Longitudinal (mm/s)',
    'Channel 3 (mm/s)': 'Transversal (mm/s)',
}

ACCEL_RENAME = {
    'Vertical (mm/s)':     'A_Vert (mm/s²)',
    'Longitudinal (mm/s)': 'A_Long (mm/s²)',
    'Transversal (mm/s)':  'A_Tran (mm/s²)',
}

DISP_RENAME = {
    'Vertical (mm/s)':     'D_Vert (mm)',
    'Longitudinal (mm/s)': 'D_Long (mm)',
    'Transversal (mm/s)':  'D_Tran (mm)',
}

ACCEL_AT_PEAK_MAP = {
    'D_Vert (mm)': 'A_Vert (mm/s²)',
    'D_Long (mm)': 'A_Long (mm/s²)',
    'D_Tran (mm)': 'A_Tran (mm/s²)',
}

# ── Equipment model detection ──────────────────────────────────────────────────
EQUIPMENT_MODELS = {
    'TE': 'Vibracord Tellus',
    'VG': 'Vibracord Gaia',
    'VB': 'Vibracord FX',
}
DEFAULT_EQUIPMENT_MODEL = 'Vibracord DX'

# ── Signal processing defaults ─────────────────────────────────────────────────
DEFAULT_SAMPLING_RATE = 2048  # sps
LOW_AMPLITUDE_THRESHOLD = 0.2  # mm/s — below this, frequency is unreliable

# ── Frequency methods ──────────────────────────────────────────────────────────
FREQUENCY_METHODS = [
    "Zero Crossing",
    "FFT Peak",
    "Energy 25%",
    "Energy 50%",
    "Energy 75%",
]
DEFAULT_FREQUENCY_METHOD = "Energy 50%"

# ── Simulation configuration ───────────────────────────────────────────────────
@dataclass
class SimulationConfig:
    sample_rate: float
    waveform: np.ndarray
    hole_delays_ms: list
    row_delays_ms: list
    n_holes: int
    n_rows: int
    n_decks: int = 1
    deck_delay_ms: float = 0.0

    def samples_per_ms(self) -> float:
        return self.sample_rate / 1000
