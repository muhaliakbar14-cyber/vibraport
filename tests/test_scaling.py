# tests/test_scaling.py
"""Tests for USBM charge-weight/distance amplitude scaling."""

import numpy as np
import pytest
from core.scaling import usbm_scale_factor, compute_scales
from core.superposition import superpose, superpose_channels
from core.engine import run_single, run_simulation
from config import SimulationConfig


def test_scale_factor_equal_weight_equal_distance_is_one():
    # Same charge, same distance as signature -> no change, any B
    assert usbm_scale_factor(10.0, 10.0, 1.0, 1.6) == pytest.approx(1.0)


def test_scale_factor_zero_field_constant_is_one():
    # B = 0 means no attenuation dependence at all -> always 1.0
    assert usbm_scale_factor(20.0, 10.0, 2.0, 0.0) == pytest.approx(1.0)


def test_scale_factor_heavier_charge_scales_up():
    scale = usbm_scale_factor(20.0, 10.0, 1.0, 1.6)
    assert scale > 1.0


def test_scale_factor_farther_distance_scales_down():
    scale = usbm_scale_factor(10.0, 10.0, 2.0, 1.6)
    assert scale < 1.0


def test_scale_factor_invalid_inputs_fail_safe_to_one():
    assert usbm_scale_factor(0.0, 10.0, 1.0, 1.6) == 1.0
    assert usbm_scale_factor(10.0, 0.0, 1.0, 1.6) == 1.0
    assert usbm_scale_factor(10.0, 10.0, 0.0, 1.6) == 1.0
    assert usbm_scale_factor(-5.0, 10.0, 1.0, 1.6) == 1.0


def test_compute_scales_length_matches_shift_count():
    scales = compute_scales(
        n_holes=3, n_rows=2, n_decks=1,
        signature_weight_kg=10.0, distance_ratio=1.0, field_constant=1.6,
    )
    assert len(scales) == 6  # 3 holes x 2 rows x 1 deck


def test_compute_scales_uniform_weight_default_is_all_ones():
    # No hole_weights_kg supplied -> every hole treated as signature weight
    scales = compute_scales(
        n_holes=4, n_rows=1, n_decks=1,
        signature_weight_kg=10.0, distance_ratio=1.0, field_constant=1.6,
    )
    assert all(s == pytest.approx(1.0) for s in scales)


def test_compute_scales_per_hole_weights_align_with_loop_order():
    # 2 holes x 2 rows: loop order is row-major (row outer, hole inner),
    # so hole_weights_kg[hole] must repeat identically across every row.
    hole_weights = [10.0, 20.0]  # hole 0 = signature weight, hole 1 = double
    scales = compute_scales(
        n_holes=2, n_rows=2, n_decks=1,
        signature_weight_kg=10.0, distance_ratio=1.0, field_constant=1.6,
        hole_weights_kg=hole_weights,
    )
    # index 0,1 = row0 (hole0, hole1); index 2,3 = row1 (hole0, hole1)
    assert scales[0] == pytest.approx(1.0)
    assert scales[2] == pytest.approx(1.0)
    assert scales[1] == pytest.approx(scales[3])
    assert scales[1] > 1.0  # heavier hole scales up, consistently every row


def test_superpose_with_scales_applies_amplitude_factor():
    sig = np.array([1.0, 1.0, 1.0])
    result = superpose(sig, [0, 3], scales=[1.0, 2.0])
    assert np.allclose(result[:3], [1.0, 1.0, 1.0])   # first copy, scale 1.0
    assert np.allclose(result[3:6], [2.0, 2.0, 2.0])  # second copy, scale 2.0


def test_superpose_default_scales_unchanged_from_before():
    sig = np.array([1.0, 2.0, 3.0])
    result_no_scale = superpose(sig, [0, 5])
    result_explicit_ones = superpose(sig, [0, 5], scales=[1.0, 1.0])
    assert np.allclose(result_no_scale, result_explicit_ones)


def test_run_simulation_scaling_disabled_matches_pre_scaling_behavior():
    waveform = {
        'Vert': np.sin(np.linspace(0, 10, 200)),
        'Long': np.cos(np.linspace(0, 10, 200)) * 0.5,
        'Tran': np.sin(np.linspace(0, 10, 200)) * 0.3,
    }
    config = SimulationConfig(
        sample_rate=2048,
        waveform=waveform,
        hole_delays_ms=[20.0],
        row_delays_ms=[50.0],
        n_holes=2,
        n_rows=1,
        n_decks=1,
        scaling_enabled=False,
    )
    results = run_simulation(config)
    assert len(results) == 1
    assert results[0]['pvs'] > 0


def test_run_simulation_scaling_enabled_changes_pvs():
    waveform = {
        'Vert': np.sin(np.linspace(0, 10, 200)),
        'Long': np.cos(np.linspace(0, 10, 200)) * 0.5,
        'Tran': np.sin(np.linspace(0, 10, 200)) * 0.3,
    }
    base_config = SimulationConfig(
        sample_rate=2048,
        waveform=waveform,
        hole_delays_ms=[20.0],
        row_delays_ms=[50.0],
        n_holes=2,
        n_rows=1,
        n_decks=1,
        scaling_enabled=False,
    )
    scaled_config = SimulationConfig(
        sample_rate=2048,
        waveform=waveform,
        hole_delays_ms=[20.0],
        row_delays_ms=[50.0],
        n_holes=2,
        n_rows=1,
        n_decks=1,
        scaling_enabled=True,
        signature_weight_kg=10.0,
        hole_weights_kg=[10.0, 30.0],  # second hole much heavier
        distance_ratio=1.0,
        field_constant=1.6,
    )
    base_pvs = run_simulation(base_config)[0]['pvs']
    scaled_pvs = run_simulation(scaled_config)[0]['pvs']
    assert scaled_pvs != base_pvs
    assert scaled_pvs > base_pvs  # heavier second hole should push PVS up
