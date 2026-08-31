"""Definitions and limit functions for supported vibration standards.

The constants below are derived from the editions named in each standard id.
They intentionally model only building-damage assessments used by Vibraport:

* SNI 7571:2023 Table 4
* DIN 4150-3:2016-12, Tables 1 and 4
* BS 7385-2:1993, Table 1 and clauses 7.4.2-7.4.3

Specialist DIN assessments for underground cavities and buried pipework are
outside this module's scope.
"""

from dataclasses import dataclass


SHORT_TERM = "short_term"
LONG_TERM = "long_term"


@dataclass(frozen=True)
class CategorySpec:
    id: int
    label: str
    short_label: str


@dataclass(frozen=True)
class StandardSpec:
    id: str
    title: str
    categories: tuple[CategorySpec, ...]
    assessments: tuple[str, ...]
    x_range: tuple[float, float]
    x_ticks: tuple[float, ...]
    breakpoints: tuple[float, ...]


SNI_LIMITS = {
    1: (2.0, 3.0, 5.0),
    2: (3.0, 5.0, 7.0),
    3: (5.0, 7.0, 12.0),
    4: (7.0, 12.0, 20.0),
    5: (12.0, 24.0, 40.0),
}

DIN_SHORT_ANCHORS = {
    1: ((1.0, 20.0), (10.0, 20.0), (50.0, 40.0), (100.0, 50.0)),
    2: ((1.0, 5.0), (10.0, 5.0), (50.0, 15.0), (100.0, 20.0)),
    3: ((1.0, 3.0), (10.0, 3.0), (50.0, 8.0), (100.0, 10.0)),
}

DIN_LONG_LIMITS = {1: 10.0, 2: 5.0, 3: 2.5}

BS_SHORT_ANCHORS = {
    1: ((4.0, 50.0), (100.0, 50.0)),
    2: ((4.0, 15.0), (15.0, 20.0), (40.0, 50.0), (100.0, 50.0)),
}


STANDARDS = {
    "sni_7571_2023": StandardSpec(
        id="sni_7571_2023",
        title="SNI 7571:2023",
        categories=(
            CategorySpec(1, "Class 1 - Highly sensitive / heritage buildings", "C1"),
            CategorySpec(2, "Class 2 - Sensitive / simple residential buildings", "C2"),
            CategorySpec(3, "Class 3 - Standard residential buildings", "C3"),
            CategorySpec(4, "Class 4 - Reinforced residential / commercial buildings", "C4"),
            CategorySpec(5, "Class 5 - Heavy industrial / critical infrastructure", "C5"),
        ),
        assessments=(SHORT_TERM,),
        x_range=(1.0, 100.0),
        x_ticks=(1.0, 5.0, 20.0, 100.0),
        breakpoints=(5.0, 20.0),
    ),
    "din_4150_3_2016": StandardSpec(
        id="din_4150_3_2016",
        title="DIN 4150-3:2016",
        categories=(
            CategorySpec(1, "Line 1 - Commercial, industrial, or similar buildings", "L1"),
            CategorySpec(2, "Line 2 - Residential buildings or similar", "L2"),
            CategorySpec(3, "Line 3 - Particularly sensitive / listed structures", "L3"),
        ),
        assessments=(SHORT_TERM, LONG_TERM),
        x_range=(1.0, 100.0),
        x_ticks=(1.0, 10.0, 50.0, 100.0),
        breakpoints=(10.0, 50.0),
    ),
    "bs_7385_2_1993": StandardSpec(
        id="bs_7385_2_1993",
        title="BS 7385-2:1993",
        categories=(
            CategorySpec(1, "Line 1 - Reinforced, framed, industrial, or heavy commercial", "L1"),
            CategorySpec(2, "Line 2 - Unreinforced, residential, or light commercial", "L2"),
        ),
        assessments=(SHORT_TERM, LONG_TERM),
        x_range=(1.0, 100.0),
        x_ticks=(1.0, 4.0, 15.0, 40.0, 100.0),
        breakpoints=(4.0, 15.0, 40.0),
    ),
}

STANDARD_ORDER = tuple(STANDARDS)


def get_standard(standard_id: str) -> StandardSpec:
    try:
        return STANDARDS[standard_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported compliance standard: {standard_id}") from exc


def assessment_options(standard_id: str) -> tuple[str, ...]:
    return get_standard(standard_id).assessments


def category_options(standard_id: str) -> tuple[CategorySpec, ...]:
    return get_standard(standard_id).categories


def assessment_label(assessment: str) -> str:
    labels = {SHORT_TERM: "Short-term", LONG_TERM: "Long-term"}
    try:
        return labels[assessment]
    except KeyError as exc:
        raise ValueError(f"Unsupported assessment duration: {assessment}") from exc


def chart_title(standard_id: str, assessment: str) -> str:
    spec = get_standard(standard_id)
    if standard_id == "sni_7571_2023":
        return spec.title
    return f"{spec.title} - {assessment_label(assessment)}"


def _linear_interpolate(freq: float, anchors: tuple[tuple[float, float], ...]) -> float | None:
    if freq < anchors[0][0]:
        return None
    if freq >= anchors[-1][0]:
        return anchors[-1][1]
    for (f0, v0), (f1, v1) in zip(anchors, anchors[1:]):
        if f0 <= freq <= f1:
            fraction = (freq - f0) / (f1 - f0)
            return v0 + fraction * (v1 - v0)
    return None


def limit_at_frequency(
    standard_id: str,
    assessment: str,
    category_id: int,
    frequency_hz: float,
) -> float | None:
    """Return the applied PPV limit in mm/s, or None when PPV alone is insufficient."""
    spec = get_standard(standard_id)
    if assessment not in spec.assessments:
        raise ValueError(f"{assessment_label(assessment)} is not available for {spec.title}")
    if category_id not in {category.id for category in spec.categories}:
        raise ValueError(f"Unknown category {category_id} for {spec.title}")
    freq = float(frequency_hz)
    if freq <= 0:
        return None

    if standard_id == "sni_7571_2023":
        segment = 0 if freq < 5 else (1 if freq < 20 else 2)
        return SNI_LIMITS[category_id][segment]

    if standard_id == "din_4150_3_2016":
        if assessment == LONG_TERM:
            return DIN_LONG_LIMITS[category_id]
        return _linear_interpolate(freq, DIN_SHORT_ANCHORS[category_id])

    if standard_id == "bs_7385_2_1993":
        transient_limit = _linear_interpolate(freq, BS_SHORT_ANCHORS[category_id])
        if transient_limit is None:
            return None
        return transient_limit if assessment == SHORT_TERM else transient_limit * 0.5

    raise ValueError(f"Unsupported compliance standard: {standard_id}")


def measurement_basis(standard_id: str, assessment: str) -> str:
    if standard_id == "sni_7571_2023":
        return "Applied basis: PPV frequency bands in SNI 7571:2023 Table 4."
    if standard_id == "din_4150_3_2016" and assessment == SHORT_TERM:
        return "Applied basis: foundation, all directions (DIN Table 1, columns 2-4)."
    if standard_id == "din_4150_3_2016":
        return "Applied basis: topmost floor, horizontal direction (DIN Table 4, column 2)."
    if assessment == SHORT_TERM:
        return "Applied basis: transient vibration measured at the base of the building."
    return "Applied basis: conservative continuous-vibration screening at 50% of BS transient values."


def measurement_explanation(standard_id: str, assessment: str) -> str:
    if standard_id == "sni_7571_2023":
        return measurement_basis(standard_id, assessment)
    if standard_id == "din_4150_3_2016" and assessment == SHORT_TERM:
        return (
            measurement_basis(standard_id, assessment)
            + " DIN Table 1 also gives frequency-independent values for the topmost-floor "
              "horizontal direction and floor-slab vertical direction; use those columns when "
              "they match the actual sensor location."
        )
    if standard_id == "din_4150_3_2016":
        return (
            measurement_basis(standard_id, assessment)
            + " DIN Table 4 separately gives floor-slab vertical values. Users should compare "
              "the result with the column matching the actual sensor location."
        )
    if assessment == SHORT_TERM:
        return (
            measurement_basis(standard_id, assessment)
            + " For Line 2 below 4 Hz, BS 7385-2 requires a 0.6 mm zero-to-peak "
              "displacement check, so Vibraport reports Review instead of PPV compliance."
        )
    return (
        measurement_basis(standard_id, assessment)
        + " BS 7385-2 states that reductions are condition-dependent; a Review result requires "
          "engineering assessment rather than being treated automatically as failure."
    )


def format_limit(limit: float | None) -> str:
    if limit is None:
        return "-"
    if float(limit).is_integer():
        return f"{limit:.0f}"
    return f"{limit:.1f}".rstrip("0").rstrip(".")


def reference_values(standard_id: str, assessment: str) -> tuple[float, ...]:
    values = {1.0, 100.0}
    for category in category_options(standard_id):
        for freq in get_standard(standard_id).x_ticks:
            limit = limit_at_frequency(standard_id, assessment, category.id, freq)
            if limit is not None:
                values.add(float(limit))
    return tuple(sorted(values))


def curve_points(
    standard_id: str,
    assessment: str,
    category_id: int,
) -> tuple[list[float], list[float]]:
    """Return enough samples to preserve linear-in-frequency interpolation on a log chart."""
    if standard_id == "sni_7571_2023":
        v1, v2, v3 = SNI_LIMITS[category_id]
        return [1, 5, 5, 20, 20, 100], [v1, v1, v2, v2, v3, v3]

    start = 4.0 if standard_id == "bs_7385_2_1993" else 1.0
    end = 100.0
    samples = 240
    x_values = [start + (end - start) * i / (samples - 1) for i in range(samples)]
    y_values = [limit_at_frequency(standard_id, assessment, category_id, x) for x in x_values]
    return x_values, [float(y) for y in y_values if y is not None]


def category_by_id(standard_id: str, category_id: int) -> CategorySpec:
    for category in category_options(standard_id):
        if category.id == category_id:
            return category
    raise ValueError(f"Unknown category {category_id} for {get_standard(standard_id).title}")
