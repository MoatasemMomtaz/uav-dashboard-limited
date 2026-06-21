"""Page 6 — Design-space explorer.

Free exploration of the dataset with three sub-views:

1. **Flexible scatter** — any X / Y / color / size combination
2. **Parallel coordinates** — 4-6 columns as parallel axes, lines per UAV,
   interactive brushing
3. **SPLOM** — scatter-plot matrix across 3-5 columns

Each sub-view honors the page-level quick filters above the tabs.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# v0.8.34b+c: enable 2x PNG export on every plotly chart in this page
from lib.chart_config import apply_default_export_config
apply_default_export_config('design-space')

import streamlit as st

import pandas as pd
import numpy as np
import plotly.graph_objects as go

from lib.loader import load_uav, NAME_COL
from lib.labels import friendly_format_func, code_to_label
from lib.explorer import (
    NUMERIC_LABELS, CATEGORICAL_LABELS,
    flexible_scatter, parallel_coordinates, splom,
)


# v0.8.34a: set_page_config removed — under st.navigation only the router (app.py) may call it.
# st.set_page_config(
#     page_title="Design-Space · UAV Explorer",
#     page_icon="🔭",
#     layout="wide",
#     initial_sidebar_state="collapsed",
# )

# The Design-space explorer has its own quick filters below.
# We don't render the global sidebar here — instead load the dataset directly.
df_full = load_uav()
filtered = df_full   # page-level filters narrow this further below

st.title("Design-Space Explorer")
st.caption(
    "Free exploration of the dataset. Pick any combination of axes, colors, "
    "and sizes — find clusters, outliers, and patterns. The sidebar filters "
    "apply throughout."
)

# Persistence note + reset button. All controls on this page keep their
# values when you navigate to other tabs and come back (Streamlit session
# state). The one thing that resets is which sub-tab is active (Flexible
# scatter / SPLOM / Parcoord) — that's a Streamlit limitation. Use the reset
# button to clear all this page's controls WITHOUT removing custom designs.
_reset_col1, _reset_col2 = st.columns([3, 1])
with _reset_col1:
    st.caption(
        "ℹ Your axis/color/filter selections here persist when you visit "
        "other tabs and return. (The active sub-tab may reset — that's a "
        "Streamlit limitation.)"
    )
with _reset_col2:
    if st.button("↺ Reset this page's controls", use_container_width=True,
                  help="Clears all axis/color/filter/brush selections on "
                       "this page. Does NOT remove your custom designs."):
        # Remove every Design-space widget key (prefixed ex_) EXCEPT the
        # custom-design store (explorer_customs).
        for k in list(st.session_state.keys()):
            if k.startswith("ex_"):
                del st.session_state[k]
        st.rerun()

if len(filtered) == 0:
    st.warning("No rows match the current filter. Loosen filters in the sidebar.")
    st.stop()


# ---- Page-level quick filters ---------------------------------------------
st.markdown("### Quick Filters")
st.caption(
    "These narrow the dataset *within* the design-space page only (on top of "
    "the global sidebar filters). Useful when you want to focus on, say, "
    "piston-engine UAVs only without resetting the sidebar."
)
qf1, qf2, qf3, qf4 = st.columns(4)
# v0.8.34c-fix1: friendly labels via code_to_label across all 4 quick filters
from lib.labels import code_to_label as _code_to_label
with qf1:
    qf_mission = st.multiselect(
        "Mission",
        sorted(filtered["Mission"].dropna().unique().tolist()),
        format_func=lambda v: _code_to_label("Mission", v),
        key="ex_qf_mission",
    )
with qf2:
    qf_engine = st.multiselect(
        "Engine type",
        sorted(filtered["EngineType"].dropna().unique().tolist()),
        format_func=lambda v: _code_to_label("EngineType", v),
        key="ex_qf_engine",
    )
with qf3:
    SIZE_ORDER = ["Nano/Micro", "Mini", "Small", "Tactical", "MALE", "HALE",
                   "HAPS", "Suspect"]
    sz_avail = filtered["SizeClassStd"].dropna().unique().tolist()
    qf_size = st.multiselect(
        "Size class",
        [s for s in SIZE_ORDER if s in sz_avail],
        format_func=lambda v: _code_to_label("SizeClassStd", v),
        key="ex_qf_size",
    )
with qf4:
    qf_launch = st.multiselect(
        "Launch method",
        sorted(filtered["LaunchMethod"].dropna().unique().tolist()),
        format_func=lambda v: _code_to_label("LaunchMethod", v),
        key="ex_qf_launch",
    )

# Second row: solar-only toggle + symmetric "exclude solar" toggle
qf5, qf6, _ = st.columns([1, 1, 2])
with qf5:
    qf_solar_only = st.checkbox(
        "☀ Solar-only (isolate solar-engine UAVs)",
        value=False, key="ex_qf_solar_only",
        help="Restricts to UAVs where EngineType=S OR SizeClassStd=HAPS. "
             "Useful when investigating solar UAV scaling relations.",
    )
with qf6:
    qf_exclude_solar = st.checkbox(
        "Exclude solar (drop S and HAPS)",
        value=False, key="ex_qf_exclude_solar",
        help="Removes solar-engine UAVs and HAPS from the dataset. Useful "
             "when fitting power laws to conventional fixed-wing aircraft.",
        disabled=qf_solar_only,
    )

# Apply
page_filtered = filtered
if qf_mission:
    page_filtered = page_filtered[page_filtered["Mission"].isin(qf_mission)]
if qf_engine:
    page_filtered = page_filtered[page_filtered["EngineType"].isin(qf_engine)]
if qf_size:
    page_filtered = page_filtered[page_filtered["SizeClassStd"].isin(qf_size)]
if qf_launch:
    page_filtered = page_filtered[page_filtered["LaunchMethod"].isin(qf_launch)]
if qf_solar_only:
    solar_mask = ((page_filtered["EngineType"] == "S")
                   | (page_filtered["SizeClassStd"] == "HAPS"))
    page_filtered = page_filtered[solar_mask]
elif qf_exclude_solar:
    not_solar = ((page_filtered["EngineType"] != "S")
                  & (page_filtered["SizeClassStd"] != "HAPS"))
    page_filtered = page_filtered[not_solar | page_filtered["EngineType"].isna()]

n_after = len(page_filtered)
n_global = len(filtered)
if n_after < n_global:
    st.caption(
        f"📊 **{n_after:,}** rows after page filters · "
        f"({n_global:,} from sidebar, narrowed by {n_global - n_after:,} here)."
    )
if n_after == 0:
    st.warning("Page filters left 0 rows. Loosen them above.")
    st.stop()


# Custom design state for THIS page (separate from Compare Platforms)
if "explorer_customs" not in st.session_state:
    st.session_state["explorer_customs"] = []
customs = st.session_state["explorer_customs"]


def custom_design_form_explorer():
    """Form for adding a custom design.
    v0.8.34c-fix4: when designs exist, the delete-chip list is now ALWAYS
    VISIBLE (not buried in a collapsed expander). Previously a user with
    multiple designs couldn't easily find the delete button because the
    expander was collapsed by default. Now the chips (each with its own
    🗑 button) render above the "add another" expander."""
    if not customs:
        # Form open by default if no customs exist yet
        st.markdown("### ⚐ Custom Design")
        _render_custom_form_inline()
    else:
        # Always show the chip row + delete buttons; the form to add
        # another custom design goes inside a collapsed expander below.
        st.markdown(f"### ⚐ Custom Designs ({len(customs)} entered)")
        _render_custom_chips()
        with st.expander(
            "➕ Add another custom design",
            expanded=False,
        ):
            _render_custom_form_inline()


def _render_custom_chips():
    st.caption(
        "Each row below shows a saved custom design. Click 🗑 to "
        "**remove** it from all charts. This action cannot be undone."
    )
    # One-row layout, up to 5 chips per row
    n_per_row = 5
    rows = (len(customs) + n_per_row - 1) // n_per_row
    for r in range(rows):
        start = r * n_per_row
        end = min(start + n_per_row, len(customs))
        cols = st.columns(n_per_row)
        for j, i in enumerate(range(start, end)):
            cd = customs[i]
            with cols[j]:
                cname = cd.get("name", f"Custom {i + 1}")
                if st.button(f"🗑 ⚐ {cname}",
                             key=f"explorer_unpick_{i}",
                             use_container_width=True,
                             help=f"Click to REMOVE '{cname}' from all "
                                  "charts. This action cannot be undone."):
                    st.session_state["explorer_customs"].pop(i)
                    st.rerun()


def _render_custom_form_inline():
    with st.form(f"explorer_custom_form_{len(customs)}"):
        cd_name = st.text_input("Name *", value=f"My candidate {len(customs)+1}",
                                  key=f"explorer_cd_name_{len(customs)}")
        c1, c2, c3 = st.columns(3)
        with c1:
            cd_mtow = st.number_input("MTOW (kg)", min_value=0.0, value=None,
                                       step=10.0, format="%.2f",
                                       key=f"explorer_cd_mtow_{len(customs)}")
            cd_payload = st.number_input("Payload (kg)", min_value=0.0,
                                          value=None, step=1.0, format="%.2f",
                                          key=f"explorer_cd_payload_{len(customs)}")
            cd_speed = st.number_input("Max speed (km/h)", min_value=0.0,
                                        value=None, step=10.0, format="%.1f",
                                        key=f"explorer_cd_speed_{len(customs)}")
        with c2:
            cd_endurance = st.number_input("Endurance (h)", min_value=0.0,
                                            value=None, step=0.5, format="%.2f",
                                            key=f"explorer_cd_endur_{len(customs)}")
            cd_range = st.number_input("Range (km)", min_value=0.0, value=None,
                                        step=10.0, format="%.1f",
                                        key=f"explorer_cd_range_{len(customs)}")
            cd_cruise = st.number_input("Cruise speed (km/h)", min_value=0.0,
                                         value=None, step=10.0, format="%.1f",
                                         key=f"explorer_cd_cruise_{len(customs)}")
        with c3:
            cd_wingspan = st.number_input("Wingspan (m)", min_value=0.0,
                                           value=None, step=0.1, format="%.2f",
                                           key=f"explorer_cd_span_{len(customs)}")
            cd_length = st.number_input("Length (m)", min_value=0.0, value=None,
                                         step=0.1, format="%.2f",
                                         key=f"explorer_cd_len_{len(customs)}")
            cd_engpower = st.number_input("Eng power (hp)", min_value=0.0,
                                           value=None, step=1.0, format="%.2f",
                                           key=f"explorer_cd_pow_{len(customs)}")

        submitted = st.form_submit_button("Add to scatters")
        if submitted:
            if not cd_name.strip():
                st.error("Please give the design a name.")
            else:
                custom = {
                    "name": cd_name.strip(),
                    "MTOW_kg": cd_mtow,
                    "Payload_kg": cd_payload,
                    "Endurance_h": cd_endurance,
                    "Range_km": cd_range,
                    "MaxSpeed_kmh": cd_speed,
                    "CruiseSpeed_kmh": cd_cruise,
                    "Wingspan_m": cd_wingspan,
                    "Length_m": cd_length,
                    "EngPower_hp": cd_engpower,
                }
                # Derived columns — same logic as UAV Profile and Compare
                # Platforms so the custom appears on every relevant axis.
                if cd_cruise and cd_endurance:
                    custom["DerivedRange_km"] = cd_cruise * cd_endurance
                # BestRange: user's typed range if any, else cruise × endurance
                if cd_range:
                    custom["BestRange_km"] = cd_range
                elif custom.get("DerivedRange_km"):
                    custom["BestRange_km"] = custom["DerivedRange_km"]
                # Payload × endurance product
                if cd_payload and cd_endurance:
                    custom["PayloadEnduranceProduct_kgh"] = cd_payload * cd_endurance
                # v0.8.34c-fix1: Mission Productivity FOMs for custom designs.
                # Without these, the candidate star wasn't appearing on the
                # Mission Productivity (Cruise) or (Max) scatters. Same
                # convention as the dataset: Speed × Endurance × Payload.
                if cd_cruise and cd_endurance and cd_payload:
                    custom["MissionProductivity_Cruise_kgkm"] = (
                        cd_cruise * cd_endurance * cd_payload)
                if cd_speed and cd_endurance and cd_payload:
                    custom["MissionProductivity_Max_kgkm"] = (
                        cd_speed * cd_endurance * cd_payload)
                # Estimated flag — always False for custom designs (user
                # entered the values directly, no fallback applied).
                custom["MissionProductivity_Cruise_kgkm_estimated"] = False
                # Payload fraction
                if cd_payload and cd_mtow:
                    custom["PayloadFraction"] = cd_payload / cd_mtow
                # Power loading
                if cd_engpower and cd_mtow:
                    custom["PowerLoading_hp_per_kg"] = cd_engpower / cd_mtow
                st.session_state["explorer_customs"].append(custom)
                st.success(f"Added '{cd_name.strip()}'")
                st.rerun()


custom_design_form_explorer()


# ---- Tab layout for the three views ----------------------------------------
tab_scatter, tab_splom, tab_parcoord = st.tabs([
    "🟣 Flexible scatter", "🔲 Scatter matrix (SPLOM)", "📊 Parallel coordinates"
])


# ---- Tab 1: Flexible scatter -----------------------------------------------
with tab_scatter:
    st.caption(
        "Pick any X, Y, color-by, and size-by columns. Log/linear toggle per axis. "
        "Custom designs overlay as ⚐ markers."
    )

    with st.expander("ℹ About the range columns (read me)"):
        st.markdown("""
The dataset has **three distinct range fields** + one composite:

| Column | What it is |
|---|---|
| **Data-link range** (`Range_km`) | The number from the source data sheet. **Often the control-link / communication radius**, not the ferry range. Most published "range" specs for tactical UAVs are this. |
| **Verified range** (`ActualRange_km`) | The publisher-confirmed maximum range, when published as a separate figure from the comm radius. About 12% of rows have this. |
| **Derived range** (`DerivedRange_km`) | `CruiseSpeed × Endurance`. Pure derivation; the endurance-limited maximum range. |
| **Best-estimate range** (`BestRange_km`) | The column to use for analysis. Picks the most credible: `Verified` if present → else `Data-link` when it agrees with `Derived` (±30%) → else `Derived` when `Data-link` looks like a comm radius (<50% of derived) → else falls back to `Data-link`. |

**Recommended**: use **Best-estimate range** for any analysis. The other columns are there for transparency / data-source auditing.
""")

    cs1, cs2, cs3 = st.columns(3)
    with cs1:
        x_col = st.selectbox(
            "X axis",
            options=list(NUMERIC_LABELS.keys()),
            format_func=lambda c: NUMERIC_LABELS[c],
            index=0,    # MTOW_kg
            key="ex_x_col",
        )
    with cs2:
        y_col = st.selectbox(
            "Y axis",
            options=list(NUMERIC_LABELS.keys()),
            format_func=lambda c: NUMERIC_LABELS[c],
            index=2,    # Endurance_h
            key="ex_y_col",
        )
    with cs3:
        cb_opts = ["(none)"] + list(CATEGORICAL_LABELS.keys())
        color_by = st.selectbox(
            "Color by",
            options=cb_opts,
            format_func=lambda c: "(none)" if c == "(none)" else CATEGORICAL_LABELS[c],
            index=0,
            key="ex_color_by",
        )
        color_by = None if color_by == "(none)" else color_by
    size_by = None    # size-by control removed in v0.8.10 (not useful)

    ca1, ca2, ca3 = st.columns([1, 1, 2])
    with ca1:
        x_type = st.radio("X scale", ["log", "linear"], horizontal=True,
                           index=0, key="ex_x_type")
    with ca2:
        y_type = st.radio("Y scale", ["log", "linear"], horizontal=True,
                           index=0, key="ex_y_type")
    with ca3:
        if color_by:
            hide_uncat = st.checkbox(
                "Hide rows with no value on color column",
                value=True, key="ex_hide_uncat",
                help="When unchecked, rows missing data on the color column "
                     "appear in a '(none)' category.",
            )
            show_fits = st.checkbox(
                "Fit a power-law per category (shown as dashed line)",
                value=False, key="ex_show_fits",
                help="Fits Y = A · X^B per category. "
                     "Uncategorized rows are never fitted. "
                     "If you've merged subcategories below, fits are computed "
                     "on the merged group.",
            )
        else:
            hide_uncat = False
            show_fits = False

        # v1.0.0-limited / v0.8.34c-fix8: prediction band toggle. Same
        # behavior as Compare Filters — wraps the live pooled fit with
        # a 95% prediction band based on log-residual stdev.
        show_pred_band = st.checkbox(
            "Show 95% prediction band (where UAVs scatter)",
            value=False, key="ex_show_pred_band",
            help="95% prediction band around the pooled fit (all visible "
                 "points). Width ∝ residual scatter: wide for messy clouds, "
                 "tight for clean ones. Computed from log-space residual stdev: "
                 "edges at log10(Y_pred) ± 1.96·σ.",
        )

    # ---- Literature fit overlay (when X/Y match a known sizing relation) ---
    # Detect whether the chosen X/Y combination corresponds to a literature
    # relation in lib/relations.py. If so, offer to overlay one of the
    # available variants (Verstraete All/Piston/Battery/etc., or Voskuijl
    # LM variants when Mission filter = LM).
    from lib.relations import SIZING_RELATIONS, applicable_literature_fits
    from lib.r2_badge import r2_badge_html, verdict_badge_html
    matching_rel = None
    for rel in SIZING_RELATIONS.values():
        if rel.x_col == x_col and rel.y_col == y_col \
           and (rel.canonical_coefficient is not None
                 or len(rel.literature_fits) > 0):
            matching_rel = rel
            break
    literature_fit = None
    flex_chosen_lit_fit = None
    if matching_rel:
        # Scope from the page-level quick filters (qf_mission, qf_engine)
        active_missions = list(qf_mission) if qf_mission else None
        active_engines = list(qf_engine) if qf_engine else None
        applicable = applicable_literature_fits(
            matching_rel,
            active_engines=active_engines,
            active_missions=active_missions,
        )
        # Show ALL variants in the picker for transparency (auto-default to
        # first applicable; user can pick any other).
        all_variants = list(matching_rel.literature_fits)
        if all_variants:
            NONE_LIT = "(none — no literature overlay)"
            # v0.8.29: option label = source name only (no scope duplication)
            lit_options = [NONE_LIT] + [lf.source for lf in all_variants]
            # v0.8.29: default = (none); user explicitly picks
            default_idx = 0
            chosen_lit_label = st.selectbox(
                "📖 Literature fit",
                options=lit_options, index=default_idx,
                key=f"ex_lit_choice_{matching_rel.key}",
                help="Pick a published equation to overlay.",
            )
            if chosen_lit_label != NONE_LIT:
                idx = lit_options.index(chosen_lit_label) - 1
                flex_chosen_lit_fit = all_variants[idx]
                literature_fit = {
                    "coef": flex_chosen_lit_fit.coef,
                    "exp": flex_chosen_lit_fit.exp,
                    "label": flex_chosen_lit_fit.source,
                }
                # Don't auto-disable the per-group fits — user may want both
                # overlays visible (literature dashed + per-group solid)

    # --- Subcategory merging UI (only when color_by is set) ---
    merge_categories = None
    only_show_cats = None
    if color_by and color_by in page_filtered.columns:
        with st.expander(
            "🔀 Merge subcategories / restrict to specific categories",
            expanded=False,
        ):
            st.caption(
                "**Merge** combines multiple subcategory labels into one "
                "(e.g. merge `T`+`R`+`e`+`Polyhedral` into 'fixed'). Up to **3 "
                "merge groups** can be active at once. The merged group is "
                "treated as one category for color, symbol, and fitting. "
                "**Show only** restricts the visible categories."
            )

            # Live unique values of the color column on page_filtered
            unique_cats = (page_filtered[color_by].dropna().astype(str)
                            .unique().tolist())
            unique_cats.sort()

            # Build up to 3 merge groups
            merge_categories = {}
            _fmt = friendly_format_func(color_by)
            for i in range(1, 4):
                st.markdown(f"**Merge group {i}** *(optional)*")
                m_left, m_right = st.columns([2, 1])
                with m_left:
                    available = [c for c in unique_cats
                                  if c not in merge_categories]
                    merge_src = st.multiselect(
                        f"Merge these {CATEGORICAL_LABELS.get(color_by, color_by)} values…",
                        options=available,
                        default=[],
                        format_func=_fmt,
                        key=f"ex_merge_src_{color_by}_{i}",
                    )
                with m_right:
                    merge_dst = st.text_input(
                        "…into this label",
                        value=f"merged{i}" if i > 1 else "merged",
                        key=f"ex_merge_dst_{color_by}_{i}",
                    )
                if merge_src and merge_dst.strip():
                    label = merge_dst.strip()
                    for src in merge_src:
                        merge_categories[src] = label

            if not merge_categories:
                merge_categories = None

            # 'Only show' multiselect — uses POST-merge category names.
            # Show friendly labels for un-merged codes; merged labels show
            # as-is (they're user-typed names).
            post_merge_options = sorted(set(
                (merge_categories or {}).get(c, c) for c in unique_cats
            ))

            def _fmt_only_show(v):
                # If v is a known code for this column, show friendly name;
                # otherwise it's a user merge label — show as-is.
                lbl = code_to_label(color_by, v)
                return lbl if lbl != v else v

            only_show_cats_pick = st.multiselect(
                f"Show only these (merged) categories — leave empty for all",
                options=post_merge_options,
                default=[],
                format_func=_fmt_only_show,
                key=f"ex_only_show_{color_by}",
            )
            only_show_cats = only_show_cats_pick if only_show_cats_pick else None

    fig, n_plot, size_info = flexible_scatter(
        page_filtered, x_col=x_col, y_col=y_col,
        color_by=color_by, size_by=size_by,
        x_type=x_type, y_type=y_type,
        custom_points=customs,
        cat_label_map=(friendly_format_func(color_by) if color_by else None),
        hide_uncategorized=hide_uncat,
        merge_categories=merge_categories,
        only_show_categories=only_show_cats,
        show_fits=show_fits,
        literature_fit=literature_fit,
        height=560,
    )

    # v1.0.0-limited / v0.8.34c-fix8: 95% PREDICTION BAND for Flex scatter.
    # Same machinery as Compare Filters — pool the visible evidence (after
    # color_by + merge + only_show), refit, and render a band based on
    # log-residual stdev. The band wraps the pooled fit; high R² + tight
    # cluster = narrow band, low R² + scattered data = wide.
    if show_pred_band:
        try:
            import plotly.graph_objects as go_band
            from lib.fitting import fit_power_law_with_ci, prediction_band
            import numpy as _np_band

            # Pool the visible evidence
            band_sub = page_filtered[[x_col, y_col]].copy()
            if color_by and color_by in page_filtered.columns:
                band_sub[color_by] = page_filtered[color_by]
            band_sub = band_sub.dropna(subset=[x_col, y_col])
            # For log axes, drop non-positive
            if x_type == "log":
                band_sub = band_sub[band_sub[x_col] > 0]
            if y_type == "log":
                band_sub = band_sub[band_sub[y_col] > 0]
            # Apply the same merge + only_show filtering used by the scatter
            if color_by and color_by in band_sub.columns:
                if merge_categories:
                    band_sub[color_by] = (band_sub[color_by].astype("object")
                                            .replace(merge_categories))
                if only_show_cats:
                    band_sub = band_sub[band_sub[color_by].astype(str)
                                          .isin([str(c) for c in only_show_cats])]
                if hide_uncat:
                    band_sub = band_sub[band_sub[color_by].notna()
                                          & (band_sub[color_by].astype(str) != "")]

            if len(band_sub) >= 5 and x_type == "log" and y_type == "log":
                band_fit_flex = fit_power_law_with_ci(
                    band_sub[x_col], band_sub[y_col])
                if band_fit_flex is not None:
                    x_min_b = band_sub[x_col].min()
                    x_max_b = band_sub[x_col].max()
                    if x_min_b > 0:
                        xs_b = _np_band.logspace(
                            _np_band.log10(x_min_b), _np_band.log10(x_max_b), 80)
                        y_lo_b, y_hi_b, sigma_log_b = prediction_band(
                            band_sub[x_col], band_sub[y_col],
                            band_fit_flex["coef"], band_fit_flex["exp"],
                            xs_b, confidence=0.95)
                        y_mid_b = (band_fit_flex["coef"]
                                     * xs_b ** band_fit_flex["exp"])
                        band_factor_b = (10 ** (1.96 * sigma_log_b)
                                            if sigma_log_b else 1.0)
                        band_color_b = "rgba(80, 80, 200, 0.13)"
                        line_color_b = "rgba(50, 50, 180, 0.95)"
                        fig.add_trace(go_band.Scatter(
                            x=xs_b, y=y_lo_b, mode="lines",
                            name="95% prediction: lower",
                            line=dict(color=line_color_b, width=1, dash="dot"),
                            hovertemplate=(
                                f"<b>95% prediction band — lower</b><br>"
                                f"{x_col}: %{{x:,.3g}}<br>"
                                f"Y: %{{y:,.3g}}<extra></extra>"
                            ),
                            legendgroup="pred_band",
                            legendgrouptitle_text="95% prediction band",
                        ))
                        fig.add_trace(go_band.Scatter(
                            x=xs_b, y=y_hi_b, mode="lines",
                            name="95% prediction: upper",
                            line=dict(color=line_color_b, width=1, dash="dot"),
                            fill="tonexty",
                            fillcolor=band_color_b,
                            hovertemplate=(
                                f"<b>95% prediction band — upper</b><br>"
                                f"{x_col}: %{{x:,.3g}}<br>"
                                f"Y: %{{y:,.3g}}<extra></extra>"
                            ),
                            legendgroup="pred_band",
                            legendgrouptitle_text="95% prediction band",
                        ))
                        fig.add_trace(go_band.Scatter(
                            x=xs_b, y=y_mid_b, mode="lines",
                            name=(f"Live fit (N={band_fit_flex['n']}, "
                                    f"R²={band_fit_flex['r_squared']:.2f}, "
                                    f"band ÷×{band_factor_b:.1f}×)"),
                            line=dict(color=line_color_b, width=2.5),
                            hovertemplate=(
                                f"<b>Live fit</b> Y = {band_fit_flex['coef']:.3g}"
                                f" · X^{band_fit_flex['exp']:.3f}<br>"
                                f"{x_col}: %{{x:,.3g}}<br>"
                                f"{y_col}: %{{y:,.3g}}<extra></extra>"
                            ),
                            legendgroup="pred_band",
                        ))
            elif show_pred_band and (x_type != "log" or y_type != "log"):
                st.caption(
                    "ℹ The 95% prediction band requires both X and Y on "
                    "**log scale** (the underlying power-law fit is fitted "
                    "in log-log space). Switch both scales to log to see it."
                )
        except Exception as _band_err:
            st.caption(f"⚠ Prediction band could not be rendered: {_band_err}")

    st.plotly_chart(fig, use_container_width=True)

    # v0.8.26: Literature-fit badge
    if flex_chosen_lit_fit is not None:
        lf = flex_chosen_lit_fit
        ci_lo, ci_hi = lf.your_ci
        ci_str = (f"[{ci_lo:.3f}, {ci_hi:.3f}]"
                   if ci_lo is not None and ci_hi is not None else "")
        if abs(lf.exp) < 1e-9:
            eq_str = f"Y = {lf.coef:g} (mean)"
        else:
            eq_str = f"Y = {lf.coef:g} · X^{lf.exp:.3f}"
        your_str = ""
        if lf.your_exp is not None:
            your_str = (f"This dataset: exponent = {lf.your_exp:.3f} {ci_str}"
                         + (f", N = {lf.your_n}" if lf.your_n else ""))
        pieces = [
            f"<b>📖 {lf.source}</b>",
            f"&nbsp;&nbsp;<code>{eq_str}</code>",
        ]
        if lf.r2_ref is not None:
            pieces.append(f"&nbsp;&nbsp;{r2_badge_html(lf.r2_ref, prefix='Literature R²')}")
        if lf.your_r2 is not None:
            pieces.append(r2_badge_html(lf.your_r2, prefix='This dataset R²'))
        if lf.verdict:
            pieces.append(verdict_badge_html(lf.verdict))
        st.markdown(
            '<div style="font-size:12px;line-height:1.8;'
            'padding:6px 10px;border-left:3px solid #534AB7;'
            'background:rgba(83,74,183,0.05);margin:4px 0;">'
            + " ".join(pieces) + "</div>"
            + (f'<div style="font-size:11px;color:#888;'
                f'padding:0 10px 6px 13px;">{your_str}</div>'
                if your_str else ""),
            unsafe_allow_html=True,
        )

    captions = [
        f"Showing {n_plot:,} of {len(page_filtered):,} page_filtered rows "
        f"(NaN values dropped on selected axes)."
    ]
    if size_info and size_info.get("label"):
        captions.append(
            f"Marker size encodes **{size_info['label']}** "
            f"(small ≈ {size_info['small']:,.1f}, large ≈ "
            f"{size_info['large']:,.1f}; log-scaled)."
        )
    st.caption(" ".join(captions))

    # Fit equations table — only shown when there ARE per-group/per-category
    # fits to display. v0.8.29: literature row removed (it has its own badge
    # above) — showing it here was redundant.
    from lib.fitting import r2_band as _r2_band
    table_rows = []
    if size_info and size_info.get("fits"):
        # Translate category labels via code_to_label for known categoricals
        if color_by in ("Mission", "EngineType", "LaunchMethod",
                         "WingForm", "WingConfig", "BodyConfig",
                         "TailConfig", "Airframe", "OperationalRole"):
            from lib.labels import code_to_label as _code_to_label
            xlate = lambda v: _code_to_label(color_by, v)
        else:
            xlate = lambda v: v
        for r in size_info["fits"]:
            r2_val = r.get("r_squared")
            table_rows.append({
                color_by or "Category": xlate(r["category"]),
                "Equation": r["equation"],
                "R²": f"{r2_val:.3f}" if r2_val is not None else "—",
                "R² band": (_r2_band(r2_val) if r2_val is not None else "—"),
                "n": r["n"],
                "Sample size band": r["reliability"],
            })
    if table_rows:
        st.markdown("**Fit Equations**")
        st.caption(
            "**R² band** = quality of the power-law fit "
            "(🟢 green ≥0.85, 🟡 amber 0.45–0.85, 🔴 red <0.45). "
            "**Sample size band** = how many points went into the fit "
            "(🟢 green ≥100, 🟡 amber 30–99, 🔴 red <30). "
            "Don't confuse the two — a large sample with poor R² means "
            "the predictor doesn't explain Y well for that subset."
        )
        df_tab = pd.DataFrame(table_rows)
        _BAND_STYLES = {
            "green": "color: #1B7A2A; font-weight: 700",
            "amber": "color: #B8870B; font-weight: 700",
            "red":   "color: #A23A2A; font-weight: 700",
        }
        def _band_style(v):
            return _BAND_STYLES.get(str(v).lower(), "")
        styled = df_tab.style.map(_band_style,
                                     subset=["R² band", "Sample size band"])
        st.dataframe(styled, hide_index=True, use_container_width=True)

    # Coverage warning if X or Y is sparse
    sparse_checks = [(x_col, "X"), (y_col, "Y")]
    if color_by:
        sparse_checks.append((color_by, "color"))
    if size_by:
        sparse_checks.append((size_by, "size"))
    sparse = []
    for c, lbl in sparse_checks:
        n_avail = page_filtered[c].notna().sum()
        if n_avail < 0.3 * len(page_filtered):
            sparse.append(f"**{c}** ({lbl}): only {n_avail} of {len(page_filtered)} "
                          f"page_filtered rows have data")
    if sparse:
        st.caption("⚠ Sparse data: " + " · ".join(sparse))


# ---- Tab 2: Parallel coordinates -------------------------------------------
with tab_parcoord:
    with st.expander("ℹ How to use parallel coordinates",
                      expanded=False):
        st.markdown("""
**Three-stage workflow:**

1. **Pick a preset or your own columns.** Separate design/output variables
   from constraint/quality measures.
2. **Color by your objective.** Set "Color lines by" to your design objective
   (e.g. Endurance for ISR, BestRange for transport). The viridis gradient
   shows which axis-pairs the objective flows through — those are your
   design rules.
3. **Brush down to feasible designs.** Use the sliders below to narrow each
   axis. Watch the "Survivors" panel below shrink to your shortlist.

**Tips:**
- Reorder axes (drag axis labels in the plot) to put coupled variables next
  to each other. Correlations only show up between **adjacent** axes.
- Cycle the color driver through different objectives — pairings that look
  flat with one driver may pop with another.
- The plot dims rows that have **any** missing value on the selected columns.
  A caption below tells you how many rows survived.
""")

    st.caption(
        "ℹ The **Custom design point** (set in the Flexible scatter tab) is "
        "not shown on parallel coordinates — Plotly's parcoord renders one "
        "line per data row and does not support overlay markers."
    )

    # ----- Stage 0: Preset workflows -----
    PRESETS = {
        "Custom (pick your own)": dict(cols=None, color_by=None, color_mode=None),
        "ISR mission (color by Endurance)": dict(
            cols=["MTOW_kg", "Payload_kg", "Endurance_h", "BestRange_km",
                   "MaxSpeed_kmh", "Wingspan_m"],
            color_by="Endurance_h", color_mode="continuous",
        ),
        "Long-range transport (color by BestRange)": dict(
            cols=["MTOW_kg", "Payload_kg", "Endurance_h", "BestRange_km",
                   "CruiseSpeed_kmh", "Wingspan_m"],
            color_by="BestRange_km", color_mode="continuous",
        ),
        "Heavy payload (color by Payload)": dict(
            cols=["MTOW_kg", "Payload_kg", "Endurance_h", "Wingspan_m",
                   "Length_m", "MaxSpeed_kmh"],
            color_by="Payload_kg", color_mode="continuous",
        ),
        "Engine regime check (color by EngineType)": dict(
            cols=["MTOW_kg", "Endurance_h", "BestRange_km", "MaxSpeed_kmh"],
            color_by="EngineType", color_mode="categorical",
        ),
    }

    preset_key = st.selectbox(
        "Workflow preset",
        options=list(PRESETS.keys()),
        index=1,    # default to ISR — most common UAV mission
        key="ex_pc_preset",
    )
    preset = PRESETS[preset_key]

    # ----- Stage 1: Column picker (defaulted from preset) -----
    DEFAULT_PC_COLS = preset["cols"] or ["MTOW_kg", "Payload_kg", "Endurance_h",
                                          "BestRange_km", "MaxSpeed_kmh",
                                          "Wingspan_m"]

    pc_cols = st.multiselect(
        "Columns to plot as parallel axes",
        options=list(NUMERIC_LABELS.keys()),
        default=[c for c in DEFAULT_PC_COLS if c in NUMERIC_LABELS],
        format_func=lambda c: NUMERIC_LABELS[c],
        key=f"ex_pc_cols_{preset_key}",   # remount when preset changes
    )

    # Warn about sparse columns — those drastically reduce the row count
    # because parallel coords drops rows missing ANY selected column.
    if pc_cols:
        sparse_warnings = []
        for c in pc_cols:
            n_with = page_filtered[c].notna().sum()
            pct = 100 * n_with / max(len(page_filtered), 1)
            if pct < 25:
                sparse_warnings.append(
                    f"**{NUMERIC_LABELS.get(c, c)}**: only {pct:.0f}% "
                    f"coverage ({n_with:,} of {len(page_filtered):,} rows)"
                )
        if sparse_warnings:
            st.warning(
                "⚠ Sparse columns picked: " + "; ".join(sparse_warnings) +
                ". Parallel coords drops rows missing ANY selected column, "
                "so the chart may show very few lines. Consider removing "
                "these from the axes list — the brush still works on them."
            )

    # ----- Stage 2: Color driver -----
    color_cols = st.columns([1, 2])
    with color_cols[0]:
        color_mode_choice = st.radio(
            "Color by what kind of variable?",
            options=["Categorical (e.g. Engine type)",
                      "Continuous / objective (e.g. Endurance)",
                      "No coloring"],
            index=(1 if preset.get("color_mode") == "continuous"
                   else 0 if preset.get("color_by") else 2),
            key=f"ex_pc_color_mode_{preset_key}",
        )

    with color_cols[1]:
        if color_mode_choice.startswith("Continuous"):
            color_by = st.selectbox(
                "Objective column (color gradient applied)",
                options=list(NUMERIC_LABELS.keys()),
                index=list(NUMERIC_LABELS.keys()).index(preset["color_by"])
                      if preset.get("color_by") in NUMERIC_LABELS else 2,
                format_func=lambda c: NUMERIC_LABELS[c],
                key=f"ex_pc_color_num_{preset_key}",
            )
            color_mode = "continuous"
        elif color_mode_choice.startswith("Categorical"):
            color_by = st.selectbox(
                "Category column",
                options=list(CATEGORICAL_LABELS.keys()),
                index=list(CATEGORICAL_LABELS.keys()).index(preset["color_by"])
                      if preset.get("color_by") in CATEGORICAL_LABELS else 1,
                format_func=lambda c: CATEGORICAL_LABELS[c],
                key=f"ex_pc_color_cat_{preset_key}",
            )
            color_mode = "categorical"
        else:
            color_by = None
            color_mode = "categorical"

    # ----- Stage 3: Brushing sliders (the VizCraft "feasibility" step) -----
    st.markdown("**Brush Controls**")
    st.caption(
        "Narrow each column to keep only UAVs in your acceptable range. Each "
        "slider's full range is fixed by the **page-filtered** dataset above, "
        "so sliding one slider does not change the limits of the others. "
        "Sliders are linear; small steps let you reach low values even when "
        "the range is wide."
    )
    # Each slider's bounds come from the PAGE-FILTERED data, computed once,
    # not from the brush-narrowed data. This was the source of the v0.8 bug
    # where moving one slider reset the others.
    SLIDER_BOUNDS = {}
    for c in pc_cols:
        series = page_filtered[c].dropna()
        if len(series) >= 2:
            v_min, v_max = float(series.min()), float(series.max())
            # Step ~1/1000 of the range gives ~3-4 significant digits on
            # the full slider, fine enough to reach small values even on
            # wide-range columns like MTOW (0.5 to 20000 kg).
            span = v_max - v_min
            if span > 0:
                step = span / 1000
                # Round step to a clean value for nicer display
                # IMPORTANT: keep step as float (Streamlit requires matching types).
                if step < 0.01: step = 0.001
                elif step < 0.1: step = 0.01
                elif step < 1:   step = 0.1
                elif step < 10:  step = 1.0
                elif step < 100: step = 10.0
                else:            step = 100.0
            else:
                step = 1.0
            SLIDER_BOUNDS[c] = (v_min, v_max, float(step))

    brush_filtered = page_filtered.copy()
    if pc_cols:
        # Wide-range columns (Endurance + BestRange) get their own row for
        # easier value selection. Others paired 2-per-row.
        FULL_WIDTH_COLS = {"Endurance_h", "BestRange_km", "Range_km",
                            "DerivedRange_km", "ActualRange_km"}
        full_width_cols = [c for c in pc_cols if c in FULL_WIDTH_COLS]
        paired_cols = [c for c in pc_cols if c not in FULL_WIDTH_COLS]

        def _render_slider(c, layout="full"):
            """Render a brush slider with paired numeric min/max inputs.

            The slider gives quick visual narrowing; the numeric boxes let
            the user type precise values (especially helpful for wide ranges
            like 0.1-5000h endurance where 1% of slider travel is 50h).

            Slider and numeric inputs are kept in sync via on_change callbacks
            writing to a shared session_state slot.
            """
            if c not in SLIDER_BOUNDS:
                return
            v_min, v_max, step = SLIDER_BOUNDS[c]
            label = NUMERIC_LABELS.get(c, c)
            key_pref = f"ex_pc_brush_{c}_{preset_key}"
            slider_key = f"{key_pref}_slider"
            num_lo_key = f"{key_pref}_num_lo"
            num_hi_key = f"{key_pref}_num_hi"

            # Initialize all three keys to the full range on first render
            if slider_key not in st.session_state:
                st.session_state[slider_key] = (float(v_min), float(v_max))
                st.session_state[num_lo_key] = float(v_min)
                st.session_state[num_hi_key] = float(v_max)

            # Clamp slider state to current bounds (preset change can narrow)
            cur_range = st.session_state[slider_key]
            try:
                cl_lo = max(float(v_min), min(float(v_max), float(cur_range[0])))
                cl_hi = max(float(v_min), min(float(v_max), float(cur_range[1])))
                if cl_lo > cl_hi:
                    cl_lo, cl_hi = float(v_min), float(v_max)
            except (TypeError, ValueError, IndexError):
                cl_lo, cl_hi = float(v_min), float(v_max)
            st.session_state[slider_key] = (cl_lo, cl_hi)
            # Same clamp for numeric inputs
            st.session_state[num_lo_key] = max(float(v_min),
                                                  min(float(v_max),
                                                      float(st.session_state.get(num_lo_key, v_min))))
            st.session_state[num_hi_key] = max(float(v_min),
                                                  min(float(v_max),
                                                      float(st.session_state.get(num_hi_key, v_max))))

            # Callbacks: slider change writes to numeric, numeric change
            # writes to slider. The shared state is the source of truth.
            def _on_slider_change():
                lo_, hi_ = st.session_state[slider_key]
                st.session_state[num_lo_key] = float(lo_)
                st.session_state[num_hi_key] = float(hi_)

            def _on_num_lo_change():
                new_lo = float(st.session_state[num_lo_key])
                cur_hi = float(st.session_state[num_hi_key])
                if new_lo > cur_hi:
                    new_lo = cur_hi
                    st.session_state[num_lo_key] = new_lo
                st.session_state[slider_key] = (new_lo, cur_hi)

            def _on_num_hi_change():
                cur_lo = float(st.session_state[num_lo_key])
                new_hi = float(st.session_state[num_hi_key])
                if new_hi < cur_lo:
                    new_hi = cur_lo
                    st.session_state[num_hi_key] = new_hi
                st.session_state[slider_key] = (cur_lo, new_hi)

            # Render slider (uses session_state via key)
            st.slider(
                label,
                min_value=float(v_min), max_value=float(v_max),
                step=float(step), key=slider_key,
                on_change=_on_slider_change,
            )

            # Render numeric inputs
            if layout == "full":
                n1, n2, _ = st.columns([1, 1, 4])
            else:
                n1, n2 = st.columns(2)
            with n1:
                st.number_input(
                    "Min", min_value=float(v_min), max_value=float(v_max),
                    step=float(step), key=num_lo_key, format="%.3f",
                    on_change=_on_num_lo_change,
                )
            with n2:
                st.number_input(
                    "Max", min_value=float(v_min), max_value=float(v_max),
                    step=float(step), key=num_hi_key, format="%.3f",
                    on_change=_on_num_hi_change,
                )

            return st.session_state[slider_key]

        # Full-width sliders first
        for c in full_width_cols:
            res = _render_slider(c, layout="full")
            if res:
                lo, hi = res
                brush_filtered = brush_filtered[
                    brush_filtered[c].between(lo, hi) | brush_filtered[c].isna()
                ]

        # Then the rest, 2 per row
        for i in range(0, len(paired_cols), 2):
            row_cols = st.columns(2)
            for j in range(2):
                if i + j < len(paired_cols):
                    c = paired_cols[i + j]
                    with row_cols[j]:
                        res = _render_slider(c, layout="paired")
                        if res:
                            lo, hi = res
                            brush_filtered = brush_filtered[
                                brush_filtered[c].between(lo, hi)
                                | brush_filtered[c].isna()
                            ]

    # ----- Render -----
    if len(pc_cols) < 2:
        st.info("Pick at least 2 columns to render the parallel-coordinates plot.")
    else:
        st.caption(
            f"📊 Plotting **{len(pc_cols)} parallel axes**: " +
            " → ".join(NUMERIC_LABELS.get(c, c) for c in pc_cols)
        )
        st.info(
            "ℹ **Plotly's parallel coordinates does NOT support hovering over "
            "individual lines.** To identify which UAVs survived your brush, "
            "use the **Surviving UAVs** table below (shown when ≤50 platforms "
            "remain). Clicking a row in that table opens the UAV's profile. "
            "This is a library limitation, not a configuration choice."
        )
        # Custom designs are intentionally NOT passed to parcoord (v0.8.12).
        # Reasons: (1) Plotly Parcoords has no per-line hover, so a custom
        # line can't be identified; (2) injecting a custom line distorts
        # the axis ranges if the custom's values exceed the dataset's; this
        # was reported as a regression. Custom designs appear on Flexible
        # scatter and SPLOM where they're identifiable as ⭐ markers.
        fig, n_plot, pc_meta = parallel_coordinates(
            brush_filtered, pc_cols,
            color_by=color_by, color_mode=color_mode, height=540,
            custom_points=None,
            cat_label_map=(friendly_format_func(color_by)
                            if color_by and color_mode != "continuous"
                            else None),
        )
        st.plotly_chart(fig, use_container_width=True)
        # Note about customs being intentionally excluded from this tab
        if customs:
            st.caption(
                "ℹ ⚐ Custom designs are NOT drawn on parallel coordinates "
                "(Plotly limitation: no per-line hover, and a custom's "
                "out-of-range values can distort the axes). They appear on "
                "Flexible scatter and SPLOM as ⭐ markers."
            )
        st.caption(
            f"Showing **{n_plot:,}** UAVs (after page filters + brushing). "
            f"Started from {len(filtered):,} sidebar-filtered rows, "
            f"narrowed to {len(page_filtered):,} after quick filters, "
            f"now {len(brush_filtered):,} after brush, "
            f"and {n_plot:,} have data on all selected columns."
        )

        # v1.0.0-limited: Survivors raw-data table removed. The limited
        # edition does not display individual UAV rows. Just show the
        # count, not the table.
        if n_plot > 0 and n_plot <= 50:
            st.markdown(
                f"**{n_plot} UAVs survived your filters and brush.** "
                "The full version of this app shows the survivors as a "
                "clickable shortlist table linking to individual UAV "
                "profiles; that feature is omitted from this limited "
                "public release."
            )
        elif n_plot > 50:
            st.caption(
                f"⚠ {n_plot} survivors is a large group. Tighten the "
                "brush sliders to narrow to a manageable shortlist."
            )

        if n_plot < 0.3 * len(brush_filtered):
            st.caption(
                "⚠ Many rows lost to missing data on selected columns. "
                "Try removing sparse columns (Eng power, Ceiling) or use a "
                "preset that excludes them."
            )


# ---- Tab 3: SPLOM ----------------------------------------------------------
with tab_splom:
    st.caption(
        "Scatter-plot matrix: every selected column plotted against every "
        "other column in one grid. Useful for seeing the full correlation "
        "structure at once. Lower triangle only (mirror is redundant)."
    )

    DEFAULT_SPLOM_COLS = ["MTOW_kg", "Payload_kg", "Endurance_h", "BestRange_km"]

    splom_cols = st.multiselect(
        "Columns to include in the matrix (3-5 recommended)",
        options=list(NUMERIC_LABELS.keys()),
        default=[c for c in DEFAULT_SPLOM_COLS if c in NUMERIC_LABELS],
        format_func=lambda c: NUMERIC_LABELS[c],
        key="ex_splom_cols",
    )

    splom_color_by = st.selectbox(
        "Color points by",
        options=["(none)"] + list(CATEGORICAL_LABELS.keys()),
        format_func=lambda c: "(none)" if c == "(none)" else CATEGORICAL_LABELS[c],
        index=0,
        key="ex_splom_color_by",
    )
    splom_color_by = None if splom_color_by == "(none)" else splom_color_by

    # Merge subcategories / restrict to specific categories (same UX as flexible scatter)
    splom_merge_categories = None
    splom_only_show_cats = None
    if splom_color_by:
        with st.expander(
            "🔀 Merge subcategories / restrict to specific categories",
            expanded=False,
        ):
            st.caption(
                "Same merge UI as Flexible scatter. Up to **3 merge groups**. "
                "Merging affects color/symbol assignment in every SPLOM cell."
            )
            sp_unique_cats = (page_filtered[splom_color_by].dropna()
                                .astype(str).unique().tolist())
            sp_unique_cats.sort()

            splom_merge_categories = {}
            for i in range(1, 4):
                st.markdown(f"**Merge group {i}** *(optional)*")
                ml, mr = st.columns([2, 1])
                with ml:
                    available = [c for c in sp_unique_cats
                                  if c not in splom_merge_categories]
                    merge_src = st.multiselect(
                        f"Merge these {splom_color_by} values…",
                        options=available, default=[],
                        key=f"ex_splom_merge_src_{splom_color_by}_{i}",
                    )
                with mr:
                    merge_dst = st.text_input(
                        "…into this label",
                        value=f"merged{i}" if i > 1 else "merged",
                        key=f"ex_splom_merge_dst_{splom_color_by}_{i}",
                    )
                if merge_src and merge_dst.strip():
                    label = merge_dst.strip()
                    for src in merge_src:
                        splom_merge_categories[src] = label

            if not splom_merge_categories:
                splom_merge_categories = None

            post_merge_options = sorted(set(
                (splom_merge_categories or {}).get(c, c)
                for c in sp_unique_cats
            ))
            only_show_pick = st.multiselect(
                "Show only these (merged) categories — leave empty for all",
                options=post_merge_options, default=[],
                key=f"ex_splom_only_show_{splom_color_by}",
            )
            splom_only_show_cats = only_show_pick if only_show_pick else None

    if len(splom_cols) < 2:
        st.info("Pick at least 2 columns.")
    elif len(splom_cols) > 6:
        st.warning(f"You picked {len(splom_cols)} columns — "
                    f"that's {len(splom_cols) * (len(splom_cols) - 1) // 2} "
                    f"pair scatters, which may be slow. Pick 3-5 for best "
                    f"readability.")
        if st.button("Render anyway"):
            fig, n_plot = splom(page_filtered, splom_cols,
                                 color_by=splom_color_by,
                                 height_per_row=300,
                                 custom_points=customs,
                                 merge_categories=splom_merge_categories,
                                 only_show_categories=splom_only_show_cats)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Showing {n_plot:,} of {len(page_filtered):,} page_filtered rows.")
    else:
        fig, n_plot = splom(page_filtered, splom_cols,
                             color_by=splom_color_by,
                             height_per_row=300,
                             custom_points=customs,
                             merge_categories=splom_merge_categories,
                             only_show_categories=splom_only_show_cats)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Showing {n_plot:,} of {len(page_filtered):,} page_filtered rows "
            f"(rows missing data on any selected column are dropped). "
            f"Custom design (if any) appears as ⭐ in every subplot."
        )