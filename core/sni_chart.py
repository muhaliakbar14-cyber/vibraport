# core/sni_chart.py
"""
SNI 7571:2023 compliance chart.

Builds a Plotly figure with:
- 5 step-function limit curves on a log-x axis
- PPV data points plotted as markers per channel/block
- Clear visual separation of all curve segments
"""

import numpy as np
import plotly.graph_objects as go


# ── SNI 7571:2023 Table 4 ──────────────────────────────────────────────────────
# {class: [0-5 Hz limit, 5-20 Hz limit, 20-100 Hz limit]}  (mm/s)
SNI_LIMITS = {
    1: [2,  3,  5],
    2: [3,  5,  7],
    3: [5,  7,  12],
    4: [7,  12, 20],
    5: [12, 24, 40],
}

# X breakpoints (Hz) — start at 1 since log axis can't reach 0
X_START = 1
X_BREAKS = [5, 20]
X_END = 100

# Curve styles — one per class
CURVE_STYLES = {
    1: dict(color='#1565C0', dash='dot'),
    2: dict(color='#2E7D32', dash='dashdot'),
    3: dict(color='#F57F17', dash='dash'),
    4: dict(color='#6A1B9A', dash='longdash'),
    5: dict(color='#B71C1C', dash='solid'),
}

# PPV point styles per channel
PPV_MARKERS = {
    'Transversal':  dict(symbol='cross',       color='#E53935', size=12, line_width=2),
    'Vertical':     dict(symbol='x',           color='#00897B', size=12, line_width=2),
    'Longitudinal': dict(symbol='circle-open', color='#1E88E5', size=12, line_width=2),
    # Block 2 variants
    'Transversal B2':  dict(symbol='cross',       color='#EF9A9A', size=10, line_width=2),
    'Vertical B2':     dict(symbol='x',           color='#26A69A', size=10, line_width=2),
    'Longitudinal B2': dict(symbol='circle-open', color='#90CAF9', size=10, line_width=2),
}


def _build_step_xy(v1, v2, v3):
    """
    Build x, y arrays for a 3-segment step curve on log axis.
    Returns two arrays suitable for go.Scatter.
    """
    x = [X_START, X_BREAKS[0], X_BREAKS[0], X_BREAKS[1], X_BREAKS[1], X_END]
    y = [v1,       v1,          v2,           v2,           v3,          v3]
    return x, y


def build_sni_chart(ppv_points):
    """
    Build and return the SNI 7571:2023 compliance Plotly figure.

    ppv_points: list of dicts with keys:
        {
          'channel': str,   e.g. 'Transversal', 'Vertical B2'
          'ppv':     float, mm/s
          'freq':    float, Hz
          'block':   int,   1 or 2
        }
    """
    fig = go.Figure()

    # ── Limit curves ──────────────────────────────────────────────────────────
    for cls, (v1, v2, v3) in SNI_LIMITS.items():
        x, y = _build_step_xy(v1, v2, v3)
        style = CURVE_STYLES[cls]
        class_desc = {
            1: 'Cl. 1 — Heritage buildings',
            2: 'Cl. 2 — Sensitive buildings',
            3: 'Cl. 3 — Residential buildings',
            4: 'Cl. 4 — Commercial buildings',
            5: 'Cl. 5 — Industrial buildings',
        }
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode='lines',
            name=class_desc[cls],
            line=dict(color=style['color'], dash=style['dash'], width=2),
            hovertemplate=f'<b>Class {cls}</b><br>Freq: %{{x}} Hz<br>Limit: %{{y}} mm/s<extra></extra>',
            showlegend=False,
        ))

        # Class label at right end
        fig.add_annotation(
            x=X_END,
            y=v3,
            xref='x', yref='y',
            text=f' Cl.{cls}',
            showarrow=False,
            font=dict(size=11, color=style['color']),
            xanchor='left',
        )

    # ── PPV data points ────────────────────────────────────────────────────────
    for pt in ppv_points:
        ch      = pt['channel']
        ppv     = pt['ppv']
        freq    = pt['freq']
        block   = pt.get('block', 1)
        marker  = PPV_MARKERS.get(ch, dict(symbol='diamond', color='black', size=10, line_width=2))

        # Compliance: find which class limit is met at this frequency
        seg_idx = 0 if freq < 5 else (1 if freq < 20 else 2)
        compliant_class = None
        for cls in range(1, 6):
            if ppv <= SNI_LIMITS[cls][seg_idx]:
                compliant_class = cls
                break

        compliance_text = f'Compliant Cl.{compliant_class}' if compliant_class else '⚠️ Exceeds Cl.5'
        label = f"Blk{block} {ch}" if block == 2 else ch

        show_legend = ch in ('Vertical', 'Longitudinal', 'Transversal')
        fig.add_trace(go.Scatter(
            x=[freq], y=[ppv],
            mode='markers',
            name=label,
            marker=dict(
                symbol=marker['symbol'],
                color=marker['color'],
                size=marker['size'],
                line=dict(color=marker['color'], width=marker['line_width']),
            ),
            showlegend=show_legend,
            hovertemplate=(
                f'<b>{label}</b><br>'
                f'PPV: {ppv:.3f} mm/s<br>'
                f'Freq: {freq:.1f} Hz<br>'
                f'{compliance_text}<extra></extra>'
            ),
        ))

    # ── Layout ─────────────────────────────────────────────────────────────────
    fig.update_layout(
        xaxis=dict(
            type='log',
            title='Frequency (Hz)',
            range=[np.log10(1), np.log10(200)],
            tickvals=[1, 2, 5, 10, 20, 50, 100],
            ticktext=['1', '2', '5', '10', '20', '50', '100'],
            showgrid=True,
            gridcolor='#eeeeee',
            minor=dict(showgrid=True, gridcolor='#f8f8f8'),
        ),
        yaxis=dict(
            type='log',
            title='PPV (mm/s)',
            range=[np.log10(1), np.log10(100)],
            tickvals=[1, 2, 3, 5, 7, 10, 12, 20, 24, 40, 100],
            ticktext=['1', '2', '3', '5', '7', '10', '12', '20', '24', '40', '100'],
            showgrid=True,
            gridcolor='#eeeeee',
        ),
        height=500,
        hovermode='closest',
        legend=dict(
            orientation='h',
            y=-0.18,
            x=0,
            font=dict(size=10),
        ),
        margin=dict(t=30, b=80, l=70, r=80),
        plot_bgcolor='white',
        paper_bgcolor='white',
    )

    # Vertical reference lines at 5 and 20 Hz
    # add_shape is more reliable than add_vline on log axes
    for xv in [5, 20]:
        fig.add_shape(
            type='line',
            x0=xv, x1=xv,
            y0=1, y1=300,
            xref='x', yref='y',
            line=dict(color='#cccccc', dash='dot', width=1),
        )

    return fig
