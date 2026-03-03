# core/sis_parser.py
"""
Binary parser for Vibracord Tellus .sis files.

Physical concept: The .sis file is a proprietary binary format produced by
Vibracord seismographs. It contains a structured header (metadata, channel
configuration, device-computed analysis) followed by raw waveform or bargraph
amplitude data starting at byte offset 0x400.

Format reference: Vibracord Tellus File Map (confidential, used with permission)
"""

import struct
import numpy as np


# ── Lookup tables ──────────────────────────────────────────────────────────────

EQUIPMENT_TYPES = {
    7: 'Vibracord Tellus',
}

CLOCK_SOURCES = {
    0: 'Internal',
    1: 'NTP',
    2: 'GPS',
}

GEOPHONE_TEST_RESULTS = {
    0: 'Fault',
    1: 'OK',
    2: 'Not performed',
}

GPS_SOURCES = {
    0: 'Not set',
    1: 'GPS',
    2: 'Manual',
}

TRANSDUCER_TYPES = {
    0x00: 'Not used',
    0x01: 'Raw Geophone',
    0x02: 'Geophone 4.5 Hz fn (1–315 Hz)',
    0x03: 'Geophone 4.5 Hz fn (1–80 Hz)',
    0x04: 'Geophone 8.0 Hz fn (2–250 Hz)',
    0x10: 'Accelerometer',
    0x20: 'Microphone linear 2–250 Hz',
    0x25: 'Microphone dBA',
    0x30: 'Hydrophone',
    0x35: 'Extensometer',
    0xA0: 'Kbf',
}

AXIS_MAP = {
    0x00: 'Not affected',
    0x01: 'Vertical',
    0x02: 'Longitudinal',
    0x03: 'Transverse',
    0x04: 'X',
    0x05: 'Y',
    0x06: 'Z',
}

MAGNITUDE_MAP = {
    0x00: 'Velocity',
    0x01: 'Acceleration',
    0x02: 'Pressure',
    0x03: 'Voltage',
    0x04: 'KBf',
    0x05: 'Length',
    0x06: 'Displacement',
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_cstring(buf: bytes) -> str:
    """Read a null-terminated ASCII/UTF-8 string from a byte buffer."""
    null_pos = buf.find(0x00)
    if null_pos == -1:
        null_pos = len(buf)
    return buf[:null_pos].decode('utf-8', errors='replace')


def _read_bit_flags(flags: int, n: int) -> list:
    """Unpack n bits from an integer into a list of booleans."""
    return [bool(flags & (1 << i)) for i in range(n)]


# ── Main parser ────────────────────────────────────────────────────────────────

def parse_sis(file_bytes: bytes) -> dict:
    """
    Parse a Vibracord Tellus .sis binary file.

    Args:
        file_bytes — raw bytes of the .sis file

    Returns:
        dict with keys:
            metadata      — recording info (datetime, device, GPS, notes, etc.)
            channel_info  — list of 14 dicts describing each channel
            waveform      — dict of {label: np.ndarray} (Waveform mode only)
            bargraph      — dict of {label: {amplitude, frequency}} (Bargraph mode only)
            time_axis     — np.ndarray of time values in seconds
            is_waveform   — bool
            sampling_rate — int (sps for Waveform, seconds/bar for Bargraph)
    """
    d = file_bytes
    r = {}

    # ── 0x00–0x05 : Record Date & Time ────────────────────────────────────────
    r['rec_day']    = d[0x00]
    r['rec_month']  = d[0x01]
    r['rec_year']   = d[0x02] + 2000
    r['rec_hour']   = d[0x03]
    r['rec_minute'] = d[0x04]
    r['rec_second'] = d[0x05]
    r['datetime']   = (
        f"{r['rec_day']:02d}/{r['rec_month']:02d}/{r['rec_year']} "
        f"{r['rec_hour']:02d}:{r['rec_minute']:02d}:{r['rec_second']:02d}"
    )

    # ── 0x06–0x08 : Calibration Date ──────────────────────────────────────────
    r['cal_day']   = d[0x06]
    r['cal_month'] = d[0x07]
    r['cal_year']  = d[0x08] + 2000
    r['cal_date']  = f"{r['cal_day']:02d}/{r['cal_month']:02d}/{r['cal_year']}"

    # ── 0x09 : Record Type ────────────────────────────────────────────────────
    record_type        = d[0x09]
    r['is_waveform']   = (record_type == 1)
    r['record_type']   = 'Waveform' if r['is_waveform'] else 'Bargraph'

    # ── 0x0A–0x0B : Pretrigger (ms) ───────────────────────────────────────────
    r['pretrigger_ms'] = struct.unpack('<h', d[0x0A:0x0C])[0]

    # ── 0x0C–0x0D : Sampling Period ───────────────────────────────────────────
    # Waveform mode: samples per second (sps)
    # Bargraph mode: seconds per bar (interval)
    r['sampling_rate'] = struct.unpack('<h', d[0x0C:0x0E])[0]

    # ── 0x0E–0x0F : Reserved ──────────────────────────────────────────────────

    # ── 0x10–0x1F : Checksum ──────────────────────────────────────────────────
    # Device integrity check — skipped (not needed for parsing)

    # ── 0x20–0x23 : Record Length (seconds) ───────────────────────────────────
    r['record_length_s'] = struct.unpack('<l', d[0x20:0x24])[0]

    # ── 0x24 : Number of Active Channels ──────────────────────────────────────
    r['num_channels'] = d[0x24]

    # ── 0x25–0x2B : Reserved ──────────────────────────────────────────────────

    # ── 0x2C : Equipment Type ─────────────────────────────────────────────────
    r['equipment_type'] = EQUIPMENT_TYPES.get(d[0x2C], f'Unknown (type {d[0x2C]})')

    # ── 0x2D–0x2F : Reserved ──────────────────────────────────────────────────

    # ── 0x30–0x3F : Serial Number (C string, 16 bytes max) ────────────────────
    r['serial_number'] = _read_cstring(d[0x30:0x40])

    # ── 0x40–0x9F : Notes 1–3 (C strings, 32 bytes each) ─────────────────────
    r['note1'] = _read_cstring(d[0x40:0x60])
    r['note2'] = _read_cstring(d[0x60:0x80])
    r['note3'] = _read_cstring(d[0x80:0xA0])

    # ── 0xA0–0xA7 : Waveform Start Time (uint64, seconds × 10000) ─────────────
    # Precision = 1/10th of a millisecond
    # Assumed to be seconds since midnight based on consistency with datetime field
    start_raw        = struct.unpack('<Q', d[0xA0:0xA8])[0]
    r['start_time_s'] = start_raw / 10000.0

    # ── 0xA8–0xAA : Bargraph End Time (hour, minute, second) ──────────────────
    r['bargraph_end_time'] = (d[0xA8], d[0xA9], d[0xAA])

    # ── 0xAB : Clock Source ───────────────────────────────────────────────────
    r['clock_source'] = CLOCK_SOURCES.get(d[0xAB], f'Unknown ({d[0xAB]})')

    # ── 0xAC–0xAF : Reserved ──────────────────────────────────────────────────

    # ── 0xB0–0xB6 : Geophone Test Results (7 physical channels) ───────────────
    r['geophone_test'] = [
        GEOPHONE_TEST_RESULTS.get(d[0xB0 + i], f'Unknown ({d[0xB0 + i]})')
        for i in range(7)
    ]

    # ── 0xB7–0xBD : Unknown ───────────────────────────────────────────────────
    # ── 0xBE–0xBF : Reserved ──────────────────────────────────────────────────

    # ── 0xC0–0xC3 : Longitude (float) ─────────────────────────────────────────
    r['longitude'] = struct.unpack('<f', d[0xC0:0xC4])[0]

    # ── 0xC4–0xC7 : Latitude (float) ──────────────────────────────────────────
    r['latitude'] = struct.unpack('<f', d[0xC4:0xC8])[0]

    # ── 0xC8 : GPS Coordinate Source ──────────────────────────────────────────
    r['gps_source'] = GPS_SOURCES.get(d[0xC8], f'Unknown ({d[0xC8]})')

    # ── 0xC9–0xCA : Over Range Flags (1 bit per channel) ──────────────────────
    r['over_range'] = _read_bit_flags(struct.unpack('<H', d[0xC9:0xCB])[0], 14)

    # ── 0xCB–0xCC : Trigger Used Flags (1 bit per channel) ────────────────────
    r['trigger_used'] = _read_bit_flags(struct.unpack('<H', d[0xCB:0xCD])[0], 14)

    # ── 0xCD–0xCF : Reserved ──────────────────────────────────────────────────

    # ── 0xD0–0xDD : Decimal Points per Channel (14 x char) ────────────────────
    r['decimal_points'] = [d[0xD0 + i] for i in range(14)]

    # ── 0xDE–0xFF : Reserved ──────────────────────────────────────────────────

    # ── 0x100–0x10D : Transducer Type (14 x char) ─────────────────────────────
    r['transducer_type'] = [
        TRANSDUCER_TYPES.get(d[0x100 + i], f'Unknown (0x{d[0x100 + i]:02X})')
        for i in range(14)
    ]

    # ── 0x10E–0x10F : Reserved ────────────────────────────────────────────────

    # ── 0x110–0x11D : Transducer Axis (14 x char) ─────────────────────────────
    # ── 0x120–0x12D : Transducer Magnitude (14 x char, MSB = RMS flag) ────────
    axes       = []
    magnitudes = []
    for i in range(14):
        axes.append(AXIS_MAP.get(d[0x110 + i], f'Unknown (0x{d[0x110 + i]:02X})'))
        mag_byte = d[0x120 + i]
        is_rms   = bool(mag_byte & 0x80)
        mag_type = mag_byte & 0x7F
        mag_str  = MAGNITUDE_MAP.get(mag_type, f'Unknown (0x{mag_type:02X})')
        magnitudes.append(f"{mag_str}{' RMS' if is_rms else ''}")

    r['transducer_axis']      = axes
    r['transducer_magnitude'] = magnitudes

    # ── 0x130–0x16F : Trigger Level per Channel (14 x float) ──────────────────
    r['trigger_level'] = [
        struct.unpack('<f', d[0x130 + i*4 : 0x134 + i*4])[0]
        for i in range(14)
    ]

    # ── 0x170–0x17D : Belongs to Block (14 x char, 0=No, 1=Yes) ──────────────
    r['belongs_to_block'] = [d[0x170 + i] for i in range(14)]

    # ── 0x17E–0x17F : Virtual Channel Flags (int, 1 bit per channel) ──────────
    r['is_virtual'] = _read_bit_flags(struct.unpack('<H', d[0x17E:0x180])[0], 14)

    # ── 0x180–0x1BF : Maximum Amplitude per Channel (14 x float) ──────────────
    r['max_amplitude'] = [
        struct.unpack('<f', d[0x180 + i*4 : 0x184 + i*4])[0]
        for i in range(14)
    ]

    # ── 0x1C0–0x1DF : Frequency Zero Crossing per Channel (14 x int) ──────────
    r['freq_zero_crossing'] = [
        struct.unpack('<h', d[0x1C0 + i*2 : 0x1C2 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x200–0x23F : FFT Peak per Channel (14 x int) ─────────────────────────
    r['freq_fft_peak'] = [
        struct.unpack('<h', d[0x200 + i*2 : 0x202 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x240–0x27F : FFT 25% Energy per Channel (14 x int) ───────────────────
    r['freq_energy_25'] = [
        struct.unpack('<h', d[0x240 + i*2 : 0x242 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x280–0x2BF : FFT 50% Energy per Channel (14 x int) ───────────────────
    r['freq_energy_50'] = [
        struct.unpack('<h', d[0x280 + i*2 : 0x282 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x2C0–0x2FF : FFT 75% Energy per Channel (14 x int) ───────────────────
    # Also used as KBf(Tm) values in Bargraph mode
    r['freq_energy_75'] = [
        struct.unpack('<h', d[0x2C0 + i*2 : 0x2C2 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x300–0x30F : Vector Sum Peak Values (4 x float) ──────────────────────
    # Groups: Ch1-3, Ch4-6, Ch8-10, Ch11-13 — <0 means not performed
    vs_raw = [struct.unpack('<f', d[0x300 + i*4 : 0x304 + i*4])[0] for i in range(4)]
    r['vector_sum'] = {
        'ch1_3':   vs_raw[0] if vs_raw[0] >= 0 else None,
        'ch4_6':   vs_raw[1] if vs_raw[1] >= 0 else None,
        'ch8_10':  vs_raw[2] if vs_raw[2] >= 0 else None,
        'ch11_13': vs_raw[3] if vs_raw[3] >= 0 else None,
    }

    # ── 0x310–0x31F : Vector Sum Time (4 x long) ──────────────────────────────
    # Waveform: sample index from first sample
    # Bargraph: seconds from midnight
    vs_time = [struct.unpack('<l', d[0x310 + i*4 : 0x314 + i*4])[0] for i in range(4)]
    r['vector_sum_time'] = {
        'ch1_3':   vs_time[0],
        'ch4_6':   vs_time[1],
        'ch8_10':  vs_time[2],
        'ch11_13': vs_time[3],
    }

    # ── 0x320–0x3FF : Unit Strings per Channel (14 x 16 char, UTF8 C string) ──
    r['units'] = [
        _read_cstring(d[0x320 + i*16 : 0x330 + i*16])
        for i in range(14)
    ]

    # ── Build channel_info ─────────────────────────────────────────────────────
    # Convenience structure combining all per-channel metadata
    r['channel_info'] = [
        {
            'index':         i + 1,
            'axis':          axes[i],
            'magnitude':     magnitudes[i],
            'type':          r['transducer_type'][i],
            'unit':          r['units'][i],
            'trigger':       r['trigger_level'][i],
            'max_amplitude': r['max_amplitude'][i],
            'is_virtual':    r['is_virtual'][i],
            'belongs_to_block': r['belongs_to_block'][i],
            'over_range':    r['over_range'][i],
            'trigger_used':  r['trigger_used'][i],
            'freq_zero_crossing': r['freq_zero_crossing'][i],
            'freq_fft_peak':      r['freq_fft_peak'][i],
            'freq_energy_25':     r['freq_energy_25'][i],
            'freq_energy_50':     r['freq_energy_50'][i],
            'freq_energy_75':     r['freq_energy_75'][i],
        }
        for i in range(14)
    ]

    # ── 0x400 : Binary Record Data ────────────────────────────────────────────
    num_ch    = r['num_channels']
    sps       = r['sampling_rate']
    rec_len   = r['record_length_s']
    n_samples = sps * rec_len

    if r['is_waveform']:
        # All samples for Ch1, then all for Ch2, etc.
        waveform = {}
        for i in range(num_ch):
            ch_start = 0x400 + i * n_samples * 4
            ch_end   = ch_start + n_samples * 4
            samples  = struct.unpack(f'<{n_samples}f', d[ch_start:ch_end])
            ch       = r['channel_info'][i]
            label    = f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"
            waveform[label] = np.array(samples, dtype=np.float32)
        r['waveform']   = waveform
        r['time_axis']  = np.arange(n_samples) / sps

    else:
        # Bargraph layout (confirmed from binary inspection):
        # n_bars is at 0x20 (u16), NOT derived from sps * rec_len
        # Per channel, all bars are stored sequentially:
        #   [amp_f32, freq_u16] * n_bars  (6 bytes per bar)
        # After all channels: vector sum amplitudes [f32] * n_bars
        n_bars = struct.unpack('<H', d[0x20:0x22])[0]

        bargraph = {}
        offset   = 0x400
        for i in range(num_ch):
            amps  = np.array([
                struct.unpack_from('<f', d, offset + j*6)[0]
                for j in range(n_bars)
            ], dtype=np.float32)
            freqs = np.array([
                struct.unpack_from('<H', d, offset + j*6 + 4)[0]
                for j in range(n_bars)
            ], dtype=np.uint16)
            offset += n_bars * 6
            ch    = r['channel_info'][i]
            label = f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"
            bargraph[label] = {
                'amplitude':  amps,
                'frequency':  freqs,
            }

        # Vector sum amplitudes after all channels
        vs_amps = np.frombuffer(d[offset : offset + n_bars*4], dtype='<f4').copy()
        r['bargraph_vs'] = vs_amps

        r['bargraph']  = bargraph
        r['time_axis'] = np.arange(n_bars) * sps  # sps = seconds per bar

    return r
