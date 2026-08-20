# Vibraport

**Vibration Data Analysis & Reporting Tool**

Vibraport adalah aplikasi berbasis **Python + Streamlit** untuk mengolah dan menganalisis data getaran hasil monitoring peledakan dari perangkat **Vibracord**.

## Fitur

- Import data **Vibracord ****`.sis`** dan CSV
- Visualisasi waveform 3 channel geophone (Vertikal, Longitudinal, Transversal) + 1 channel air blast overpressure
- Visualisasi dalam grafik **SNI 7571:2023**
- Analisis **PPV, frekuensi, displacement, dan acceleration**
- **FFT / frequency analysis**
- **Signature Hole Analysis (SHA)**
- Simulasi **superposition waveform** dengan delay (opsi scaling USBM)
- PPV attenuation / **scaled-distance regression**
- Safe Zone Prediction + kalkulator isian dan jarak
- Analisis monitoring jangka panjang (**Bargraph**)
- Pembuatan laporan

## Struktur Utama

```text
vibraport/
├── app.py
├── core/
│   ├── sis_parser.py
│   ├── waveform.py
│   ├── fft_analysis.py
│   ├── superposition.py
│   ├── scaling.py
│   ├── delay.py
│   └── metrics.py
├── pages/
│   ├── overview.py
│   ├── signal_analysis.py
│   ├── sha.py
│   ├── ppv_analysis.py
│   ├── monitoring.py
│   └── report.py
└── regression/
    ├── fitting.py
    └── scaled_distance.py
```

## Instalasi

Clone repository:

```bash
git clone https://github.com/muhaliakbar14-cyber/vibraport.git
cd vibraport
```

Buat virtual environment:

Linux/MacOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```
python -m venv .venv
.venv\Scripts\activate
```

Install dependency:

```bash
pip install -r requirements.txt
```

Jalankan aplikasi:

```bash
streamlit run app.py
```

Kemudian buka:

```text
http://localhost:8501
```

## Catatan

Vibraport merupakan **alat bantu analisis engineering**, bukan pengganti alat ukur, prosedur monitoring yang benar, standar/regulasi, atau engineering judgement.

Hasil analisis, terutama simulasi **Signature Hole Analysis** dan prediksi PPV, perlu diinterpretasikan berdasarkan kondisi lapangan dan karakteristik site.

## Repository

[https://github.com/muhaliakbar14-cyber/vibraport](https://github.com/muhaliakbar14-cyber/vibraport)
