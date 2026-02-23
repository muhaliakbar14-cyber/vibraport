# optimizer/delay_scan.py
"""
Delay scan optimizer for Signature Hole Analysis.

Physical concept: Searches over a grid of hole and row delay
combinations to find the timing that minimizes peak vibration.
This is the core of SHA — finding optimal blast timing.
"""

import numpy as np
import pandas as pd
from typing import List, Callable, Optional
from config import SimulationConfig
from core.engine import run_simulation, find_best


def build_delay_grid(
    hole_delay_start: float,
    hole_delay_end: float,
    hole_delay_increment: float,
    row_delay_start: float,
    row_delay_end: float,
    row_delay_increment: float,
) -> tuple:
    """
    Build the grid of hole and row delays to scan over.

    Returns:
        hole_delays (list) — list of hole delays in ms
        row_delays  (list) — list of row delays in ms
        total       (int)  — total number of combinations
    """
    hole_delays = list(np.arange(
        hole_delay_start,
        hole_delay_end + hole_delay_increment,
        hole_delay_increment
    ))
    row_delays = list(np.arange(
        row_delay_start,
        row_delay_end + row_delay_increment,
        row_delay_increment
    ))
    return hole_delays, row_delays, len(hole_delays) * len(row_delays)


def results_to_dataframe(results: List[dict]) -> pd.DataFrame:
    """
    Convert simulation results list to a formatted DataFrame.
    """
    rows = []
    for r in results:
        rows.append({
            'Hole Delay (ms)': int(r['hole_delay_ms']),
            'Row Delay (ms)': int(r['row_delay_ms']),
            'PPV Vert (mm/s)': r['ppv_vert'],
            'PPV Long (mm/s)': r['ppv_long'],
            'PPV Tran (mm/s)': r['ppv_tran'],
            'Peak Vector Sum (mm/s)': r['pvs'],
            'Freq Vert (Hz)': r['freq_vert'],
            'Freq Long (Hz)': r['freq_long'],
            'Freq Tran (Hz)': r['freq_tran'],
        })
    return pd.DataFrame(rows)


def scan(
    config: SimulationConfig,
    progress_callback: Optional[Callable] = None,
) -> tuple:
    """
    Run the full delay scan and return results and best combination.

    Args:
        config            — SimulationConfig with waveform and delay ranges
        progress_callback — optional callable(count, total) for UI progress

    Returns:
        df      (pd.DataFrame) — all results
        best    (dict)         — row with minimum Peak Vector Sum
        best_idx (int)         — index of best row in df
    """
    results = run_simulation(config, progress_callback)
    best = find_best(results, key='pvs')
    df = results_to_dataframe(results)
    best_idx = df['Peak Vector Sum (mm/s)'].idxmin()
    return df, best, best_idx
