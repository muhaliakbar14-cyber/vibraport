# core/scaling.py
"""
USBM charge-weight / distance amplitude scaling for Signature Hole Analysis.

Physical concept: A signature-hole waveform is recorded from ONE hole at
ONE charge weight and ONE monitoring distance. When simulating a full
pattern, holes may carry a different charge weight than the signature hole
(different loading), and — as a simplification — the whole pattern is
treated as being at one distance ratio relative to the signature shot.

Approach — USBM square-root scaled-distance law (Duvall & Petkof):
    PPV = K * (D / sqrt(W)) ** -B

Rearranged to a per-hole AMPLITUDE SCALE FACTOR relative to the recorded
signature waveform (K cancels out because we're scaling a measured
waveform, not predicting PPV from scratch):

    scale = ((W_hole / W_signature) / distance_ratio ** 2) ** (0.5 * B)

Where:
    W_hole        — charge weight of the hole being simulated (kg)
    W_signature   — charge weight of the recorded signature hole (kg)
    distance_ratio — D_hole / D_signature (>0). 1.0 = same distance as the
                     signature shot (pure charge-weight scaling only).
    B (field_constant) — site-specific attenuation exponent from a prior
                     PPV-vs-scaled-distance regression (see regression/).
                     NOT calibrated from the signature wave itself.

IMPORTANT — this only rescales AMPLITUDE. It assumes the scaled hole
produces a waveform of the SAME SHAPE (same frequency content, same
duration) as the signature hole, just bigger or smaller. This is a
standard engineering approximation, not an exact physical model:

  - It holds reasonably well for charge-weight changes at a similar
    propagation path (same rock, similar distance to the signature shot).
  - It gets less reliable as charge weight departs far from the signature
    weight, since very different charge/deck configurations can change
    pulse duration, not just amplitude.
  - It does NOT capture that ground attenuates high frequencies faster
    than low frequencies over distance — a hole genuinely farther from
    the monitor should, physically, arrive lower-frequency and more
    dispersed, not just "the same wave, smaller." Distance scaling here
    only correct for amplitude, not for that frequency-content shift.
  - It doesn't capture differing geology along different propagation
    paths (joints, benches, weathered zones).

See the "About USBM Scaling" panel on the Signature Hole Analysis page
for the same explanation shown to the user.
"""

from typing import List, Optional


def usbm_scale_factor(
    hole_weight_kg: float,
    signature_weight_kg: float,
    distance_ratio: float,
    field_constant: float,
) -> float:
    """
    Compute the amplitude scale factor for one hole relative to the
    recorded signature waveform, using the USBM scaled-distance law.

    Returns 1.0 (no scaling) if either weight is non-positive or the
    distance ratio is non-positive, to fail safe rather than raise or
    produce NaN/inf in a live simulation.
    """
    if hole_weight_kg <= 0 or signature_weight_kg <= 0 or distance_ratio <= 0:
        return 1.0
    weight_ratio = hole_weight_kg / signature_weight_kg
    return (weight_ratio / (distance_ratio ** 2)) ** (0.5 * field_constant)


def compute_scales(
    n_holes: int,
    n_rows: int,
    n_decks: int,
    signature_weight_kg: float,
    distance_ratio: float = 1.0,
    field_constant: float = 1.6,
    hole_weights_kg: Optional[List[float]] = None,
) -> List[float]:
    """
    Compute one amplitude scale factor per (row, hole, deck) firing event,
    in EXACTLY the same loop order as core.delay.compute_firing_times /
    compute_shifts, so the returned list lines up index-for-index with
    the shifts list without any separate sort or re-matching step.

    (This sidesteps a real bug class seen in other signature-hole tools,
    where delay values get sorted independently of the weight list they're
    supposed to correspond to, silently mismatching hole identity.)

    Args:
        hole_weights_kg — optional list of length n_holes, one charge
            weight (kg) per hole position, reused identically for every
            row. If None or empty, every hole is treated as firing at
            signature_weight_kg (i.e. scale = distance-only, or 1.0 if
            distance_ratio is also 1.0 — matches pre-scaling behavior).
        distance_ratio — single value applied to the whole pattern
            (D_hole_pattern / D_signature). Per-hole distance is not
            modeled — see module docstring.

    Returns:
        List[float] of length n_holes * n_rows * n_decks.
    """
    scales = []
    for _row in range(n_rows):
        for hole in range(n_holes):
            for _deck in range(n_decks):
                if hole_weights_kg:
                    w = hole_weights_kg[hole]
                else:
                    w = signature_weight_kg
                scales.append(
                    usbm_scale_factor(
                        hole_weight_kg=w,
                        signature_weight_kg=signature_weight_kg,
                        distance_ratio=distance_ratio,
                        field_constant=field_constant,
                    )
                )
    return scales
