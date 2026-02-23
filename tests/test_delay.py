# tests/test_delay.py
"""Tests for delay timing computations."""

import pytest
from core.delay import (
    ms_to_samples,
    compute_firing_times,
    compute_shifts,
    max_delay_samples,
    delay_range,
)

SAMPLES_PER_MS = 2.048  # 2048 sps


def test_ms_to_samples_basic():
    assert ms_to_samples(10.0, SAMPLES_PER_MS) == 20


def test_ms_to_samples_zero():
    assert ms_to_samples(0.0, SAMPLES_PER_MS) == 0


def test_compute_firing_times_single_hole():
    times = compute_firing_times(1, 1, 1, 10.0, 20.0, 0.0)
    assert times == [0.0]


def test_compute_firing_times_two_holes():
    times = compute_firing_times(2, 1, 1, 10.0, 20.0, 0.0)
    assert times == [0.0, 10.0]


def test_compute_firing_times_two_rows():
    times = compute_firing_times(1, 2, 1, 10.0, 20.0, 0.0)
    assert times == [0.0, 20.0]


def test_compute_firing_times_decks():
    times = compute_firing_times(1, 1, 2, 10.0, 20.0, 5.0)
    assert times == [0.0, 5.0]


def test_compute_shifts_length():
    shifts = compute_shifts(3, 2, 1, 10.0, 20.0, 0.0, SAMPLES_PER_MS)
    assert len(shifts) == 6  # 3 holes × 2 rows × 1 deck


def test_compute_shifts_are_integers():
    shifts = compute_shifts(2, 2, 1, 10.0, 20.0, 0.0, SAMPLES_PER_MS)
    assert all(isinstance(s, int) for s in shifts)


def test_max_delay_samples():
    shifts = [0, 10, 20, 30]
    assert max_delay_samples(shifts) == 30


def test_delay_range_length():
    delays = delay_range(10, 50, 10)
    assert len(delays) == 5


def test_delay_range_values():
    delays = delay_range(10, 30, 10)
    assert delays == [10.0, 20.0, 30.0]
