"""Regression snapshot and attenuation-navigation regression tests."""

from pathlib import Path

import pytest

from pages.ppv_analysis import _build_regression_result


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _rows():
    return [
        {
            "No.": index,
            "Source": f"event-{index}",
            "Block": 1,
            "Charge (kg)": 100.0 + index * 10,
            "Distance (m)": 50.0 + index * 20,
            "Vertical (mm/s)": 9.0 - index,
            "Longitudinal (mm/s)": 7.5 - index * 0.7,
            "Transversal (mm/s)": 6.0 - index * 0.5,
        }
        for index in range(1, 6)
    ]


def test_attenuation_precedes_signature_hole_in_waveform_navigation():
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    menu = source.split('page = st.radio(', 1)[1].split('key="waveform_page"', 1)[0]

    assert menu.index('"📈 Attenuation & Safe Zone"') < menu.index(
        '"💥 Signature Hole Analysis"'
    )


def test_regression_result_is_a_snapshot_of_calculate_click():
    rows = _rows()
    result = _build_regression_result(rows, ["Vertical", "Longitudinal"])
    plotted_values = tuple(result["figure"].data[0].y)
    equation = result["regression_equation"]

    rows[0]["Vertical (mm/s)"] = 999.0
    rows[1]["Distance (m)"] = 999.0

    assert tuple(result["figure"].data[0].y) == plotted_values
    assert result["regression_equation"] == equation
    assert result["selected_channels"] == ("Vertical", "Longitudinal")
    assert result["figure"].data[-2].name == "Regression line"
    assert result["figure"].data[-1].name == "95% Confidence line"


def test_regression_requires_a_selected_channel():
    with pytest.raises(ValueError, match="select at least one channel"):
        _build_regression_result(_rows(), [])


def test_regression_requires_enough_positive_selected_values():
    rows = _rows()
    for row in rows:
        row["Vertical (mm/s)"] = 0.0

    with pytest.raises(ValueError, match="at least 4 positive PPV values"):
        _build_regression_result(rows, ["Vertical"])


def test_render_source_keeps_last_result_outside_button_branch():
    source = (PROJECT_ROOT / "pages" / "ppv_analysis.py").read_text(
        encoding="utf-8"
    )

    assert "st.session_state['ppv_regression_result'] = regression_result" in source
    assert "regression_result = st.session_state.get('ppv_regression_result')" in source
    assert "_render_regression_result(regression_result)" in source
