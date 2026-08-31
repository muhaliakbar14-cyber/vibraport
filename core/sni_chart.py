"""Backward-compatible SNI chart imports.

New code should import from :mod:`core.compliance`. This wrapper keeps older
call sites and third-party imports working while Vibraport transitions to the
multi-standard compliance engine.
"""

from core.compliance import SNI_LIMITS, build_compliance_chart
from core.compliance.chart import PPV_MARKERS


def build_sni_chart(ppv_points, selected_class=None, compact=False):
    return build_compliance_chart(
        ppv_points=ppv_points,
        standard_id="sni_7571_2023",
        assessment="short_term",
        selected_category=int(selected_class or 3),
        compact=compact,
    )


__all__ = ["PPV_MARKERS", "SNI_LIMITS", "build_sni_chart"]
