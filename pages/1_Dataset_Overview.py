"""Dataset Overview page.

v0.8.34a (this round):
- Moved from app.py to pages/ for use under st.navigation API. The router
  in app.py now declares this page with the display name "Dataset Overview"
  via st.Page(..., title="Dataset Overview").
- All chart logic, coverage captions, percentage Y-axes, and friendly labels
  for Mission/Engine carried over unchanged.

History (carried over from app.py):
- v0.8.33a: no auto-filter on mass/engine/launch; coverage captions
  per section; percentage Y-axes on Mass / Mission×Engine / Launch charts.
- v0.8.33a-fix1: friendly labels on Mission × Engine heatmap axes; removed
  redundant "Mission & engine-type reference" expander.
"""
import streamlit as st

import sys
from pathlib import Path
# Add project root to sys.path so `lib` imports work when running under
# st.navigation (running file is pages/1_Dataset_Overview.py, root is parent of pages/)
sys.path.insert(0, str(Path(__file__).parent.parent))

# v0.8.34b+c: enable 2x PNG export on every plotly chart in this page
from lib.chart_config import apply_default_export_config
apply_default_export_config('dataset-overview')

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from lib.sidebar import render_sidebar
from lib.loader import load_uav, load_acronyms, NAME_COL


# ---- Sidebar runs first ----------------------------------------------------
filtered, fs, cuts = render_sidebar()

# ---- Acronym lookup helpers ------------------------------------------------
acronyms = load_acronyms()


def acronym_table_for(*categories: str) -> pd.DataFrame:
    """Pull acronym entries for the given category(ies) and return a clean df."""
    a = acronyms[acronyms["category"].isin(categories)][["code", "expansion", "category"]]
    return a.sort_values(["category", "code"]).reset_index(drop=True)


# ---- Main page content -----------------------------------------------------
st.title("Dataset Overview")
st.caption("Dataset shape — counts, mass distribution, mission × engine, completeness, filtered data.")
# v0.8.34b+c: data-provenance statement per locked decision. Single
# project-level statement; per-row citations were deferred (collection
# burden too high; current dataset is curator-reviewed but not yet
# annotated with per-cell source URLs).
st.info(
    "ℹ **Data provenance** — Data is reviewed from datasheets, official "
    "homepages, UAV ARMADA, official data, and research papers.",
    icon="📚",
)

# v1.0.0-limited: condensed license/copyright/citation block (one-liner).
st.warning(
    "**⚖ License & Terms** — Code: AGPL-3.0 · Dataset: CC BY-NC 4.0 · "
    "UI layout, charts, visual design, and analytical structure © 2026 "
    "Moatasem B Momtaz · **Cite this work if used in any publication** "
    "(see `CITATION.cff`).",
    icon="⚖",
)

if len(filtered) == 0:
    st.warning("No rows match the current filter. Loosen filters in the sidebar.")
    st.stop()
# Top KPI row -----------------------------------------------------------------
total = len(load_uav())
n = len(filtered)
n_countries = filtered["Country"].nunique()
n_producers = filtered["Producer"].nunique()
mtow_min = filtered["MTOW_kg"].min()
mtow_max = filtered["MTOW_kg"].max()

core_fields = ["MTOW_kg", "Endurance_h", "Range_km", "Wingspan_m"]
core_complete = filtered[core_fields].notna().all(axis=1).sum()
core_pct = 100 * core_complete / n if n else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Filtered rows", f"{n:,}", f"{100*n/total:.1f}% of dataset")
c2.metric("Countries", n_countries)
c3.metric("Producers", n_producers)
c4.metric("MTOW range",
          f"{mtow_min:,.2g} – {mtow_max:,.0f} kg" if pd.notna(mtow_min) else "—")

st.caption(
    f"Core completeness (all of MTOW, Endurance, Range, Wingspan present): "
    f"**{core_complete:,} rows ({core_pct:.0f}%)**"
)

st.divider()

# Helper for formatting kg values on histogram bin labels
def _fmt_kg(v):
    if v < 1: return f"{v:.2f}"
    if v < 10: return f"{v:.1f}"
    if v < 1000: return f"{v:.0f}"
    return f"{v/1000:.0f}k"

# ---- Mass histogram by SizeClassStd ----------------------------------------
st.subheader("Mass Distribution by Size Class")
# v0.8.33a: coverage caption shows how many filtered platforms actually have
# MTOW data. The histogram below normalizes to % of the populated subset so
# small-vs-large filters give comparable bar heights.
n_with_mtow = filtered["MTOW_kg"].notna().sum()
pct_with_mtow = 100 * n_with_mtow / max(n, 1)
st.caption(
    f"**{n_with_mtow:,} of {n:,} filtered UAVs ({pct_with_mtow:.1f}%) have MTOW data.** "
    "Bars show **% of platforms-with-MTOW** in each bin. "
    "Log-scale bins aligned to class boundaries so each bar contains only "
    "one size class. Boundaries: Nano/Micro (<2 kg), Mini (2–20), Small "
    "(20–150), Tactical (150–600), MALE (600–2000), HALE (>2000)."
)

SIZESTD_ORDER = ["Nano/Micro", "Mini", "Small", "Tactical", "MALE", "HALE",
                 "HAPS", "Suspect", "Other / unclassified"]
SIZESTD_COLORS = {
    "Nano/Micro": "#9F8CD8",
    "Mini":       "#7F77DD",
    "Small":      "#534AB7",
    "Tactical":   "#185FA5",
    "MALE":       "#0F6E56",
    "HALE":       "#993C1D",
    "HAPS":       "#E89C00",    # gold — solar / high-altitude pseudo-satellite
    "Suspect":    "#B0B0B0",    # gray — quarantined questionable data
    "Other / unclassified": "#7B7B7B",
}

# Boundaries in kg — these are the EXACT class edges from SizeClassStd
CLASS_BOUNDARIES_KG = [0.001, 2, 20, 150, 600, 2000, 100000]
# Sub-divide each class span into 2 bins so the histogram has a bit of detail
# while keeping the class boundary as an exact edge
def _build_aligned_bins():
    edges = []
    for i in range(len(CLASS_BOUNDARIES_KG) - 1):
        lo = np.log10(CLASS_BOUNDARIES_KG[i])
        hi = np.log10(CLASS_BOUNDARIES_KG[i + 1])
        # 2 sub-bins per class span — finer detail without crossing boundaries
        edges.extend([lo, lo + (hi - lo) / 2])
    edges.append(np.log10(CLASS_BOUNDARIES_KG[-1]))
    return edges

mass_df = filtered.copy()
mass_df["SizeClassStd"] = mass_df["SizeClassStd"].fillna("Other / unclassified")
mass_df_plot = mass_df.dropna(subset=["MTOW_kg"])
if len(mass_df_plot) > 0:
    mass_df_plot["log_mtow"] = np.log10(mass_df_plot["MTOW_kg"].clip(lower=0.001))
    bins = _build_aligned_bins()
    bin_labels = []
    for i in range(len(bins) - 1):
        lo_v = 10 ** bins[i]
        hi_v = 10 ** bins[i + 1]
        # Format the bin label as the actual kg range
        bin_labels.append(f"{_fmt_kg(lo_v)}–{_fmt_kg(hi_v)}")
    mass_df_plot["bin"] = pd.cut(
        mass_df_plot["log_mtow"], bins=bins, include_lowest=True,
        labels=bin_labels,
    )
    counts = (
        mass_df_plot.groupby(["bin", "SizeClassStd"], observed=True).size()
        .reset_index(name="count")
    )
    # v0.8.33a: convert raw counts to % of UAVs with MTOW in current filter
    total_with_mtow = max(len(mass_df_plot), 1)
    counts["pct"] = 100 * counts["count"] / total_with_mtow
    # Only keep bin labels that actually have data — otherwise empty bins
    # appear as ticks on the x-axis, which looks like the histogram includes
    # those classes when in fact they're empty.
    present_bins = [b for b in bin_labels
                    if b in counts["bin"].astype(str).unique()]
    present_classes = [c for c in SIZESTD_ORDER
                       if c in counts["SizeClassStd"].unique()]
    fig = px.bar(
        counts, x="bin", y="pct", color="SizeClassStd",
        category_orders={
            "bin": present_bins,
            "SizeClassStd": present_classes,
        },
        color_discrete_map=SIZESTD_COLORS,
        labels={"bin": "MTOW (kg)", "pct": "% of UAVs with MTOW",
                 "SizeClassStd": "Size class"},
        height=340,
        custom_data=["count"],
    )
    fig.update_traces(
        hovertemplate=(
            "%{x}<br>%{fullData.name}<br>"
            "%{y:.1f}% (%{customdata[0]} UAVs)<extra></extra>"
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.4),
    )
    n_unclassified = (mass_df["SizeClassStd"] == "Other / unclassified").sum()
    if n_unclassified > 0:
        st.caption(
            f"ℹ {n_unclassified} of {len(mass_df)} UAVs in current filter have no MTOW data — "
            "they're tagged **Other / unclassified** but cannot be placed on the x-axis (no MTOW)."
        )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No MTOW data in current filter.")

with st.expander("Size class reference"):
    st.dataframe(
        acronym_table_for("SizeClassStd"),
        hide_index=True, use_container_width=True,
    )

st.divider()

# ---- Mission × Engine heatmap ----------------------------------------------
st.subheader("Mission × Engine Type")
# v0.8.33a: coverage caption + percentage cells (% of filtered fleet with
# both Mission AND EngineType populated).
mission_eng_mask = (filtered["Mission"].notna()
                      & filtered["EngineType"].notna()
                      & (filtered["Mission"].astype(str).str.strip() != "")
                      & (filtered["EngineType"].astype(str).str.strip() != ""))
n_mission_eng = int(mission_eng_mask.sum())
pct_mission_eng = 100 * n_mission_eng / max(n, 1)
st.caption(
    f"**{n_mission_eng:,} of {n:,} filtered UAVs ({pct_mission_eng:.1f}%) "
    f"have both Mission and Engine type.** "
    "Cells show **% of populated subset**. Hover for raw counts."
)

cross = pd.crosstab(filtered["Mission"], filtered["EngineType"])
if cross.size > 0:
    # v0.8.33b: friendly labels on both axes — full names instead of codes.
    from lib.labels import code_to_label
    x_friendly = [code_to_label("EngineType", c) for c in cross.columns]
    y_friendly = [code_to_label("Mission", m) for m in cross.index]
    # v0.8.33a: normalize to % of populated subset
    cross_pct = 100 * cross / max(n_mission_eng, 1)
    text_labels = [[f"{v:.1f}%" if v > 0 else ""
                     for v in row] for row in cross_pct.values]
    custom = cross.values  # raw counts for hover
    fig = px.imshow(
        cross_pct.values,
        x=x_friendly,
        y=y_friendly,
        color_continuous_scale="Purples",
        aspect="auto",
        labels=dict(x="Engine type", y="Mission",
                    color="% of populated subset"),
        height=380,
    )
    # Set custom text + hover with counts
    fig.update_traces(
        text=text_labels, texttemplate="%{text}",
        customdata=custom,
        hovertemplate=(
            "Mission: %{y}<br>Engine: %{x}<br>"
            "%{z:.1f}%% (n=%{customdata})<extra></extra>"
        ),
    )
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No Mission × Engine combinations in current filter.")

st.divider()

# ---- Launch method frequency -----------------------------------------------
# v0.8.24: relocated from Aerodynamic page (not an aero attribute).
# v0.8.33a: coverage caption + bars switched to % within each group so
# small and large groups (e.g. LM vs ISR) are directly comparable.
st.subheader("Launch Method Frequency")

lm_group = st.radio(
    "Group by",
    options=["Mission", "SizeClassStd"],
    format_func=lambda v: ("Mission" if v == "Mission"
                              else "Weight category (SizeClassStd)"),
    horizontal=True, key="overview_launch_group",
)
lm_sub = filtered[["LaunchMethod", lm_group]].dropna()
lm_sub = lm_sub[lm_sub["LaunchMethod"].astype(str).str.strip().ne("")]
lm_sub = lm_sub[lm_sub[lm_group].astype(str).str.strip().ne("")]

n_lm_populated = len(lm_sub)
pct_lm_populated = 100 * n_lm_populated / max(n, 1)
st.caption(
    f"**{n_lm_populated:,} of {n:,} filtered UAVs ({pct_lm_populated:.1f}%) "
    f"have both LaunchMethod and {lm_group} populated.** "
    "Bars show **% within each group** so small and large groups are "
    "directly comparable. Hover for raw counts."
)

if len(lm_sub) == 0:
    st.info("No data for Launch method × " + lm_group + " under current filter.")
else:
    counts = (lm_sub.groupby([lm_group, "LaunchMethod"])
                     .size().reset_index(name="count"))
    # v0.8.33a: per-group totals so each bar normalizes to 100% within the group
    group_totals = counts.groupby(lm_group)["count"].sum()
    counts["pct_in_group"] = counts.apply(
        lambda r: 100 * r["count"] / max(group_totals[r[lm_group]], 1),
        axis=1,
    )
    # Order groups by total count desc
    group_order = (counts.groupby(lm_group)["count"].sum()
                            .sort_values(ascending=False).index.tolist())
    # Order categories by total count desc
    cats_sorted = (counts.groupby("LaunchMethod")["count"].sum()
                            .sort_values(ascending=False).index.tolist())

    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
                "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC",
                "#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD"]

    fig_lm = go.Figure()
    for i, lm in enumerate(cats_sorted):
        sub_c = counts[counts["LaunchMethod"] == lm]
        d_pct = {row[lm_group]: row["pct_in_group"] for _, row in sub_c.iterrows()}
        d_cnt = {row[lm_group]: row["count"] for _, row in sub_c.iterrows()}
        ys = [d_pct.get(g, 0) for g in group_order]
        cnts = [d_cnt.get(g, 0) for g in group_order]
        fig_lm.add_trace(go.Bar(
            x=[str(g) for g in group_order], y=ys, name=str(lm),
            marker_color=palette[i % len(palette)],
            customdata=cnts,
            hovertemplate=(f"<b>{lm}</b><br>"
                            f"{lm_group}: %{{x}}<br>"
                            f"%{{y:.1f}}%% (%{{customdata}} UAVs)<extra></extra>"),
        ))
    fig_lm.update_layout(
        barmode="stack",
        height=380,
        margin=dict(l=60, r=20, t=20, b=70),
        xaxis=dict(
            title=lm_group,
            showgrid=False, showline=True, linewidth=1.5,
            linecolor="rgba(80,80,80,0.8)", mirror=True, ticks="outside",
            tickangle=-15,
        ),
        yaxis=dict(
            title="% of platforms within group",
            range=[0, 105],
            showgrid=True, gridcolor="rgba(128,128,128,0.25)",
            zeroline=False, showline=True, linewidth=1.5,
            linecolor="rgba(80,80,80,0.8)", mirror=True, ticks="outside",
            ticksuffix="%",
        ),
        legend=dict(orientation="v", x=1.02, y=1.0,
                     xanchor="left", yanchor="top", font=dict(size=10)),
    )
    st.plotly_chart(fig_lm, use_container_width=True)

st.divider()

# ---- Field completeness ----------------------------------------------------
st.subheader("Field Completeness in Current Filter")
st.caption("Coverage of each numeric column. Green ≥70%, amber 30–70%, red <30%.")

display_fields = [
    ("MTOW_kg", "MTOW"),
    ("Endurance_h", "Endurance"),
    ("Range_km", "Range"),
    ("MaxSpeed_kmh", "Max speed"),
    ("Payload_kg", "Payload"),
    ("Wingspan_m", "Wingspan"),
    ("Length_m", "Length"),
    ("CruiseSpeed_kmh", "Cruise speed"),
    ("Height_m", "Height"),
    ("EngPower_hp", "Eng power"),
    ("Ceiling_km", "Ceiling"),
]
rows = []
for col, label in display_fields:
    if col in filtered.columns:
        cov = 100 * filtered[col].notna().sum() / max(n, 1)
        rows.append({"field": label, "coverage_pct": cov})
cov_df = pd.DataFrame(rows)


def cov_color(pct):
    if pct >= 70: return "#0F6E56"
    if pct >= 30: return "#BA7517"
    return "#A32D2D"


fig = go.Figure(go.Bar(
    x=cov_df["coverage_pct"], y=cov_df["field"], orientation="h",
    marker_color=[cov_color(p) for p in cov_df["coverage_pct"]],
    text=[f"{p:.0f}%" for p in cov_df["coverage_pct"]],
    textposition="outside",
))
fig.update_layout(
    height=420,
    margin=dict(l=10, r=40, t=10, b=10),
    xaxis=dict(range=[0, 110], title="% coverage"),
    yaxis=dict(autorange="reversed"),
)
st.plotly_chart(fig, use_container_width=True)


# v1.0.0-limited: Filtered Data table removed. The limited
# edition does not expose raw row data.
