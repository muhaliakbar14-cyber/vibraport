# Project Overview

## Name
Vibraport

## Goal
Provide mining and vibration practitioners with a reliable Streamlit application for importing Vibracord recordings, inspecting waveforms and derived signals, performing blast/attenuation analyses, assessing structural-vibration compliance, and producing professional PDF reports.

## Current Direction
- Streamlit-first application in `app.py`.
- `.sis` and waveform `.csv` support.
- Local/offline browser workflow first; online deployment remains possible later.
- Shared compliance engine for SNI 7571:2023, DIN 4150-3:2016, and BS 7385-2:1993.
- Professional, field-usable reports with consistent calculations between the UI and PDF output.

## Product Principles
- Formula and standards correctness before feature breadth.
- One shared implementation for calculations used in multiple pages.
- Clear assumptions and `REVIEW` states where a standard cannot safely become a simple automatic pass/fail check.
- Verify important work with automated tests, live UI interaction, and rendered-output inspection.

## Deferred Work
- Authentication, cloud project storage, and SaaS deployment.
- A native Windows executable; the current local/offline mode uses Streamlit in a local browser.
