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


def parse_sis_file(file_bytes: bytes) -> tuple:
    """
    Parse a Vibracord .sis binary file and convert to Vibraport's standard format.

    Returns the same 4-tuple as parse_file():
        metadata      (dict)         — recording info
        df            (pd.DataFrame) — time-series waveform data
        time_axis     (np.ndarray)   — time in seconds
        sampling_rate (int)          — samples per second

    The df columns follow Vibraport naming conventions:
        Velocity channels  : 'Vertical (mm/s)', 'Longitudinal (mm/s)', 'Transversal (mm/s)'
        Pressure channel   : 'Channel N (Pa)'
        Acceleration       : 'A_Vert (mm/s²)', etc. (derived)
        Displacement       : 'D_Vert (mm)', etc. (derived)

    For files with 2 geophone blocks, both blocks are included in df with
    suffixed column names: 'Vertical B2 (mm/s)', 'Longitudinal B2 (mm/s)', etc.
    """
    from core.sis_parser import parse_sis

    r = parse_sis(file_bytes)

    # ── Build metadata dict matching Vibraport conventions ────────────────────
    metadata = {
        'Date':            r['date'], 
        'Time':            r['time'],
        'Calibration date': r['cal_date'],
        'Record type':     r['record_type'],
        'Sampling rate':   f"{r['sampling_rate']} sps",
        'Record length':   f"{r['record_length_s']} s",
        'Pretrigger':      f"{r['pretrigger_ms']} ms",
        'Serial number':   r['serial_number'],
        'Equipment':       r['equipment_type'],
        'Clock source':    r['clock_source'],
        'GPS source':      r['gps_source'],
        'Latitude':        r['latitude'] if r['gps_source'] != 'Not set' else None,
        'Longitude':       r['longitude'] if r['gps_source'] != 'Not set' else None,
        'Note 1':          r['note1'] or '',
        'Note 2':          r['note2'] or '',
        'Note 3':          r['note3'] or '',
        'Geophone test':   r['geophone_test'],
        'Vector sum':      r['vector_sum'],
        'Vector sum time': r['vector_sum_time'],
        'Channel info':    r['channel_info'],
        'is_sis':          True,
        'is_waveform':     r['is_waveform'],
        'Bargraph end time': r.get('bargraph_end_time', (0, 0, 0)),
    }

    sampling_rate = r['sampling_rate']
    time_axis     = r['time_axis']

    if r['is_waveform']:
        df = _build_waveform_df(r, sampling_rate)
    else:
        df = _build_bargraph_df(r)

    return metadata, df, time_axis, sampling_rate


def _build_waveform_df(r: dict, sampling_rate: int) -> pd.DataFrame:
    """
    Convert waveform data from sis_parser output into a Vibraport-standard DataFrame.

    Channel naming strategy:
    - Physical velocity Block 1: Vertical (mm/s), Longitudinal (mm/s), Transversal (mm/s)
    - Physical velocity Block 2: Vertical B2 (mm/s), Longitudinal B2 (mm/s), Transversal B2 (mm/s)
    - Axis names Vertical/Longitudinal/Transverse and X/Y/Z are both supported
    - Pressure channel: Channel N (Pa)
    - Virtual/other channels: Ch{N} {Axis} {Magnitude} ({unit})
    """
    # Normalize axis names — some devices use X/Y/Z, others use Vertical/Longitudinal/Transverse
    AXIS_NORMALIZE = {
        'Vertical':     'Vertical',
        'Longitudinal': 'Longitudinal',
        'Transverse':   'Transversal',
        'X':            'Vertical',
        'Y':            'Longitudinal',
        'Z':            'Transversal',
    }

    df = pd.DataFrame({'time_s': r['time_axis']})

    # Separate physical velocity channels by block
    block1_done = False
    block2_done = False

    for i, ch in enumerate(r['channel_info']):
        if ch['type'] == 'Not used':
            continue

        label_key = f"Ch{ch['index']}_{ch['axis']}_{ch['magnitude']}"
        if label_key not in r['waveform']:
            continue

        signal = r['waveform'][label_key]
        mag    = ch['magnitude']
        axis   = ch['axis']
        block  = ch['belongs_to_block']
        unit   = ch['unit']

        normalized = AXIS_NORMALIZE.get(axis)

        if 'Velocity' in mag and normalized and not ch['is_virtual']:
            if block == 1:
                df[f'{normalized} (mm/s)'] = signal
            elif block == 2:
                df[f'{normalized} B2 (mm/s)'] = signal
            else:
                # Fallback: assign by order if block flag not set
                existing = [c for c in df.columns if '(mm/s)' in c and 'B2' not in c and 'A_' not in c and 'D_' not in c]
                if len(existing) < 3:
                    df[f'{normalized} (mm/s)'] = signal
                else:
                    df[f'{normalized} B2 (mm/s)'] = signal

        elif 'Pressure' in mag:
            df[f"Channel {ch['index']} (Pa)"] = signal

        else:
            # Virtual channels or other types (KBf, Acceleration, Displacement, etc.)
            u = f'({unit})' if unit else f'({mag})'
            col = f"Ch{ch['index']} {axis} {mag} {u}"
            df[col] = signal

    # ── Derived channels for Block 1 velocity columns only ───────────────────
    # Block 2 derived channels use B2-suffixed names via ACCEL/DISP rename maps
    b1_vel_cols = [c for c in df.columns if '(mm/s)' in c and 'B2' not in c and 'A_' not in c and 'D_' not in c]
    b2_vel_cols = [c for c in df.columns if '(mm/s)' in c and 'B2' in c]
    df = _compute_acceleration(df, b1_vel_cols, sampling_rate)
    df = _compute_displacement(df, b1_vel_cols, sampling_rate)
    if b2_vel_cols:
        B2_ACCEL = {
            'Vertical B2 (mm/s)':     'A_Vert B2 (mm/s²)',
            'Longitudinal B2 (mm/s)': 'A_Long B2 (mm/s²)',
            'Transversal B2 (mm/s)':  'A_Tran B2 (mm/s²)',
        }
        B2_DISP = {
            'Vertical B2 (mm/s)':     'D_Vert B2 (mm)',
            'Longitudinal B2 (mm/s)': 'D_Long B2 (mm)',
            'Transversal B2 (mm/s)':  'D_Tran B2 (mm)',
        }
        for col in b2_vel_cols:
            accel_col = B2_ACCEL.get(col, col.replace('(mm/s)', '(mm/s²)'))
            df[accel_col] = np.gradient(df[col].values, 1 / sampling_rate)
            disp_col = B2_DISP.get(col, col.replace('(mm/s)', '(mm)'))
            sig = df[col].values - np.mean(df[col].values)
            disp = np.cumsum(sig) * (1 / sampling_rate)
            df[disp_col] = disp - np.mean(disp)

    return df


def _build_bargraph_df(r: dict) -> pd.DataFrame:
    """
    Convert bargraph data into a Vibraport-standard DataFrame.
    Each row = one monitoring interval.
    Columns: time_s, then per-channel amplitude and frequency.
    """
    df = pd.DataFrame({'time_s': r['time_axis']})

    for label, data in r['bargraph'].items():
        df[f"{label}_amplitude"] = data['amplitude']
        df[f"{label}_frequency"] = data['frequency']

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
