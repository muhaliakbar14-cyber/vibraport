# regression/fitting.py
"""
Regression fitting for PPV attenuation models.

Physical concept: PPV follows a power law with scaled distance:
    PPV = K × SD^n

K and n are site constants fitted from field measurements.
The 95% confidence line provides an upper bound for safe design.
"""

import numpy as np


def fit_power_law(
    scaled_distance: np.ndarray,
    ppv: np.ndarray,
) -> dict:
    """
    Fit PPV = K × SD^n using log-log linear regression.

    Returns:
        dict with K, n, r (correlation), K_conf (95% upper bound)
    """
    log_SD = np.log(scaled_distance)
    log_V = np.log(ppv)
    A = np.column_stack([np.ones_like(log_SD), log_SD])
    result = np.linalg.lstsq(A, log_V, rcond=None)
    log_K, n = result[0]
    K = np.exp(log_K)

    log_V_pred = log_K + n * log_SD
    r = float(np.corrcoef(log_V, log_V_pred)[0, 1])

    residuals = log_V - log_V_pred
    std_res = np.std(residuals)
    K_conf = np.exp(log_K + 1.645 * std_res)

    return {
        'K': round(K, 2),
        'n': round(n, 3),
        'r': round(r, 3),
        'K_conf': round(K_conf, 2),
    }


def regression_curve(
    K: float,
    n: float,
    sd_range: np.ndarray,
) -> np.ndarray:
    """
    Compute regression line values over a range of scaled distances.
    """
    return K * (sd_range ** n)


def confidence_curve(
    K_conf: float,
    n: float,
    sd_range: np.ndarray,
) -> np.ndarray:
    """
    Compute 95% confidence line values over a range of scaled distances.
    """
    return K_conf * (sd_range ** n)


def predict_ppv(K: float, n: float, scaled_distance: float) -> float:
    """
    Predict PPV at a given scaled distance using fitted K and n.
    """
    return float(K * (scaled_distance ** n))


def predict_safe_distance(
    K: float,
    n: float,
    charge: float,
    ppv_limit: float,
    use_confidence: bool = True,
    K_conf: float = None,
) -> float:
    """
    Predict the minimum safe distance for a given charge and PPV limit.

    Inverts PPV = K × (D/√Q)^n to solve for D:
        D = √Q × (PPV_limit / K)^(1/n)

    Args:
        use_confidence — if True, uses K_conf for conservative estimate
    """
    k = K_conf if (use_confidence and K_conf) else K
    return float(np.sqrt(charge) * (ppv_limit / k) ** (1 / n))
