# core/engine.py
"""
Simulation engine — orchestrates the full SHA pipeline.

Physical concept: Ties together delay computation, superposition,
and metric extraction into a single simulation run. This is the
main entry point for running a Signature Hole Analysis.
"""

import numpy as np
from typing import Dict, List
from core.delay import compute_shifts, max_delay_samples
from core.superposition import superpose_channels
from core.metrics import peak_particle_velocity, vector_sum
from core.fft_analysis import calculate_frequency


def run_single(
    channels: Dict[str, np.ndarray],
    shifts: List[int],
) -> dict:
    """
    Run a single superposition for one delay combination.

    Returns:
        dict with PPV per channel, Peak Vector Sum,
        and dominant frequency per channel.
    """
    combined = superpose_channels(channels, shifts)

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

            result = run_single(channels, shifts)

            # Dominant frequency per channel
            freqs = {
                ch: calculate_frequency(
                    result['combined'][ch],
                    int(config.sample_rate),
                    "Energy 50%"
                )
                for ch in channels
            }

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
