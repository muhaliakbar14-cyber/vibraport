"""Domain helpers for long-term bargraph monitoring records.

The SIS parsers expose the instrument payload faithfully.  This module adds a
small normalized layer for the monitoring UI so that a bar is never confused
with a raw waveform sample.  It also owns display-only downsampling and
full-resolution descriptive statistics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.compliance import evaluate_point


_AXIS_NAMES = {
    "Transverse": "Transversal",
    "Transversal": "Transversal",
}

_DEFAULT_UNITS = {
    "Velocity": "mm/s",
    "Acceleration": "m/s²",
    "Pressure": "Pa",
    "KBf": "KBf",
    "Length": "mm",
    "Displacement": "mm",
    "Voltage": "V",
}


@dataclass(frozen=True)
class BargraphChannel:
    """Normalized description of one instrument bargraph channel."""

    index: int
    axis: str
    label: str
    magnitude: str
    quantity: str
    statistic: str
    unit: str
    amplitude_column: str
    frequency_column: str | None
    frequency_available: bool
    transducer_type: str
    sample_count: int
    over_range: bool
    is_virtual: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MonitoringEvent:
    """One grouped operational-threshold event from full-resolution bars."""

    channel: str
    quantity: str
    unit: str
    severity: str
    start_index: int
    end_index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    interval_count: int
    exceedance_intervals: int
    peak: float
    peak_index: int
    peak_seconds: float
    frequency_at_peak: float | None
    yellow_threshold: float
    red_threshold: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MonitoringCompliancePoint:
    """One full-resolution bargraph interval evaluated against a PPV limit."""

    channel: str
    interval_index: int
    time_seconds: float
    ppv: float
    frequency_hz: float
    limit: float | None
    utilization_percent: float | None
    status: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MonitoringTrendBin:
    """One time bucket calculated from original bargraph intervals."""

    channel: str
    quantity: str
    statistic: str
    unit: str
    start_seconds: float
    end_seconds: float
    midpoint_seconds: float
    interval_count: int
    valid_count: int
    maximum: float | None
    mean: float | None
    median: float | None
    p95: float | None
    p99: float | None
    frequency_at_max: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_monitoring_interval(
    time_axis: np.ndarray | list[float], fallback: float | None = None
) -> float | None:
    """Return the median positive interval in seconds for a bargraph axis."""

    times = np.asarray(time_axis, dtype=float)
    if times.size > 1:
        differences = np.diff(times)
        valid = differences[np.isfinite(differences) & (differences > 0)]
        if valid.size:
            return float(np.median(valid))
    if fallback is not None and np.isfinite(fallback) and fallback > 0:
        return float(fallback)
    return None


def _quantity_from_magnitude(magnitude: str) -> str:
    cleaned = magnitude.replace(" RMS", "").strip()
    return cleaned or "Unknown"


def _display_axis(axis: str, quantity: str) -> str:
    if axis == "Not affected" and quantity == "Pressure":
        return "Pressure"
    return _AXIS_NAMES.get(axis, axis or "Unknown")


def build_bargraph_channel_metadata(parser_result: dict) -> list[dict[str, Any]]:
    """Build serializable normalized channel metadata from a SIS parser result."""

    channel_info = parser_result.get("channel_info", [])
    normalized: list[dict[str, Any]] = []

    for position, (base_name, data) in enumerate(parser_result.get("bargraph", {}).items()):
        info = channel_info[position] if position < len(channel_info) else {}
        index = int(info.get("index", position + 1))
        magnitude = str(info.get("magnitude", "Unknown"))
        quantity = _quantity_from_magnitude(magnitude)
        axis = _display_axis(str(info.get("axis", "Unknown")), quantity)
        statistic = "RMS" if "RMS" in magnitude.upper() else "Interval peak"
        unit = str(info.get("unit", "") or _DEFAULT_UNITS.get(quantity, ""))
        amplitudes = np.asarray(data.get("amplitude", []))
        frequencies = np.asarray(data.get("frequency", []))
        frequency_available = bool(
            frequencies.size and np.any(np.isfinite(frequencies) & (frequencies > 0))
        )
        frequency_column = f"{base_name}_frequency" if frequencies.size else None

        normalized.append(
            BargraphChannel(
                index=index,
                axis=axis,
                label=f"{axis} (Ch{index})",
                magnitude=magnitude,
                quantity=quantity,
                statistic=statistic,
                unit=unit,
                amplitude_column=f"{base_name}_amplitude",
                frequency_column=frequency_column,
                frequency_available=frequency_available,
                transducer_type=str(info.get("type", "Unknown")),
                sample_count=int(amplitudes.size),
                over_range=bool(info.get("over_range", False)),
                is_virtual=bool(info.get("is_virtual", False)),
            ).to_dict()
        )

    return normalized


def legacy_bargraph_channel_metadata(columns: list[str]) -> list[dict[str, Any]]:
    """Infer a conservative model for older cached data without normalized metadata."""

    column_set = set(columns)
    normalized: list[dict[str, Any]] = []
    for amplitude_column in columns:
        if not amplitude_column.endswith("_amplitude"):
            continue
        base_name = amplitude_column[: -len("_amplitude")]
        parts = base_name.split("_", 2)
        if len(parts) != 3:
            continue
        channel_name, raw_axis, magnitude = parts
        try:
            index = int(channel_name.removeprefix("Ch"))
        except ValueError:
            index = len(normalized) + 1
        quantity = _quantity_from_magnitude(magnitude)
        axis = _display_axis(raw_axis, quantity)
        frequency_column = f"{base_name}_frequency"
        normalized.append(
            BargraphChannel(
                index=index,
                axis=axis,
                label=f"{axis} (Ch{index})",
                magnitude=magnitude,
                quantity=quantity,
                statistic="RMS" if "RMS" in magnitude.upper() else "Interval peak",
                unit=_DEFAULT_UNITS.get(quantity, ""),
                amplitude_column=amplitude_column,
                frequency_column=frequency_column if frequency_column in column_set else None,
                frequency_available=frequency_column in column_set,
                transducer_type="Unknown",
                sample_count=0,
                over_range=False,
                is_virtual=False,
            ).to_dict()
        )
    return normalized


def get_bargraph_channels(df, metadata: dict | None = None) -> list[dict[str, Any]]:
    """Return usable normalized channels, with compatibility fallback."""

    metadata = metadata or {}
    channels = metadata.get("Bargraph channels") or legacy_bargraph_channel_metadata(
        list(df.columns)
    )
    return [
        dict(channel)
        for channel in channels
        if channel.get("amplitude_column") in df.columns
    ]


def ppv_compliance_eligibility(channel: dict[str, Any]) -> tuple[bool, str]:
    """Return whether a normalized bargraph channel stores interval-peak PPV."""

    if str(channel.get("quantity", "")).casefold() != "velocity":
        return False, "Only velocity channels can be assessed as PPV."
    if str(channel.get("statistic", "")).casefold() != "interval peak":
        return False, "Only interval-peak bars are eligible; RMS is a different metric."
    unit = str(channel.get("unit", "")).replace(" ", "").casefold()
    if unit not in {"mm/s", "mm/sec", "mms-1", "mm·s⁻¹"}:
        return False, "PPV assessment requires velocity in mm/s."
    if not channel.get("amplitude_column"):
        return False, "The amplitude column is unavailable."
    return True, "Eligible interval-peak velocity channel."


def evaluate_bargraph_ppv(
    df,
    time_values: np.ndarray | list[float],
    channels: list[dict[str, Any]],
    standard_id: str,
    assessment: str,
    category_id: int,
) -> list[dict[str, Any]]:
    """Evaluate every eligible, finite interval using the shared compliance engine.

    Dominant frequency is preserved interval by interval. Missing, non-finite,
    or zero frequency is passed to the shared evaluator as zero and therefore
    produces REVIEW; this function never substitutes or estimates frequency.
    """

    times = np.asarray(time_values, dtype=float)
    records: list[dict[str, Any]] = []

    for channel in channels:
        eligible, _ = ppv_compliance_eligibility(channel)
        if not eligible:
            continue

        amplitude_column = channel["amplitude_column"]
        if amplitude_column not in df.columns:
            continue
        amplitudes = df[amplitude_column].to_numpy(dtype=float)
        frequency_column = channel.get("frequency_column")
        frequencies = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else np.empty(0, dtype=float)
        )

        for index, raw_ppv in enumerate(amplitudes):
            if not np.isfinite(raw_ppv):
                continue
            frequency = frequencies[index] if index < frequencies.size else 0.0
            if not np.isfinite(frequency) or frequency <= 0:
                frequency = 0.0
            point = {
                "channel": channel["label"],
                "ppv": abs(float(raw_ppv)),
                "freq": float(frequency),
            }
            result = evaluate_point(point, standard_id, assessment, category_id)
            limit = result.limit
            utilization = (
                result.ppv / limit * 100
                if limit is not None and limit > 0
                else None
            )
            time_seconds = (
                float(times[index])
                if index < times.size and np.isfinite(times[index])
                else float(index)
            )
            records.append(
                MonitoringCompliancePoint(
                    channel=result.channel,
                    interval_index=index,
                    time_seconds=time_seconds,
                    ppv=result.ppv,
                    frequency_hz=result.frequency_hz,
                    limit=result.limit,
                    utilization_percent=utilization,
                    status=result.status,
                    note=result.note,
                ).to_dict()
            )

    return records


def summarize_channel(
    amplitude: np.ndarray | list[float],
    frequency: np.ndarray | list[float] | None = None,
) -> dict[str, Any]:
    """Calculate descriptive statistics from the complete channel series."""

    values = np.asarray(amplitude, dtype=float)
    valid_mask = np.isfinite(values)
    valid_values = values[valid_mask]
    summary: dict[str, Any] = {
        "sample_count": int(values.size),
        "valid_count": int(valid_values.size),
        "invalid_count": int(values.size - valid_values.size),
        "maximum": None,
        "minimum": None,
        "mean": None,
        "median": None,
        "p95": None,
        "p99": None,
        "peak_index": None,
        "frequency_at_peak": None,
    }
    if not valid_values.size:
        return summary

    valid_indices = np.flatnonzero(valid_mask)
    peak_index = int(valid_indices[int(np.argmax(valid_values))])
    summary.update(
        maximum=float(np.max(valid_values)),
        minimum=float(np.min(valid_values)),
        mean=float(np.mean(valid_values)),
        median=float(np.median(valid_values)),
        p95=float(np.percentile(valid_values, 95)),
        p99=float(np.percentile(valid_values, 99)),
        peak_index=peak_index,
    )

    if frequency is not None:
        frequencies = np.asarray(frequency, dtype=float)
        if peak_index < frequencies.size:
            peak_frequency = frequencies[peak_index]
            if np.isfinite(peak_frequency) and peak_frequency > 0:
                summary["frequency_at_peak"] = float(peak_frequency)
    return summary


def aggregate_monitoring_trends(
    df,
    time_values: np.ndarray | list[float],
    channels: list[dict[str, Any]],
    bucket_seconds: float,
    *,
    interval_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Aggregate original bargraph intervals into elapsed-time trend buckets.

    The output includes distribution statistics of the stored interval values;
    for example, P95 is the 95th percentile of interval peaks inside a bucket,
    not a percentile reconstructed from the unavailable raw waveform.
    """

    if not np.isfinite(bucket_seconds) or bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be greater than zero")

    times = np.asarray(time_values, dtype=float)
    if not times.size:
        return []
    finite_times = times[np.isfinite(times)]
    if not finite_times.size:
        return []

    inferred_interval = infer_monitoring_interval(times, fallback=interval_seconds)
    interval = float(inferred_interval) if inferred_interval else float(bucket_seconds)
    anchor = float(finite_times[0])
    recording_end = float(finite_times[-1] + interval)
    native_buckets = bucket_seconds <= interval * (1 + 1e-9)
    records: list[dict[str, Any]] = []

    for channel in channels:
        amplitude_column = channel.get("amplitude_column")
        if not amplitude_column or amplitude_column not in df.columns:
            continue
        amplitudes = df[amplitude_column].to_numpy(dtype=float)
        if amplitudes.size != times.size:
            raise ValueError("Time and amplitude arrays must have the same length")
        frequency_column = channel.get("frequency_column")
        frequencies = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else np.empty(0, dtype=float)
        )

        if native_buckets:
            for index, (time_value, amplitude) in enumerate(zip(times, amplitudes)):
                if not np.isfinite(time_value):
                    continue
                valid = bool(np.isfinite(amplitude))
                value = float(amplitude) if valid else None
                frequency_at_max = None
                if valid and index < frequencies.size:
                    frequency = frequencies[index]
                    if np.isfinite(frequency) and frequency > 0:
                        frequency_at_max = float(frequency)
                end_seconds = min(float(time_value + interval), recording_end)
                records.append(
                    MonitoringTrendBin(
                        channel=channel["label"],
                        quantity=channel["quantity"],
                        statistic=channel["statistic"],
                        unit=channel["unit"],
                        start_seconds=float(time_value),
                        end_seconds=end_seconds,
                        midpoint_seconds=float((time_value + end_seconds) / 2),
                        interval_count=1,
                        valid_count=int(valid),
                        maximum=value,
                        mean=value,
                        median=value,
                        p95=value,
                        p99=value,
                        frequency_at_max=frequency_at_max,
                    ).to_dict()
                )
            continue

        finite_time_mask = np.isfinite(times)
        bucket_indices = np.full(times.size, -1, dtype=int)
        bucket_indices[finite_time_mask] = np.floor(
            (times[finite_time_mask] - anchor) / bucket_seconds
        ).astype(int)

        for bucket_index in np.unique(bucket_indices[bucket_indices >= 0]):
            positions = np.flatnonzero(bucket_indices == bucket_index)
            segment = amplitudes[positions]
            finite_positions = np.flatnonzero(np.isfinite(segment))
            start_seconds = anchor + float(bucket_index) * bucket_seconds
            end_seconds = min(start_seconds + bucket_seconds, recording_end)
            if not finite_positions.size:
                maximum = mean = median = p95 = p99 = None
                frequency_at_max = None
            else:
                valid_values = segment[finite_positions]
                peak_local = int(finite_positions[int(np.argmax(valid_values))])
                peak_index = int(positions[peak_local])
                maximum = float(np.max(valid_values))
                mean = float(np.mean(valid_values))
                median = float(np.median(valid_values))
                p95 = float(np.percentile(valid_values, 95))
                p99 = float(np.percentile(valid_values, 99))
                frequency_at_max = None
                if peak_index < frequencies.size:
                    frequency = frequencies[peak_index]
                    if np.isfinite(frequency) and frequency > 0:
                        frequency_at_max = float(frequency)

            records.append(
                MonitoringTrendBin(
                    channel=channel["label"],
                    quantity=channel["quantity"],
                    statistic=channel["statistic"],
                    unit=channel["unit"],
                    start_seconds=float(start_seconds),
                    end_seconds=float(end_seconds),
                    midpoint_seconds=float((start_seconds + end_seconds) / 2),
                    interval_count=int(positions.size),
                    valid_count=int(finite_positions.size),
                    maximum=maximum,
                    mean=mean,
                    median=median,
                    p95=p95,
                    p99=p99,
                    frequency_at_max=frequency_at_max,
                ).to_dict()
            )

    return records


def detect_threshold_events(
    time_values: np.ndarray | list[float],
    amplitude: np.ndarray | list[float],
    *,
    channel: str,
    quantity: str,
    unit: str,
    yellow_threshold: float,
    red_threshold: float | None = None,
    frequency: np.ndarray | list[float] | None = None,
    interval_seconds: float | None = None,
    gap_tolerance_seconds: float = 0.0,
    hysteresis: float = 0.0,
    minimum_duration_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    """Group operational threshold exceedances into chronological events.

    An event starts at the yellow threshold and stays active while values remain
    above the release threshold. Shorter drops can be bridged with
    gap_tolerance_seconds. The returned peak and frequency always come from the
    original, full-resolution arrays.
    """

    times = np.asarray(time_values, dtype=float)
    values = np.asarray(amplitude, dtype=float)
    if times.size != values.size:
        raise ValueError("Time and amplitude arrays must have the same length")
    if yellow_threshold <= 0:
        raise ValueError("yellow_threshold must be greater than zero")
    if gap_tolerance_seconds < 0:
        raise ValueError("gap_tolerance_seconds cannot be negative")
    if hysteresis < 0:
        raise ValueError("hysteresis cannot be negative")
    if minimum_duration_seconds < 0:
        raise ValueError("minimum_duration_seconds cannot be negative")
    if not times.size:
        return []

    interval = interval_seconds or infer_monitoring_interval(times)
    interval = float(interval) if interval and interval > 0 else 0.0
    release_threshold = max(0.0, yellow_threshold - hysteresis)
    effective_red = (
        float(red_threshold)
        if red_threshold is not None and red_threshold > yellow_threshold
        else None
    )
    frequencies = (
        np.asarray(frequency, dtype=float) if frequency is not None else None
    )
    events: list[dict[str, Any]] = []
    start_index: int | None = None
    last_qualifying_index: int | None = None

    def close_event(end_index: int) -> None:
        if start_index is None:
            return
        segment = values[start_index : end_index + 1]
        finite_positions = np.flatnonzero(np.isfinite(segment))
        if not finite_positions.size:
            return
        finite_values = segment[finite_positions]
        local_peak_position = int(
            finite_positions[int(np.argmax(finite_values))]
        )
        peak_index = start_index + local_peak_position
        peak = float(values[peak_index])
        duration = float(times[end_index] - times[start_index] + interval)
        if duration < minimum_duration_seconds:
            return
        peak_frequency = None
        if frequencies is not None and peak_index < frequencies.size:
            candidate = frequencies[peak_index]
            if np.isfinite(candidate) and candidate > 0:
                peak_frequency = float(candidate)
        exceedance_intervals = int(
            np.sum(np.isfinite(segment) & (segment >= yellow_threshold))
        )
        events.append(
            MonitoringEvent(
                channel=channel,
                quantity=quantity,
                unit=unit,
                severity=(
                    "Red"
                    if effective_red is not None and peak >= effective_red
                    else "Yellow"
                ),
                start_index=start_index,
                end_index=end_index,
                start_seconds=float(times[start_index]),
                end_seconds=float(times[end_index]),
                duration_seconds=duration,
                interval_count=end_index - start_index + 1,
                exceedance_intervals=exceedance_intervals,
                peak=peak,
                peak_index=peak_index,
                peak_seconds=float(times[peak_index]),
                frequency_at_peak=peak_frequency,
                yellow_threshold=float(yellow_threshold),
                red_threshold=effective_red,
            ).to_dict()
        )

    for index, (time_value, amplitude_value) in enumerate(zip(times, values)):
        finite = np.isfinite(time_value) and np.isfinite(amplitude_value)
        if start_index is None:
            if finite and amplitude_value >= yellow_threshold:
                start_index = index
                last_qualifying_index = index
            continue

        if finite and amplitude_value >= release_threshold:
            last_qualifying_index = index
            continue

        assert last_qualifying_index is not None
        gap_duration = (
            float(time_value - times[last_qualifying_index])
            if np.isfinite(time_value)
            else float("inf")
        )
        if gap_duration <= gap_tolerance_seconds:
            continue

        close_event(last_qualifying_index)
        start_index = None
        last_qualifying_index = None
        if finite and amplitude_value >= yellow_threshold:
            start_index = index
            last_qualifying_index = index

    if start_index is not None and last_qualifying_index is not None:
        close_event(last_qualifying_index)

    return events


def detect_events_for_channels(
    df,
    time_values: np.ndarray | list[float],
    channels: list[dict[str, Any]],
    thresholds: dict[str, tuple[float, float]],
    *,
    interval_seconds: float | None = None,
    gap_tolerance_seconds: float = 0.0,
    hysteresis_percent: float = 0.0,
    minimum_duration_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    """Detect and merge events for all threshold-eligible channels."""

    all_events: list[dict[str, Any]] = []
    for channel in channels:
        limits = thresholds.get(channel["quantity"])
        if not limits:
            continue
        yellow_threshold, red_threshold = limits
        if yellow_threshold <= 0:
            continue
        frequency_column = channel.get("frequency_column")
        frequency = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else None
        )
        events = detect_threshold_events(
            time_values,
            df[channel["amplitude_column"]].to_numpy(dtype=float),
            channel=channel["label"],
            quantity=channel["quantity"],
            unit=channel["unit"],
            yellow_threshold=yellow_threshold,
            red_threshold=red_threshold,
            frequency=frequency,
            interval_seconds=interval_seconds,
            gap_tolerance_seconds=gap_tolerance_seconds,
            hysteresis=yellow_threshold * hysteresis_percent / 100,
            minimum_duration_seconds=minimum_duration_seconds,
        )
        all_events.extend(events)

    return sorted(
        all_events,
        key=lambda event: (
            event["start_seconds"],
            event["channel"],
            event["end_seconds"],
        ),
    )


def peak_preserving_downsample(
    time_values: np.ndarray | list[float],
    amplitude: np.ndarray | list[float],
    max_points: int = 1800,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce a display series while retaining each bucket's minimum and maximum.

    This function is for visualization only.  Engineering calculations must use
    the original arrays.
    """

    times = np.asarray(time_values, dtype=float)
    values = np.asarray(amplitude, dtype=float)
    if times.size != values.size:
        raise ValueError("Time and amplitude arrays must have the same length")
    if max_points < 4:
        raise ValueError("max_points must be at least 4")
    if times.size <= max_points:
        return times.copy(), values.copy()

    bucket_count = max(1, (max_points - 2) // 2)
    edges = np.linspace(0, times.size, bucket_count + 1, dtype=int)
    selected: set[int] = {0, times.size - 1}

    for start, end in zip(edges[:-1], edges[1:]):
        if end <= start:
            continue
        segment = values[start:end]
        finite_positions = np.flatnonzero(np.isfinite(segment))
        if not finite_positions.size:
            selected.add(start)
            continue
        finite_values = segment[finite_positions]
        selected.add(start + int(finite_positions[int(np.argmin(finite_values))]))
        selected.add(start + int(finite_positions[int(np.argmax(finite_values))]))

    indices = np.asarray(sorted(selected), dtype=int)
    return times[indices], values[indices]
