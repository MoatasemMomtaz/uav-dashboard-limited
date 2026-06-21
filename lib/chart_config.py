"""Plotly chart export configuration helper.

v0.8.34b+c: pre-configures Plotly's built-in modeBar (the floating tool
strip on the top-right of every chart) so the camera-icon download
produces high-DPI PNGs with sensible filenames.

Two ways to use this:

1. Per-call config (preferred when the chart has a meaningful name):

    from lib.chart_config import chart_config
    st.plotly_chart(fig, use_container_width=True,
                    config=chart_config("wingspan-vs-mtow"))

2. Drop-in `apply_default_export_config()` at the top of a page that
   patches every subsequent st.plotly_chart call so a default config
   is auto-injected when none is provided. Useful for pages with many
   small charts (Overview, UAV Profile).

    from lib.chart_config import apply_default_export_config
    apply_default_export_config("dataset-overview")
    # ... all st.plotly_chart calls now get a 2x PNG export by default
"""
from datetime import date
import re
import streamlit as st


def _sanitize_filename(name: str) -> str:
    """Convert any string into a safe filename component."""
    # Replace spaces and special chars with dashes; keep alphanumerics
    name = re.sub(r"[^\w\s-]", "", name.lower())
    name = re.sub(r"[-\s]+", "-", name).strip("-")
    return name or "chart"


def chart_config(chart_name: str = "chart",
                  scale: int = 2,
                  format: str = "png") -> dict:
    """Build a Plotly `config` dict that:
    - keeps the modeBar always visible (so the download button is
      discoverable, not hidden until hover)
    - configures PNG export at 2x resolution by default (slide-deck-grade)
    - sets a filename like 'wingspan-vs-mtow_2026-06-18.png'

    Parameters
    ----------
    chart_name : str
        Short descriptive name used in the saved filename. Auto-sanitized.
    scale : int
        Image upscale factor. 2 = retina; 3 = print-grade; 1 = on-screen size.
    format : str
        'png' (default), 'svg', 'jpeg', or 'webp'.
    """
    safe_name = _sanitize_filename(chart_name)
    today = date.today().isoformat()
    return {
        # Always show the modeBar so the download icon is visible
        "displayModeBar": True,
        # Remove tools that aren't useful for our charts to reduce clutter
        "modeBarButtonsToRemove": [
            "lasso2d", "select2d", "autoScale2d", "toggleSpikelines",
            "hoverClosestCartesian", "hoverCompareCartesian",
        ],
        # Configure the download-image button
        "toImageButtonOptions": {
            "format": format,
            "filename": f"{safe_name}_{today}",
            "scale": scale,
        },
        # Hide the small Plotly logo since it shrinks the modeBar
        "displaylogo": False,
    }


def apply_default_export_config(page_name: str,
                                  scale: int = 2,
                                  format: str = "png"):
    """Patch st.plotly_chart on the current page so it auto-injects a
    PNG-export config when the caller hasn't supplied one.

    Call once at the top of a page (after imports). All subsequent
    st.plotly_chart calls without an explicit `config=` argument will
    use the default chart_config(page_name) settings.

    No-op if already patched (safe to call from imports that re-run).
    """
    if getattr(st.plotly_chart, "_export_patched", False):
        return
    original = st.plotly_chart

    def patched(*args, **kwargs):
        if "config" not in kwargs:
            kwargs["config"] = chart_config(page_name, scale=scale,
                                              format=format)
        return original(*args, **kwargs)

    patched._export_patched = True
    patched._wraps = original
    st.plotly_chart = patched
