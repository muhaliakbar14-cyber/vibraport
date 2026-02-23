# core/fft_analysis.py
"""
Frequency domain analysis of vibration signals.

Physical concept: Vibration signals contain energy at multiple frequencies.
FFT decomposes the signal into its frequency components, allowing us to
identify the dominant frequency and energy distribution.
"""

import numpy as np


def compute_fft(sig: np.ndarray, sampling_rate: int) -> tuple:
    """
    Compute FFT magnitude spectrum and frequency axis.

    Returns:
        freqs   (np.ndarray) — frequency axis in Hz
        fft_mag (np.ndarray) — magnitude spectrum
    """
    n = len(sig)
    fft_mag = np.abs(np.fft.rfft(sig))
    freqs = np.fft.rfftfreq(n, d=1 / sampling_rate)
    return freqs, fft_mag


def compute_energy_spectrum(fft_mag: np.ndarray) -> tuple:
    """
    Compute cumulative energy spectrum from FFT magnitude.

    Returns:
        energy            (np.ndarray) — power per frequency bin
        cumulative_energy (np.ndarray) — cumulative sum of energy
        total_energy      (float)      — total signal energy
    """
    energy = fft_mag ** 2
    cumulative_energy = np.cumsum(energy)
    total_energy = cumulative_energy[-1]
    return energy, cumulative_energy, total_energy


def frequency_zero_crossing(sig: np.ndarray, sampling_rate: int) -> float:
    """
    Estimate dominant frequency via zero crossing rate.

    DC offset removed before counting to avoid bias.
    Uses full signal duration as denominator — no segment removal
    which would artificially inflate frequency.
    """
    sig = sig - np.mean(sig)
    zero_crossings = np.where(np.diff(np.sign(sig)))[0]
    if len(zero_crossings) < 2:
        return 0.0
    total_duration = len(sig) / sampling_rate
    return round(len(zero_crossings) / (2 * total_duration), 2)


def frequency_fft_peak(freqs: np.ndarray, fft_mag: np.ndarray) -> float:
    """
    Dominant frequency as the FFT bin with maximum magnitude.
    """
    return round(float(freqs[np.argmax(fft_mag)]), 2)


def frequency_energy_percentile(
    freqs: np.ndarray,
    cumulative_energy: np.ndarray,
    total_energy: float,
    percentile: float
) -> float:
    """
    Frequency at which cumulative energy reaches a given percentile.

    Args:
        percentile — value between 0 and 1 (e.g. 0.5 for median frequency)
    """
    idx = np.searchsorted(cumulative_energy, percentile * total_energy)
    idx = min(idx, len(freqs) - 1)
    return round(float(freqs[idx]), 2)


def calculate_frequency(sig: np.ndarray, sampling_rate: int, method: str) -> float:
    """
    Unified frequency estimator. Dispatches to the appropriate method.

    Args:
        sig          — velocity signal (mm/s)
        sampling_rate — samples per second
        method       — one of: Zero Crossing, FFT Peak,
                       Energy 25%, Energy 50%, Energy 75%
    """
    if method == "Zero Crossing":
        return frequency_zero_crossing(sig, sampling_rate)

    freqs, fft_mag = compute_fft(sig, sampling_rate)
    _, cumulative_energy, total_energy = compute_energy_spectrum(fft_mag)

    if method == "FFT Peak":
        return frequency_fft_peak(freqs, fft_mag)
    elif method == "Energy 25%":
        return frequency_energy_percentile(freqs, cumulative_energy, total_energy, 0.25)
    elif method == "Energy 50%":
        return frequency_energy_percentile(freqs, cumulative_energy, total_energy, 0.50)
    elif method == "Energy 75%":
        return frequency_energy_percentile(freqs, cumulative_energy, total_energy, 0.75)
    return 0.0
