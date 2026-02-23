# core/waveform.py
"""
Waveform parsing and preparation.

Physical concept: The raw vibration signal as recorded by the seismograph.
Handles reading, cleaning, and preparing the time-series data before analysis.
"""

import numpy as np
import pandas as pd
from io import StringIO, BytesIO
from config import (
    CHANNEL_RENAME, ACCEL_RENAME, DISP_RENAME,
    DEFAULT_SAMPLING_RATE
)


def parse_file(file_bytes: bytes) -> tuple:
    """
    Parse a Vibracord CSV file from raw bytes.

    Returns:
        metadata   (dict)         — recording info from header
        df         (pd.DataFrame) — time-series data with all derived columns
        time_axis  (np.ndarray)   — time in milliseconds
        sampling_rate (int)       — samples per second
    """
    uploaded_file = BytesIO(file_bytes)
    lines = uploaded_file.read().decode("utf-8").splitlines()

    # ── Parse metadata header ──────────────────────────────────────────────────
    metadata = {}
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith('"Time","Channel'):
            data_start = i
            break
        parts = line.replace('\r', '').split('","')
        if len(parts) >= 2:
            key = parts[0].strip('"')
            value = parts[1].strip('"')
            if key:
                metadata[key] = value

    # ── Parse data section ─────────────────────────────────────────────────────
    data_text = "\n".join(lines[data_start:])
    df = pd.read_csv(StringIO(data_text), on_bad_lines='skip')
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(axis=1, how='all')
    df = df.rename(columns=CHANNEL_RENAME)

    # ── Sampling rate ──────────────────────────────────────────────────────────
    sampling_rate_str = metadata.get("Sampling rate", f"{DEFAULT_SAMPLING_RATE} sps")
    sampling_rate = int(sampling_rate_str.split()[0])

    # ── Time axis in milliseconds ──────────────────────────────────────────────
    time_axis = np.arange(len(df)) * 1000 / sampling_rate

    # ── Derived columns ────────────────────────────────────────────────────────
    velocity_cols = [c for c in df.columns if 'mm/s' in c and 'Vector' not in c]
    df = _compute_acceleration(df, velocity_cols, sampling_rate)
    df = _compute_displacement(df, velocity_cols, sampling_rate)

    return metadata, df, time_axis, sampling_rate


def _compute_acceleration(df: pd.DataFrame, velocity_cols: list, sampling_rate: int) -> pd.DataFrame:
    """
    Acceleration as the time derivative of velocity (mm/s²).
    """
    for col in velocity_cols:
        accel_col = ACCEL_RENAME.get(col, col.replace('mm/s', 'mm/s²'))
        df[accel_col] = np.gradient(df[col].values, 1 / sampling_rate)
    return df


def _compute_displacement(df: pd.DataFrame, velocity_cols: list, sampling_rate: int) -> pd.DataFrame:
    """
    Displacement as the time integral of velocity (mm).
    DC offset removed before integration to prevent drift.
    Post-integration mean removal eliminates residual drift.
    """
    for col in velocity_cols:
        disp_col = DISP_RENAME.get(col, col.replace('mm/s', 'mm'))
        sig = df[col].values
        sig = sig - np.mean(sig)
        displacement = np.cumsum(sig) * (1 / sampling_rate)
        displacement = displacement - np.mean(displacement)
        df[disp_col] = displacement
    return df


def detect_equipment_model(serial: str) -> str:
    """
    Detect Vibracord equipment model from serial number prefix.
    """
    from config import EQUIPMENT_MODELS, DEFAULT_EQUIPMENT_MODEL
    for prefix, model in EQUIPMENT_MODELS.items():
        if serial.startswith(prefix):
            return model
    return DEFAULT_EQUIPMENT_MODEL
