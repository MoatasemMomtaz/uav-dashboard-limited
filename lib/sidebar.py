"""Sidebar UI. Renders all global filters; returns FilterState + filtered df.

v0.2 changes:
- MTOW preset buttons use a callback that writes to the slider's own session key.
- Adds SizeClassStd as the primary size-class filter (derived from MTOW per
  standard UAV taxonomy).
"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Tuple, Dict
from .loader import load_uav
from .filters import FilterState, apply_filters


MTOW_PRESETS = ["Nano/Micro", "Mini", "Small", "Tactical", "MALE", "HALE", "HAPS"]
# Upper bounds use values just below the next class to avoid the slider
# catching rows at the exact boundary. SizeClassStd uses strict < at each step:
# Nano/Micro: MTOW < 2, Mini: 2 <= MTOW < 20, Small: 20 <= MTOW < 150, etc.
# The slider's upper end is INCLUSIVE, so we subtract a tiny epsilon.
# v0.8.34c-fix6 / v1.0.0-limited: HAPS doesn't have a clean mass range
# — it's a size class defined by solar-engine + endurance > 24h regardless
# of mass. We use a wide range (covers all known HAPS platforms by mass)
# and rely on the user combining this with the SizeClassStd multi-select
# if they want HAPS-only.
PRESET_RANGES = {
    "Nano/Micro": (0,    1.9999),
    "Mini":       (2,    19.999),
    "Small":      (20,   149.999),
    "Tactical":   (150,  599.999),
    "MALE":       (600,  1999.999),
    "HALE":       (2000, 1e6),
    "HAPS":       (0,    1e6),    # covers all HAPS by mass
}

ROLE_ORDER = ["M", "DP", "CC", "DV", "RA", "ML"]
SIZE_STD_ORDER = ["Nano/Micro", "Mini", "Small", "Tactical", "MALE", "HALE",
                   "HAPS", "Suspect"]
ENGINE_ORDER = ["P", "E", "H", "FC", "S", "Turbojet", "Turbofan", "Turboprop", "DF", "G"]

SLIDER_KEY = "mtow_log_slider"
SIZESTD_KEY = "sidebar_size_classes_std"


def _sorted_by_pref(values, pref):
    pref_set = set(pref)
    head = [v for v in pref if v in values]
    tail = sorted(v for v in values if v not in pref_set)
    return head + tail


def _apply_preset_callback(preset_name: str, lo_kg: float, hi_kg: float,
                           abs_min_kg: float, abs_max_kg: float):
    """Callback runs *before* the slider re-renders, so it sees the new value.

    Clamps to the slider's actual bounds — otherwise presets that target ranges
    extending past the dataset (e.g. Nano/Micro down to 0 kg when the smallest
    UAV is 0.008 kg) cause Streamlit to raise a value-below-min error.

    v0.8.34c-fix6 / v1.0.0-limited: also handles HAPS specially. HAPS isn't
    defined by mass — it's a size class for solar + endurance > 24h. So the
    HAPS preset opens the MTOW slider to its full range AND sets the
    SizeClassStd filter to ['HAPS'] so the user gets HAPS-only rows. Other
    presets clear the SizeClassStd filter to avoid conflict with the MTOW
    range they just set.
    """
    lo_clamped = max(lo_kg, abs_min_kg)
    hi_clamped = min(hi_kg, abs_max_kg)
    lo = float(np.log10(max(lo_clamped, 0.001)))
    hi = float(np.log10(max(hi_clamped, 0.001)))
    st.session_state[SLIDER_KEY] = (lo, hi)
    # HAPS = solar + endurance category, not mass. Pin via SizeClassStd.
    if preset_name == "HAPS":
        st.session_state[SIZESTD_KEY] = ["HAPS"]
    else:
        # Other presets define a mass range; clear any leftover HAPS pin
        # so the user doesn't see "Nano/Micro preset + HAPS filter = 0 rows".
        if SIZESTD_KEY in st.session_state:
            st.session_state[SIZESTD_KEY] = []


def render_sidebar() -> Tuple[pd.DataFrame, FilterState, Dict[str, int]]:
    df = load_uav()
    n_total = len(df)
    mtow_min = float(np.nanmin(df["MTOW_kg"].values))
    mtow_max = float(np.nanmax(df["MTOW_kg"].values))
    log_min = float(np.log10(max(mtow_min, 0.001)))
    log_max = float(np.log10(mtow_max))

    if SLIDER_KEY not in st.session_state:
        st.session_state[SLIDER_KEY] = (log_min, log_max)

    with st.sidebar:
        st.markdown(
            "<div style='font-size: 13px; font-weight: 500;'>Fixed-wing UAV dataset</div>",
            unsafe_allow_html=True,
        )
        st.caption("v0.2 · explorer + design tool")
        st.divider()

        st.markdown("**Coverage**")
        gauge_slot = st.empty()
        st.divider()

        st.markdown("**MTOW Class Preset** *(standard taxonomy)*")
        preset_cols = st.columns(3)
        for i, p in enumerate(MTOW_PRESETS):
            lo_kg, hi_kg = PRESET_RANGES[p]
            with preset_cols[i % 3]:
                st.button(
                    p, key=f"preset_{p}", use_container_width=True,
                    on_click=_apply_preset_callback,
                    args=(p, lo_kg, hi_kg, mtow_min, mtow_max),
                )

        log_range = st.slider(
            "MTOW range (log10 kg)",
            min_value=log_min, max_value=log_max,
            step=0.1, key=SLIDER_KEY,
        )
        mtow_range = (10 ** log_range[0], 10 ** log_range[1])
        st.caption(f"{mtow_range[0]:,.2f} kg → {mtow_range[1]:,.0f} kg")

        st.divider()

        # v0.8.33b: friendly labels via code_to_label for all categorical
        # multiselects in the sidebar. Codes (E, P, H, ISR, LM, ...) now
        # appear as their full names ("Electric (E)", "Loitering Munition
        # (LM)", etc.). The Operational role multiselect was removed —
        # it duplicated information already covered by Mission and was
        # noisy in the UI per user feedback.
        from lib.labels import code_to_label as _code_to_label

        st.markdown("**Mission**")
        mission_counts = df["Mission"].value_counts()
        missions = st.multiselect(
            "Mission", mission_counts.index.tolist(), default=[],
            format_func=lambda v: f"{_code_to_label('Mission', v)} ({mission_counts[v]})",
            label_visibility="collapsed",
        )

        st.markdown("**Engine Type**")
        eng_counts = df["EngineType"].value_counts()
        eng_options = _sorted_by_pref(eng_counts.index.tolist(), ENGINE_ORDER)
        engines = st.multiselect(
            "Engine", eng_options, default=[],
            format_func=lambda v: f"{_code_to_label('EngineType', v)} ({eng_counts.get(v, 0)})",
            label_visibility="collapsed",
        )

        st.markdown("**Launch Method**")
        launch_counts = df["LaunchMethod"].value_counts()
        launches = st.multiselect(
            "Launch", launch_counts.index.tolist(), default=[],
            format_func=lambda v: f"{_code_to_label('LaunchMethod', v)} ({launch_counts[v]})",
            label_visibility="collapsed",
        )

        st.markdown("**Size Class (Standard, MTOW-Derived)**")
        sizestd_counts = df["SizeClassStd"].value_counts()
        sizestd_options = _sorted_by_pref(sizestd_counts.index.tolist(), SIZE_STD_ORDER)
        size_classes_std = st.multiselect(
            "Size class std", sizestd_options, default=[],
            format_func=lambda v: f"{_code_to_label('SizeClassStd', v)} ({sizestd_counts.get(v, 0)})",
            label_visibility="collapsed",
            key=SIZESTD_KEY,
        )

        # v0.8.33b: Operational role multiselect REMOVED per user request.
        # Empty list passed downstream to keep FilterState shape stable.
        op_roles = []

        st.divider()

        st.markdown("**Country**")
        country_counts = df["Country"].value_counts()
        countries = st.multiselect(
            f"Country ({len(country_counts)} available)",
            country_counts.index.tolist(), default=[],
            format_func=lambda v: f"{v} ({country_counts[v]})",
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("**Coverage Gate**")
        st.caption("Require these fields to be non-null")
        gate_options = [
            "MTOW_kg", "Endurance_h", "Range_km", "Wingspan_m",
            "Payload_kg", "EngPower_hp", "Ceiling_km",
        ]
        coverage_required = st.multiselect(
            "Coverage gate", gate_options, default=[],
            label_visibility="collapsed",
        )

        st.divider()

        st.markdown("**Data Hygiene**")
        hide_outliers = st.checkbox("Hide outliers (top/bot 1%, solar-aware)", value=False)
        include_unknown = st.checkbox("Include unknown in categorical filters", value=False)

        st.divider()
        if st.button("Reset all filters", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    fs = FilterState(
        mtow_range=mtow_range,
        countries=countries,
        missions=missions,
        engines=engines,
        launches=launches,
        size_classes_std=size_classes_std,
        op_roles=op_roles,
        coverage_required=coverage_required,
        hide_outliers=hide_outliers,
        include_unknown_in_categoricals=include_unknown,
    )
    filtered, cuts = apply_filters(df, fs)

    with gauge_slot.container():
        n = len(filtered)
        pct = 100 * n / n_total if n_total else 0
        st.metric(label=f"{n:,} / {n_total:,} rows", value=f"{pct:.1f}%")
        st.progress(min(1.0, n / n_total))
        if cuts:
            attr = ", ".join(f"{k} −{v}" for k, v in cuts.items())
            st.caption(f"Cut by: {attr}")
        else:
            st.caption("No filters applied")

    return filtered, fs, cuts
