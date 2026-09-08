"""Compliance evaluation independent of Streamlit and report rendering."""

import math
from dataclasses import dataclass

from .standards import LONG_TERM, category_by_id, get_standard, limit_at_frequency


@dataclass(frozen=True)
class ComplianceResult:
    channel: str
    ppv: float
    frequency_hz: float
    limit: float | None
    status: str
    note: str = ""


def evaluate_point(
    point: dict,
    standard_id: str,
    assessment: str,
    category_id: int,
) -> ComplianceResult:
    ppv = float(point["ppv"])
    freq = float(point["freq"])
    channel = str(point.get("channel", "Channel"))

    if not math.isfinite(freq) or freq <= 0:
        return ComplianceResult(
            channel,
            ppv,
            freq,
            None,
            "REVIEW",
            "Dominant frequency is missing or zero; no PPV limit was guessed.",
        )

    limit = limit_at_frequency(standard_id, assessment, category_id, freq)

    if limit is None:
        if standard_id == "bs_7385_2_1993" and freq < 4:
            note = "Below 4 Hz: check the BS 0.6 mm zero-to-peak displacement criterion."
        else:
            note = "Frequency is outside the PPV assessment range."
        return ComplianceResult(channel, ppv, freq, None, "REVIEW", note)

    if standard_id == "bs_7385_2_1993" and assessment == LONG_TERM and ppv > limit:
        return ComplianceResult(
            channel, ppv, freq, limit, "REVIEW",
            "Exceeds the conservative 50% continuous-vibration screening curve; engineering review is required.",
        )

    status = "PASS" if ppv <= limit else "FAIL"
    return ComplianceResult(channel, ppv, freq, limit, status)


def evaluate_points(
    points: list[dict],
    standard_id: str,
    assessment: str,
    category_id: int,
) -> list[ComplianceResult]:
    get_standard(standard_id)
    category_by_id(standard_id, category_id)
    return [evaluate_point(point, standard_id, assessment, category_id) for point in points]


def overall_status(results: list[ComplianceResult]) -> str:
    if not results:
        return "REVIEW"
    statuses = {result.status for result in results}
    if "FAIL" in statuses:
        return "FAIL"
    if "REVIEW" in statuses:
        return "REVIEW"
    return "PASS"
