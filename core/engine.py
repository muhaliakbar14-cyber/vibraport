# core/engine.py
"""
Simulation engine — orchestrates the full SHA pipeline.

Physical concept: Ties together delay computation, superposition,
and metric extraction into a single simulation run. This is the
main entry point for running a Signature Hole Analysis.
"""

import numpy as np
from typing import Dict, List, Optional
from core.delay import compute_shifts, max_delay_samples
from core.superposition import superpose_channels
from core.metrics import peak_particle_velocity, vector_sum
from core.fft_analysis import calculate_frequency
from core.scaling import compute_scales


def run_single(
    channels: Dict[str, np.ndarray],
    shifts: List[int],
    scales: Optional[List[float]] = None,
) -> dict:
    """
    Run a single superposition for one delay combination.

    Args:
        scales — optional per-event amplitude scale factors from
                 core.scaling.compute_scales(); None = unscaled.

    Returns:
        dict with PPV per channel, Peak Vector Sum,
        and dominant frequency per channel.
    """
    combined = superpose_channels(channels, shifts, scales)

    ppv = {ch: peak_particle_velocity(sig) for ch, sig in combined.items()}
    pvs = vector_sum(ppv['Vert'], ppv['Long'], ppv['Tran'])

    return {
        'ppv': ppv,
        'pvs': pvs,
        'combined': combined,
    }


def run_simulation(
    config,
    progress_callback=None,
) -> List[dict]:
    """
    Run the full SHA simulation across all delay combinations.

    Args:
        config           — SimulationConfig instance
        progress_callback — optional callable(count, total) for UI progress

    Returns:
        List of result dicts, one per delay combination.
    """
    samples_per_ms = config.samples_per_ms()

    channels = {
        'Vert': config.waveform['Vert'],
        'Long': config.waveform['Long'],
        'Tran': config.waveform['Tran'],
    }

    # Scale factors don't depend on delay timing — same for every
    # (hole_delay, row_delay) combination in the grid — so compute once
    # outside the scan loop rather than recomputing per iteration.
    scales = None
    if getattr(config, 'scaling_enabled', False):
        scales = compute_scales(
            n_holes=config.n_holes,
            n_rows=config.n_rows,
            n_decks=config.n_decks,
            signature_weight_kg=config.signature_weight_kg,
            distance_ratio=config.distance_ratio,
            field_constant=config.field_constant,
            hole_weights_kg=config.hole_weights_kg,
        )

    results = []
    total = len(config.hole_delays_ms) * len(config.row_delays_ms)
    count = 0

    for hd in config.hole_delays_ms:
        for rd in config.row_delays_ms:
            shifts = compute_shifts(
                n_holes=config.n_holes,
                n_rows=config.n_rows,
                n_decks=config.n_decks,
                hole_delay_ms=hd,
                row_delay_ms=rd,
                deck_delay_ms=config.deck_delay_ms,
                samples_per_ms=samples_per_ms,
            )

            result = run_single(channels, shifts, scales)

            # Dominant frequency per channel
            freqs = {
                ch: calculate_frequency(
                    result['combined'][ch],
                    int(config.sample_rate),
                    "Energy 50%"
                )
                for ch in channels
            }

            # PPV-weighted average frequency across the three channels.
            # Weights each channel's dominant frequency by its PPV contribution,
            # so the channel with the most vibration energy drives the result.
            # More meaningful than min-frequency (dragged down by noisy channels)
            # and avoids the envelope artifact of the vector sum signal approach.
            ppv_v = result['ppv']['Vert']
            ppv_l = result['ppv']['Long']
            ppv_t = result['ppv']['Tran']
            total_ppv = ppv_v + ppv_l + ppv_t
            if total_ppv > 0:
                freq_vs = round(
                    (freqs['Vert'] * ppv_v +
                     freqs['Long'] * ppv_l +
                     freqs['Tran'] * ppv_t) / total_ppv,
                    2
                )
            else:
                freq_vs = 0.0

            results.append({
                'hole_delay_ms': hd,
                'row_delay_ms': rd,
                'ppv_vert': round(result['ppv']['Vert'], 2),
                'ppv_long': round(result['ppv']['Long'], 2),
                'ppv_tran': round(result['ppv']['Tran'], 2),
                'pvs': round(result['pvs'], 2),
                'freq_vert': freqs['Vert'],
                'freq_long': freqs['Long'],
                'freq_tran': freqs['Tran'],
                'freq_vs': freq_vs,
            })

            count += 1
            if progress_callback:
                progress_callback(count, total)

    return results


def find_best(results: List[dict], key: str = 'pvs') -> dict:
    """
    Find the result with the minimum value for a given key.

    Default key is 'pvs' (Peak Vector Sum).
    Could also sort by frequency if needed in future.
    """
    return min(results, key=lambda r: r[key])
