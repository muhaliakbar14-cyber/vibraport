# core/delay.py
"""
Delay timing computations for blast hole firing sequences.

Physical concept: Each hole, row, and deck fires at a specific time
determined by the detonator delay. This module converts timing
parameters into sample offsets for waveform superposition.
"""

import numpy as np
from typing import List


def ms_to_samples(delay_ms: float, samples_per_ms: float) -> int:
    """
    Convert a delay in milliseconds to integer sample offset.
    """
    return int(delay_ms * samples_per_ms)


def compute_firing_times(
    n_holes: int,
    n_rows: int,
    n_decks: int,
    hole_delay_ms: float,
    row_delay_ms: float,
    deck_delay_ms: float,
) -> List[float]:
    """
    Compute the firing time (ms) for every hole-row-deck combination.

    Firing time = (hole × hole_delay) + (row × row_delay) + (deck × deck_delay)

    Returns a flat list of firing times in milliseconds.
    """
    return [
        (hole * hole_delay_ms) + (row * row_delay_ms) + (deck * deck_delay_ms)
        for row in range(n_rows)
        for hole in range(n_holes)
        for deck in range(n_decks)
    ]


def compute_shifts(
    n_holes: int,
    n_rows: int,
    n_decks: int,
    hole_delay_ms: float,
    row_delay_ms: float,
    deck_delay_ms: float,
    samples_per_ms: float,
) -> List[int]:
    """
    Compute integer sample shifts for every hole-row-deck combination.

    This is the sample-domain equivalent of compute_firing_times,
    ready for direct use in superposition.
    """
    firing_times = compute_firing_times(
        n_holes, n_rows, n_decks,
        hole_delay_ms, row_delay_ms, deck_delay_ms
    )
    return [ms_to_samples(t, samples_per_ms) for t in firing_times]


def max_delay_samples(shifts: List[int]) -> int:
    """
    Return the maximum sample shift — used to size the output array.
    """
    return max(shifts) if shifts else 0


def delay_range(start_ms: float, end_ms: float, increment_ms: float) -> List[float]:
    """
    Generate a list of delay values to scan over.

    Args:
        start_ms     — minimum delay in ms
        end_ms       — maximum delay in ms
        increment_ms — step size in ms
    """
    return list(np.arange(start_ms, end_ms + increment_ms, increment_ms))
