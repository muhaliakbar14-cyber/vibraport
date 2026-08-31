"""Boundary and integration tests for structural vibration standards."""

import pytest

from core.compliance import (
    build_compliance_chart,
    evaluate_point,
    evaluate_points,
    limit_at_frequency,
    overall_status,
)
from core.sni_chart import build_sni_chart


def point(ppv=4.0, freq=32.0, channel="Vertical"):
    return {"channel": channel, "ppv": ppv, "freq": freq, "block": 1}


@pytest.mark.parametrize(
    "frequency, expected",
    [(4.99, 5.0), (5.0, 7.0), (19.99, 7.0), (20.0, 12.0), (100.0, 12.0)],
)
def test_sni_class_3_boundaries(frequency, expected):
    assert limit_at_frequency("sni_7571_2023", "short_term", 3, frequency) == expected


@pytest.mark.parametrize(
    "category, frequency, expected",
    [
        (1, 1, 20), (1, 10, 20), (1, 30, 30), (1, 50, 40), (1, 75, 45), (1, 100, 50),
        (2, 30, 10), (2, 75, 17.5),
        (3, 30, 5.5), (3, 75, 9),
    ],
)
def test_din_short_term_foundation_interpolation(category, frequency, expected):
    actual = limit_at_frequency("din_4150_3_2016", "short_term", category, frequency)
    assert actual == pytest.approx(expected)


def test_din_short_term_below_range_requires_review():
    result = evaluate_point(point(freq=0.8), "din_4150_3_2016", "short_term", 2)
    assert result.status == "REVIEW"
    assert result.limit is None


@pytest.mark.parametrize("category, expected", [(1, 10), (2, 5), (3, 2.5)])
def test_din_long_term_topmost_floor_limits(category, expected):
    for frequency in (1, 20, 100, 200):
        assert limit_at_frequency("din_4150_3_2016", "long_term", category, frequency) == expected


@pytest.mark.parametrize(
    "category, frequency, expected",
    [(1, 4, 50), (1, 100, 50), (2, 4, 15), (2, 15, 20), (2, 27.5, 35), (2, 40, 50)],
)
def test_bs_short_term_interpolation(category, frequency, expected):
    actual = limit_at_frequency("bs_7385_2_1993", "short_term", category, frequency)
    assert actual == pytest.approx(expected)


def test_bs_below_four_hz_requires_displacement_review():
    result = evaluate_point(point(ppv=1, freq=3), "bs_7385_2_1993", "short_term", 2)
    assert result.status == "REVIEW"
    assert result.limit is None
    assert "0.6 mm" in result.note


def test_bs_long_term_uses_conservative_half_curve():
    assert limit_at_frequency("bs_7385_2_1993", "long_term", 2, 15) == 10
    passing = evaluate_point(point(ppv=9, freq=15), "bs_7385_2_1993", "long_term", 2)
    review = evaluate_point(point(ppv=11, freq=15), "bs_7385_2_1993", "long_term", 2)
    assert passing.status == "PASS"
    assert review.status == "REVIEW"


def test_overall_status_precedence():
    passed = evaluate_point(point(ppv=2, freq=20), "din_4150_3_2016", "short_term", 2)
    failed = evaluate_point(point(ppv=30, freq=20), "din_4150_3_2016", "short_term", 2)
    review = evaluate_point(point(ppv=2, freq=3), "bs_7385_2_1993", "short_term", 2)
    assert overall_status([passed]) == "PASS"
    assert overall_status([passed, review]) == "REVIEW"
    assert overall_status([passed, review, failed]) == "FAIL"
    assert overall_status([]) == "REVIEW"


@pytest.mark.parametrize(
    "standard, duration, category, expected_title, expected_ticks",
    [
        ("sni_7571_2023", "short_term", 3, "SNI 7571:2023", (1, 5, 20, 100)),
        ("din_4150_3_2016", "short_term", 2, "DIN 4150-3:2016 - Short-term", (1, 10, 50, 100)),
        ("din_4150_3_2016", "long_term", 2, "DIN 4150-3:2016 - Long-term", (1, 10, 50, 100)),
        ("bs_7385_2_1993", "short_term", 2, "BS 7385-2:1993 - Short-term", (1, 4, 15, 40, 100)),
        ("bs_7385_2_1993", "long_term", 2, "BS 7385-2:1993 - Long-term", (1, 4, 15, 40, 100)),
    ],
)
def test_chart_configuration(standard, duration, category, expected_title, expected_ticks):
    fig = build_compliance_chart([point()], standard, duration, category)
    assert fig.layout.title.text == expected_title
    assert tuple(fig.layout.xaxis.tickvals) == expected_ticks
    assert fig.layout.xaxis.minor.showgrid is False
    assert fig.layout.yaxis.minor.showgrid is False
    assert fig.layout.showlegend is False


def test_din_long_term_chart_has_no_frequency_boundaries():
    fig = build_compliance_chart([point()], "din_4150_3_2016", "long_term", 2)
    vertical_lines = [shape for shape in fig.layout.shapes if shape.type == "line" and shape.x0 == shape.x1]
    assert vertical_lines == []


def test_sni_compatibility_wrapper():
    fig = build_sni_chart([point()], selected_class=3, compact=True)
    assert fig.layout.title.text == "SNI 7571:2023"


def test_invalid_category_rejected():
    with pytest.raises(ValueError):
        evaluate_points([point()], "din_4150_3_2016", "short_term", 99)
