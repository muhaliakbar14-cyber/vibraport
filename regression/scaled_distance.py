# regression/scaled_distance.py
"""
Scaled distance computation for PPV attenuation analysis.

Physical concept: Vibration attenuates with distance from the blast.
Scaled distance normalizes distance by charge weight, allowing
comparison of measurements from different blast sizes.
"""

import numpy as np
from typing import List


def standard_scaled_distance(
    distances: np.ndarray,
    charges: np.ndarray,
) -> np.ndarray:
    """
    Standard scaled distance: SD = D / √Q

    The most widely used form. Assumes charge and distance
    interact with a fixed exponent of -0.5.

    Args:
        distances — array of distances in meters
        charges   — array of charge weights in kg

    Returns:
        scaled distance array (m/kg^0.5)
    """
    return distances / np.sqrt(charges)


def optimized_scaled_distance(
    distances: np.ndarray,
    charges: np.ndarray,
    exponent: float,
) -> np.ndarray:
    """
    Two-variable scaled distance: SD = D × Q^exponent

    The exponent is fitted to maximize correlation,
    rather than fixed at -0.5. More accurate for
    site-specific conditions.

    Args:
        distances — array of distances in meters
        charges   — array of charge weights in kg
        exponent  — fitted charge exponent

    Returns:
        scaled distance array
    """
    return distances * (charges ** exponent)


def find_best_exponent(
    distances: np.ndarray,
    charges: np.ndarray,
    ppv: np.ndarray,
) -> float:
    """
    Find the charge exponent that maximizes correlation
    between scaled distance and PPV on a log-log scale.

    Uses scipy bounded scalar minimization over [-2, 2].
    """
    from scipy.optimize import minimize_scalar

    def neg_correlation(exp):
        SD = optimized_scaled_distance(distances, charges, exp)
        log_SD = np.log(SD)
        log_V = np.log(ppv)
        A = np.column_stack([np.ones_like(log_SD), log_SD])
        result = np.linalg.lstsq(A, log_V, rcond=None)
        log_V_pred = A @ result[0]
        r = np.corrcoef(log_V, log_V_pred)[0, 1]
        return -abs(r)

    opt = minimize_scalar(neg_correlation, bounds=(-2, 2), method='bounded')
    return float(opt.x)
