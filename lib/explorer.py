"""Design-space explorer plotting helpers.

Three views supported:
- `flexible_scatter`: any X / Y, color-by, size-by, log/linear axes
- `parallel_coordinates`: N columns as parallel axes, lines per UAV
- `splom`: scatter-plot-matrix across N columns

Designed so the user picks any combination of columns at runtime, with the
machinery here handling: log-axis tick fixes, hover tooltips with row id +
designation, NaN dropping, color palette assignment, and graceful handling
of sparse data.
"""
from typing import List, Optional, Dict, Tuple
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from .loader import NAME_COL
from .fitting import fit_power_law, fit_line_xy


# Numeric columns and their display labels (units in parens)
NUMERIC_LABELS = {
    "MTOW_kg": "MTOW (kg)",
    "Payload_kg": "Payload (kg)",
    "Endurance_h": "Endurance (h)",
    "Range_km": "Data-link range (km, as published)",
    "BestRange_km": "Best-estimate range (km, recommended)",
    "DerivedRange_km": "Derived range (km, cruise × endurance)",
    "ActualRange_km": "Verified range (km, publisher-confirmed)",
    "MaxSpeed_kmh": "Max speed (km/h)",
    "CruiseSpeed_kmh": "Cruise speed (km/h)",
    "Wingspan_m": "Wingspan (m)",
    "Length_m": "Length (m)",
    "Height_m": "Height (m)",
    "Ceiling_km": "Ceiling (km)",
    "EngPower_hp": "Eng power (hp)",
    "PayloadEnduranceProduct_kgh": "Payload × Endurance (kg·h)",
    # v0.8.32 + v0.8.33b: full descriptive labels matching the
    # SizingRelation y_label exactly, so flex-scatter, 3D view, and
    # SPLOM all show the same axis text the user picked from the
    # relation menu. Was "Mission productivity, cruise (km·kg)" — too
    # generic; now includes the formula.
    "MissionProductivity_Cruise_kgkm":
        "Cruise Speed × Endurance × Payload (km·kg)",
    "MissionProductivity_Max_kgkm":
        "Max Speed × Endurance × Payload (km·kg)",
    # v0.8.34b+c: 8 calculated columns (A4 pre-defined recipes).
    # Each is grouped with a "Calculated" prefix in axis pickers via
    # the CALCULATED_COLUMNS set below — keeps the standard columns clean
    # while still exposing derived metrics in dropdowns.
    "Calc_EndurancePerMTOW_h_per_kg":  "Endurance per kg of MTOW (h/kg)",
    "Calc_RangePerMTOW_km_per_kg":     "Range per kg of MTOW (km/kg)",
    "Calc_PayloadRangePerMTOW_km":     "Payload × Range / MTOW (km)",
    "Calc_WingLoadingProxy_kg_per_m2": "Wing-Loading Proxy MTOW / Wingspan² (kg/m²)",
    "Calc_PowerToWeight_hp_per_kg":    "Power-to-Weight (hp/kg)",
    "Calc_PEPerMTOW_h":                "Anchor Payload × Endurance / MTOW (h)",
    "Calc_EnduranceXCruise_km":        "Endurance × Cruise Speed (km, derived range check)",
    "Calc_StructuralFraction":         "Structural Fraction (MTOW − Payload) / MTOW",
    # Ratio metrics — added back in v0.8.18 at user request, specifically for
    # Design-space flexible scatter X/Y axis selection. Bounded ratios — use
    # linear axes when picking these. Coverage: PayloadFraction ~66%,
    # PowerLoading_hp_per_kg ~15%.
    "PayloadFraction": "Payload fraction (Payload/MTOW, -)",
    "PowerLoading_hp_per_kg": "Power loading (hp/kg)",
}

# Categorical columns suitable for color/group (small unique counts)
CATEGORICAL_LABELS = {
    "Mission": "Mission",
    "EngineType": "Engine type",
    "LaunchMethod": "Launch method",
    "SizeClassStd": "Size class (standard)",
    "Airframe": "Airframe",
    "WingForm": "Wing form",
    "WingConfig": "Wing configuration (position)",
    "BodyConfig": "Body config",
    "TailConfig": "Tail configuration",
}

# Fixed engine palette (matches sizing_scatter for consistency)
ENGINE_COLORS = {
    "P": "#1f77b4", "E": "#2ca02c", "H": "#9467bd", "FC": "#17becf",
    "S": "#ff7f0e", "Turbojet": "#d62728", "Turbofan": "#8c564b",
    "Turboprop": "#e377c2", "DF": "#bcbd22", "G": "#7f7f7f",
}

# 20-color palette designed for maximum contrast between adjacent indices.
# Avoids the yellow-yellow / green-green collisions seen with hash assignment.
GENERIC_PALETTE = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#17becf",  # teal
    "#bcbd22",  # olive
    "#7f7f7f",  # grey
    "#393b79",  # dark blue
    "#8c6d31",  # dark gold
    "#843c39",  # dark red
    "#7b4173",  # dark purple
    "#3182bd",  # mid blue
    "#31a354",  # mid green
    "#e6550d",  # mid orange
    "#756bb1",  # mid purple
    "#636363",  # mid grey
    "#5254a3",  # lavender
]

# Symbol palette — cycled in parallel with color so categories with similar
# hues remain visually distinguishable by shape.
SYMBOL_PALETTE = [
    "circle", "square", "diamond", "triangle-up", "triangle-down",
    "star", "hexagon", "cross", "x", "pentagon",
    "triangle-left", "triangle-right", "hourglass", "bowtie",
    "circle-cross", "circle-x", "square-cross", "diamond-tall",
    "star-square", "hexagon2",
]


def _decade_ticks(vmin: float, vmax: float):
    """Return (vals, labels) for log-axis ticks within [vmin, vmax].

    When the data span is <= 2.5 decades, includes intermediate 1/2/5 ticks
    (e.g. 0.5, 1, 2, 5, 10, 20) so narrow ranges aren't reduced to a single
    visible decade tick. For wider ranges, uses decade-only ticks.
    """
    if vmin is None or vmax is None or vmin <= 0 or vmax <= 0:
        return None, None
    if vmin >= vmax:
        return [vmin], [f"{vmin:g}"]

    lo_exp = int(np.floor(np.log10(vmin)))
    hi_exp = int(np.ceil(np.log10(vmax)))
    actual_span = np.log10(vmax) - np.log10(vmin)

    # v0.8.22: threshold lowered from 2.5 → 1.5 to match sizing_scatter.
    # Wider ranges get decade-only ticks (less dense at large values).
    if actual_span <= 1.5:
        vals = []
        for e in range(lo_exp - 1, hi_exp + 1):
            base = 10 ** e
            for mult in (1, 2, 5):
                v = base * mult
                if v >= vmin * 0.5 and v <= vmax * 2:
                    vals.append(v)
    else:
        vals = [10 ** e for e in range(lo_exp, hi_exp + 1)]

    vals = sorted(set(vals))

    # Cap to ~8 ticks for readability
    if len(vals) > 8:
        vals = [v for v in vals
                 if any(abs(v - 10 ** e * m) / max(v, 1e-9) < 0.01
                        for e in range(-5, 6) for m in (1, 5))]
        if len(vals) > 10:
            vals = [v for v in vals
                     if abs(v - 10 ** round(np.log10(v))) / v < 0.01]

    labels = [f"{v:,.0f}" if v >= 1000 else f"{v:g}" for v in vals]
    return vals, labels


def _color_for(cat, color_map: dict, palette: list,
                 stable_order: list = None) -> str:
    """Pick a stable color for a category label.

    If `stable_order` is given, color is assigned by position in that ordered
    list — prevents collisions when many categories exist. Without it falls
    back to a hash (used only as a last resort).
    """
    s = str(cat)
    if s in color_map:
        return color_map[s]
    if stable_order is not None and s in stable_order:
        return palette[stable_order.index(s) % len(palette)]
    idx = abs(hash(s)) % len(palette)
    return palette[idx]


def flexible_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    color_by: Optional[str] = None,    # categorical column
    size_by: Optional[str] = None,     # numeric column
    x_type: str = "log",
    y_type: str = "log",
    custom_points: Optional[List[dict]] = None,
    height: int = 520,
    hide_uncategorized: bool = False,
    merge_categories: Optional[dict] = None,    # old_label -> merged_label
    only_show_categories: Optional[List[str]] = None,  # if set, only these
    show_fits: bool = False,           # fit power law per (merged) category
    literature_fit: Optional[dict] = None,  # {"coef": A, "exp": B, "label": str}
    cat_label_map=None,                # optional fn(code)->friendly label for legend
) -> Tuple[go.Figure, int, Optional[dict]]:
    """Flexible X-Y scatter.

    `custom_points` is an optional list of {"name", "x", "y"} dicts to overlay
    as ⚐ markers (the user's candidate designs).

    `hide_uncategorized`: when color_by is set, drop rows with no value on
    that column (instead of showing them as "(none)").

    `merge_categories`: dict mapping subcategory labels to merged labels. E.g.
    {"T": "fixed", "R": "fixed", "e": "fixed", "Polyhedral": "fixed"} merges
    those four wing-form labels into a single "fixed" group. Applied AFTER
    `hide_uncategorized` but BEFORE category-based color/symbol assignment
    and fitting — so the merged group gets one color, one symbol, one fit.

    `only_show_categories`: if set, only these (merged) labels appear; others
    are dropped. Useful for "show only delta + swept" workflows.

    `show_fits`: when True, fit a power-law per (merged) category. Returns
    the fit equations in `size_info["fits"]`.

    Returns (figure, n_rows_plotted, info_dict).
    info_dict contains 'size_label', 'size_small', 'size_large', 'fits' (a list).
    """
    # Guard against X = Y (would crash matplotlib/Plotly when same column)
    if x_col == y_col:
        fig = go.Figure()
        fig.update_layout(
            height=height,
            annotations=[dict(
                text="X and Y columns must differ. Pick a different column "
                     "for one of the axes.",
                showarrow=False, xref="paper", yref="paper",
                x=0.5, y=0.5, font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0, None

    sub = df[[x_col, y_col, NAME_COL]].copy()
    sub["__id"] = df.index
    if color_by and color_by in df.columns:
        sub[color_by] = df[color_by]
    if size_by and size_by in df.columns:
        sub[size_by] = df[size_by]

    sub = sub.dropna(subset=[x_col, y_col])
    if x_type == "log":
        sub = sub[sub[x_col] > 0]
    if y_type == "log":
        sub = sub[sub[y_col] > 0]

    # Drop uncategorized rows if requested
    if color_by and hide_uncategorized and color_by in sub.columns:
        sub = sub[sub[color_by].notna()]

    # Apply category merging — replace specific subcategory labels with
    # their merged target. Done as a string-level rename, leaving column
    # type unchanged.
    if color_by and merge_categories and color_by in sub.columns:
        # Work on a string copy so we can use replace cleanly
        merged_col = sub[color_by].astype("object")
        merged_col = merged_col.replace(merge_categories)
        sub[color_by] = merged_col

    # Apply only_show_categories — restrict to selected (merged) labels
    if color_by and only_show_categories and color_by in sub.columns:
        sub = sub[sub[color_by].astype(str).isin(only_show_categories)]

    fig = go.Figure()
    n_plotted = 0
    if len(sub) == 0:
        fig.update_layout(
            height=height,
            annotations=[dict(
                text="No rows match the current filter and axes.",
                showarrow=False, xref="paper", yref="paper",
                x=0.5, y=0.5, font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0, None

    x_label = NUMERIC_LABELS.get(x_col, x_col)
    y_label = NUMERIC_LABELS.get(y_col, y_col)

    # Compute marker sizes. Use rank-based log scaling so the visual range
    # is even — otherwise a long-tailed column (Wingspan: 0.1–35 m) puts
    # most points at size 5 with a few outliers at 25.
    if size_by and size_by in sub.columns and sub[size_by].notna().any():
        size_vals = sub[size_by].copy()
        # Use log of values for size encoding (skip if values are non-positive)
        if (size_vals.dropna() > 0).all():
            size_basis = np.log10(size_vals.fillna(size_vals.median()))
        else:
            # Fall back to rank for non-positive (negative or zero) data
            size_basis = size_vals.fillna(size_vals.median()).rank(pct=True)
        s_min, s_max = size_basis.min(), size_basis.max()
        if s_max > s_min:
            # Scale to 6-26 px range
            marker_sizes = 6 + 20 * (size_basis - s_min) / (s_max - s_min)
        else:
            marker_sizes = pd.Series([12] * len(size_basis), index=size_basis.index)
        size_legend = NUMERIC_LABELS.get(size_by, size_by)
        # Compute small-large reference values for legend annotation
        v_small = size_vals.quantile(0.1) if size_vals.notna().any() else None
        v_large = size_vals.quantile(0.9) if size_vals.notna().any() else None
    else:
        marker_sizes = 10
        size_legend = None
        v_small = v_large = None

    fits_out = []   # list of dicts with category/equation/r2/n

    # Literature fit overlay drawn FIRST so it sits at the BOTTOM of the
    # z-order. Per-category fit lines drawn afterwards will always be
    # visible on top of it. Previous versions drew literature LAST, which
    # visually covered per-category fits at intersection points.
    if literature_fit and sub.size > 0:
        coef = literature_fit.get("coef")
        exp = literature_fit.get("exp")
        lit_label = literature_fit.get("label", "Literature fit")
        if coef is not None and exp is not None:
            try:
                xs_lit = np.geomspace(max(sub[x_col].min(), 1e-3),
                                        sub[x_col].max(), 60)
                ys_lit = coef * xs_lit ** exp
                eq_str = f"Y = {coef:g} · X^{exp:.3f}"
                fig.add_trace(go.Scatter(
                    x=xs_lit, y=ys_lit, mode="lines",
                    name=f"📖 {lit_label}: {eq_str}",
                    line=dict(color="#C0392B", width=2.0, dash="longdash"),
                    hoverinfo="skip", opacity=0.75,
                    legendgroup="literature",
                ))
            except (ValueError, TypeError):
                pass    # axes not log-compatible — skip the line

    if color_by and color_by in sub.columns:
        # Pre-compute sorted category list for stable color/symbol assignment
        cats_present = (sub[color_by].fillna("(none)").astype(str)
                          .unique().tolist())
        cats_present.sort()
        # Split into per-category traces
        for cat, sub_cat in sub.groupby(color_by, dropna=False):
            cat_label = str(cat) if pd.notna(cat) else "(none)"
            color = _color_for(cat_label, ENGINE_COLORS, GENERIC_PALETTE,
                                stable_order=cats_present)
            sym_idx = (cats_present.index(cat_label)
                        if cat_label in cats_present else 0)
            symbol = SYMBOL_PALETTE[sym_idx % len(SYMBOL_PALETTE)]
            if cat_label == "(none)":
                symbol = "circle-open"
            sizes = marker_sizes.loc[sub_cat.index] if isinstance(marker_sizes, pd.Series) else marker_sizes
            customdata = np.column_stack([
                sub_cat["__id"].astype(int).to_numpy(),
                sub_cat[NAME_COL].astype(str).str.strip().to_numpy(),
            ])
            hovertemplate = (
                f"<b>%{{customdata[1]}}</b><br>"
                f"row id: %{{customdata[0]}}<br>"
                f"{color_by}: {cat_label}<br>"
                f"{x_label}: %{{x:,.3g}}<br>"
                f"{y_label}: %{{y:,.3g}}<extra></extra>"
            )
            display_label = (cat_label_map(cat_label)
                              if cat_label_map and cat_label != "(none)"
                              else cat_label)
            fig.add_trace(go.Scatter(
                x=sub_cat[x_col], y=sub_cat[y_col], mode="markers",
                name=f"{display_label} (n={len(sub_cat)})",
                marker=dict(color=color, size=sizes, opacity=0.7,
                            line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
                            symbol=symbol),
                customdata=customdata, hovertemplate=hovertemplate,
                legendgroup=cat_label,
            ))
            n_plotted += len(sub_cat)

            # Fit a power-law line per category if requested.
            # Skip uncategorized — fitting "unknown" points is meaningless.
            if show_fits and cat_label != "(none)":
                fit = fit_power_law(sub_cat[x_col], sub_cat[y_col],
                                     label=cat_label)
                if fit is not None:
                    xs, ys = fit_line_xy(fit)
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys, mode="lines",
                        name=(f"{display_label} fit: {fit.equation} "
                              f"(R²={fit.r_squared:.2f}, n={fit.n})"),
                        line=dict(color=color, width=2.5, dash="dash"),
                        hoverinfo="skip", opacity=0.85,
                        legendgroup=cat_label,
                    ))
                    fits_out.append({
                        "category": cat_label,
                        "equation": fit.equation,
                        "r_squared": fit.r_squared,
                        "n": fit.n,
                        "reliability": fit.reliability,
                    })
    else:
        customdata = np.column_stack([
            sub["__id"].astype(int).to_numpy(),
            sub[NAME_COL].astype(str).str.strip().to_numpy(),
        ])
        hovertemplate = (
            f"<b>%{{customdata[1]}}</b><br>"
            f"row id: %{{customdata[0]}}<br>"
            f"{x_label}: %{{x:,.3g}}<br>"
            f"{y_label}: %{{y:,.3g}}<extra></extra>"
        )
        fig.add_trace(go.Scatter(
            x=sub[x_col], y=sub[y_col], mode="markers",
            name=f"Dataset (n={len(sub)})",
            marker=dict(color="rgba(83,74,183,0.55)", size=marker_sizes,
                        line=dict(width=0.5, color="rgba(0,0,0,0.2)")),
            customdata=customdata, hovertemplate=hovertemplate,
        ))
        n_plotted = len(sub)

    # Custom design overlays
    if custom_points:
        CUSTOM_COLORS = ["#BA7517", "#854F0B", "#0F4F6E", "#6E0F3F", "#4F0F6E"]
        for i, cp in enumerate(custom_points):
            cx = cp.get(x_col)
            cy = cp.get(y_col)
            if cx is None or cy is None or pd.isna(cx) or pd.isna(cy):
                continue
            color = CUSTOM_COLORS[i % len(CUSTOM_COLORS)]
            name = cp.get("name", f"Custom {i+1}")
            fig.add_trace(go.Scatter(
                x=[cx], y=[cy], mode="markers",
                marker=dict(color=color, size=18, symbol="diamond",
                            line=dict(color="white", width=2)),
                name=f"⚐ {name}",
                hovertemplate=(
                    f"<b>⚐ {name}</b><br>"
                    f"{x_label}: %{{x:,.3g}}<br>"
                    f"{y_label}: %{{y:,.3g}}<extra></extra>"
                ),
            ))

    # Axes — full styling: gridlines, axis line (spine), ticks, minor grid.
    grid_style = dict(
        showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.25)",
        zeroline=False, showticklabels=True,
        showline=True, linewidth=1.5, linecolor="rgba(80,80,80,0.8)",
        mirror=True, ticks="outside", ticklen=5,
        tickcolor="rgba(80,80,80,0.8)",
    )
    xaxis_config = dict(title=x_label, **grid_style)
    yaxis_config = dict(title=y_label, **grid_style)
    if x_type == "log":
        vals, labels = _decade_ticks(sub[x_col].min(), sub[x_col].max())
        if vals:
            xaxis_config.update(type="log", tickmode="array",
                                 tickvals=vals, ticktext=labels,
                                 minor=dict(showgrid=False, ticks=""))
    if y_type == "log":
        vals, labels = _decade_ticks(sub[y_col].min(), sub[y_col].max())
        if vals:
            yaxis_config.update(type="log", tickmode="array",
                                 tickvals=vals, ticktext=labels,
                                 minor=dict(showgrid=False, ticks=""))

    legend_title = NUMERIC_LABELS.get(color_by, color_by) if color_by else None
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=20, b=50),
        xaxis=xaxis_config, yaxis=yaxis_config,
        legend=dict(orientation="v", x=1.02, y=1.0, xanchor="left",
                    yanchor="top", title=legend_title, font=dict(size=10),
                    itemclick=False,         # disable single-click toggle
                    itemdoubleclick=False),  # disable double-click isolate
    )
    size_info = {"fits": fits_out}
    if size_legend is not None and v_small is not None and v_large is not None:
        size_info["label"] = size_legend
        size_info["small"] = v_small
        size_info["large"] = v_large
    return fig, n_plotted, size_info


def parallel_coordinates(
    df: pd.DataFrame,
    cols: List[str],
    color_by: Optional[str] = None,
    color_mode: str = "categorical",       # "categorical" | "continuous"
    height: int = 500,
    custom_points: Optional[List[dict]] = None,
    cat_label_map=None,                # optional fn(code)->friendly label
) -> Tuple[go.Figure, int]:
    """Parallel coordinates plot across N columns.

    Each UAV is one line crossing all axes. Drag a section of any axis to filter
    interactively. `color_by` colors lines by another column.

    `color_mode`:
      - "categorical" — `color_by` is a categorical column (Engine type etc.).
        Builds a discrete-color scale.
      - "continuous"  — `color_by` is a numeric column (Endurance, Range, ...).
        Builds a viridis gradient — VizCraft-style objective coloring.

    `custom_points`: list of dicts to overlay as bright-yellow lines. The dicts
    should contain values for the columns being plotted (and ideally the
    `color_by` column too, otherwise the custom line gets the middle color).
    Note: Plotly's parcoords does NOT support per-line hover. Custom lines
    can be identified by their distinctive bright color.

    This is the workflow's most important interaction: color drives the eye to
    the high-objective regions of the design space.
    """
    use_cols = [c for c in cols if c in df.columns]
    if len(use_cols) < 2:
        fig = go.Figure()
        fig.update_layout(
            height=height,
            annotations=[dict(
                text="Pick at least 2 columns.", showarrow=False,
                xref="paper", yref="paper", x=0.5, y=0.5,
                font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0, {"n_custom": 0, "skipped": [], "categorical_cats": None}

    sub = df[use_cols].copy()
    sub["__id"] = df.index
    sub[NAME_COL] = df[NAME_COL]
    if color_by and color_by in df.columns:
        sub[color_by] = df[color_by]
    sub = sub.dropna(subset=use_cols)
    if len(sub) == 0:
        fig = go.Figure()
        fig.update_layout(
            height=height,
            annotations=[dict(
                text="No rows have data on every selected column.",
                showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
                font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0, {"n_custom": 0, "skipped": [], "categorical_cats": None}

    # Append custom points as extra rows. They'll appear as parcoord lines.
    # Plotly parcoords doesn't support per-line markup, so the only way to
    # show custom designs is to inject them into the line set. We mark them
    # in NAME_COL for visibility.
    n_custom = 0
    custom_skipped = []
    if custom_points:
        custom_rows = []
        for cp in custom_points:
            row = {}
            missing_cols = []
            for c in use_cols:
                v = cp.get(c)
                if v is None or pd.isna(v):
                    missing_cols.append(c)
                else:
                    row[c] = float(v)
            if missing_cols:
                # Track which custom designs can't be plotted and why
                custom_skipped.append({
                    "name": cp.get("name", "Custom"),
                    "missing": missing_cols,
                })
                continue
            row[NAME_COL] = f"⚐ {cp.get('name', 'Custom')}"
            row["__id"] = -1 - len(custom_rows)
            if color_by and color_by in sub.columns:
                row[color_by] = cp.get(color_by)
            custom_rows.append(row)
        if custom_rows:
            custom_df = pd.DataFrame(custom_rows)
            sub = pd.concat([sub, custom_df], ignore_index=True)
            n_custom = len(custom_rows)
    # Store skipped customs for caller to display in caption
    _custom_skipped_info = custom_skipped

    # Build parcoord dimensions
    dims = []
    for c in use_cols:
        label = NUMERIC_LABELS.get(c, c)
        dims.append(dict(
            label=label,
            values=sub[c],
            range=[sub[c].min(), sub[c].max()],
        ))

    # Color mapping
    if color_by and color_by in sub.columns and color_mode == "continuous":
        # Numeric objective coloring (VizCraft style)
        color_vals = pd.to_numeric(sub[color_by], errors="coerce")
        # Fill NaN with median so the line still draws
        if color_vals.notna().any():
            color_vals = color_vals.fillna(color_vals.median())
            cmin = float(color_vals.min())
            cmax = float(color_vals.max())
        else:
            color_vals = pd.Series([0] * len(sub), index=sub.index)
            cmin, cmax = 0, 1
        line = dict(
            color=color_vals.values,
            colorscale="Viridis",
            cmin=cmin, cmax=cmax,
            showscale=True,
            colorbar=dict(
                title=NUMERIC_LABELS.get(color_by, color_by),
                thickness=14, len=0.75,
            ),
        )
    elif color_by and color_by in sub.columns:
        # Categorical
        cats = sub[color_by].fillna("(none)").astype(str)
        unique_cats = sorted(cats.unique())
        cat_to_idx = {cat: i for i, cat in enumerate(unique_cats)}
        color_idx = cats.map(cat_to_idx).values

        colors = [_color_for(c, ENGINE_COLORS, GENERIC_PALETTE,
                                stable_order=unique_cats)
                  for c in unique_cats]
        if len(unique_cats) > 1:
            colorscale = []
            for i, c in enumerate(colors):
                colorscale.append([i / (len(unique_cats) - 1), c])
                if i < len(unique_cats) - 1:
                    colorscale.append([(i + 1) / (len(unique_cats) - 1), c])
        else:
            colorscale = [[0, colors[0]], [1, colors[0]]]

        line = dict(
            color=color_idx,
            colorscale=colorscale,
            cmin=0, cmax=max(0, len(unique_cats) - 1),
            showscale=True,
            colorbar=dict(
                title=dict(text=color_by, side="right"),
                thickness=16, len=0.85,
                # Place a tick at the center of each category band so the
                # category name shows. Plotly Parcoords can't do a true
                # discrete legend, but a labeled colorbar is the closest
                # equivalent and tells the user which color = which category.
                tickmode="array",
                tickvals=list(range(len(unique_cats))),
                ticktext=[cat_label_map(c) if cat_label_map else c
                           for c in unique_cats],
                tickfont=dict(size=10),
            ),
        )
    else:
        line = dict(color="rgba(83,74,183,0.45)")

    # v0.8.29: explicit dark fonts for parcoord. Plotly's default font color
    # follows the theme, which in Streamlit "light" mode renders too pale
    # against the white background — axis labels and tick values become
    # blurred / unreadable. A dark gray (#2c3e50) contrasts well on both
    # white and dark backgrounds.
    PARCOORD_LABEL_COLOR = "#2c3e50"
    PARCOORD_TICK_COLOR = "#2c3e50"
    fig = go.Figure(data=go.Parcoords(
        line=line,
        dimensions=dims,
        labelfont=dict(size=12, color=PARCOORD_LABEL_COLOR),
        tickfont=dict(size=10, color=PARCOORD_TICK_COLOR),
        rangefont=dict(size=10, color=PARCOORD_TICK_COLOR),
    ))
    fig.update_layout(height=height, margin=dict(l=60, r=80, t=40, b=20))
    return fig, len(sub), {"n_custom": n_custom, "skipped": _custom_skipped_info,
                            "categorical_cats": (unique_cats if
                                (color_by and color_by in sub.columns
                                 and color_mode != "continuous") else None)}


def splom(
    df: pd.DataFrame,
    cols: List[str],
    color_by: Optional[str] = None,
    height_per_row: int = 280,
    custom_points: Optional[List[dict]] = None,
    merge_categories: Optional[dict] = None,
    only_show_categories: Optional[List[str]] = None,
) -> Tuple[go.Figure, int]:
    """Pair-scatter grid: every unique (col_a, col_b) combination as its own
    scatter, laid out 2 plots per row. Each subplot has full x AND y axis
    labels/ticks and gridlines (vs. the Plotly Splom default where only the
    leftmost column shows y-axis ticks).

    Custom design overlays appear in every subplot.

    `merge_categories`: dict mapping subcategory labels to merged labels
    (same semantics as in flexible_scatter). Applied before color/symbol
    assignment so merged groups get one color, one symbol.

    `only_show_categories`: if set, only these (merged) labels appear.
    """
    from plotly.subplots import make_subplots
    from itertools import combinations

    use_cols = [c for c in cols if c in df.columns]
    if len(use_cols) < 2:
        fig = go.Figure()
        fig.update_layout(
            height=400,
            annotations=[dict(
                text="Pick at least 2 columns.", showarrow=False,
                xref="paper", yref="paper", x=0.5, y=0.5,
                font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0

    sub = df[use_cols + [NAME_COL]].copy()
    sub["__id"] = df.index
    if color_by and color_by in df.columns:
        sub[color_by] = df[color_by]
    sub = sub.dropna(subset=use_cols)
    for c in use_cols:
        sub = sub[sub[c] > 0]

    # Apply category merging — replace specific subcategory labels with their
    # merged target. Done before color/symbol assignment so merged groups
    # get one color, one symbol.
    if color_by and merge_categories and color_by in sub.columns:
        merged_col = sub[color_by].astype("object")
        merged_col = merged_col.replace(merge_categories)
        sub[color_by] = merged_col

    # Apply only_show_categories — restrict to selected (merged) labels
    if color_by and only_show_categories and color_by in sub.columns:
        sub = sub[sub[color_by].astype(str).isin(only_show_categories)]

    if len(sub) == 0:
        fig = go.Figure()
        fig.update_layout(
            height=400,
            annotations=[dict(
                text="No rows have data on every selected column.",
                showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
                font=dict(size=14, color="gray"),
            )],
        )
        return fig, 0

    # All unique pairs (lower triangle)
    pairs = list(combinations(use_cols, 2))
    n_pairs = len(pairs)
    n_cols_grid = 2    # 2 plots per row
    n_rows_grid = (n_pairs + n_cols_grid - 1) // n_cols_grid

    # v0.8.33b: FULL friendly names instead of cryptic short codes. The
    # SHORT_LABELS dict was used everywhere — subplot titles, axis titles,
    # hover. User reported "Cr×End×PL" is unreadable; switched to the same
    # full names that NUMERIC_LABELS uses in the rest of the app.
    # FULL_LABELS = NUMERIC_LABELS for these keys, with a few hand-tuned
    # short variants where the full version is too long for axis titles.
    FULL_LABELS = {
        "MTOW_kg": "MTOW (kg)",
        "Payload_kg": "Payload (kg)",
        "Endurance_h": "Endurance (h)",
        "BestRange_km": "Best Range (km)",
        "Range_km": "Datalink Range (km)",
        "DerivedRange_km": "Derived Range (km)",
        "ActualRange_km": "Verified Range (km)",
        "MaxSpeed_kmh": "Max Speed (km/h)",
        "CruiseSpeed_kmh": "Cruise Speed (km/h)",
        "StallSpeed_kmh": "Stall Speed (km/h)",
        "Wingspan_m": "Wingspan (m)",
        "Length_m": "Length (m)",
        "Height_m": "Height (m)",
        "Ceiling_km": "Ceiling (km)",
        "EngPower_hp": "Engine Power (hp)",
        "PayloadFraction": "Payload Fraction",
        "PowerLoading_hp_per_kg": "Power Loading (hp/kg)",
        "PayloadEnduranceProduct_kgh": "Payload × Endurance (kg·h)",
        "MissionProductivity_Cruise_kgkm":
            "Cruise Speed × Endurance × Payload (km·kg)",
        "MissionProductivity_Max_kgkm":
            "Max Speed × Endurance × Payload (km·kg)",
        "AspectRatio": "Aspect Ratio",
        "MeanChord_m": "Mean Chord (m)",
    }
    # Back-compat alias — older code in this function still references SHORT_LABELS
    SHORT_LABELS = FULL_LABELS

    # Build subplot titles: "Y vs X" for each pair, using FULL friendly names
    subplot_titles = [f"{FULL_LABELS.get(b, b)} vs {FULL_LABELS.get(a, a)}"
                      for a, b in pairs]
    # Pad to fill the grid
    subplot_titles += [""] * (n_rows_grid * n_cols_grid - n_pairs)

    # v0.8.33b: fixed-pixel plot-area + fixed-pixel gap. Plotly's
    # vertical_spacing is a fraction of total height, so naively keeping
    # height_per_row=280 while adding rows made each subplot SHRINK
    # (more rows × same fractional gap = more total gap eaten from each).
    # Fix: pre-compute total height so plot-area is constant 280 px per
    # row regardless of column count, plus a 60 px gap between rows.
    PLOT_AREA_PER_ROW = max(height_per_row, 280)
    # v0.8.34a: gap bumped 60 → 100 px. v0.8.33b's 60 px wasn't enough —
    # second row's subplot titles were overlapping the first row's x-axis
    # numeric labels. 100 px leaves clearance for both x-axis title + ticks
    # above and subplot title below.
    GAP_PX_BETWEEN_ROWS = 100
    total_height = (n_rows_grid * PLOT_AREA_PER_ROW
                     + max(n_rows_grid - 1, 0) * GAP_PX_BETWEEN_ROWS
                     + 80)   # top/bottom margins
    v_spacing = (GAP_PX_BETWEEN_ROWS / total_height) if n_rows_grid > 1 else 0

    fig = make_subplots(
        rows=n_rows_grid, cols=n_cols_grid,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.14,    # generous spacing for axis labels
        vertical_spacing=v_spacing,
    )

    # Build color mapping
    if color_by and color_by in sub.columns:
        cats = sub[color_by].fillna("(none)").astype(str)
        unique_cats = sorted(cats.unique())
        cat_to_color = {c: _color_for(c, ENGINE_COLORS, GENERIC_PALETTE,
                                         stable_order=unique_cats)
                        for c in unique_cats}
        cat_to_symbol = {c: SYMBOL_PALETTE[i % len(SYMBOL_PALETTE)]
                          for i, c in enumerate(unique_cats)}
    else:
        cat_to_color = None
        cat_to_symbol = None

    # Draw each pair into the appropriate subplot
    legend_shown = set()    # categories already legend-shown
    for idx, (col_a, col_b) in enumerate(pairs):
        r = idx // n_cols_grid + 1
        c_idx = idx % n_cols_grid + 1

        if cat_to_color is not None:
            for cat in unique_cats:
                mask = cats == cat
                sub_cat = sub[mask]
                if len(sub_cat) == 0:
                    continue
                show_in_legend = cat not in legend_shown
                fig.add_trace(go.Scatter(
                    x=sub_cat[col_a], y=sub_cat[col_b], mode="markers",
                    name=cat, legendgroup=cat,
                    showlegend=show_in_legend,
                    marker=dict(color=cat_to_color[cat],
                                size=5, opacity=0.7,
                                symbol=cat_to_symbol[cat],
                                line=dict(width=0)),
                    text=sub_cat[NAME_COL].astype(str).str.strip(),
                    hovertemplate=(f"<b>%{{text}}</b><br>"
                                   f"{SHORT_LABELS.get(col_a, col_a)}: %{{x:,.3g}}<br>"
                                   f"{SHORT_LABELS.get(col_b, col_b)}: %{{y:,.3g}}<extra></extra>"),
                ), row=r, col=c_idx)
                legend_shown.add(cat)
        else:
            fig.add_trace(go.Scatter(
                x=sub[col_a], y=sub[col_b], mode="markers",
                name=f"Dataset", legendgroup="data",
                showlegend=(idx == 0),
                marker=dict(color="rgba(83,74,183,0.55)", size=5,
                            opacity=0.7, line=dict(width=0)),
                text=sub[NAME_COL].astype(str).str.strip(),
                hovertemplate=(f"<b>%{{text}}</b><br>"
                               f"{SHORT_LABELS.get(col_a, col_a)}: %{{x:,.3g}}<br>"
                               f"{SHORT_LABELS.get(col_b, col_b)}: %{{y:,.3g}}<extra></extra>"),
            ), row=r, col=c_idx)

        # Overlay custom designs
        if custom_points:
            for cp in custom_points:
                cx = cp.get(col_a)
                cy = cp.get(col_b)
                if cx is None or cy is None or pd.isna(cx) or pd.isna(cy):
                    continue
                if cx <= 0 or cy <= 0:
                    continue    # log-incompatible
                name = cp.get("name", "Custom")
                fig.add_trace(go.Scatter(
                    x=[cx], y=[cy], mode="markers",
                    name=f"⚐ {name}", legendgroup=f"custom_{name}",
                    showlegend=(idx == 0),    # legend once
                    marker=dict(symbol="star", color="#BA7517",
                                size=14, line=dict(width=2, color="#000")),
                    hovertemplate=(f"<b>⚐ {name}</b><br>"
                                   f"{SHORT_LABELS.get(col_a, col_a)}: %{{x:,.3g}}<br>"
                                   f"{SHORT_LABELS.get(col_b, col_b)}: %{{y:,.3g}}<extra></extra>"),
                ), row=r, col=c_idx)

        # Configure this subplot's axes
        fig.update_xaxes(
            title=dict(text=SHORT_LABELS.get(col_a, col_a),
                        font=dict(size=10)),
            type="log",
            showgrid=True, gridcolor="rgba(128,128,128,0.18)",
            tickfont=dict(size=9), showticklabels=True,
            showline=True, linewidth=1.2, linecolor="rgba(80,80,80,0.8)",
            mirror=True, ticks="outside", ticklen=4,
            row=r, col=c_idx,
        )
        fig.update_yaxes(
            title=dict(text=SHORT_LABELS.get(col_b, col_b),
                        font=dict(size=10)),
            type="log",
            showgrid=True, gridcolor="rgba(128,128,128,0.18)",
            tickfont=dict(size=9), showticklabels=True,
            showline=True, linewidth=1.2, linecolor="rgba(80,80,80,0.8)",
            mirror=True, ticks="outside", ticklen=4,
            row=r, col=c_idx,
        )

    fig.update_layout(
        # v0.8.33b: total_height pre-computed above to guarantee 280 px
        # plot area per row + 60 px gap, regardless of column count.
        height=total_height,
        margin=dict(l=60, r=20, t=40, b=40),
        legend=dict(orientation="v", x=1.02, y=1.0, xanchor="left",
                     yanchor="top", font=dict(size=10),
                     itemclick=False, itemdoubleclick=False),
    )
    return fig, len(sub)
