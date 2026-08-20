# core/superposition.py
"""
Waveform superposition for blast vibration simulation.

Physical concept: When multiple blast holes fire with time delays,
their vibration waveforms arrive at the monitoring point at different
times and add together (superimpose). The combined waveform determines
the resulting ground vibration.
"""

import numpy as np
from typing import List, Optional


def superpose(sig: np.ndarray, shifts: List[int], scales: Optional[List[float]] = None) -> np.ndarray:
    """
    Superimpose time-shifted copies of a signature waveform.

    Zero-padded output — no wrap-around artifacts.
    Each shifted copy represents one hole-row-deck firing event.

    Args:
        sig    — signature waveform (single hole recording)
        shifts — list of sample offsets for each firing event
        scales — optional list of per-event amplitude scale factors,
                 same length and order as shifts (see core.scaling).
                 Defaults to 1.0 for every event, i.e. unscaled — the
                 original behavior before charge-weight/distance scaling
                 was added.

    Returns:
        combined — superimposed waveform
    """
    if not shifts:
        return sig.copy()

    if scales is None:
        scales = [1.0] * len(shifts)

    total_len = len(sig) + max(shifts) + 1
    combined = np.zeros(total_len)
    for s, sc in zip(shifts, scales):
        combined[s:s + len(sig)] += sig * sc
    return combined


def superpose_channels(
    channels: dict,
    shifts: List[int],
    scales: Optional[List[float]] = None,
) -> dict:
    """
    Superimpose multiple channels simultaneously using the same shifts
    and the same per-event scale factors (a hole's charge-weight/distance
    scale factor applies uniformly across Vert/Long/Tran — we're scaling
    the whole recorded vector, not re-deriving each axis separately).

    Args:
        channels — dict of {channel_name: waveform_array}
        shifts   — sample offsets from compute_shifts()
        scales   — optional per-event amplitude scale factors (core.scaling)

    Returns:
        dict of {channel_name: combined_waveform}
    """
    return {
        ch_name: superpose(sig, shifts, scales)
        for ch_name, sig in channels.items()
    }
