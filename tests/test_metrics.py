# tests/test_metrics.py
"""Tests for vibration hazard metrics."""

import numpy as np
import pytest
from core.metrics import (
    peak_particle_velocity,
    vector_sum,
    peak_displacement,
    acceleration_at_peak,
    acceleration_in_g,
)


def test_ppv_positive():
    sig = np.array([0.1, -0.5, 0.3, -0.2])
    assert peak_particle_velocity(sig) == 0.5


def test_ppv_all_positive():
    sig = np.array([1.0, 2.0, 3.0])
    assert peak_particle_velocity(sig) == 3.0


def test_vector_sum_basic():
    result = vector_sum(3.0, 4.0, 0.0)
    assert pytest.approx(result, 0.001) == 5.0


def test_vector_sum_zero():
    assert vector_sum(0.0, 0.0, 0.0) == 0.0


def test_peak_displacement_value():
    sig = np.array([0.1, -0.8, 0.3])
    val, idx = peak_displacement(sig)
    assert val == -0.8
    assert idx == 1


def test_acceleration_at_peak():
    accel = np.array([1.0, 5.0, 2.0])
    result = acceleration_at_peak(accel, peak_idx=1)
    assert result == 5.0


def test_acceleration_in_g():
    result = acceleration_in_g(9806.65)
    assert pytest.approx(result, 0.001) == 1.0


def test_acceleration_in_g_half():
    result = acceleration_in_g(4903.325)
    assert pytest.approx(result, 0.001) == 0.5
