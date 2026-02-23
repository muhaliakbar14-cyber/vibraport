# core/superposition.py
"""
Waveform superposition for blast vibration simulation.

Physical concept: When multiple blast holes fire with time delays,
their vibration waveforms arrive at the monitoring point at different
times and add together (superimpose). The combined waveform determines
the resulting ground vibration.
"""

import numpy as np
from typing import List


def superpose(sig: np.ndarray, shifts: List[int]) -> np.ndarray:
    """
    Superimpose time-shifted copies of a signature waveform.

    Zero-padded output — no wrap-around artifacts.
    Each shifted copy represents one hole-row-deck firing event.

    Args:
        sig    — signature waveform (single hole recording)
        shifts — list of sample offsets for each firing event

    Returns:
        combined — superimposed waveform
    """
    if not shifts:
        return sig.copy()

    total_len = len(sig) + max(shifts) + 1
    combined = np.zeros(total_len)
    for s in shifts:
        combined[s:s + len(sig)] += sig
    return combined


def superpose_channels(
    channels: dict,
    shifts: List[int],
) -> dict:
    """
    Superimpose multiple channels simultaneously using the same shifts.

    Args:
        channels — dict of {channel_name: waveform_array}
        shifts   — sample offsets from compute_shifts()

    Returns:
        dict of {channel_name: combined_waveform}
    """
    return {
        ch_name: superpose(sig, shifts)
        for ch_name, sig in channels.items()
    }
