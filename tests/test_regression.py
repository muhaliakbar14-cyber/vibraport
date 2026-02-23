# tests/test_regression.py
"""Tests for PPV regression models."""

import numpy as np
import pytest
from regression.scaled_distance import standard_scaled_distance, optimized_scaled_distance
from regression.fitting import fit_power_law, predict_ppv, predict_safe_distance


def test_standard_scaled_distance():
    distances = np.array([100.0, 200.0])
    charges = np.array([100.0, 100.0])
    sd = standard_scaled_distance(distances, charges)
    assert pytest.approx(sd[0], 0.001) == 10.0
    assert pytest.approx(sd[1], 0.001) == 20.0


def test_optimized_scaled_distance_exp_zero():
    # Q^0 = 1, so SD = D * 1 = D
    distances = np.array([100.0, 200.0])
    charges = np.array([50.0, 100.0])
    sd = optimized_scaled_distance(distances, charges, 0.0)
    assert np.allclose(sd, distances)


def test_fit_power_law_returns_keys():
    sd = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    ppv = 1000.0 * (sd ** -1.6)
    result = fit_power_law(sd, ppv)
    assert set(result.keys()) == {'K', 'n', 'r', 'K_conf'}


def test_fit_power_law_perfect_fit():
    sd = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    ppv = 1000.0 * (sd ** -1.6)
    result = fit_power_law(sd, ppv)
    assert pytest.approx(result['r'], abs=0.01) == 1.0
    assert pytest.approx(result['K'], rel=0.01) == 1000.0
    assert pytest.approx(result['n'], abs=0.01) == -1.6


def test_predict_ppv():
    ppv = predict_ppv(K=1000.0, n=-1.6, scaled_distance=10.0)
    expected = 1000.0 * (10.0 ** -1.6)
    assert pytest.approx(ppv, rel=0.001) == expected


def test_predict_safe_distance():
    d = predict_safe_distance(K=1000.0, n=-1.6, charge=100.0,
                              ppv_limit=5.0, use_confidence=False)
    assert d > 0
