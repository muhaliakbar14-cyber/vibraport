# Latest Handoff (2026-08-20)

## Where We Are
- The app is a Streamlit-first Vibraport app in `app.py`.
- `.sis` and `.csv` upload support is restored.
- `Print Report` is restored and routed through `pages/report.py`.
- "📐 Math Analysis" removed (Signal Analysis fully superseded it). Nav is
  now 6 pages: Data Overview, Signal Analysis, Signature Hole Analysis,
  Attenuation & Safe Zone, Bargraph Monitoring, Print Report.
- Signature Hole Analysis now supports optional USBM charge-weight/
  distance amplitude scaling — see `core/scaling.py` and Step 2 on the
  SHA page (**note:** scaling is now Step 2, blast design params are
  Step 3 — swapped from the original order; see decisions.md for why).
  6 inputs: Signature Hole Charge Weight, Signature Hole Distance, Field
  Constant (B), Blast Pattern Distance, and either a single Blast Pattern
  Charge Weight (uniform mode) or a per-hole weight table with dynamic
  add/remove rows (no artificial row cap). No K input — it cancels out
  algebraically for this specific scale-factor computation; explained
  with the derivation in the page's "About USBM Scaling" panel.
- **Fixed — orphaned-module pattern found and resolved twice this session:**
  both `pages/sha.py` and `pages/overview.py` existed but were never
  imported by `app.py`, which had its own independent inline
  implementations of each. Consolidated both onto their `pages/*.py`
  versions:
  - SHA: `pages/sha.py` now has Step 1 ported from the tested inline
    version, `st.form`-wrapped Steps 2/2.5/3, frequency-band analysis,
    and the new scaling feature.
  - Data Overview: `pages/overview.py` is now live — richer recording
    info (SIS/CSV-aware), per-channel/block measurement table with
    transducer+test status, and the **SNI 7571:2023 compliance chart**
    (plots this recording's actual PPV against building-class limit
    curves) that the inline version never had.
  - Audited `app.py`'s import line against every file in `pages/` —
    everything is now wired in (`report, ppv_analysis, monitoring,
    signal_analysis, sha, overview`). No further orphans found.
  - See `decisions.md` 2026-08-20 entries for full detail on both.

## Immediate Direction
- Keep Streamlit as the primary implementation path.
- Plan for server deployment later, after the Streamlit UX and feature parity feel right.
- Before starting any new page/feature, re-check `ls pages/*.py` against `app.py`'s import line as a matter of habit — this pattern has recurred twice now.

## Current Scope
- Preserve `.sis` parsing and the report flow.
- Improve responsiveness and reduce blinking without abandoning Streamlit.
- Ignore the earlier offline desktop and Supabase branches unless the direction changes again.
