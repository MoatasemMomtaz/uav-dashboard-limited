"""Page 3 — Compare filters.

Build two independent filter states A and B, then compare the resulting subsets
side by side on KPIs, distributions, dominance breakdowns, and reference
correlations.

Sidebar is hidden on this page — we use the main canvas for the two filter
panels so users can see A and B at the same time.
"""
import sys
from pathlib import Path
from typing import Tuple
sys.path.insert(0, str(Path(__file__).parent.parent))

# v0.8.34b+c: enable 2x PNG export on every plotly chart in this page
from lib.chart_config import apply_default_export_config
apply_default_export_config('compare-filters')

import streamlit as st

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from lib.loader import load_uav, load_acronyms, NAME_COL
from lib.labels import friendly_format_func, code_to_label
from lib.filters import FilterState, apply_filters
from lib.sidebar import MTOW_PRESETS, PRESET_RANGES, SIZE_STD_ORDER, ENGINE_ORDER

# v0.8.34a: set_page_config removed — under st.navigation only the router (app.py) may call it.
# st.set_page_config(
#     page_title="Compare · UAV Explorer",
#     page_icon="⚖",
#     layout="wide",
#     initial_sidebar_state="collapsed",
# )

st.title("Compare Two Filters")
st.caption(
    "Build Filter A and Filter B independently. The page shows their subsets "
    "side by side — KPIs, mass distribution, mission/engine mix, correlation "
    "snapshots. Useful for e.g. *electric vs piston*, *MALE vs Tactical*, "
    "*USA vs China*."
)

df_full = load_uav()
mtow_min = float(np.nanmin(df_full["MTOW_kg"].values))
mtow_max = float(np.nanmax(df_full["MTOW_kg"].values))
log_min = float(np.log10(max(mtow_min, 0.001)))
log_max = float(np.log10(mtow_max))


def _sorted_by_pref(values, pref):
    pref_set = set(pref)
    head = [v for v in pref if v in values]
    tail = sorted(v for v in values if v not in pref_set)
    return head + tail


def filter_panel(label: str, color_hex: str, key_prefix: str) -> Tuple[FilterState, bool]:
    """Render a compact filter-builder UI. Returns (FilterState, enabled)."""
    # Default enabled state — A on, B on (user can disable per-panel)
    default_enabled = True
    enabled = st.checkbox(
        f"**Enable {label}**", value=default_enabled,
        key=f"{key_prefix}_enabled",
        help=f"When unchecked, {label} is hidden from all comparison views.",
    )
    st.markdown(
        f"<div style='border-left: 4px solid {color_hex}; padding-left: 10px;'>"
        f"<h3 style='margin:0;color:{color_hex}'>{label}</h3></div>",
        unsafe_allow_html=True,
    )

    with st.container():
        # MTOW preset row
        preset_cols = st.columns(3)
        for i, p in enumerate(MTOW_PRESETS):
            lo_kg, hi_kg = PRESET_RANGES[p]
            with preset_cols[i % 3]:
                if st.button(p, key=f"{key_prefix}_preset_{p}",
                             use_container_width=True):
                    lo_clamp = max(lo_kg, mtow_min)
                    hi_clamp = min(hi_kg, mtow_max)
                    st.session_state[f"{key_prefix}_mtow"] = (
                        float(np.log10(max(lo_clamp, 0.001))),
                        float(np.log10(max(hi_clamp, 0.001))),
                    )

        # MTOW slider
        default_mtow = st.session_state.get(f"{key_prefix}_mtow",
                                             (log_min, log_max))
        log_range = st.slider(
            "MTOW range (log10 kg)",
            min_value=log_min, max_value=log_max, step=0.1,
            value=default_mtow,
            key=f"{key_prefix}_mtow",
        )
        mtow_range = (10 ** log_range[0], 10 ** log_range[1])
        st.caption(f"{mtow_range[0]:,.2f} kg → {mtow_range[1]:,.0f} kg")

        # Categorical filters in two compact columns
        # v0.8.34a-fix1: friendly labels via code_to_label, matching the
        # sidebar overview convention. Codes like "LM", "E", "P" now read
        # as "Loitering Munition / Kamikaze (LM)", "Electric (E)", etc.
        from lib.labels import code_to_label as _code_to_label
        c1, c2 = st.columns(2)
        with c1:
            mission_counts = df_full["Mission"].value_counts()
            missions = st.multiselect(
                "Mission", mission_counts.index.tolist(),
                default=[], key=f"{key_prefix}_mis",
                format_func=lambda v: f"{_code_to_label('Mission', v)} ({mission_counts[v]})",
            )
            launch_counts = df_full["LaunchMethod"].value_counts()
            launches = st.multiselect(
                "Launch", launch_counts.index.tolist(),
                default=[], key=f"{key_prefix}_lau",
                format_func=lambda v: f"{_code_to_label('LaunchMethod', v)} ({launch_counts[v]})",
            )
            sizestd_counts = df_full["SizeClassStd"].value_counts()
            sizestd_options = _sorted_by_pref(
                sizestd_counts.index.tolist(), SIZE_STD_ORDER
            )
            size_classes_std = st.multiselect(
                "Size class", sizestd_options,
                default=[], key=f"{key_prefix}_sze",
                format_func=lambda v: f"{_code_to_label('SizeClassStd', v)} ({sizestd_counts.get(v,0)})",
            )

        with c2:
            eng_counts = df_full["EngineType"].value_counts()
            eng_options = _sorted_by_pref(
                eng_counts.index.tolist(), ENGINE_ORDER
            )
            engines = st.multiselect(
                "Engine", eng_options,
                default=[], key=f"{key_prefix}_eng",
                format_func=lambda v: f"{_code_to_label('EngineType', v)} ({eng_counts.get(v,0)})",
            )
            country_counts = df_full["Country"].value_counts()
            countries = st.multiselect(
                "Country", country_counts.index.tolist(),
                default=[], key=f"{key_prefix}_cty",
                format_func=lambda v: f"{v} ({country_counts[v]})",
            )

        # v0.8.22: Exclude solar toggle — removes EngineType='S' AND
        # SizeClassStd='HAPS' rows. Useful for sizing fits that get
        # distorted by the solar/HAPS outliers.
        exclude_solar = st.checkbox(
            "Exclude solar / HAPS",
            value=False, key=f"{key_prefix}_excl_solar",
            help="Drop solar-powered (EngineType='S') and HAPS-class "
                 "platforms. These have extreme endurance/range that "
                 "skews fits.",
        )

    fs = FilterState(
        mtow_range=mtow_range,
        missions=missions, engines=engines, launches=launches,
        size_classes_std=size_classes_std, countries=countries,
        op_roles=[],
        exclude_solar=exclude_solar,
    )
    return fs, enabled


# ---- Two filter panels side by side ----------------------------------------
COLOR_A = "#534AB7"   # purple
COLOR_B = "#0F6E56"   # green

panel_a, panel_b = st.columns(2, gap="medium")
with panel_a:
    fs_a, enabled_a = filter_panel("Filter A", COLOR_A, "a")
with panel_b:
    fs_b, enabled_b = filter_panel("Filter B", COLOR_B, "b")

if not enabled_a and not enabled_b:
    st.warning("**Both filter groups are disabled.** Enable at least one to see comparisons.")
    st.stop()

df_a, cuts_a = (apply_filters(df_full, fs_a) if enabled_a else
                (df_full.iloc[0:0], {}))
df_b, cuts_b = (apply_filters(df_full, fs_b) if enabled_b else
                (df_full.iloc[0:0], {}))

# The MTOW range filter in lib/filters.py passes NaN MTOW rows through
# by default (for the "include unknown" workflow on other pages). But the
# Compare Filters page sets MTOW range on EVERY filter — so a NaN-MTOW row
# can't legitimately belong to any class. Drop them locally so e.g.
# selecting the MALE preset doesn't catch Molniya (MTOW=NaN, source-class=Mini).
if enabled_a and fs_a.mtow_range is not None:
    n_before_a = len(df_a)
    df_a = df_a[df_a["MTOW_kg"].notna()]
    n_dropped_a = n_before_a - len(df_a)
    if n_dropped_a > 0:
        cuts_a["NaN MTOW excluded"] = n_dropped_a
if enabled_b and fs_b.mtow_range is not None:
    n_before_b = len(df_b)
    df_b = df_b[df_b["MTOW_kg"].notna()]
    n_dropped_b = n_before_b - len(df_b)
    if n_dropped_b > 0:
        cuts_b["NaN MTOW excluded"] = n_dropped_b

st.divider()

# ---- KPI compare row -------------------------------------------------------
st.subheader("Headline Comparison")

k1, k2 = st.columns(2, gap="medium")


def kpi_block(col, df_sub: pd.DataFrame, label: str, color: str):
    with col:
        st.markdown(
            f"<div style='font-size:13px;font-weight:500;color:{color}'>{label}"
            f" — {len(df_sub):,} UAVs ({100*len(df_sub)/len(df_full):.1f}% of dataset)</div>",
            unsafe_allow_html=True,
        )
        if len(df_sub) == 0:
            st.warning("No UAVs match this filter.")
            return
        m_med = df_sub["MTOW_kg"].median()
        e_med = df_sub["Endurance_h"].median()
        r_med = df_sub["Range_km"].median()
        p_med = df_sub["Payload_kg"].median()
        cols = st.columns(4)
        cols[0].metric("Median MTOW",
                       f"{m_med:,.1f} kg" if pd.notna(m_med) else "—")
        cols[1].metric("Median endurance",
                       f"{e_med:,.1f} h" if pd.notna(e_med) else "—")
        cols[2].metric("Median range",
                       f"{r_med:,.0f} km" if pd.notna(r_med) else "—")
        cols[3].metric("Median payload",
                       f"{p_med:,.1f} kg" if pd.notna(p_med) else "—")


if enabled_a:
    kpi_block(k1, df_a, "Filter A", COLOR_A)
else:
    with k1:
        st.caption("_Filter A disabled_")
if enabled_b:
    kpi_block(k2, df_b, "Filter B", COLOR_B)
else:
    with k2:
        st.caption("_Filter B disabled_")

if len(df_a) == 0 and len(df_b) == 0:
    st.stop()

st.divider()

# ---- Mass distribution overlay --------------------------------------------
st.subheader("Mass Distribution Overlay")
st.caption("Histograms on log-MTOW axis. Y is **number of UAVs** in each bin.")


def mass_bins(df_sub):
    s = df_sub["MTOW_kg"].dropna()
    if len(s) == 0:
        return None
    return np.log10(s.clip(lower=0.001))


a_log = mass_bins(df_a)
b_log = mass_bins(df_b)

fig = go.Figure()
common_bins = dict(start=log_min, end=log_max, size=0.3)
if a_log is not None:
    fig.add_trace(go.Histogram(
        x=a_log, name="A", marker_color=COLOR_A, opacity=0.65,
        xbins=common_bins,
    ))
if b_log is not None:
    fig.add_trace(go.Histogram(
        x=b_log, name="B", marker_color=COLOR_B, opacity=0.65,
        xbins=common_bins,
    ))
fig.update_layout(
    barmode="overlay", height=300,
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title="MTOW (log10 kg)",
    yaxis_title="Number of UAVs",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- Mission and Engine breakdowns side by side ---------------------------
st.subheader("Dominance Breakdown — Mission, Engine, Launch, Wing Form, Body Config")
st.caption(
    "% of each filter that falls in each bucket. Helps see what each filter "
    "is dominated by. Optional merge fields collapse sub-categories locally "
    "(does not affect the scatter plots below)."
)

# Friendly column-name → display title
_DIM_TITLES = {
    "Mission": "Mission",
    "EngineType": "Engine type",
    "LaunchMethod": "Launch method",
    "WingForm": "Wing form",
    "BodyConfig": "Body configuration",
}


def dominance_bars(col, df_sub: pd.DataFrame, dimension: str,
                    label: str, color: str,
                    merge_map: dict | None = None):
    """Render a horizontal % bar chart for `dimension` within df_sub.
    Bar labels use friendly names. Optional merge_map collapses codes
    into named groups before counting."""
    with col:
        s = df_sub[dimension].dropna()
        if len(s) == 0:
            st.info(f"{label}: no data")
            return
        if merge_map:
            s = s.astype(str).map(lambda v: merge_map.get(v, v))
        vc = s.value_counts(normalize=True).head(6) * 100
        # Friendly y-axis tick labels — keep user merge labels verbatim,
        # else translate the code via code_to_label.
        merged_labels = set((merge_map or {}).values())
        y_labels = [
            v if v in merged_labels else code_to_label(dimension, v)
            for v in vc.index.tolist()
        ]
        fig = go.Figure(go.Bar(
            x=vc.values, y=y_labels, orientation="h",
            marker_color=color,
            text=[f"{v:.0f}%" for v in vc.values],
            textposition="outside",
        ))
        title_dim = _DIM_TITLES.get(dimension, dimension)
        fig.update_layout(
            height=200, margin=dict(l=10, r=30, t=20, b=10),
            xaxis=dict(range=[0, 110]),
            yaxis=dict(autorange="reversed"),
            title=dict(text=f"<b style='color:{color}'>{label}</b> · {title_dim}",
                        font=dict(size=12)),
        )
        st.plotly_chart(fig, use_container_width=True)


for dim in ["Mission", "EngineType", "LaunchMethod", "WingForm", "BodyConfig"]:
    title_dim = _DIM_TITLES.get(dim, dim)

    # v0.8.29: per-dimension merge UI — distinct from the general merge in
    # the sizing-relation scatter. One simple optional merge per dimension
    # row. Picks raw codes from EITHER filter's data, collapses them into
    # a named group, and applies to both filter bars below.
    union_vals = pd.concat([
        df_a[dim].dropna() if dim in df_a.columns else pd.Series(dtype=object),
        df_b[dim].dropna() if dim in df_b.columns else pd.Series(dtype=object),
    ]).astype(str).unique().tolist()
    union_vals.sort()

    with st.expander(
        f"🔀 Merge {title_dim} subcategories  *(optional)*",
        expanded=False,
    ):
        m_left, m_right = st.columns([3, 1])
        with m_left:
            merge_src = st.multiselect(
                f"Merge these {title_dim} values…",
                options=union_vals, default=[],
                format_func=friendly_format_func(dim),
                key=f"cf_dom_merge_src_{dim}",
            )
        with m_right:
            merge_dst = st.text_input(
                "…into this label",
                value="merged",
                key=f"cf_dom_merge_dst_{dim}",
            )
        merge_map_dim = None
        if merge_src and merge_dst.strip():
            merge_map_dim = {s: merge_dst.strip() for s in merge_src}

    c1, c2 = st.columns(2, gap="medium")
    dominance_bars(c1, df_a, dim, "Filter A", COLOR_A, merge_map_dim)
    dominance_bars(c2, df_b, dim, "Filter B", COLOR_B, merge_map_dim)

st.divider()

# ---- Sizing-relation scatter (configurable) ---------------------------------
st.subheader("Sizing-Relation Scatter — fitted curves, literature overlay, prediction band")
st.caption(
    "Compare A and B on a sizing relation. Fit a power law to each filter "
    "(or per engine type), overlay published literature correlations, and "
    "optionally show a 95% prediction band that wraps the pooled fit. "
    "Switch between relations and axis types using the controls below. "
    "Hover any point for its row id and UAV designation."
)

from lib.relations import (
    SIZING_RELATIONS, DEFAULT_RELATIONS, get_relation,
    applicable_literature_fits,
)
from lib.r2_badge import r2_badge_html, verdict_badge_html
from lib.sizing_scatter import make_sizing_scatter, make_categorical_box

rel_col, mode_col, ref_col = st.columns([2, 2, 3])

with rel_col:
    rel_labels = {k: SIZING_RELATIONS[k].label for k in DEFAULT_RELATIONS}
    # Include the secondary relations after a separator
    for k in SIZING_RELATIONS:
        if k not in rel_labels:
            rel_labels[k] = f"{SIZING_RELATIONS[k].label}  (sparse data)"
    chosen_relation_key = st.selectbox(
        "Relation",
        options=list(rel_labels.keys()),
        format_func=lambda k: rel_labels[k],
        key="cf_relation",
    )
    chosen_relation = get_relation(chosen_relation_key)

with mode_col:
    axis_choice = st.radio(
        "Axis type",
        options=["Default for relation", "Both log", "Both linear",
                 "Linear X / log Y", "Log X / linear Y"],
        horizontal=False, key="cf_axis_mode",
    )
    if axis_choice == "Default for relation":
        x_type = chosen_relation.default_x_type
        y_type = chosen_relation.default_y_type
    elif axis_choice == "Both log":
        x_type, y_type = "log", "log"
    elif axis_choice == "Both linear":
        x_type, y_type = "linear", "linear"
    elif axis_choice == "Linear X / log Y":
        x_type, y_type = "linear", "log"
    else:
        x_type, y_type = "log", "linear"

with ref_col:
    has_ref = chosen_relation.canonical_coefficient is not None or \
               len(chosen_relation.literature_fits) > 0
    st.markdown("**Overlays**")
    show_fit_a = st.checkbox("Fit A's data", value=True, key="cf_fit_a")
    show_fit_b = st.checkbox("Fit B's data", value=True, key="cf_fit_b")
    # v0.8.34c-fix4: REPLACED CI-on-line with PREDICTION BAND. Previous
    # bootstrap-CI band described where the regression LINE is — which
    # depends mainly on N, not R². User correctly observed the band
    # looked the same for high-R² and low-R² fits. The PREDICTION band
    # describes where INDIVIDUAL UAVs scatter around the line — width
    # proportional to residual stdev, visibly tracks R² as expected.
    show_ci_band = st.checkbox(
        "Show 95% prediction band (where UAVs scatter)",
        value=False, key="cf_show_ci_band",
        help="95% prediction band around the live dataset fit. This shows "
             "where INDIVIDUAL UAVs are expected to fall around the fitted "
             "line (NOT where the line itself is). Width is proportional "
             "to residual scatter — wide for messy clouds (low R²), tight "
             "for clean clouds (high R²). Computed from log-space residual "
             "standard deviation: edges at log10(Y_pred) ± 1.96·σ.",
    )

    # v0.8.33b: density-view is now its own section ("Density Heatmap")
    # below the scatter block. Removed the radio toggle from here per
    # user request — Color-by, Merge, Fit options don't apply to a heatmap
    # and were causing confusion when shown in the same control panel.

    # v0.8.33a: scatter-area exclude solar/HAPS toggle (independent from
    # the per-filter sidebar checkboxes). Affects only this scatter and
    # its fits, not KPIs / histogram / dominance. Useful for keeping
    # solar+HAPS in the breakdown but excluding them from sizing fits.
    scatter_excl_solar = st.checkbox(
        "Exclude Solar / HAPS From Scatter",
        value=False, key="cf_scatter_excl_solar",
        help="Local to this scatter only. Drops solar (EngineType='S') and "
             "HAPS-class platforms from both A and B before refitting. "
             "Does not change the headline KPIs or distribution charts above.",
    )

    # v0.8.27: Dropdown lists ALL variants for the relation (so user can
    # always reach LM/engine-specific variants manually). The DEFAULT
    # selection is the auto-applicable variant per Filter A's scope.
    # Fix for v0.8.26 LM-leak: if no applicable variant for current scope,
    # the default is "(none)" — Voskuijl LM no longer leaks when LM isn't
    # filtered.
    applicable = applicable_literature_fits(
        chosen_relation,
        active_engines=list(fs_a.engines) if fs_a.engines else None,
        active_missions=list(fs_a.missions) if fs_a.missions else None,
    )
    all_variants = list(chosen_relation.literature_fits or [])
    # v0.8.34c-fix3: group Palmer-style envelope upper+lower into one
    # selection (EnvelopePair). The dropdown shows one entry; the
    # renderer draws both curves with a filled band between them.
    from lib.relations import group_envelope_pairs, EnvelopePair
    picker_items = group_envelope_pairs(all_variants)
    if picker_items:
        NONE_LIT = "(none — no literature overlay)"
        lit_options = [NONE_LIT] + [
            it.source for it in picker_items
        ]
        default_idx = 0
        chosen_lit_label = st.selectbox(
            "Literature fit",
            options=lit_options, index=default_idx,
            key="cf_lit_choice",
            help="Pick a published equation to overlay. Envelope pairs "
                 "(e.g. Palmer 2014 — manned envelope) appear as one "
                 "selection; both upper and lower bounds will be drawn.",
        )
        chosen_lit_fit = None
        if chosen_lit_label != NONE_LIT:
            idx = lit_options.index(chosen_lit_label) - 1
            chosen_lit_fit = picker_items[idx]
    else:
        chosen_lit_fit = None
        st.caption("No literature reference for this relation.")
    show_ref = chosen_lit_fit is not None

# Color-by and per-category fit toggles, on their own row
opt_col1, opt_col2 = st.columns([1, 2])
with opt_col1:
    color_by_choice = st.selectbox(
        "Color points by",
        options=[
            "(none — group color only)",
            "EngineType", "Mission", "SizeClassStd",
            "WingForm", "WingConfig", "BodyConfig",
            "LaunchMethod", "TailConfig",
        ],
        index=0, key="cf_color_by",
        help="When set, points are colored by category — useful to spot "
             "regime changes (e.g. jet vs piston follow different scaling).",
    )
    color_by = None if color_by_choice.startswith("(none") else color_by_choice
with opt_col2:
    if color_by:
        fit_per_cat = st.checkbox(
            f"Fit a separate power-law per **{color_by}** "
            "(uses both A and B together)",
            value=True, key="cf_fit_per_cat",
        )
        hide_uncat = st.checkbox(
            f"Hide rows with no **{color_by}** value",
            value=True, key="cf_hide_uncat",
            help="When unchecked, rows missing a value on this column appear "
                 "in a grey '(uncategorized)' group. They are NEVER included "
                 "in fitting regardless of this toggle.",
        )
    else:
        fit_per_cat = False
        hide_uncat = True

# --- Subcategory merging UI (only when color_by is set) ---
merge_categories = None
only_show_cats = None
if color_by:
    with st.expander(
        "🔀 Merge subcategories / restrict to specific categories",
        expanded=False,
    ):
        st.caption(
            "**Merge** combines multiple subcategory labels into one "
            "(e.g. merge `T`+`R`+`e`+`Polyhedral` into 'fixed'). The "
            "merged group gets one color, one symbol, one fit line. "
            "Up to **3 merge groups** can be active at once (e.g. one for "
            "'fixed', one for 'swept-all'). **Show only** restricts the "
            "visible categories."
        )

        # Collect unique values from both groups
        combined = pd.concat([df_a, df_b]) if enabled_a or enabled_b else pd.DataFrame()
        unique_cats = (combined[color_by].dropna().astype(str).unique().tolist()
                        if color_by in combined.columns else [])
        unique_cats.sort()

        # Build up to 3 merge groups
        merge_categories = {}
        for i in range(1, 4):
            st.markdown(f"**Merge group {i}** *(optional)*")
            m_left, m_right = st.columns([2, 1])
            with m_left:
                # Filter out values already used in earlier merge groups
                available = [c for c in unique_cats
                              if c not in merge_categories]
                merge_src = st.multiselect(
                    f"Merge these {color_by} values…",
                    options=available,
                    default=[],
                    format_func=friendly_format_func(color_by),
                    key=f"cf_merge_src_{color_by}_{i}",
                )
            with m_right:
                merge_dst = st.text_input(
                    "…into this label",
                    value=f"merged{i}" if i > 1 else "merged",
                    key=f"cf_merge_dst_{color_by}_{i}",
                )
            if merge_src and merge_dst.strip():
                label = merge_dst.strip()
                for src in merge_src:
                    merge_categories[src] = label

        if not merge_categories:
            merge_categories = None

        post_merge_options = sorted(set(
            (merge_categories or {}).get(c, c) for c in unique_cats
        ))
        def _cf_only_fmt(v):
            lbl = code_to_label(color_by, v)
            return lbl if lbl != v else v

        only_show_cats_pick = st.multiselect(
            "Show only these (merged) categories — leave empty for all",
            options=post_merge_options,
            default=[],
            format_func=_cf_only_fmt,
            key=f"cf_only_show_{color_by}",
        )
        only_show_cats = only_show_cats_pick if only_show_cats_pick else None

# Notes for the chosen relation
if chosen_relation.notes:
    st.caption(f"ℹ {chosen_relation.notes}")

# Build scatter — only include enabled groups
groups = []
if enabled_a:
    df_a_for_scatter = df_a
    if scatter_excl_solar:
        df_a_for_scatter = df_a_for_scatter[
            (df_a_for_scatter["EngineType"] != "S")
            & (df_a_for_scatter["SizeClassStd"] != "HAPS")
        ]
    groups.append({"df": df_a_for_scatter, "name": "A",
                    "color": COLOR_A, "symbol": "circle"})
if enabled_b:
    df_b_for_scatter = df_b
    if scatter_excl_solar:
        df_b_for_scatter = df_b_for_scatter[
            (df_b_for_scatter["EngineType"] != "S")
            & (df_b_for_scatter["SizeClassStd"] != "HAPS")
        ]
    groups.append({"df": df_b_for_scatter, "name": "B",
                    "color": COLOR_B, "symbol": "diamond"})

# Detect categorical-X relations (e.g. powerloading_launchmethod) and route
# to a box plot instead of a scatter. Categorical = the X column dtype is
# object/string rather than numeric.
_is_categorical_x = not pd.api.types.is_numeric_dtype(
    df_full[chosen_relation.x_col]
)

# v0.8.33b: density_view_active must be defined before either branch sets
# it conditionally — the categorical branch doesn't touch it but the fit-
# table block below checks it unconditionally. Default = False (scatter
# mode); the numeric scatter branch may flip it to True.
density_view_active = False

if _is_categorical_x:
    fig, scatter_info = make_categorical_box(
        chosen_relation, groups, height=440,
    )
    st.caption(
        "ℹ This relation has a categorical X axis — shown as a box plot "
        "of the Y distribution per category. Per-group fits, literature "
        "reference, and color-by are not applicable here."
    )
    # v0.8.29: box-plot reader's guide. Only shown for categorical relations.
    with st.expander("📖 How to read a box plot (click to expand)",
                       expanded=False):
        st.markdown(
            "A box plot summarises the **distribution** of Y values within "
            "each X category. Each box represents one category (e.g. one "
            "engine type), and shows where the values cluster.\n\n"
            "**The five reference lines (bottom to top):**\n"
            "- **Lower whisker** — smallest typical value\n"
            "- **Bottom of box** — 25th percentile (one-quarter of values are below)\n"
            "- **Line inside box** — **median** (half of values are above, half below)\n"
            "- **Top of box** — 75th percentile (three-quarters of values are below)\n"
            "- **Upper whisker** — largest typical value\n\n"
            "**Dots outside the whiskers** are outliers — unusual values.\n\n"
            "**Worked example**: if you select *Engine type vs MTOW*, "
            "the **Piston** box's median tells you the typical mass of a "
            "piston-engine UAV. A taller box means piston UAVs span a "
            "wider mass range than (say) electric ones. Outlier dots at "
            "the top are unusually heavy piston platforms.\n\n"
            "**What to look for**:\n"
            "- *Box height* = spread within the category\n"
            "- *Median position* = where the typical value sits relative "
            "to other categories\n"
            "- *Non-overlapping boxes* = the categories really do separate "
            "on this Y variable"
        )
else:
    # v0.8.26: if user picked a non-default literature variant, swap its
    # coef/exp/source into the relation copy before drawing.
    # v0.8.34c-fix3: EnvelopePair handled separately below (two curves +
    # fill, drawn AFTER make_sizing_scatter returns). For now skip the
    # canonical override when picked item is an envelope.
    from lib.relations import EnvelopePair
    rel_for_draw = chosen_relation
    is_envelope = isinstance(chosen_lit_fit, EnvelopePair)
    if chosen_lit_fit is not None and not is_envelope:
        import dataclasses as _dc
        rel_for_draw = _dc.replace(
            chosen_relation,
            canonical_coefficient=chosen_lit_fit.coef,
            canonical_exponent=chosen_lit_fit.exp,
            canonical_source=f"{chosen_lit_fit.scope['label']} — {chosen_lit_fit.source}",
        )

    # v0.8.33b: density (heatmap) mode is now in its own section below.
    # Scatter rendering path is unconditional here.
    fig, scatter_info = make_sizing_scatter(
        rel_for_draw, groups,
        x_type=x_type, y_type=y_type,
        show_canonical_fit=show_ref,
        show_group_fits=(show_fit_a or show_fit_b or fit_per_cat),
        color_by=color_by,
        fit_per_category=fit_per_cat,
        side_by_side=False,
        hide_uncategorized=hide_uncat,
        merge_categories=merge_categories,
        only_show_categories=only_show_cats,
        height=440,
    )
    # Selectively hide A or B fit lines when the user didn't tick them
    if not show_fit_a:
        for trace in fig.data:
            if trace.name and "A fit" in trace.name:
                trace.visible = "legendonly"
    if not show_fit_b:
        for trace in fig.data:
            if trace.name and "B fit" in trace.name:
                trace.visible = "legendonly"

    # v0.8.34c-fix3: ENVELOPE-PAIR OVERLAY. When user picked an
    # EnvelopePair (e.g. Palmer 2014 — manned envelope), draw both
    # upper and lower curves with a filled translucent band between.
    if is_envelope and isinstance(chosen_lit_fit, EnvelopePair):
        import numpy as _np
        ep = chosen_lit_fit
        # Build X array covering visible data extent in log space
        x_min, x_max = None, None
        for g_ in groups:
            sub_ = g_["df"][[rel_for_draw.x_col, rel_for_draw.y_col]].dropna()
            sub_ = sub_[sub_[rel_for_draw.x_col] > 0]
            if len(sub_) == 0:
                continue
            xmn = sub_[rel_for_draw.x_col].min()
            xmx = sub_[rel_for_draw.x_col].max()
            x_min = xmn if x_min is None else min(x_min, xmn)
            x_max = xmx if x_max is None else max(x_max, xmx)
        if x_min is not None and x_max is not None and x_min > 0:
            xs = _np.logspace(_np.log10(x_min), _np.log10(x_max), 100)
            ys_up = ep.upper.coef * xs ** ep.upper.exp
            ys_lo = ep.lower.coef * xs ** ep.lower.exp
            env_color = "rgba(180, 90, 30, 0.85)"   # warm bronze, distinct
            fill_color = "rgba(180, 90, 30, 0.10)"
            # Lower curve first (so fill renders correctly)
            fig.add_trace(go.Scatter(
                x=xs, y=ys_lo, mode="lines",
                name=f"{ep.source}: lower",
                line=dict(color=env_color, width=2, dash="dot"),
                hovertemplate=(
                    f"<b>{ep.lower.source}</b><br>"
                    f"{rel_for_draw.x_label}: %{{x:,.3g}}<br>"
                    f"{rel_for_draw.y_label}: %{{y:,.3g}}<extra></extra>"
                ),
                legendgroup="envelope",
                legendgrouptitle_text="Envelope",
            ))
            fig.add_trace(go.Scatter(
                x=xs, y=ys_up, mode="lines",
                name=f"{ep.source}: upper",
                line=dict(color=env_color, width=2, dash="dash"),
                fill="tonexty",   # fill to previous trace (lower)
                fillcolor=fill_color,
                hovertemplate=(
                    f"<b>{ep.upper.source}</b><br>"
                    f"{rel_for_draw.x_label}: %{{x:,.3g}}<br>"
                    f"{rel_for_draw.y_label}: %{{y:,.3g}}<extra></extra>"
                ),
                legendgroup="envelope",
                legendgrouptitle_text="Envelope",
            ))

    # v0.8.34c-fix4: 95% PREDICTION band — describes residual scatter
    # of individual UAVs around the fitted line. Replaces the bootstrap
    # CI-on-line from fix3 which didn't visually track R².
    # v1.0.0-limited / v0.8.34c-fix7: also expose band_fit + band_sigma_log
    # at scatter scope so the Fit Equations table below can add a
    # "A + B combined (95% band center)" row.
    band_fit = None
    band_sigma_log = None
    if show_ci_band:
        try:
            from lib.fitting import fit_power_law_with_ci, prediction_band
            import numpy as _np
            ci_xs, ci_ys = [], []
            for g_ in groups:
                sub_ = g_["df"][[rel_for_draw.x_col, rel_for_draw.y_col]].copy()
                est_col_ = getattr(rel_for_draw, "y_estimated_col", None)
                if est_col_ and est_col_ in g_["df"].columns:
                    est_mask_ = g_["df"][est_col_].fillna(False).astype(bool)
                    sub_ = sub_[~est_mask_]
                if color_by and color_by in g_["df"].columns:
                    sub_[color_by] = g_["df"][color_by]
                sub_ = sub_.dropna(subset=[rel_for_draw.x_col,
                                              rel_for_draw.y_col])
                sub_ = sub_[(sub_[rel_for_draw.x_col] > 0)
                              & (sub_[rel_for_draw.y_col] > 0)]
                if color_by and color_by in sub_.columns:
                    if merge_categories:
                        sub_[color_by] = (sub_[color_by].astype("object")
                                            .replace(merge_categories))
                    if only_show_cats:
                        sub_ = sub_[sub_[color_by].astype(str)
                                     .isin([str(c) for c in only_show_cats])]
                ci_xs.extend(sub_[rel_for_draw.x_col].tolist())
                ci_ys.extend(sub_[rel_for_draw.y_col].tolist())
            band_fit = fit_power_law_with_ci(pd.Series(ci_xs),
                                                pd.Series(ci_ys))
            if band_fit is not None and len(ci_xs) >= 5:
                x_min_b = min(ci_xs)
                x_max_b = max(ci_xs)
                if x_min_b > 0:
                    xs_b = _np.logspace(_np.log10(x_min_b),
                                           _np.log10(x_max_b), 80)
                    y_lo, y_hi, sigma_log = prediction_band(
                        pd.Series(ci_xs), pd.Series(ci_ys),
                        band_fit["coef"], band_fit["exp"], xs_b,
                        confidence=0.95)
                    band_sigma_log = sigma_log   # carried forward to table
                    y_mid = band_fit["coef"] * xs_b ** band_fit["exp"]
                    # How wide is the band in multiplicative terms?
                    band_factor = 10 ** (1.96 * sigma_log) if sigma_log else 1.0
                    band_color = "rgba(80, 80, 200, 0.13)"
                    line_color = "rgba(50, 50, 180, 0.95)"
                    # Lower edge
                    fig.add_trace(go.Scatter(
                        x=xs_b, y=y_lo, mode="lines",
                        name="95% prediction: lower",
                        line=dict(color=line_color, width=1, dash="dot"),
                        hovertemplate=(
                            f"<b>95% prediction band — lower</b><br>"
                            f"{rel_for_draw.x_label}: %{{x:,.3g}}<br>"
                            f"Y: %{{y:,.3g}}<extra></extra>"
                        ),
                        legendgroup="ci_band",
                        legendgrouptitle_text="95% prediction band",
                    ))
                    fig.add_trace(go.Scatter(
                        x=xs_b, y=y_hi, mode="lines",
                        name="95% prediction: upper",
                        line=dict(color=line_color, width=1, dash="dot"),
                        fill="tonexty",
                        fillcolor=band_color,
                        hovertemplate=(
                            f"<b>95% prediction band — upper</b><br>"
                            f"{rel_for_draw.x_label}: %{{x:,.3g}}<br>"
                            f"Y: %{{y:,.3g}}<extra></extra>"
                        ),
                        legendgroup="ci_band",
                        legendgrouptitle_text="95% prediction band",
                    ))
                    # Central line (the live fit itself)
                    fig.add_trace(go.Scatter(
                        x=xs_b, y=y_mid, mode="lines",
                        name=(f"Live fit (N={band_fit['n']}, "
                                f"R²={band_fit['r_squared']:.2f}, "
                                f"band ÷×{band_factor:.1f}×)"),
                        line=dict(color=line_color, width=2.5),
                        hovertemplate=(
                            f"<b>Live fit</b> Y = {band_fit['coef']:.3g} · X^{band_fit['exp']:.3f}<br>"
                            f"{rel_for_draw.x_label}: %{{x:,.3g}}<br>"
                            f"{rel_for_draw.y_label}: %{{y:,.3g}}<extra></extra>"
                        ),
                        legendgroup="ci_band",
                    ))
        except Exception as _ci_err:
            st.caption(f"⚠ Prediction band could not be rendered: {_ci_err}")

    st.plotly_chart(fig, use_container_width=True)

    # v0.8.29: Literature-fit badge — plain-English labels.
    # v0.8.34b+c: LIVE recomputation (approach i). Previously `your_r2`,
    # `your_exp`, `your_ci`, `verdict` came from a frozen inventory
    # snapshot — these described some earlier dataset state, not the
    # current filter. Now we recompute them at runtime against the
    # actual filtered data shown on the chart, so "This dataset R²"
    # genuinely reflects what you're looking at. Same for the verdict.
    if chosen_lit_fit is not None and isinstance(chosen_lit_fit, EnvelopePair):
        # v0.8.34c-fix3: envelope pairs use a simpler badge (no slope
        # verdict — slope-equality doesn't make sense for a boundary).
        ep = chosen_lit_fit
        up = ep.upper
        lo = ep.lower
        eq_up = f"Upper: Y = {up.coef:g} · X^{up.exp:.3f}"
        eq_lo = f"Lower: Y = {lo.coef:g} · X^{lo.exp:.3f}"
        st.markdown(
            '<div style="font-size:12px;line-height:1.8;'
            'padding:6px 10px;border-left:3px solid #B45A1E;'
            'background:rgba(180,90,30,0.05);margin:4px 0;">'
            f'<b>📖 {ep.source}</b><br>'
            f'&nbsp;&nbsp;<code>{eq_up}</code><br>'
            f'&nbsp;&nbsp;<code>{eq_lo}</code><br>'
            f'<span style="font-size:11px;color:#666;">'
            f'Boundary reference — no slope verdict applicable.'
            f'</span>'
            f'</div>'
            f'<div style="font-size:10px;color:#888;'
            f'padding:0 10px 6px 13px;">{ep.caveat}</div>',
            unsafe_allow_html=True,
        )
    elif chosen_lit_fit is not None:
        # Regular LiteratureFit — standard live-verdict badge
        lf = chosen_lit_fit
        # Pool A+B (after solar/HAPS exclusion) into one evidence set for
        # the live recomputation. Use the rendered scatter groups, which
        # already reflect the user's filter+exclude choices.
        # MEASURED only — exclude estimated points (v0.8.34b+c).
        #
        # v0.8.34c-fix2 (CRITICAL FIX): also apply the same color_by +
        # merge_categories + only_show_cats filtering that the scatter
        # applies. Previously the live recompute used each group's full
        # df, so when the user picked "color_by=EngineType + show only
        # piston", the badge reported R² on the WHOLE filter (n=759)
        # while the fit-table reported R² on the visible piston subset
        # (n=320). Two R² numbers on different subsets = apples-to-
        # oranges comparison.
        live_xs, live_ys = [], []
        for g_live in groups:
            sub_live = g_live["df"][[rel_for_draw.x_col,
                                      rel_for_draw.y_col]].copy()
            # Carry color_by column for merge + only_show filtering below
            if color_by and color_by in g_live["df"].columns:
                sub_live[color_by] = g_live["df"][color_by]
            est_col = getattr(rel_for_draw, "y_estimated_col", None)
            if est_col and est_col in g_live["df"].columns:
                est_mask = g_live["df"][est_col].fillna(False).astype(bool)
                sub_live = sub_live[~est_mask]
            sub_live = sub_live.dropna(subset=[rel_for_draw.x_col,
                                                  rel_for_draw.y_col])
            sub_live = sub_live[(sub_live[rel_for_draw.x_col] > 0)
                                  & (sub_live[rel_for_draw.y_col] > 0)]

            # === v0.8.34c-fix2: apply the same color_by + merge +
            # only_show_categories filter that the scatter uses ===
            if color_by and color_by in sub_live.columns:
                # Apply merge mapping first (same as in sizing_scatter)
                if merge_categories:
                    sub_live[color_by] = (sub_live[color_by]
                                            .astype("object")
                                            .replace(merge_categories))
                # Apply only_show_cats restriction
                if only_show_cats:
                    sub_live = sub_live[sub_live[color_by].astype(str)
                                          .isin([str(c) for c in only_show_cats])]
                # Hide uncategorized if the user has that toggle on
                if hide_uncat:
                    sub_live = sub_live[sub_live[color_by].notna()
                                          & (sub_live[color_by].astype(str) != "")]

            live_xs.extend(sub_live[rel_for_draw.x_col].tolist())
            live_ys.extend(sub_live[rel_for_draw.y_col].tolist())

        # Refit dataset (live) and compute literature R² against the
        # same evidence set.
        from lib.fitting import (fit_power_law_with_ci,
                                    literature_r2_on_data, derive_verdict)
        live_fit = fit_power_law_with_ci(pd.Series(live_xs),
                                            pd.Series(live_ys))
        live_lit_r2 = literature_r2_on_data(lf.coef, lf.exp,
                                              pd.Series(live_xs),
                                              pd.Series(live_ys))

        # Build the badge using LIVE values if available, otherwise fall
        # back to the inventory snapshot (legacy).
        if live_fit is not None:
            live_your_exp = live_fit["exp"]
            live_your_ci = (live_fit["ci_lo"], live_fit["ci_hi"])
            live_your_r2 = live_fit["r_squared"]
            live_your_n = live_fit["n"]
            live_verdict = derive_verdict(
                lf.exp, live_your_exp,
                live_fit["ci_lo"], live_fit["ci_hi"],
                live_your_r2)
        else:
            live_your_exp, live_your_ci = lf.your_exp, lf.your_ci
            live_your_r2, live_your_n = lf.your_r2, lf.your_n
            live_verdict = lf.verdict

        ci_lo, ci_hi = live_your_ci
        ci_str = (f"[{ci_lo:.3f}, {ci_hi:.3f}]"
                   if ci_lo is not None and ci_hi is not None else "")
        if abs(lf.exp) < 1e-9:
            eq_str = f"Y = {lf.coef:g} (mean)"
        else:
            eq_str = f"Y = {lf.coef:g} · X^{lf.exp:.3f}"
        # v0.8.34c-fix1: explicit slope comparison so the user
        # immediately sees WHY the verdict is "Slope matches/differs".
        # The R² numbers are about FIT QUALITY; the verdict is about
        # SLOPE EQUALITY — orthogonal questions, easily confused.
        slope_compare = ""
        if live_your_exp is not None and ci_lo is not None and ci_hi is not None:
            inside = ci_lo <= lf.exp <= ci_hi
            arrow = "✓ inside CI" if inside else "✗ outside CI"
            slope_compare = (
                f"<div style='font-size:11px;padding:4px 10px 0 13px;'>"
                f"<b>Slope comparison:</b> "
                f"Literature exponent = <code>{lf.exp:.3f}</code> · "
                f"Live exponent = <code>{live_your_exp:.3f}</code> "
                f"<span style='color:#666;'>(95% CI {ci_str})</span> · "
                f"<b>{arrow}</b>"
                f"</div>"
                f"<div style='font-size:10px;color:#888;padding:0 10px 4px 13px;'>"
                f"R² measures variance explained; verdict checks whether "
                f"the literature's <i>slope</i> falls inside the dataset's "
                f"confidence interval. These are independent: R²s can be "
                f"close even when slopes differ."
                f"</div>"
            )
        your_str = ""
        if live_your_exp is not None:
            your_str = (f"This dataset (live): exponent = {live_your_exp:.3f} {ci_str}"
                         + (f", N = {live_your_n}" if live_your_n else "")
                         + " · recomputed on current filter")
        pieces = [
            f"<b>📖 {lf.source}</b>",
            f"&nbsp;&nbsp;<code>{eq_str}</code>",
        ]
        # v0.8.34b+c: show LIVE literature R² on this filter (not the
        # published r2_ref which is for Verstraete's own dataset). Keep
        # r2_ref as a small grey footnote if it's available.
        if live_lit_r2 is not None:
            pieces.append(f"&nbsp;&nbsp;{r2_badge_html(live_lit_r2, prefix='Literature equation R² on this filter')}")
        if live_your_r2 is not None:
            pieces.append(r2_badge_html(live_your_r2, prefix='Live dataset R²'))
        if live_verdict:
            pieces.append(verdict_badge_html(live_verdict))
        published_note = ""
        if lf.r2_ref is not None:
            published_note = (
                f"<div style='font-size:10px;color:#888;padding:0 10px 6px 13px;'>"
                f"Published R² (from {lf.source}'s own dataset, n={lf.n_ref}): "
                f"{lf.r2_ref:.2f}</div>"
            )
        st.markdown(
            '<div style="font-size:12px;line-height:1.8;'
            'padding:6px 10px;border-left:3px solid #534AB7;'
            'background:rgba(83,74,183,0.05);margin:4px 0;">'
            + " ".join(pieces) + "</div>"
            + slope_compare
            + (f'<div style="font-size:11px;color:#888;'
                f'padding:0 10px 6px 13px;">{your_str}</div>'
                if your_str else "")
            + published_note,
            unsafe_allow_html=True,
        )

# Caption: show data-completeness so the user knows whether the
# "hide_uncategorized" toggle has anything to hide
if color_by:
    null_summary = []
    for g_label, g_df in [("A", df_a if enabled_a else pd.DataFrame()),
                            ("B", df_b if enabled_b else pd.DataFrame())]:
        if len(g_df) == 0 or color_by not in g_df.columns:
            continue
        usable = g_df.dropna(subset=[chosen_relation.x_col,
                                       chosen_relation.y_col])
        n_total = len(usable)
        n_null = usable[color_by].isna().sum()
        if n_null > 0:
            status = ("hidden" if hide_uncat
                       else "shown as grey '(uncategorized)'")
            null_summary.append(f"**{g_label}** has **{n_null}** of "
                                  f"{n_total} rows with no {color_by} value "
                                  f"({status})")
        else:
            null_summary.append(f"**{g_label}** has full {color_by} coverage "
                                  f"({n_total} rows)")
    if null_summary:
        st.caption("ℹ Data coverage on **" + color_by + "**: " +
                     " · ".join(null_summary))

# Display the equation+reliability table
# v0.8.33a fix: skip the fit-table machinery entirely in density (heatmap)
# mode — scatter_info doesn't contain a 'fits' key in that branch and the
# per-category fits don't apply when bars are bin counts, not points.
from lib.fitting import r2_band as _r2_band
if not density_view_active:
    fits = scatter_info["fits"]
    stats = scatter_info["stats"]

    # Real fits = non-None values NOT keyed under "_skipped:" (those are tracked separately)
    has_real_fits = any(v is not None and not (isinstance(k, str) and k.startswith("_skipped:"))
                          for k, v in fits.items())

    # v0.8.29: We no longer add a literature row to the fit table — the
    # literature fit has its own dedicated badge above with R²/verdict.
    # Showing it again here is redundant and the equation strings differ
    # (table uses our internal eq, badge uses the per-variant lit eq).
    if has_real_fits:
        # v0.8.29: friendly column header for the category column
        color_by_label_for_table = (
            {"Mission": "Mission", "EngineType": "Engine type",
             "LaunchMethod": "Launch method", "WingForm": "Wing form",
             "WingConfig": "Wing configuration", "BodyConfig": "Body configuration",
             "TailConfig": "Tail configuration", "Airframe": "Airframe",
             "OperationalRole": "Operational role", "SizeClassStd": "Size class",
             "Country": "Country"}.get(color_by, color_by)
            if color_by else "Source"
        )
        rel_rows = []
        if not fit_per_cat:
            if show_fit_a and fits.get("A"):
                f = fits["A"]
                rel_rows.append({
                    "Source": "Filter A (fitted)",
                    "Equation": f.equation,
                    "R²": f"{f.r_squared:.3f}",
                    "R² band": _r2_band(f.r_squared),
                    "n": f.n,
                    "Sample size band": f.reliability,
                })
            if show_fit_b and fits.get("B"):
                f = fits["B"]
                rel_rows.append({
                    "Source": "Filter B (fitted)",
                    "Equation": f.equation,
                    "R²": f"{f.r_squared:.3f}",
                    "R² band": _r2_band(f.r_squared),
                    "n": f.n,
                    "Sample size band": f.reliability,
                })
        else:
            # Per-category fits — keys in fits dict are category labels (not A/B)
            for cat_label, f in fits.items():
                if cat_label in ("A", "B") or f is None:
                    continue
                if cat_label.startswith("_skipped:"):
                    continue   # tracked separately below
                # Friendly label for known categorical columns
                if color_by in ("Mission", "EngineType", "LaunchMethod",
                                 "WingForm", "WingConfig", "BodyConfig",
                                 "TailConfig", "Airframe", "OperationalRole"):
                    cat_disp = code_to_label(color_by, cat_label)
                else:
                    cat_disp = cat_label
                rel_rows.append({
                    "Source": cat_disp,
                    "Equation": f.equation,
                    "R²": f"{f.r_squared:.3f}",
                    "R² band": _r2_band(f.r_squared),
                    "n": f.n,
                    "Sample size band": f.reliability,
                })
        # v1.0.0-limited / v0.8.34c-fix7: append the 95% prediction band's
        # center fit as its own row IF the band is enabled AND it isn't
        # an exact duplicate of an already-listed fit. Exact-match check
        # (no tolerance) per user direction — when "merge + only_show =
        # single category" makes the pooled fit identical to that single
        # category's fit, suppress the duplicate row.
        if band_fit is not None and show_ci_band:
            band_coef = band_fit["coef"]
            band_exp = band_fit["exp"]
            band_n = band_fit["n"]
            band_r2 = band_fit["r_squared"]
            # Build the equation string the same way fit_power_law produces it
            band_eq = f"Y = {band_coef:.3g} · X^{band_exp:.3f}"
            # Exact-match check across already-listed rows. Compare to
            # the underlying PowerLawFit objects in `fits` rather than
            # the formatted strings, so floating-point precision is preserved.
            is_redundant = False
            for f in fits.values():
                if f is None or not hasattr(f, 'coef'):
                    continue
                # Exact equality on coef, exp, AND n
                if f.coef == band_coef and f.exp == band_exp and f.n == band_n:
                    is_redundant = True
                    break
            if not is_redundant:
                # Compute R² band + sample-size band for the new row
                from lib.fitting import reliability_band as _reliability_band
                band_factor_disp = (10 ** (1.96 * band_sigma_log)
                                       if band_sigma_log else 1.0)
                rel_rows.append({
                    "Source": (f"A + B combined (95% band center)"
                                if (enabled_a and enabled_b)
                                else "95% band center"),
                    "Equation": (f"{band_eq}   (band ÷×{band_factor_disp:.1f}×)"
                                    if band_sigma_log else band_eq),
                    "R²": f"{band_r2:.3f}",
                    "R² band": _r2_band(band_r2),
                    "n": band_n,
                    "Sample size band": _reliability_band(band_n),
                })
        if rel_rows:
            st.markdown("**Fit Equations**")
            st.caption(
                "**R² band** = quality of the power-law fit "
                "(🟢 green ≥0.85, 🟡 amber 0.45–0.85, 🔴 red <0.45). "
                "**Sample size band** = how many points went into the fit "
                "(🟢 green ≥100, 🟡 amber 30–99, 🔴 red <30). "
                "A green sample-size with a red R² means lots of data went "
                "into a poor fit — mass alone doesn't predict the Y variable "
                "well for that subset. "
                "If the **95% prediction band** is on, its center line and "
                "÷×band-factor are listed as a separate row labeled "
                "*A + B combined (95% band center)* (suppressed when it "
                "would be an exact duplicate of an existing row)."
            )
            df_tab = pd.DataFrame(rel_rows)
            # v0.8.29: Color band cells (green / amber / red text on light bg)
            _BAND_STYLES = {
                "green": "color: #1B7A2A; font-weight: 700",
                "amber": "color: #B8870B; font-weight: 700",
                "red":   "color: #A23A2A; font-weight: 700",
                "literature": "color: #888888; font-style: italic",
            }
            def _band_style(v):
                return _BAND_STYLES.get(str(v).lower(), "")
            styled = df_tab.style.map(_band_style,
                                         subset=["R² band", "Sample size band"])
            st.dataframe(styled, hide_index=True, use_container_width=True)

    # Notify about categories that couldn't be fitted due to too few points
    # (outside the has_real_fits gate so it shows even when no categories qualified)
    if fit_per_cat:
        skipped = {k.replace("_skipped:", ""): v for k, v in fits.items()
                    if isinstance(k, str) and k.startswith("_skipped:")}
        if skipped:
            skipped_msg = ", ".join(
                f"**{cat}** (n={info['n']})" for cat, info in skipped.items()
            )
            st.caption(
                f"ℹ Categories without a fit (n<5 required): {skipped_msg}. "
                f"Their points are still shown in the scatter — only the "
                f"power-law fit is omitted because too few points produce an "
                f"unreliable line. Try expanding the filter or merging these "
                f"subcategories with similar ones using the merge controls above."
            )

    if stats:
        stat_msg = " · ".join(f"**{k}**: {v} points" for k, v in stats.items())
        st.caption(stat_msg)


# ---- Density Heatmap (own section) ----------------------------------------
# v0.8.33b: density-heatmap view is its own section, independent from the
# scatter block above. No color-by / merge / fit options here — those don't
# apply to a binned count view. Per-relation picker + axis-type + bin count.
st.divider()
st.subheader("Density Heatmap")
st.caption(
    "Binned 2D count of UAVs across the selected relation. Useful when the "
    "scatter has many overlapping points (1,344 platforms can stack into "
    "opaque clouds). Color saturation reads as density: pale = sparse, "
    "saturated = thick cluster. Color-by, merge, and fit options from the "
    "scatter above are intentionally NOT shown — they don't apply to a "
    "binned heatmap."
)

dh_col_rel, dh_col_axis, dh_col_bins = st.columns([3, 2, 2])
with dh_col_rel:
    # Same relation choices as the scatter section; ALL relations, default
    # rotates from the scatter pick for continuity.
    dh_rel_labels = {k: SIZING_RELATIONS[k].label for k in DEFAULT_RELATIONS}
    for k in SIZING_RELATIONS:
        if k not in dh_rel_labels:
            dh_rel_labels[k] = f"{SIZING_RELATIONS[k].label}  (sparse data)"
    dh_relation_key = st.selectbox(
        "Relation",
        options=list(dh_rel_labels.keys()),
        format_func=lambda k: dh_rel_labels[k],
        key="dh_relation",
    )
    dh_relation = get_relation(dh_relation_key)

with dh_col_axis:
    dh_axis_choice = st.radio(
        "Axis Type",
        options=["Default for relation", "Both log", "Both linear",
                 "Linear X / log Y", "Log X / linear Y"],
        horizontal=False, key="dh_axis_mode",
    )
    if dh_axis_choice == "Default for relation":
        dh_x_type = dh_relation.default_x_type
        dh_y_type = dh_relation.default_y_type
    elif dh_axis_choice == "Both log":
        dh_x_type, dh_y_type = "log", "log"
    elif dh_axis_choice == "Both linear":
        dh_x_type, dh_y_type = "linear", "linear"
    elif dh_axis_choice == "Linear X / log Y":
        dh_x_type, dh_y_type = "linear", "log"
    else:
        dh_x_type, dh_y_type = "log", "linear"

with dh_col_bins:
    dh_n_bins = st.select_slider(
        "Number of Bins (per axis)",
        options=[15, 20, 25, 30, 40, 50],
        value=30,
        key="dh_n_bins",
        help="More bins = finer resolution but lower count-per-cell. "
             "30 is a balanced default for 1,000+ platforms.",
    )
    dh_show_lit = st.checkbox(
        "Overlay Canonical Literature Fit",
        value=True, key="dh_show_lit",
        help="Draws the relation's default canonical equation as a dashed "
             "line across the heatmap (if one exists).",
    )

# Detect categorical-X relations — heatmap is only for numeric-numeric
_dh_is_categorical_x = not pd.api.types.is_numeric_dtype(
    df_full[dh_relation.x_col]
)
if _dh_is_categorical_x:
    st.info(
        f"ℹ The selected relation has a categorical X axis "
        f"({dh_relation.x_col}). Density heatmap is for numeric × numeric "
        "relations only — pick a different relation or see the scatter "
        "section above (which renders categorical X as a box plot)."
    )
else:
    # Build groups for the heatmap. Same A/B groups as the scatter block.
    dh_groups = []
    if enabled_a:
        dh_groups.append({"df": df_a, "name": "A", "color": COLOR_A})
    if enabled_b:
        dh_groups.append({"df": df_b, "name": "B", "color": COLOR_B})

    if dh_groups:
        from lib.density_heatmap import make_density_heatmap
        dh_fig, dh_info = make_density_heatmap(
            dh_relation, dh_groups,
            x_type=dh_x_type, y_type=dh_y_type,
            n_bins=dh_n_bins,
            show_canonical_fit=dh_show_lit,
            height=440,
        )
        st.plotly_chart(dh_fig, use_container_width=True)
        st.caption(
            f"Bins: {dh_n_bins} × {dh_n_bins} | "
            f"Max cell count: {dh_info['max_count']} UAVs | "
            f"Total points binned: {dh_info['n_total']:,}"
        )
    else:
        st.info("No filter is currently enabled. Enable Filter A or B above.")



# v1.0.0-limited: Filtered Rows tabs removed. The limited
# edition does not expose raw row data.
