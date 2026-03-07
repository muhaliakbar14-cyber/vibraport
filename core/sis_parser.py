# core/sis_parser.py
"""
Binary parser for Vibracord .sis files.

Supports:
  - Vibracord DX     (equipment type 3) — data at 0x400, float32, 7 ch
  - Vibracord FX     (equipment type 5) — data at 0x200, int16 scaled, 7 ch
  - Vibracord Gaia   (equipment type 6) — same format as FX
  - Vibracord Tellus (equipment type 7) — data at 0x400, float32, 14 ch

Format references: DX, FX, and Tellus File Maps (confidential, used with permission)
"""

import struct
import numpy as np


# ── Shared lookup tables ───────────────────────────────────────────────────────

EQUIPMENT_TYPES = {
    3: 'Vibracord DX',
    5: 'Vibracord FX',
    6: 'Vibracord Gaia',
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

# Tellus / Gaia transducer codes
TRANSDUCER_TYPES_TE = {
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

# FX / Gaia transducer codes
TRANSDUCER_TYPES_FX = {
    0x00: 'Not connected',
    0x01: 'Geophone without filtering',
    0x02: 'Geophone 4.5 Hz fn',
    0x03: 'Geophone 8.0 Hz fn',
    0x04: 'KBf',
    0x10: 'Accelerometer',
    0x20: 'Microphone linear 2–250 Hz',
    0x25: 'Microphone dBA',
    0x30: 'Hydrophone',
    0x35: 'Extensometer',
}

# DX transducer codes (value + 100 = imperial units variant)
TRANSDUCER_TYPES_DX = {
    0:  'No transducer',
    1:  'Geophone 8 Hz (mm/s)',
    2:  'Geophone 4.5 Hz (mm/s)',
    3:  'Microphone (Pa)',
    4:  'Accelerometer (g)',
    5:  'Accelerometer (m/s²)',
    6:  'Hydrophone (Pa)',
    7:  'Extensometer (mm)',
    101: 'Geophone 8 Hz (in/s)',
    102: 'Geophone 4.5 Hz (in/s)',
    103: 'Microphone (Pa) imperial',
    104: 'Accelerometer (g) imperial',
    105: 'Accelerometer (m/s²) imperial',
    106: 'Hydrophone (Pa) imperial',
    107: 'Extensometer (in) imperial',
}

# DX axis map (0-based, different from Tellus/FX)
AXIS_MAP_DX = {
    0: 'Vertical',
    1: 'Longitudinal',
    2: 'Transverse',
    3: 'Not affected',
}

# Tellus / FX / Gaia axis map
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


def _make_channel_info(i, axes, magnitudes, r, n_ch):
    """Build a single channel_info dict from parsed arrays."""
    return {
        'index':              i + 1,
        'axis':               axes[i],
        'magnitude':          magnitudes[i],
        'type':               r['transducer_type'][i],
        'unit':               r['units'][i] if i < len(r.get('units', [])) else '',
        'trigger':            r['trigger_level'][i] if i < len(r.get('trigger_level', [])) else 0.0,
        'max_amplitude':      r['max_amplitude'][i] if i < len(r.get('max_amplitude', [])) else 0.0,
        'is_virtual':         r['is_virtual'][i] if i < len(r.get('is_virtual', [])) else False,
        'belongs_to_block':   r['belongs_to_block'][i] if i < len(r.get('belongs_to_block', [])) else 1,
        'over_range':         r['over_range'][i] if i < len(r.get('over_range', [])) else False,
        'trigger_used':       r['trigger_used'][i] if i < len(r.get('trigger_used', [])) else False,
        'freq_zero_crossing': r['freq_zero_crossing'][i] if i < len(r.get('freq_zero_crossing', [])) else 0,
        'freq_fft_peak':      r['freq_fft_peak'][i] if i < len(r.get('freq_fft_peak', [])) else 0,
        'freq_energy_25':     r['freq_energy_25'][i] if i < len(r.get('freq_energy_25', [])) else 0,
        'freq_energy_50':     r['freq_energy_50'][i] if i < len(r.get('freq_energy_50', [])) else 0,
        'freq_energy_75':     r['freq_energy_75'][i] if i < len(r.get('freq_energy_75', [])) else 0,
    }


# ── Main entry point ───────────────────────────────────────────────────────────

def parse_sis(file_bytes: bytes) -> dict:
    """
    Parse a Vibracord .sis binary file.

    Detects model from equipment type byte at 0x2C and routes to the
    appropriate internal parser. All parsers return the same dict structure.
    """
    d = file_bytes
    equipment_type = d[0x2C]

    if equipment_type == 3:
        return _parse_dx(d)
    elif equipment_type in (5, 6):
        return _parse_fx(d)
    else:
        return _parse_tellus(d)  # type 7 (Tellus) and unknown — default


# ── Tellus parser ──────────────────────────────────────────────────────────────

def _parse_tellus(d: bytes) -> dict:
    """Vibracord Tellus (type 7). Data at 0x400, float32, up to 14 channels."""
    r = {}

    # ── 0x00–0x05 : Record Date & Time ────────────────────────────────────────
    r['rec_day']    = d[0x00]
    r['rec_month']  = d[0x01]
    r['rec_year']   = d[0x02] + 2000
    r['rec_hour']   = d[0x03]
    r['rec_minute'] = d[0x04]
    r['rec_second'] = d[0x05]
    r['date'] = f"{r['rec_day']:02d}/{r['rec_month']:02d}/{r['rec_year']}"
    r['time'] = f"{r['rec_hour']:02d}:{r['rec_minute']:02d}:{r['rec_second']:02d}"

    # ── 0x06–0x08 : Calibration Date ──────────────────────────────────────────
    r['cal_day']   = d[0x06]
    r['cal_month'] = d[0x07]
    r['cal_year']  = d[0x08] + 2000
    r['cal_date']  = f"{r['cal_day']:02d}/{r['cal_month']:02d}/{r['cal_year']}"

    # ── 0x09 : Record Type ────────────────────────────────────────────────────
    r['is_waveform'] = (d[0x09] == 1)
    r['record_type'] = 'Waveform' if r['is_waveform'] else 'Bargraph'

    # ── 0x0A–0x0B : Pretrigger (ms) ───────────────────────────────────────────
    r['pretrigger_ms'] = struct.unpack('<h', d[0x0A:0x0C])[0]

    # ── 0x0C–0x0D : Sampling Period ───────────────────────────────────────────
    r['sampling_rate'] = struct.unpack('<h', d[0x0C:0x0E])[0]

    # ── 0x20–0x23 : Record Length (seconds) ───────────────────────────────────
    r['record_length_s'] = struct.unpack('<l', d[0x20:0x24])[0]

    # ── 0x24 : Number of Active Channels ──────────────────────────────────────
    r['num_channels'] = d[0x24]

    # ── 0x2C : Equipment Type ─────────────────────────────────────────────────
    r['equipment_type'] = EQUIPMENT_TYPES.get(d[0x2C], f'Unknown (type {d[0x2C]})')

    # ── 0x30–0x3F : Serial Number ─────────────────────────────────────────────
    r['serial_number'] = _read_cstring(d[0x30:0x40])

    # ── 0x40–0x9F : Notes 1–3 ─────────────────────────────────────────────────
    r['note1'] = _read_cstring(d[0x40:0x60])
    r['note2'] = _read_cstring(d[0x60:0x80])
    r['note3'] = _read_cstring(d[0x80:0xA0])

    # ── 0xA0–0xA7 : Waveform Start Time (uint64, seconds × 10000) ─────────────
    r['start_time_s'] = struct.unpack('<Q', d[0xA0:0xA8])[0] / 10000.0

    # ── 0xA8–0xAA : Bargraph End Time ─────────────────────────────────────────
    r['bargraph_end_time'] = (d[0xA8], d[0xA9], d[0xAA])

    # ── 0xAB : Clock Source ───────────────────────────────────────────────────
    r['clock_source'] = CLOCK_SOURCES.get(d[0xAB], f'Unknown ({d[0xAB]})')

    # ── 0xB0–0xB6 : Geophone Test Results ─────────────────────────────────────
    r['geophone_test'] = [
        GEOPHONE_TEST_RESULTS.get(d[0xB0 + i], f'Unknown ({d[0xB0 + i]})')
        for i in range(7)
    ]

    # ── 0xC0–0xC7 : GPS Longitude / Latitude ──────────────────────────────────
    r['longitude'] = struct.unpack('<f', d[0xC0:0xC4])[0]
    r['latitude']  = struct.unpack('<f', d[0xC4:0xC8])[0]
    r['gps_source'] = GPS_SOURCES.get(d[0xC8], f'Unknown ({d[0xC8]})')

    # ── 0xC9–0xCC : Over Range / Trigger Used Flags ────────────────────────────
    r['over_range']   = _read_bit_flags(struct.unpack('<H', d[0xC9:0xCB])[0], 14)
    r['trigger_used'] = _read_bit_flags(struct.unpack('<H', d[0xCB:0xCD])[0], 14)

    # ── 0xD0–0xDD : Decimal Points per Channel (14 x char) ────────────────────
    r['decimal_points'] = [d[0xD0 + i] for i in range(14)]

    # ── 0x100–0x10D : Transducer Type (14 x char) ─────────────────────────────
    r['transducer_type'] = [
        TRANSDUCER_TYPES_TE.get(d[0x100 + i], f'Unknown (0x{d[0x100 + i]:02X})')
        for i in range(14)
    ]

    # ── 0x110–0x11D : Axis / 0x120–0x12D : Magnitude (14 x char each) ─────────
    axes, magnitudes = [], []
    for i in range(14):
        axes.append(AXIS_MAP.get(d[0x110 + i], f'Unknown (0x{d[0x110 + i]:02X})'))
        mag_byte = d[0x120 + i]
        is_rms   = bool(mag_byte & 0x80)
        mag_str  = MAGNITUDE_MAP.get(mag_byte & 0x7F, f'Unknown (0x{mag_byte & 0x7F:02X})')
        magnitudes.append(f"{mag_str}{' RMS' if is_rms else ''}")

    r['transducer_axis']      = axes
    r['transducer_magnitude'] = magnitudes

    # ── 0x130–0x16F : Trigger Level (14 x float) ──────────────────────────────
    r['trigger_level'] = [
        struct.unpack('<f', d[0x130 + i*4 : 0x134 + i*4])[0]
        for i in range(14)
    ]

    # ── 0x170–0x17D : Belongs to Block (14 x char) ────────────────────────────
    r['belongs_to_block'] = [d[0x170 + i] for i in range(14)]

    # ── 0x17E–0x17F : Virtual Channel Flags ───────────────────────────────────
    r['is_virtual'] = _read_bit_flags(struct.unpack('<H', d[0x17E:0x180])[0], 14)

    # ── 0x180–0x1BF : Max Amplitude (14 x float) ──────────────────────────────
    r['max_amplitude'] = [
        struct.unpack('<f', d[0x180 + i*4 : 0x184 + i*4])[0]
        for i in range(14)
    ]

    # ── 0x1C0–0x1DF : Zero Crossing Frequency (14 x int) ──────────────────────
    r['freq_zero_crossing'] = [
        struct.unpack('<h', d[0x1C0 + i*2 : 0x1C2 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x200–0x23F : FFT Peak (14 x int) ─────────────────────────────────────
    r['freq_fft_peak'] = [
        struct.unpack('<h', d[0x200 + i*2 : 0x202 + i*2])[0]
        for i in range(14)
    ]

    # ── 0x240–0x27F / 0x280–0x2BF / 0x2C0–0x2FF : FFT Energy (14 x int each) ─
    r['freq_energy_25'] = [struct.unpack('<h', d[0x240 + i*2 : 0x242 + i*2])[0] for i in range(14)]
    r['freq_energy_50'] = [struct.unpack('<h', d[0x280 + i*2 : 0x282 + i*2])[0] for i in range(14)]
    r['freq_energy_75'] = [struct.unpack('<h', d[0x2C0 + i*2 : 0x2C2 + i*2])[0] for i in range(14)]

    # ── 0x300–0x31F : Vector Sum (4 x float + 4 x long) ──────────────────────
    vs_raw  = [struct.unpack('<f', d[0x300 + i*4 : 0x304 + i*4])[0] for i in range(4)]
    vs_time = [struct.unpack('<l', d[0x310 + i*4 : 0x314 + i*4])[0] for i in range(4)]
    r['vector_sum'] = {
        'ch1_3':   vs_raw[0]  if vs_raw[0]  >= 0 else None,
        'ch4_6':   vs_raw[1]  if vs_raw[1]  >= 0 else None,
        'ch8_10':  vs_raw[2]  if vs_raw[2]  >= 0 else None,
        'ch11_13': vs_raw[3]  if vs_raw[3]  >= 0 else None,
    }
    r['vector_sum_time'] = {
        'ch1_3': vs_time[0], 'ch4_6': vs_time[1],
        'ch8_10': vs_time[2], 'ch11_13': vs_time[3],
    }

    # ── 0x320–0x3FF : Unit Strings (14 x 16 char) ─────────────────────────────
    r['units'] = [_read_cstring(d[0x320 + i*16 : 0x330 + i*16]) for i in range(14)]

    # ── channel_info ───────────────────────────────────────────────────────────
    r['channel_info'] = [_make_channel_info(i, axes, magnitudes, r, 14) for i in range(14)]

    # ── 0x400 : Binary Record Data ────────────────────────────────────────────
    num_ch  = r['num_channels']
    sps     = r['sampling_rate']
    rec_len = r['record_length_s']

    if r['is_waveform']:
        n_samples = sps * rec_len
        waveform  = {}
        for i in range(num_ch):
            ch_start = 0x400 + i * n_samples * 4
            samples  = struct.unpack(f'<{n_samples}f', d[ch_start : ch_start + n_samples * 4])
            ch       = r['channel_info'][i]
            waveform[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = np.array(samples, dtype=np.float32)
        r['waveform']  = waveform
        r['time_axis'] = np.arange(n_samples) / sps

    else:
        n_bars   = struct.unpack('<H', d[0x20:0x22])[0]
        bargraph = {}
        offset   = 0x400
        for i in range(num_ch):
            amps  = np.array([struct.unpack_from('<f', d, offset + j*6)[0]     for j in range(n_bars)], dtype=np.float32)
            freqs = np.array([struct.unpack_from('<H', d, offset + j*6 + 4)[0] for j in range(n_bars)], dtype=np.uint16)
            offset += n_bars * 6
            ch = r['channel_info'][i]
            bargraph[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = {'amplitude': amps, 'frequency': freqs}
        r['bargraph_vs'] = np.frombuffer(d[offset : offset + n_bars*4], dtype='<f4').copy()
        r['bargraph']    = bargraph
        r['time_axis']   = np.arange(n_bars) * sps

    return r


# ── FX / Gaia parser ───────────────────────────────────────────────────────────

def _parse_fx(d: bytes) -> dict:
    """Vibracord FX (type 5) and Gaia (type 6). Data at 0x200, int16 scaled, 7 channels."""
    r = {}

    # ── 0x00–0x08 : Dates (same as Tellus) ────────────────────────────────────
    r['rec_day']    = d[0x00];  r['rec_month']  = d[0x01]
    r['rec_year']   = d[0x02] + 2000
    r['rec_hour']   = d[0x03];  r['rec_minute'] = d[0x04];  r['rec_second'] = d[0x05]
    r['date'] = f"{r['rec_day']:02d}/{r['rec_month']:02d}/{r['rec_year']}"
    r['time'] = f"{r['rec_hour']:02d}:{r['rec_minute']:02d}:{r['rec_second']:02d}"

    r['cal_day']   = d[0x06];  r['cal_month'] = d[0x07]
    r['cal_year']  = d[0x08] + 2000
    r['cal_date']  = f"{r['cal_day']:02d}/{r['cal_month']:02d}/{r['cal_year']}"

    # ── 0x09 : Record Type ────────────────────────────────────────────────────
    r['is_waveform'] = (d[0x09] == 1)
    r['record_type'] = 'Waveform' if r['is_waveform'] else 'Bargraph'

    # ── 0x0A–0x0D : Pretrigger / Sampling Rate ────────────────────────────────
    r['pretrigger_ms'] = struct.unpack('<h', d[0x0A:0x0C])[0]
    r['sampling_rate'] = struct.unpack('<h', d[0x0C:0x0E])[0]

    # ── 0x20–0x23 : Record Length ─────────────────────────────────────────────
    r['record_length_s'] = struct.unpack('<l', d[0x20:0x24])[0]

    # ── 0x24 : Number of Channels ─────────────────────────────────────────────
    r['num_channels'] = d[0x24]

    # ── 0x2C : Equipment Type ─────────────────────────────────────────────────
    r['equipment_type'] = EQUIPMENT_TYPES.get(d[0x2C], f'Unknown (type {d[0x2C]})')

    # ── 0x30–0x3F : Serial Number ─────────────────────────────────────────────
    r['serial_number'] = _read_cstring(d[0x30:0x40])

    # ── 0x40–0xAF : Notes 1–3 (note 3 is 48 bytes UTF-8) ─────────────────────
    r['note1'] = _read_cstring(d[0x40:0x60])
    r['note2'] = _read_cstring(d[0x60:0x80])
    r['note3'] = _read_cstring(d[0x80:0xB0])

    # ── 0xA0–0xAC : KBf(Tm) values (3 x float, within note 3 range) ───────────
    r['kbf_tm'] = [struct.unpack('<f', d[0xA0 + i*4 : 0xA4 + i*4])[0] for i in range(3)]

    # ── 0xB0–0xB6 : Geophone Test Results ─────────────────────────────────────
    r['geophone_test'] = [
        GEOPHONE_TEST_RESULTS.get(d[0xB0 + i], f'Unknown ({d[0xB0 + i]})')
        for i in range(7)
    ]

    # FX / Gaia has no GPS or clock source fields
    r['gps_source']        = 'Not set'
    r['latitude']          = None
    r['longitude']         = None
    r['clock_source']      = 'Internal'
    r['bargraph_end_time'] = (0, 0, 0)
    r['start_time_s']      = 0.0

    # ── 0x100–0x106 : Transducer Type (7 x char) ──────────────────────────────
    r['transducer_type'] = [
        TRANSDUCER_TYPES_FX.get(d[0x100 + i], f'Unknown (0x{d[0x100 + i]:02X})')
        for i in range(7)
    ]

    # ── 0x108–0x10E : Axis / 0x110–0x116 : Magnitude (7 x char each) ──────────
    axes      = [AXIS_MAP.get(d[0x108 + i], f'Unknown (0x{d[0x108 + i]:02X})') for i in range(7)]
    magnitudes = [MAGNITUDE_MAP.get(d[0x110 + i], f'Unknown (0x{d[0x110 + i]:02X})') for i in range(7)]
    r['transducer_axis']      = axes
    r['transducer_magnitude'] = magnitudes

    # ── 0x118–0x11E : Decimal Points (7 x char) ───────────────────────────────
    r['decimal_points'] = [d[0x118 + i] for i in range(7)]

    # ── 0x120–0x13C : Trigger Level (7 x float) ───────────────────────────────
    r['trigger_level'] = [struct.unpack('<f', d[0x120 + i*4 : 0x124 + i*4])[0] for i in range(7)]

    # ── 0x13D / 0x13E : Over Range / Trigger Used (bit flags) ─────────────────
    r['over_range']   = _read_bit_flags(d[0x13D], 7)
    r['trigger_used'] = _read_bit_flags(d[0x13E], 7)

    # ── 0x140–0x15C : Peak Value (7 x float) ──────────────────────────────────
    r['max_amplitude'] = [struct.unpack('<f', d[0x140 + i*4 : 0x144 + i*4])[0] for i in range(7)]

    # ── 0x160–0x16D : FFT Peak (7 x int) ──────────────────────────────────────
    r['freq_fft_peak'] = [struct.unpack('<h', d[0x160 + i*2 : 0x162 + i*2])[0] for i in range(7)]

    # ── 0x170–0x17D / 0x180–0x18D / 0x190–0x19D : FFT Energy (7 x int each) ──
    r['freq_energy_25'] = [struct.unpack('<h', d[0x170 + i*2 : 0x172 + i*2])[0] for i in range(7)]
    r['freq_energy_50'] = [struct.unpack('<h', d[0x180 + i*2 : 0x182 + i*2])[0] for i in range(7)]
    r['freq_energy_75'] = [struct.unpack('<h', d[0x190 + i*2 : 0x192 + i*2])[0] for i in range(7)]

    # ── 0x1A0–0x1AD : Zero Crossing Frequency (7 x int) ───────────────────────
    r['freq_zero_crossing'] = [struct.unpack('<h', d[0x1A0 + i*2 : 0x1A2 + i*2])[0] for i in range(7)]

    # ── 0x1B0–0x1BF : Vector Sum (2 x float + 2 x long) ──────────────────────
    vs_b1 = struct.unpack('<f', d[0x1B0:0x1B4])[0]
    vs_b2 = struct.unpack('<f', d[0x1B4:0x1B8])[0]
    r['vector_sum'] = {
        'ch1_3':   vs_b1 if vs_b1 >= 0 else None,
        'ch4_6':   vs_b2 if vs_b2 >= 0 else None,
        'ch8_10':  None,
        'ch11_13': None,
    }
    r['vector_sum_time'] = {
        'ch1_3':   struct.unpack('<l', d[0x1B8:0x1BC])[0],
        'ch4_6':   struct.unpack('<l', d[0x1BC:0x1C0])[0],
        'ch8_10':  0,
        'ch11_13': 0,
    }

    # ── 0x1C0–0x1F7 : Unit Strings (7 x 8 char) ───────────────────────────────
    r['units'] = [_read_cstring(d[0x1C0 + i*8 : 0x1C8 + i*8]) for i in range(7)]

    # FX has no block assignment or virtual channel fields
    r['belongs_to_block'] = [1] * 7
    r['is_virtual']       = [False] * 7

    # ── channel_info ───────────────────────────────────────────────────────────
    r['channel_info'] = [_make_channel_info(i, axes, magnitudes, r, 7) for i in range(7)]

    # ── 0x200 : Binary Record Data ────────────────────────────────────────────
    num_ch  = r['num_channels']
    sps     = r['sampling_rate']
    rec_len = r['record_length_s']

    if r['is_waveform']:
        # FX/Gaia waveform: interleaved int16 per sample
        # Layout: [ch0, ch1, ch2, ..., chN, ch0, ch1, ...]
        n_samples = sps * rec_len
        all_raw   = np.frombuffer(d[0x200 : 0x200 + n_samples * num_ch * 2], dtype='<i2').astype(np.float32)
        waveform  = {}
        for i in range(num_ch):
            scale = 10.0 ** (-r['decimal_points'][i])
            ch    = r['channel_info'][i]
            waveform[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = all_raw[i::num_ch] * scale
        r['waveform']  = waveform
        r['time_axis'] = np.arange(n_samples) / sps

    else:
        # Interleaved per sample: [ch0_peak(i16), ch0_freq(i16), ch1_peak(i16), ch1_freq(i16), ...]
        n_bars           = rec_len
        bytes_per_sample = num_ch * 4
        bargraph         = {}
        for i in range(num_ch):
            scale = 10.0 ** (-r['decimal_points'][i])
            amps  = np.array([
                struct.unpack_from('<h', d, 0x200 + j * bytes_per_sample + i*4)[0] * scale
                for j in range(n_bars)
            ], dtype=np.float32)
            freqs = np.array([
                struct.unpack_from('<h', d, 0x200 + j * bytes_per_sample + i*4 + 2)[0]
                for j in range(n_bars)
            ], dtype=np.int16)
            ch = r['channel_info'][i]
            bargraph[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = {'amplitude': amps, 'frequency': freqs}
        r['bargraph_vs'] = np.array([])
        r['bargraph']    = bargraph
        r['time_axis']   = np.arange(n_bars) * sps

    return r


# ── DX parser ─────────────────────────────────────────────────────────────────

def _parse_dx(d: bytes) -> dict:
    """Vibracord DX (type 3). Data at 0x400, float32, 7 channels."""
    r = {}

    # ── 0x00–0x08 : Dates ─────────────────────────────────────────────────────
    r['rec_day']    = d[0x00];  r['rec_month']  = d[0x01]
    r['rec_year']   = d[0x02] + 2000
    r['rec_hour']   = d[0x03];  r['rec_minute'] = d[0x04];  r['rec_second'] = d[0x05]
    r['date'] = f"{r['rec_day']:02d}/{r['rec_month']:02d}/{r['rec_year']}"
    r['time'] = f"{r['rec_hour']:02d}:{r['rec_minute']:02d}:{r['rec_second']:02d}"
    
    r['cal_day']   = d[0x06];  r['cal_month'] = d[0x07]
    r['cal_year']  = d[0x08] + 2000
    r['cal_date']  = f"{r['cal_day']:02d}/{r['cal_month']:02d}/{r['cal_year']}"

    # ── 0x09 : Record Type ────────────────────────────────────────────────────
    # DX: 0=Normal, 1=KBf/Monitor, 2=Monitor
    r['is_waveform'] = (d[0x09] == 0)
    r['record_type'] = 'Waveform' if r['is_waveform'] else 'Bargraph'

    # ── 0x0A–0x0B : Serial Number (unsigned short, not C string) ──────────────
    r['serial_number'] = str(struct.unpack('<H', d[0x0A:0x0C])[0])

    # ── 0x2C : Equipment Type ─────────────────────────────────────────────────
    r['equipment_type'] = EQUIPMENT_TYPES.get(d[0x2C], f'Unknown (type {d[0x2C]})')

    # ── 0x40–0x9F : Notes 1–3 (32 x char each) ────────────────────────────────
    r['note1'] = _read_cstring(d[0x40:0x60])
    r['note2'] = _read_cstring(d[0x60:0x80])
    r['note3'] = _read_cstring(d[0x80:0xA0])

    # ── 0xB1–0xB7 : Decimal Points (7 x char) ─────────────────────────────────
    r['decimal_points'] = [d[0xB1 + i] for i in range(7)]

    # ── 0xC0 : Number of Channels ─────────────────────────────────────────────
    r['num_channels'] = d[0xC0]

    # ── 0xD0–0xD1 : Record Length (int, seconds) ──────────────────────────────
    r['record_length_s'] = struct.unpack('<h', d[0xD0:0xD2])[0]

    # ── 0xD2–0xD3 : Pretrigger (ms) ───────────────────────────────────────────
    r['pretrigger_ms'] = struct.unpack('<h', d[0xD2:0xD4])[0]

    # ── 0xD4–0xD5 : Sampling Rate (SPS) ───────────────────────────────────────
    r['sampling_rate'] = struct.unpack('<h', d[0xD4:0xD6])[0]

    # ── 0xE0–0xFF : Trigger Level (7 x float) ─────────────────────────────────
    r['trigger_level'] = [struct.unpack('<f', d[0xE0 + i*4 : 0xE4 + i*4])[0] for i in range(7)]

    # ── 0x100–0x106 : Trigger Used (7 x char) ─────────────────────────────────
    r['trigger_used'] = [bool(d[0x100 + i]) for i in range(7)]

    # ── 0x120–0x126 : Transducer Type (7 x unsigned char) ─────────────────────
    r['transducer_type'] = [
        TRANSDUCER_TYPES_DX.get(d[0x120 + i], f'Unknown ({d[0x120 + i]})')
        for i in range(7)
    ]

    # ── 0x130–0x136 : Transducer Axis (7 x char) ──────────────────────────────
    axes = [AXIS_MAP_DX.get(d[0x130 + i], f'Unknown ({d[0x130 + i]})') for i in range(7)]
    r['transducer_axis'] = axes

    # DX doesn't store magnitude separately — derive from transducer type byte
    def _dx_magnitude(type_byte):
        t = type_byte % 100  # strip imperial flag
        if t in (1, 2): return 'Velocity'
        if t in (3, 6): return 'Pressure'
        if t in (4, 5): return 'Acceleration'
        if t == 7:      return 'Length'
        return 'Velocity'
    magnitudes = [_dx_magnitude(d[0x120 + i]) for i in range(7)]
    r['transducer_magnitude'] = magnitudes

    # ── 0x140–0x146 : Over Range (7 x char) ───────────────────────────────────
    r['over_range'] = [bool(d[0x140 + i]) for i in range(7)]

    # ── 0x150–0x156 : Geophone Test (7 x char, 0=Fault 1=OK) ──────────────────
    r['geophone_test'] = [
        'OK' if d[0x150 + i] == 1 else 'Fault'
        for i in range(7)
    ]

    # ── 0x180–0x18D : FFT Peak (7 x int) ──────────────────────────────────────
    r['freq_fft_peak'] = [struct.unpack('<h', d[0x180 + i*2 : 0x182 + i*2])[0] for i in range(7)]

    # ── 0x190 / 0x1A0 / 0x1B0 / 0x1C0 : FFT Energy & ZC (7 x int each) ───────
    # Monitor mode map has ZC at 0x180, FFT Peak at 0x190 — waveform map is used here
    r['freq_zero_crossing'] = [struct.unpack('<h', d[0x180 + i*2 : 0x182 + i*2])[0] for i in range(7)]
    r['freq_energy_25']     = [struct.unpack('<h', d[0x1A0 + i*2 : 0x1A2 + i*2])[0] for i in range(7)]
    r['freq_energy_50']     = [struct.unpack('<h', d[0x1B0 + i*2 : 0x1B2 + i*2])[0] for i in range(7)]
    r['freq_energy_75']     = [struct.unpack('<h', d[0x1C0 + i*2 : 0x1C2 + i*2])[0] for i in range(7)]

    # ── 0x1D0–0x1EC : Peak Value (7 x float) ──────────────────────────────────
    r['max_amplitude'] = [struct.unpack('<f', d[0x1D0 + i*4 : 0x1D4 + i*4])[0] for i in range(7)]

    # ── 0x1F0–0x1FF : Vector Sum (2 x float + 2 x float for time) ─────────────
    vs_b1 = struct.unpack('<f', d[0x1F0:0x1F4])[0]
    vs_b2 = struct.unpack('<f', d[0x1F4:0x1F8])[0]
    r['vector_sum'] = {
        'ch1_3':   vs_b1 if vs_b1 >= 0 else None,
        'ch4_6':   vs_b2 if vs_b2 >= 0 else None,
        'ch8_10':  None,
        'ch11_13': None,
    }
    r['vector_sum_time'] = {
        'ch1_3':   struct.unpack('<f', d[0x1F8:0x1FC])[0],
        'ch4_6':   struct.unpack('<f', d[0x1FC:0x200])[0],
        'ch8_10':  0,
        'ch11_13': 0,
    }

    # DX has no GPS, clock source, unit strings, block assignment, virtual channels
    r['gps_source']        = 'Not set'
    r['latitude']          = None
    r['longitude']         = None
    r['clock_source']      = 'Internal'
    r['bargraph_end_time'] = (0, 0, 0)
    r['start_time_s']      = 0.0
    r['units']             = [''] * 7
    r['belongs_to_block']  = [1] * 7
    r['is_virtual']        = [False] * 7

    # ── channel_info ───────────────────────────────────────────────────────────
    r['channel_info'] = [_make_channel_info(i, axes, magnitudes, r, 7) for i in range(7)]

    # ── 0x400 : Binary Record Data ────────────────────────────────────────────
    num_ch  = r['num_channels']
    sps     = r['sampling_rate']
    rec_len = r['record_length_s']

    if r['is_waveform']:
        n_samples = sps * rec_len
        waveform  = {}
        for i in range(num_ch):
            ch_start = 0x400 + i * n_samples * 4
            samples  = struct.unpack(f'<{n_samples}f', d[ch_start : ch_start + n_samples * 4])
            ch       = r['channel_info'][i]
            waveform[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = np.array(samples, dtype=np.float32)
        r['waveform']  = waveform
        r['time_axis'] = np.arange(n_samples) / sps

    else:
        # Sequential per channel, float32, one value per 2 seconds, no frequency
        # Total bars = record_length_s / 2
        n_bars   = rec_len // 2
        bargraph = {}
        for i in range(num_ch):
            ch_start = 0x400 + i * n_bars * 4
            amps     = np.frombuffer(d[ch_start : ch_start + n_bars * 4], dtype='<f4').copy()
            freqs    = np.zeros(n_bars, dtype=np.uint16)  # DX does not store frequency
            ch       = r['channel_info'][i]
            bargraph[f"Ch{i+1}_{ch['axis']}_{ch['magnitude']}"] = {'amplitude': amps, 'frequency': freqs}
        r['bargraph_vs'] = np.array([])
        r['bargraph']    = bargraph
        r['time_axis']   = np.arange(n_bars) * 2  # 2 seconds per bar

    return r