"""Tests for normalized bargraph metadata and scalable display helpers."""

import numpy as np
import pandas as pd
import pytest

from core.monitoring import (
    aggregate_monitoring_trends,
    build_bargraph_channel_metadata,
    detect_events_for_channels,
    detect_threshold_events,
    evaluate_bargraph_ppv,
    get_bargraph_channels,
    infer_monitoring_interval,
    peak_preserving_downsample,
    ppv_compliance_eligibility,
    summarize_channel,
)
from pages.monitoring_trends import (
    _build_trend_figure,
    _shared_axis_compatible,
)


def _parser_result(magnitude="Velocity", unit="mm/s", frequencies=None):
    if frequencies is None:
        frequencies = np.array([4, 5, 6], dtype=np.uint16)
    base = f"Ch1_Vertical_{magnitude}"
    return {
        "channel_info": [
            {
                "index": 1,
                "axis": "Vertical",
                "magnitude": magnitude,
                "type": "Geophone 8.0 Hz fn",
                "unit": unit,
                "over_range": False,
                "is_virtual": False,
            }
        ],
        "bargraph": {
            base: {
                "amplitude": np.array([0.2, 1.5, 0.4], dtype=np.float32),
                "frequency": frequencies,
            }
        },
    }


def test_unflagged_velocity_bars_are_interval_peaks():
    channel = build_bargraph_channel_metadata(_parser_result())[0]

    assert channel["quantity"] == "Velocity"
    assert channel["statistic"] == "Interval peak"
    assert channel["unit"] == "mm/s"
    assert channel["frequency_available"] is True
    assert channel["label"] == "Vertical (Ch1)"


def test_rms_flag_is_preserved_without_inventing_vdv():
    channel = build_bargraph_channel_metadata(
        _parser_result(magnitude="Acceleration RMS", unit="m/s²")
    )[0]

    assert channel["quantity"] == "Acceleration"
    assert channel["statistic"] == "RMS"
    assert "vdv" not in {key.lower() for key in channel}


def test_frequency_is_unavailable_when_payload_contains_only_zeroes():
    channel = build_bargraph_channel_metadata(
        _parser_result(frequencies=np.zeros(3, dtype=np.uint16))
    )[0]

    assert channel["frequency_available"] is False


@pytest.mark.parametrize(
    "changes,expected,reason_fragment",
    [
        ({}, True, "Eligible"),
        ({"statistic": "RMS"}, False, "RMS"),
        ({"quantity": "Acceleration", "unit": "m/s²"}, False, "velocity"),
        ({"unit": "in/s"}, False, "mm/s"),
    ],
)
def test_ppv_compliance_channel_eligibility(changes, expected, reason_fragment):
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    channel.update(changes)

    eligible, reason = ppv_compliance_eligibility(channel)

    assert eligible is expected
    assert reason_fragment in reason


def test_bargraph_ppv_uses_full_interval_frequency_and_shared_limits():
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    df = pd.DataFrame(
        {
            channel["amplitude_column"]: [2.0, 7.0, 20.0],
            channel["frequency_column"]: [5.0, 30.0, 30.0],
        }
    )

    records = evaluate_bargraph_ppv(
        df,
        [0.0, 1.0, 2.0],
        [channel],
        "din_4150_3_2016",
        "short_term",
        2,
    )

    assert len(records) == 3
    assert [record["limit"] for record in records] == pytest.approx([5.0, 10.0, 10.0])
    assert [record["status"] for record in records] == ["PASS", "PASS", "FAIL"]
    assert records[2]["utilization_percent"] == pytest.approx(200.0)
    assert records[2]["time_seconds"] == 2.0


def test_bargraph_ppv_missing_frequency_is_review_even_for_din_long_term():
    channel = build_bargraph_channel_metadata(
        _parser_result(frequencies=np.zeros(3, dtype=np.uint16))
    )[0]
    df = pd.DataFrame({channel["amplitude_column"]: [1.0, 2.0, 3.0]})

    records = evaluate_bargraph_ppv(
        df,
        [0.0, 1.0, 2.0],
        [channel],
        "din_4150_3_2016",
        "long_term",
        2,
    )

    assert len(records) == 3
    assert {record["status"] for record in records} == {"REVIEW"}
    assert {record["limit"] for record in records} == {None}
    assert all("no PPV limit was guessed" in record["note"] for record in records)


def test_bargraph_ppv_skips_rms_and_non_velocity_channels():
    base = build_bargraph_channel_metadata(_parser_result())[0]
    rms = {**base, "label": "RMS", "statistic": "RMS"}
    pressure = {
        **base,
        "label": "Pressure",
        "quantity": "Pressure",
        "unit": "Pa",
    }
    df = pd.DataFrame(
        {
            base["amplitude_column"]: [1.0, 2.0],
            base["frequency_column"]: [10.0, 20.0],
        }
    )

    assert evaluate_bargraph_ppv(
        df,
        [0.0, 1.0],
        [rms, pressure],
        "sni_7571_2023",
        "short_term",
        3,
    ) == []


def test_monitoring_interval_uses_time_axis_not_header_fallback():
    assert infer_monitoring_interval([0, 2, 4, 6], fallback=1000) == 2
    assert infer_monitoring_interval([0], fallback=5) == 5
    assert infer_monitoring_interval([], fallback=None) is None


def test_get_channels_uses_normalized_metadata_and_filters_missing_columns():
    parser_result = _parser_result()
    channel = build_bargraph_channel_metadata(parser_result)[0]
    df = pd.DataFrame(
        {
            channel["amplitude_column"]: [0.2, 1.5, 0.4],
            channel["frequency_column"]: [4, 5, 6],
        }
    )

    actual = get_bargraph_channels(
        df,
        {
            "Bargraph channels": [
                channel,
                {**channel, "amplitude_column": "missing_amplitude"},
            ]
        },
    )

    assert actual == [channel]


def test_channel_summary_uses_full_finite_series_and_peak_frequency():
    result = summarize_channel(
        [1.0, np.nan, 4.0, 2.0],
        [3.0, 4.0, 12.0, 8.0],
    )

    assert result["sample_count"] == 4
    assert result["valid_count"] == 3
    assert result["invalid_count"] == 1
    assert result["maximum"] == 4.0
    assert result["median"] == 2.0
    assert result["p95"] == pytest.approx(3.8)
    assert result["peak_index"] == 2
    assert result["frequency_at_peak"] == 12.0


def test_trend_aggregation_uses_original_intervals_and_bucket_peak_frequency():
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    times = np.arange(120, dtype=float)
    amplitudes = np.arange(120, dtype=float)
    frequencies = np.arange(120, dtype=float) + 2
    df = pd.DataFrame(
        {
            channel["amplitude_column"]: amplitudes,
            channel["frequency_column"]: frequencies,
        }
    )

    records = aggregate_monitoring_trends(
        df,
        times,
        [channel],
        60,
        interval_seconds=1,
    )

    assert len(records) == 2
    assert records[0]["start_seconds"] == 0
    assert records[0]["end_seconds"] == 60
    assert records[0]["midpoint_seconds"] == 30
    assert records[0]["interval_count"] == 60
    assert records[0]["valid_count"] == 60
    assert records[0]["maximum"] == 59
    assert records[0]["mean"] == pytest.approx(29.5)
    assert records[0]["median"] == pytest.approx(29.5)
    assert records[0]["p95"] == pytest.approx(np.percentile(amplitudes[:60], 95))
    assert records[0]["p99"] == pytest.approx(np.percentile(amplitudes[:60], 99))
    assert records[0]["frequency_at_max"] == 61
    assert records[1]["maximum"] == 119


def test_trend_aggregation_counts_invalid_values_without_inventing_statistics():
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    df = pd.DataFrame(
        {
            channel["amplitude_column"]: [1.0, np.nan, 3.0, np.nan],
            channel["frequency_column"]: [4.0, 5.0, 8.0, 9.0],
        }
    )

    records = aggregate_monitoring_trends(
        df,
        [0.0, 1.0, 2.0, 3.0],
        [channel],
        2,
        interval_seconds=1,
    )

    assert [record["interval_count"] for record in records] == [2, 2]
    assert [record["valid_count"] for record in records] == [1, 1]
    assert [record["maximum"] for record in records] == [1.0, 3.0]
    assert [record["frequency_at_max"] for record in records] == [4.0, 8.0]


def test_native_trend_buckets_preserve_each_interval_and_data_gap():
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    df = pd.DataFrame(
        {
            channel["amplitude_column"]: [1.0, np.nan, 3.0],
            channel["frequency_column"]: [4.0, 5.0, 8.0],
        }
    )

    records = aggregate_monitoring_trends(
        df,
        [0.0, 1.0, 2.0],
        [channel],
        1,
        interval_seconds=1,
    )

    assert len(records) == 3
    assert [record["maximum"] for record in records] == [1.0, None, 3.0]
    assert [record["valid_count"] for record in records] == [1, 0, 1]
    assert records[1]["frequency_at_max"] is None


@pytest.mark.parametrize("bucket_seconds", [0, -1, np.nan])
def test_trend_aggregation_rejects_invalid_bucket(bucket_seconds):
    with pytest.raises(ValueError, match="bucket_seconds"):
        aggregate_monitoring_trends(
            pd.DataFrame(),
            [],
            [],
            bucket_seconds,
        )


def test_trend_aggregation_rejects_mismatched_time_and_amplitude_arrays():
    channel = build_bargraph_channel_metadata(_parser_result())[0]
    df = pd.DataFrame({channel["amplitude_column"]: [1.0, 2.0]})

    with pytest.raises(ValueError, match="same length"):
        aggregate_monitoring_trends(df, [0.0], [channel], 60)


def test_peak_preserving_downsample_caps_points_and_keeps_extrema():
    times = np.arange(10_000, dtype=float)
    values = np.sin(times / 30)
    values[1234] = 18.0
    values[8765] = -12.0

    display_times, display_values = peak_preserving_downsample(
        times, values, max_points=500
    )

    assert len(display_times) <= 500
    assert np.all(np.diff(display_times) > 0)
    assert display_times[0] == 0
    assert display_times[-1] == 9999
    assert np.max(display_values) == 18.0
    assert np.min(display_values) == -12.0


def test_short_display_series_is_not_changed():
    times = np.arange(20, dtype=float)
    values = np.arange(20, dtype=float) ** 2

    display_times, display_values = peak_preserving_downsample(
        times, values, max_points=100
    )

    np.testing.assert_array_equal(display_times, times)
    np.testing.assert_array_equal(display_values, values)


def test_downsample_rejects_mismatched_arrays():
    with pytest.raises(ValueError, match="same length"):
        peak_preserving_downsample([0, 1], [2], max_points=10)


def test_event_detector_groups_consecutive_intervals_and_classifies_peak():
    events = detect_threshold_events(
        np.arange(8, dtype=float),
        [0, 1.1, 1.2, 0.8, 1.3, 0, 0, 2.2],
        channel="Vertical (Ch1)",
        quantity="Velocity",
        unit="mm/s",
        yellow_threshold=1.0,
        red_threshold=2.0,
        frequency=[0, 4, 5, 6, 7, 0, 0, 12],
        interval_seconds=1,
        hysteresis=0.2,
    )

    assert len(events) == 2
    assert events[0]["severity"] == "Yellow"
    assert events[0]["start_index"] == 1
    assert events[0]["end_index"] == 4
    assert events[0]["duration_seconds"] == 4
    assert events[0]["peak"] == 1.3
    assert events[0]["frequency_at_peak"] == 7
    assert events[1]["severity"] == "Red"
    assert events[1]["peak"] == 2.2


def test_event_gap_tolerance_bridges_one_quiet_interval():
    separate = detect_threshold_events(
        np.arange(5, dtype=float),
        [0, 1.1, 0, 1.2, 0],
        channel="Vertical",
        quantity="Velocity",
        unit="mm/s",
        yellow_threshold=1.0,
        interval_seconds=1,
        gap_tolerance_seconds=0,
    )
    merged = detect_threshold_events(
        np.arange(5, dtype=float),
        [0, 1.1, 0, 1.2, 0],
        channel="Vertical",
        quantity="Velocity",
        unit="mm/s",
        yellow_threshold=1.0,
        interval_seconds=1,
        gap_tolerance_seconds=1,
    )

    assert len(separate) == 2
    assert len(merged) == 1
    assert merged[0]["start_index"] == 1
    assert merged[0]["end_index"] == 3
    assert merged[0]["interval_count"] == 3
    assert merged[0]["exceedance_intervals"] == 2


def test_event_minimum_duration_filters_short_events():
    events = detect_threshold_events(
        np.arange(4, dtype=float),
        [0, 1.2, 0, 0],
        channel="Vertical",
        quantity="Velocity",
        unit="mm/s",
        yellow_threshold=1.0,
        interval_seconds=1,
        minimum_duration_seconds=2,
    )

    assert events == []


def test_multi_channel_events_are_chronologically_sorted():
    times = np.arange(5, dtype=float)
    df = pd.DataFrame(
        {
            "vertical_amplitude": [0, 0, 1.5, 0, 0],
            "vertical_frequency": [0, 0, 8, 0, 0],
            "longitudinal_amplitude": [0, 1.2, 0, 0, 0],
            "longitudinal_frequency": [0, 5, 0, 0, 0],
        }
    )
    channels = [
        {
            "label": "Vertical (Ch1)",
            "quantity": "Velocity",
            "unit": "mm/s",
            "amplitude_column": "vertical_amplitude",
            "frequency_column": "vertical_frequency",
        },
        {
            "label": "Longitudinal (Ch2)",
            "quantity": "Velocity",
            "unit": "mm/s",
            "amplitude_column": "longitudinal_amplitude",
            "frequency_column": "longitudinal_frequency",
        },
    ]

    events = detect_events_for_channels(
        df,
        times,
        channels,
        {"Velocity": (1.0, 2.0)},
        interval_seconds=1,
    )

    assert [event["channel"] for event in events] == [
        "Longitudinal (Ch2)",
        "Vertical (Ch1)",
    ]


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("yellow_threshold", 0),
        ("gap_tolerance_seconds", -1),
        ("hysteresis", -0.1),
        ("minimum_duration_seconds", -1),
    ],
)
def test_event_detector_rejects_invalid_settings(keyword, value):
    arguments = {
        "yellow_threshold": 1.0,
        "gap_tolerance_seconds": 0.0,
        "hysteresis": 0.0,
        "minimum_duration_seconds": 0.0,
    }
    arguments[keyword] = value

    with pytest.raises(ValueError):
        detect_threshold_events(
            [0, 1],
            [0, 2],
            channel="Vertical",
            quantity="Velocity",
            unit="mm/s",
            **arguments,
        )


def test_trend_shared_axis_requires_matching_quantity_and_unit():
    velocity_channels = [
        {"quantity": "Velocity", "unit": "mm/s"},
        {"quantity": "Velocity", "unit": "mm/s"},
    ]

    assert _shared_axis_compatible(velocity_channels) is True
    assert _shared_axis_compatible(velocity_channels[:1]) is False
    assert _shared_axis_compatible(
        [velocity_channels[0], {"quantity": "Pressure", "unit": "Pa"}]
    ) is False
    assert _shared_axis_compatible(
        [velocity_channels[0], {"quantity": "Velocity", "unit": "in/s"}]
    ) is False


def test_stacked_trend_figure_can_synchronize_y_axes():
    channels, records = _trend_figure_fixture()

    rendered, figure = _build_trend_figure(
        records,
        channels,
        "maximum",
        "Maximum",
        synchronize_y_axis=True,
    )

    assert rendered == 6
    assert len(figure.data) == 2
    assert figure.layout.showlegend is False
    assert figure.layout.yaxis2.matches == "y"


def test_combined_trend_figure_overlays_channels_with_legend_toggles():
    channels, records = _trend_figure_fixture()

    rendered, figure = _build_trend_figure(
        records,
        channels,
        "p95",
        "P95",
        chart_layout="Combined overlay",
    )

    assert rendered == 6
    assert [trace.name for trace in figure.data] == [
        "Vertical (Ch1)",
        "Longitudinal (Ch2)",
    ]
    assert figure.layout.showlegend is True
    assert figure.layout.yaxis.title.text == "P95 (mm/s)"
    assert figure.layout.hovermode == "x unified"


def _trend_figure_fixture():
    channels = [
        {
            "label": "Vertical (Ch1)",
            "axis": "Vertical",
            "quantity": "Velocity",
            "unit": "mm/s",
        },
        {
            "label": "Longitudinal (Ch2)",
            "axis": "Longitudinal",
            "quantity": "Velocity",
            "unit": "mm/s",
        },
    ]
    records = []
    for channel_index, channel in enumerate(channels, start=1):
        for bucket in range(3):
            records.append(
                {
                    "channel": channel["label"],
                    "midpoint_seconds": bucket * 60 + 30,
                    "maximum": float(channel_index * (bucket + 1)),
                    "p95": float(channel_index * (bucket + 1) * 0.9),
                }
            )
    return channels, records
