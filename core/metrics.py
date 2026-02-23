# core/metrics.py
"""
Vibration hazard metrics.

Physical concept: Raw waveforms must be reduced to scalar metrics
that engineers can use to assess hazard and compare against
regulatory limits. PPV is the primary metric in blast vibration.
"""

import numpy as np
from typing import Dict


def peak_particle_velocity(sig: np.ndarray) -> float:
    """
    Peak Particle Velocity — maximum absolute value of the waveform.

    The primary metric for blast vibration hazard assessment.
    """
    return float(np.abs(sig).max())


def vector_sum(ppv_vert: float, ppv_long: float, ppv_tran: float) -> float:
    """
    Peak Vector Sum — geometric combination of three-component PPVs.

    PVS = sqrt(PPV_V² + PPV_L² + PPV_T²)

    More conservative than individual channel PPV since it accounts
    for the combined effect of all three vibration components.
    """
    return float(np.sqrt(ppv_vert**2 + ppv_long**2 + ppv_tran**2))


def peak_displacement(sig: np.ndarray) -> tuple:
    """
    Find the peak displacement value and its index.

    Returns:
        peak_val (float) — maximum absolute displacement (mm)
        peak_idx (int)   — sample index of peak displacement
    """
    peak_idx = int(np.abs(sig).argmax())
    peak_val = float(sig[peak_idx])
    return peak_val, peak_idx


def acceleration_at_peak(
    accel_sig: np.ndarray,
    peak_idx: int
) -> float:
    """
    Acceleration value at the moment of peak displacement.

    Useful for structural response assessment — a structure at
    peak displacement experiences this acceleration.

    Returns acceleration in mm/s².
    """
    return float(accel_sig[peak_idx])


def acceleration_in_g(accel_mms2: float) -> float:
    """
    Convert acceleration from mm/s² to g.

    1 g = 9806.65 mm/s²
    """
    return float(accel_mms2 / 9806.65)


def extract_channel_metrics(
    df,
    accel_at_peak_map: dict,
    sampling_rate: int,
    freq_method: str,
    calculate_frequency_fn,
) -> Dict[str, dict]:
    """
    Extract full set of metrics for each velocity channel.

    Returns dict of {channel_name: {ppv, frequency, peak_disp,
                                     accel_at_peak, accel_g}}
    """
    results = {}
    for disp_col, accel_col in accel_at_peak_map.items():
        disp_sig = df[disp_col].values
        accel_sig = df[accel_col].values
        peak_val, peak_idx = peak_displacement(disp_sig)
        accel_val = acceleration_at_peak(accel_sig, peak_idx)
        results[disp_col] = {
            'peak_displacement': abs(peak_val),
            'accel_at_peak': abs(accel_val),
            'accel_g': abs(acceleration_in_g(accel_val)),
            'peak_time_ms': peak_idx * 1000 / sampling_rate,
        }
    return results
