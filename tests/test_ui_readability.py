"""Source-level regression checks for the global readability treatment."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_global_ui_styles_enlarge_sidebar_expanders_and_metrics():
    app_source = _source("app.py")

    assert '[data-testid="stSidebar"] [role="radiogroup"] label p' in app_source
    assert ':not(:has(.metis-compact-expander))' in app_source
    assert '[data-testid="stMetricValue"]' in app_source
    assert '.metis-key-result' in app_source


def test_metric_values_keep_the_compact_readable_scale():
    app_source = _source("app.py")
    overview_source = _source("pages/overview.py")

    metric_value_rule = app_source.split('[data-testid="stMetricValue"]', 1)[1].split("}}", 1)[0]
    assert "font-size: 1.9rem" in metric_value_rule
    assert ".metis-prominent-metrics" not in app_source
    assert 'st.metric("Equipment", model)' in overview_source


def test_only_reference_expanders_opt_out_of_larger_content():
    marker = 'class="metis-compact-expander"'

    assert marker in _source("pages/sha.py")
    assert marker in _source("pages/report.py")
    assert sum(
        path.read_text(encoding="utf-8").count(marker)
        for path in (PROJECT_ROOT / "pages").glob("*.py")
    ) == 2


def test_plotly_template_and_signal_axes_use_larger_titles():
    app_source = _source("app.py")
    signal_source = _source("pages/signal_analysis.py")

    assert 'title=dict(font=dict(size=16, color="#20242A"), standoff=10)' in app_source
    assert 'tickfont=dict(size=13)' in app_source
    assert 'title_font=dict(size=16, color="#20242A")' in signal_source
    assert 'title_text=unit' in signal_source


def test_ppv_and_pvs_results_receive_emphasis():
    overview_source = _source("pages/overview.py")
    compliance_source = _source("pages/monitoring_compliance.py")

    assert 'subset=["PPV"]' in overview_source
    assert 'class="metis-key-result"' in overview_source
    assert '"Critical PPV (mm/s)"' in compliance_source
    assert '"font-weight": "700"' in compliance_source


def test_confidence_equation_has_dedicated_emphasis():
    app_source = _source("app.py")
    ppv_source = _source("pages/ppv_analysis.py")

    assert ".metis-confidence-result__equation" in app_source
    assert 'class="metis-confidence-result"' in ppv_source
    assert 'class="metis-confidence-result__equation"' in ppv_source
    assert '**Confidence (95%):**' not in ppv_source
