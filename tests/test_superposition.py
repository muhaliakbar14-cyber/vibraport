# tests/test_superposition.py
"""Tests for waveform superposition."""

import numpy as np
import pytest
from core.superposition import superpose, superpose_channels


def test_superpose_no_shift():
    sig = np.array([1.0, 2.0, 3.0])
    result = superpose(sig, [0])
    assert np.allclose(result[:3], sig)


def test_superpose_output_length():
    sig = np.array([1.0, 2.0, 3.0])
    shifts = [0, 5]
    result = superpose(sig, shifts)
    assert len(result) == len(sig) + max(shifts) + 1


def test_superpose_two_identical_shifts():
    sig = np.array([1.0, 1.0, 1.0])
    result = superpose(sig, [0, 0])
    assert np.allclose(result[:3], [2.0, 2.0, 2.0])


def test_superpose_no_wraparound():
    sig = np.ones(10)
    result = superpose(sig, [0, 100])
    # Values before shift 100 should only contain first copy
    assert np.allclose(result[:10], np.ones(10))


def test_superpose_channels():
    channels = {
        'Vert': np.array([1.0, 2.0, 3.0]),
        'Long': np.array([0.5, 1.0, 1.5]),
        'Tran': np.array([0.1, 0.2, 0.3]),
    }
    result = superpose_channels(channels, [0, 2])
    assert set(result.keys()) == {'Vert', 'Long', 'Tran'}
    assert len(result['Vert']) > 3
