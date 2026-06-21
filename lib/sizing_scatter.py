"""Sizing-scatter plotting helpers.

`make_sizing_scatter` produces a Plotly figure for one sizing relation given
a list of "groups" (each with its own data, color, name). Used by Compare
filters to render overlays of A vs B subsets.

Key features:
- log or linear axes per relation (overridable)
- explicit log-axis tick values (fixes Plotly's irregular 2/3/5/100/800 ticks)
- hover tooltips include id + designation
- optional canonical-fit overlay line from the literature
- optional per-group power-law fits with equation labels
- distinct color + symbol per category to disambiguate similar hues
"""
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from .relations import SizingRelation
from .loader import NAME_COL
from .fitting import fit_power_law, fit_line_xy
from .labels import code_to_label


# Fixed engine palette (kept stable across releases so the same engine type
# always gets the same color across charts)
ENGINE_COLORS = {
    "P": "#1f77b4", "E": "#2ca02c", "H": "#9467bd", "FC": "#17becf",
    "S": "#ff7f0e", "Turbojet": "#d62728", "Turbofan": "#8c564b",
    "Turboprop": "#e377c2", "DF": "#bcbd22", "G": "#7f7f7f",
}

# 24-color high-contrast palette. Adjacent indices intentionally differ in
# both hue AND lightness. This is the same palette used by lib/explorer.py
# so categorical colors are consistent across pages.
HC_PALETTE = [
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
    "#637939",  # dark olive
    "#a55194",  # magenta
    "#bd9e39",  # mustard
    "#ad494a",  # rose-red
]

# Symbol palette — cycled in parallel with color. So even if two categories
# end up with similar shades, their shapes differ. Plotly accepts these names:
SYMBOL_PALETTE = [
    "circle", "square", "diamond", "triangle-up", "triangle-down",
    "star", "hexagon", "cross", "x", "pentagon",
    "triangle-left", "triangle-right", "hourglass", "bowtie", "circle-cross",
    "circle-x", "square-cross", "diamond-tall", "star-square", "hexagon2",
    "octagon", "asterisk", "circle-open", "square-open",
]


def _assign_color_symbol(cat_label: str, stable_order: List[str]) -> Tuple[str, str]:
    """Return (color, symbol) for a category. ENGINE_COLORS overrides the
    palette for known engine codes. Stable-order assignment prevents hash
    collisions.
    """
    if cat_label in ENGINE_COLORS:
        # Engine has a fixed color; still pick a symbol by position
        symbol = SYMBOL_PALETTE[stable_order.index(cat_label)
                                  % len(SYMBOL_PALETTE)] \
            if cat_label in stable_order else "circle"
        return ENGINE_COLORS[cat_label], symbol
    if cat_label in stable_order:
        idx = stable_order.index(cat_label)
        return HC_PALETTE[idx % len(HC_PALETTE)], \
               SYMBOL_PALETTE[idx % len(SYMBOL_PALETTE)]
    # Fallback (shouldn't normally hit this)
    return "#666666", "circle"


# Explicit major-tick values for log axes.
LOG_DECADE_TICKS = [
    0.001, 0.01, 0.1, 1, 10, 100, 1_000, 10_000, 100_000,
]


def _decade_ticks_for_range(vmin: float, vmax: float):
    """Return (vals, labels) for log-axis ticks within [vmin, vmax].

    - If the range spans <2 decades, include intermediate values (1, 2, 5, 10,
      20, 50, ...) so the user has multiple readable ticks. A pure decade
      tickset like [1, 10] is unreadable when actual data sits between 1 and 8.
    - For wider ranges, return decades only to keep labels uncluttered.
    """
    if vmin <= 0 or vmax <= 0:
        return None, None
    if vmin >= vmax:
        # Degenerate range — show one decade around the value
        return [vmin], [f"{vmin:g}"]

    lo_exp = int(np.floor(np.log10(vmin)))
    hi_exp = int(np.ceil(np.log10(vmax)))
    # Use the actual log range, not floor/ceil bounds, to decide if we need
    # intermediate ticks. e.g. 0.5 to 15 has actual span ~1.5 decades, even
    # though floor/ceil bounds span 3.
    actual_span = np.log10(vmax) - np.log10(vmin)

    # When the actual data span is <= 1.5 decades, include intermediate 2x
    # and 5x ticks so narrow ranges still have several labeled values.
    # Above 1.5 decades, decade-only — keeps wider plots (MTOW spanning
    # 6 decades, Endurance ~6, Ceiling ~5) from looking dense with gridlines.
    # v0.8.22: threshold lowered from 2.5 → 1.5 per user request.
    if actual_span <= 1.5:
        vals = []
        for e in range(lo_exp - 1, hi_exp + 1):
            base = 10**e
            for mult in [1, 2, 5]:
                v = base * mult
                if v >= vmin * 0.5 and v <= vmax * 2:
                    vals.append(v)
    else:
        # Wide range: just decades
        vals = [10**e for e in range(lo_exp, hi_exp + 1)]

    # De-duplicate and sort
    vals = sorted(set(vals))

    # Cap to ~8 ticks for readability; if too many, drop the 2x ticks first
    # (keeping 1x and 5x which form a nice 1/5/10/50/100 pattern).
    if len(vals) > 8:
        # Keep multiples of 1 and 5 only
        vals = [v for v in vals
                 if any(abs(v - 10**e * m) / max(v, 1e-9) < 0.01
                        for e in range(-5, 6) for m in [1, 5])]
        if len(vals) > 10:    # still too many — fall back to decades
            decades = [v for v in vals
                        if abs(v - 10**round(np.log10(v))) / v < 0.01]
            vals = decades

    # Format labels: integers for >=1, decimals for <1
    labels = []
    for v in vals:
        if v >= 1000:
            labels.append(f"{v:,.0f}")
        elif v >= 1:
            labels.append(f"{v:g}")
        else:
            labels.append(f"{v:g}")
    return vals, labels


def make_sizing_scatter(
    relation: SizingRelation,
    groups: List[dict],            # each: {df, name, color, [symbol]}
    x_type: str = None,
    y_type: str = None,
    show_canonical_fit: bool = False,
    show_group_fits: bool = False,
    color_by: Optional[str] = None,
    fit_per_category: bool = False,
    height: int = 380,
    side_by_side: bool = False,    # if True with color_by, render A and B as
                                    # separate subplots side-by-side
    hide_uncategorized: bool = True,  # drop rows with NaN in the color column
    merge_categories: Optional[dict] = None,    # old_label -> merged_label
    only_show_categories: Optional[List[str]] = None,  # if set, only these
) -> Tuple[go.Figure, dict]:
    """Build a scatter for one sizing relation across multiple groups.

    Returns (fig, info) where:
      info['stats'][group_name] = n_points
      info['fits']              = dict of FitResult keyed by 'A', 'B', or
                                   '<category>' if fit_per_category

    `hide_uncategorized`: when color_by is set, drop rows with no value on
    that column (NaN). These rows can't reliably be assigned a category, so
    fitting them as a single "(none)" group produces a meaningless line.
    Default True.

    `merge_categories`: dict mapping subcategory labels to merged labels. E.g.
    {"T": "fixed", "R": "fixed", "e": "fixed", "Polyhedral": "fixed"} merges
    those four wing-form labels into a single "fixed" group. Applied before
    color/symbol assignment and fitting — so the merged group gets one color,
    one symbol, one fit line.

    `only_show_categories`: if set, only these (merged) labels appear.
    """
    if x_type is None:
        x_type = relation.default_x_type
    if y_type is None:
        y_type = relation.default_y_type

    # Side-by-side handler — for color_by + multi-group, render two subplots
    if side_by_side and color_by and len(groups) > 1:
        return _make_side_by_side_scatter(
            relation, groups, x_type, y_type,
            show_canonical_fit, show_group_fits,
            color_by, fit_per_category, height,
            hide_uncategorized=hide_uncategorized,
        )

    fig = go.Figure()
    stats = {}
    fits = {}
    all_x, all_y = [], []

    # Pre-compute stable category order across all groups so the same category
    # always maps to the same color + symbol, regardless of group ordering.
    # IMPORTANT: apply merge_categories BEFORE computing the order, so that
    # merged labels (e.g. "fixed", "swept-all") appear in the stable list and
    # each gets a unique color/symbol from the palette.
    stable_order: List[str] = []
    if color_by:
        all_cats = set()
        for g in groups:
            if color_by in g["df"].columns:
                vals = g["df"][color_by].dropna().astype(str).unique()
                all_cats.update(vals)
        # Apply merge mapping to the category set
        if merge_categories:
            all_cats = {merge_categories.get(c, c) for c in all_cats}
        # Filter to only_show_categories if set
        if only_show_categories:
            all_cats = all_cats & set(only_show_categories)
        stable_order = sorted(all_cats)

    accumulated_by_category = {}   # category -> {x, y, color}

    for g in groups:
        sub = g["df"][[relation.x_col, relation.y_col, NAME_COL]].copy()
        sub["__id"] = g["df"].index
        if color_by and color_by in g["df"].columns:
            sub[color_by] = g["df"][color_by]
        # v0.8.34b+c: carry the per-row estimated flag if the relation
        # has one. Used downstream to render estimated points with open
        # markers, mark them in hover, and EXCLUDE them from the fit.
        y_est_col = getattr(relation, "y_estimated_col", None)
        if y_est_col and y_est_col in g["df"].columns:
            sub["__estimated"] = g["df"][y_est_col].fillna(False).astype(bool)
        else:
            sub["__estimated"] = False
        sub = sub.dropna(subset=[relation.x_col, relation.y_col])
        if x_type == "log":
            sub = sub[sub[relation.x_col] > 0]
        if y_type == "log":
            sub = sub[sub[relation.y_col] > 0]

        # Apply category merging — replace specific subcategory labels with
        # their merged target. Done before color/symbol/fitting so the merged
        # group acts as a single category.
        if color_by and merge_categories and color_by in sub.columns:
            merged_col = sub[color_by].astype("object")
            merged_col = merged_col.replace(merge_categories)
            sub[color_by] = merged_col

        # Apply only_show_categories — restrict to selected (merged) labels
        if color_by and only_show_categories and color_by in sub.columns:
            sub = sub[sub[color_by].astype(str).isin(only_show_categories)]

        stats[g["name"]] = len(sub)
        if len(sub) == 0:
            continue
        all_x.extend(sub[relation.x_col].tolist())
        all_y.extend(sub[relation.y_col].tolist())

        # Legend group makes Plotly cluster these entries together
        group_legendgroup = f"group_{g['name']}"
        marker_symbol = g.get("symbol", "circle")

        if color_by and color_by in sub.columns:
            for cat, sub_cat in sub.groupby(color_by, dropna=False):
                is_uncategorized = pd.isna(cat)
                # When color_by is set, uncategorized rows can't be assigned
                # to a meaningful group. If hide_uncategorized, skip them
                # entirely. Otherwise still show the points but never fit them.
                if is_uncategorized and hide_uncategorized:
                    continue
                cat_label = str(cat) if not is_uncategorized else "(uncategorized)"
                # v0.8.29: friendly display name for the legend. cat_label
                # stays as the raw code for stable color/symbol assignment
                # and hover; only the trace name surface uses cat_display.
                if is_uncategorized or color_by not in ("Mission", "EngineType",
                        "LaunchMethod", "WingForm", "WingConfig", "BodyConfig",
                        "TailConfig", "Airframe", "OperationalRole"):
                    cat_display = cat_label
                else:
                    cat_display = code_to_label(color_by, cat_label)
                color, sym = _assign_color_symbol(cat_label, stable_order)
                # v0.8.34a-fix2: PRECEDENCE FLIPPED per user direction.
                # When color_by is ON AND multiple groups are visible,
                # Filter A and Filter B should keep their canonical colors
                # (purple / green) across the WHOLE app — dominance bars,
                # scatter, histogram, everything. Otherwise tracking
                # which dot belongs to A vs B requires reading both color
                # AND symbol. v0.8.34a's logic (color=category,
                # symbol=group) was visually noisy: category color carried
                # no useful information once color_by was used as a filter.
                # Now: color = GROUP (consistent A vs B), symbol = CATEGORY.
                if len(groups) > 1 and "color" in g:
                    point_color = g["color"]
                    point_symbol = sym   # category symbol
                else:
                    point_color = color   # category color (single-group case)
                    point_symbol = sym
                if is_uncategorized:
                    point_color = "#999999"
                    point_symbol = "circle-open"   # ringed grey, clearly different
                # v0.8.34c-fix1: also split measured vs estimated in the
                # color_by branch. Previously only the no-color_by branch
                # did this, so when the user picked "color by EngineType"
                # the estimated-flag distinction was lost.
                if "__estimated" in sub_cat.columns:
                    sub_cat_real = sub_cat[~sub_cat["__estimated"]]
                    sub_cat_est  = sub_cat[ sub_cat["__estimated"]]
                else:
                    sub_cat_real = sub_cat
                    sub_cat_est  = sub_cat.iloc[0:0]

                # Render measured points (filled markers)
                if len(sub_cat_real) > 0:
                    customdata = np.column_stack([
                        sub_cat_real["__id"].astype(int).to_numpy(),
                        sub_cat_real[NAME_COL].astype(str).str.strip().to_numpy(),
                    ])
                    hovertemplate = (
                        f"<b>%{{customdata[1]}}</b><br>"
                        f"row id: %{{customdata[0]}}<br>"
                        f"{color_by}: {cat_display}<br>"
                        f"{relation.x_label}: %{{x:,.3g}}<br>"
                        f"{relation.y_label}: %{{y:,.3g}}<extra></extra>"
                    )
                    fig.add_trace(go.Scatter(
                        x=sub_cat_real[relation.x_col],
                        y=sub_cat_real[relation.y_col],
                        mode="markers",
                        name=f"{g['name']} · {cat_display} (n={len(sub_cat_real)})",
                        marker=dict(color=point_color, size=8, opacity=0.75,
                                    line=dict(width=0.5,
                                              color="rgba(0,0,0,0.3)"),
                                    symbol=point_symbol),
                        customdata=customdata,
                        hovertemplate=hovertemplate,
                        legendgroup=group_legendgroup,
                        legendgrouptitle_text=f"Group {g['name']}",
                    ))
                # Render estimated points (open markers, "≈ est." label)
                if len(sub_cat_est) > 0:
                    customdata_est = np.column_stack([
                        sub_cat_est["__id"].astype(int).to_numpy(),
                        sub_cat_est[NAME_COL].astype(str).str.strip().to_numpy(),
                    ])
                    hovertemplate_est = (
                        f"<b>%{{customdata[1]}} ≈ estimated</b><br>"
                        f"row id: %{{customdata[0]}}<br>"
                        f"{color_by}: {cat_display}<br>"
                        f"{relation.x_label}: %{{x:,.3g}}<br>"
                        f"{relation.y_label}: %{{y:,.3g}} (≈ est. from MaxSpeed)"
                        f"<extra></extra>"
                    )
                    base_sym = point_symbol if point_symbol else "circle"
                    est_symbol = base_sym + "-open" if not base_sym.endswith("-open") else base_sym
                    fig.add_trace(go.Scatter(
                        x=sub_cat_est[relation.x_col],
                        y=sub_cat_est[relation.y_col],
                        mode="markers",
                        name=f"{g['name']} · {cat_display} ≈ est. (n={len(sub_cat_est)})",
                        marker=dict(color=point_color, size=9, opacity=0.9,
                                    line=dict(width=1.5, color=point_color),
                                    symbol=est_symbol),
                        customdata=customdata_est,
                        hovertemplate=hovertemplate_est,
                        legendgroup=group_legendgroup,
                        legendgrouptitle_text=f"Group {g['name']}",
                    ))
                if fit_per_category and not is_uncategorized:
                    if cat_label not in accumulated_by_category:
                        accumulated_by_category[cat_label] = {
                            "x": [], "y": [], "color": color,
                        }
                    # v0.8.34b+c: exclude estimated rows from per-category fit
                    accumulated_by_category[cat_label]["x"].extend(
                        sub_cat_real[relation.x_col].tolist())
                    accumulated_by_category[cat_label]["y"].extend(
                        sub_cat_real[relation.y_col].tolist())
        else:
            # v0.8.34b+c: two-tier rendering when relation carries an
            # estimated-flag column. Split sub into measured (filled
            # markers) and estimated (open markers, with "≈" tag in hover).
            sub_real = sub[~sub["__estimated"]]
            sub_est  = sub[ sub["__estimated"]]

            # Always render the measured trace
            customdata = np.column_stack([
                sub_real["__id"].astype(int).to_numpy(),
                sub_real[NAME_COL].astype(str).str.strip().to_numpy(),
            ])
            hovertemplate = (
                f"<b>%{{customdata[1]}}</b><br>"
                f"row id: %{{customdata[0]}}<br>"
                f"{relation.x_label}: %{{x:,.3g}}<br>"
                f"{relation.y_label}: %{{y:,.3g}}<extra></extra>"
            )
            fig.add_trace(go.Scatter(
                x=sub_real[relation.x_col], y=sub_real[relation.y_col],
                mode="markers",
                name=f"{g['name']} (n={len(sub_real)})",
                marker=dict(color=g["color"], size=7, opacity=0.7,
                            line=dict(width=0), symbol=marker_symbol),
                customdata=customdata, hovertemplate=hovertemplate,
                legendgroup=group_legendgroup,
                legendgrouptitle_text=f"Group {g['name']}",
            ))
            # Render the estimated trace as open markers if any rows have
            # been estimated. Hover marks them with "≈ estimated".
            if len(sub_est) > 0:
                est_customdata = np.column_stack([
                    sub_est["__id"].astype(int).to_numpy(),
                    sub_est[NAME_COL].astype(str).str.strip().to_numpy(),
                ])
                est_hovertemplate = (
                    f"<b>%{{customdata[1]}} ≈ estimated</b><br>"
                    f"row id: %{{customdata[0]}}<br>"
                    f"{relation.x_label}: %{{x:,.3g}}<br>"
                    f"{relation.y_label}: %{{y:,.3g}} (≈ est. from MaxSpeed)"
                    f"<extra></extra>"
                )
                # Build open-marker symbol: take base symbol and add '-open'
                base_sym = marker_symbol if marker_symbol else "circle"
                # Plotly uses '-open' suffix for hollow versions
                if not base_sym.endswith("-open"):
                    est_symbol = base_sym + "-open"
                else:
                    est_symbol = base_sym
                fig.add_trace(go.Scatter(
                    x=sub_est[relation.x_col], y=sub_est[relation.y_col],
                    mode="markers",
                    name=f"{g['name']} ≈ est. (n={len(sub_est)})",
                    marker=dict(color=g["color"], size=8, opacity=0.85,
                                line=dict(width=1.5, color=g["color"]),
                                symbol=est_symbol),
                    customdata=est_customdata,
                    hovertemplate=est_hovertemplate,
                    legendgroup=group_legendgroup,
                    legendgrouptitle_text=f"Group {g['name']}",
                ))

        # Per-group fit (when not fit_per_category)
        # v0.8.34b+c: fit on MEASURED rows only (exclude estimated points).
        # Estimated points are derived from MaxSpeed and would confirm
        # whatever shape they carry; including them would taint the fit.
        sub_for_fit = sub[~sub["__estimated"]] if "__estimated" in sub.columns else sub
        if show_group_fits and not fit_per_category:
            fit = fit_power_law(sub_for_fit[relation.x_col],
                                 sub_for_fit[relation.y_col],
                                 label=g["name"])
            fits[g["name"]] = fit
            if fit is not None:
                xs, ys = fit_line_xy(fit)
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    name=(f"{g['name']} fit · {fit.equation} "
                          f"(R²={fit.r_squared:.2f}, n={fit.n})"),
                    line=dict(color=g["color"], width=2.5, dash="solid"),
                    hoverinfo="skip", opacity=0.9,
                    legendgroup="fits",
                    legendgrouptitle_text="Fits",
                ))
        elif not show_group_fits:
            fits[g["name"]] = None

    # Per-category fits across merged groups
    if show_group_fits and fit_per_category:
        for cat_label, acc in accumulated_by_category.items():
            if len(acc["x"]) < 5:
                # Track for caller to surface as a notification
                fits[f"_skipped:{cat_label}"] = {
                    "category": cat_label,
                    "n": len(acc["x"]),
                    "reason": "n<5 — too few points for reliable fit",
                }
                continue
            fit = fit_power_law(pd.Series(acc["x"]), pd.Series(acc["y"]),
                                 label=cat_label)
            fits[cat_label] = fit
            if fit is not None:
                # v0.8.29: friendly display name in the legend.
                if color_by and color_by in ("Mission", "EngineType",
                        "LaunchMethod", "WingForm", "WingConfig", "BodyConfig",
                        "TailConfig", "Airframe", "OperationalRole"):
                    cat_disp = code_to_label(color_by, cat_label)
                else:
                    cat_disp = cat_label
                xs, ys = fit_line_xy(fit)
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    name=(f"{cat_disp} fit · {fit.equation} "
                          f"(R²={fit.r_squared:.2f}, n={fit.n})"),
                    line=dict(color=acc["color"], width=2.5, dash="solid"),
                    hoverinfo="skip", opacity=0.9,
                    legendgroup="fits",
                    legendgrouptitle_text="Per-category fits",
                ))

    # Canonical literature line. v0.8.28: when exp == 0, the line is a
    # horizontal constant (a "mean" reference, not a power law).
    # X^0 = 1 mathematically, so the math works, but the label "Y = c · X^0"
    # is confusing — special-case to "Y = c (mean)".
    if show_canonical_fit and relation.canonical_coefficient is not None \
       and relation.canonical_exponent is not None and len(all_x) > 0:
        x_min, x_max = min(all_x), max(all_x)
        if x_min > 0:
            xs = np.geomspace(x_min, x_max, 50)
            ys = relation.canonical_coefficient * xs ** relation.canonical_exponent
            if abs(relation.canonical_exponent) < 1e-9:
                eq_str = f"Y = {relation.canonical_coefficient:g} (mean)"
            else:
                eq_str = (f"Y = {relation.canonical_coefficient:g} · X^"
                          f"{relation.canonical_exponent:.3f}")
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                name=f"{relation.canonical_source}: {eq_str}",
                line=dict(color="#1A1A1A", width=2.5, dash="dash"),
                hoverinfo="skip", opacity=0.9,
                legendgroup="reference",
                legendgrouptitle_text="Literature reference",
            ))

    # Axes — always show gridlines, tick labels, AND the axis line (spine)
    # so the chart frame is visible even when no fits or data are present.
    # showline draws the axis line itself; mirror draws it on both sides;
    # zeroline off because log axes have no meaningful zero.
    grid_style = dict(
        showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.25)",
        zeroline=False, showticklabels=True,
        showline=True, linewidth=1.5, linecolor="rgba(80,80,80,0.8)",
        mirror=True, ticks="outside", ticklen=5,
        tickcolor="rgba(80,80,80,0.8)",
    )
    xaxis_config = dict(title=relation.x_label, **grid_style)
    yaxis_config = dict(title=relation.y_label, **grid_style)
    if x_type == "log" and all_x:
        vals, labels = _decade_ticks_for_range(min(all_x), max(all_x))
        if vals:
            # v0.8.23: minor showgrid OFF — the prior subtle minor grid still
            # produced ~8 extra lines per decade × 6 decades = ~48 extra
            # gridlines, making wide-range plots look dense after Plotly
            # finished rendering. Major-only is the cleaner read.
            xaxis_config.update(dict(type="log", tickmode="array",
                                     tickvals=vals, ticktext=labels,
                                     minor=dict(showgrid=False, ticks="")))
    if y_type == "log" and all_y:
        vals, labels = _decade_ticks_for_range(min(all_y), max(all_y))
        if vals:
            yaxis_config.update(dict(type="log", tickmode="array",
                                     tickvals=vals, ticktext=labels,
                                     minor=dict(showgrid=False, ticks="")))

    # Move legend to right side and give the plot some breathing room.
    # itemclick=False disables the unreliable single-click toggle (which
    # was reported to scramble points/fits when many categories present).
    # Double-click still works for isolation. Use "Show only these" in the
    # merge expander above the chart for category filtering.
    # v0.8.30: increased right margin so the legend (especially with
    # longer friendly labels in v0.8.29) doesn't sit on top of data points
    # at the right edge of the plot.
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=140, t=20, b=50),
        xaxis=xaxis_config, yaxis=yaxis_config,
        legend=dict(
            orientation="v", x=1.02, y=1.0, xanchor="left", yanchor="top",
            groupclick="togglegroup",
            itemclick=False,           # disable single-click toggle
            itemdoubleclick="toggle",  # double-click still hides/shows
            font=dict(size=10),
        ),
    )
    return fig, {"stats": stats, "fits": fits}


def _make_side_by_side_scatter(
    relation: SizingRelation, groups, x_type, y_type,
    show_canonical_fit, show_group_fits,
    color_by, fit_per_category, height,
    hide_uncategorized: bool = True,
) -> Tuple[go.Figure, dict]:
    """Render Group A in left subplot, Group B in right subplot."""
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=1, cols=len(groups),
        subplot_titles=[f"Group {g['name']}" for g in groups],
        horizontal_spacing=0.10,
    )
    stats = {}
    fits = {}
    all_x_global, all_y_global = [], []

    # Pre-compute stable category order across both groups
    stable_order: List[str] = []
    if color_by:
        all_cats = set()
        for g in groups:
            if color_by in g["df"].columns:
                vals = g["df"][color_by].dropna().astype(str).unique()
                all_cats.update(vals)
        stable_order = sorted(all_cats)

    # Track which categories have been added to legend to avoid duplicates
    seen_cats = set()

    for col_idx, g in enumerate(groups, start=1):
        sub = g["df"][[relation.x_col, relation.y_col, NAME_COL]].copy()
        sub["__id"] = g["df"].index
        if color_by and color_by in g["df"].columns:
            sub[color_by] = g["df"][color_by]
        sub = sub.dropna(subset=[relation.x_col, relation.y_col])
        if x_type == "log":
            sub = sub[sub[relation.x_col] > 0]
        if y_type == "log":
            sub = sub[sub[relation.y_col] > 0]
        stats[g["name"]] = len(sub)
        if len(sub) == 0:
            continue
        all_x_global.extend(sub[relation.x_col].tolist())
        all_y_global.extend(sub[relation.y_col].tolist())

        # Per-category scatter
        for cat, sub_cat in sub.groupby(color_by, dropna=False):
            is_uncategorized = pd.isna(cat)
            if is_uncategorized and hide_uncategorized:
                continue
            cat_label = str(cat) if not is_uncategorized else "(uncategorized)"
            # v0.8.29: friendly display label
            if is_uncategorized or color_by not in ("Mission", "EngineType",
                    "LaunchMethod", "WingForm", "WingConfig", "BodyConfig",
                    "TailConfig", "Airframe", "OperationalRole"):
                cat_display = cat_label
            else:
                cat_display = code_to_label(color_by, cat_label)
            color, sym = _assign_color_symbol(cat_label, stable_order)
            if is_uncategorized:
                color = "#999999"
                sym = "circle-open"
            customdata = np.column_stack([
                sub_cat["__id"].astype(int).to_numpy(),
                sub_cat[NAME_COL].astype(str).str.strip().to_numpy(),
            ])
            hovertemplate = (
                f"<b>%{{customdata[1]}}</b><br>"
                f"row id: %{{customdata[0]}}<br>"
                f"{color_by}: {cat_display}<br>"
                f"{relation.x_label}: %{{x:,.3g}}<br>"
                f"{relation.y_label}: %{{y:,.3g}}<extra></extra>"
            )
            # Only show legend entry once per category across subplots
            show_legend = cat_label not in seen_cats
            seen_cats.add(cat_label)
            fig.add_trace(go.Scatter(
                x=sub_cat[relation.x_col], y=sub_cat[relation.y_col],
                mode="markers",
                name=f"{cat_display}",
                marker=dict(color=color, size=8, opacity=0.75,
                            line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
                            symbol=sym),
                customdata=customdata, hovertemplate=hovertemplate,
                legendgroup=cat_label,
                showlegend=show_legend,
            ), row=1, col=col_idx)

        # Per-group fit on this subplot
        if show_group_fits:
            for cat, sub_cat in sub.groupby(color_by, dropna=False):
                if not fit_per_category:
                    break    # fit per group (entire subplot)
                if pd.isna(cat):
                    continue    # never fit the uncategorized cluster
                cat_label = str(cat)
                if len(sub_cat) < 5:
                    continue
                color, _ = _assign_color_symbol(cat_label, stable_order)
                fit = fit_power_law(sub_cat[relation.x_col],
                                     sub_cat[relation.y_col], label=cat_label)
                if fit is None:
                    continue
                fits[f"{g['name']}·{cat_label}"] = fit
                xs, ys = fit_line_xy(fit)
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    name=f"{g['name']}·{cat_label} fit",
                    line=dict(color=color, width=2.5),
                    hoverinfo="skip", opacity=0.9,
                    showlegend=False,
                ), row=1, col=col_idx)

            if not fit_per_category:
                fit = fit_power_law(sub[relation.x_col], sub[relation.y_col],
                                     label=g["name"])
                fits[g["name"]] = fit
                if fit:
                    xs, ys = fit_line_xy(fit)
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys, mode="lines",
                        name=f"{g['name']} fit",
                        line=dict(color=g["color"], width=2.5),
                        hoverinfo="skip", opacity=0.9,
                        showlegend=False,
                    ), row=1, col=col_idx)

        # Canonical line per subplot
        if show_canonical_fit and relation.canonical_coefficient is not None \
           and relation.canonical_exponent is not None:
            sub_x = sub[relation.x_col]
            if len(sub_x):
                xs = np.geomspace(sub_x.min(), sub_x.max(), 50)
                ys = relation.canonical_coefficient * xs ** relation.canonical_exponent
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    name="literature",
                    line=dict(color="#1A1A1A", width=2.5, dash="dash"),
                    hoverinfo="skip", opacity=0.9,
                    showlegend=(col_idx == 1),
                ), row=1, col=col_idx)

    # Configure axis types and ticks for each subplot.
    # Apply BOTH x and y config to every subplot (the make_subplots
    # `shared_yaxes=True` is unreliable across Plotly versions).
    n_cols_total = len(groups)
    grid_style = dict(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.25)",
                        zeroline=False,
                        showline=True, linewidth=1.5,
                        linecolor="rgba(80,80,80,0.8)", mirror=True,
                        ticks="outside", ticklen=5,
                        tickcolor="rgba(80,80,80,0.8)")

    if x_type == "log" and all_x_global:
        vals, labels = _decade_ticks_for_range(min(all_x_global), max(all_x_global))
        for col_idx in range(1, n_cols_total + 1):
            fig.update_xaxes(type="log", tickmode="array",
                              tickvals=vals, ticktext=labels,
                              minor=dict(showgrid=False, ticks=""),
                              title=relation.x_label, row=1, col=col_idx,
                              **grid_style)
    else:
        for col_idx in range(1, n_cols_total + 1):
            fig.update_xaxes(title=relation.x_label, row=1, col=col_idx,
                              **grid_style)

    if y_type == "log" and all_y_global:
        vals, labels = _decade_ticks_for_range(min(all_y_global), max(all_y_global))
        for col_idx in range(1, n_cols_total + 1):
            fig.update_yaxes(type="log", tickmode="array",
                              tickvals=vals, ticktext=labels,
                              minor=dict(showgrid=False, ticks=""),
                              title=relation.y_label if col_idx == 1 else None,
                              showticklabels=True,    # numbers on every subplot
                              row=1, col=col_idx, **grid_style)
    else:
        for col_idx in range(1, n_cols_total + 1):
            fig.update_yaxes(title=relation.y_label if col_idx == 1 else None,
                              showticklabels=True,
                              row=1, col=col_idx, **grid_style)

    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=40, b=50),
        legend=dict(orientation="v", x=1.02, y=1.0,
                    xanchor="left", yanchor="top", font=dict(size=10)),
    )
    return fig, {"stats": stats, "fits": fits}


def make_categorical_box(
    relation: SizingRelation,
    groups: List[dict],
    height: int = 500,
) -> Tuple[go.Figure, dict]:
    """Build a box plot for a categorical X column versus numeric Y.

    Used by relations like `powerloading_launchmethod` where the X axis is
    a discrete column (e.g. LaunchMethod) rather than a continuous variable.
    Each `group` produces one box per category, side-by-side.

    Returns (figure, info_dict) where info_dict has the same shape as
    `make_sizing_scatter` (with empty fits) so the calling page can use the
    same downstream code without branching.
    """
    fig = go.Figure()
    stats = {}
    has_any_data = False

    # Collect all categories present across groups, sorted by sample count desc
    all_cats = {}
    for g in groups:
        sub = g["df"][[relation.x_col, relation.y_col]].dropna(
            subset=[relation.y_col])
        # Drop empty/blank category labels
        sub = sub[sub[relation.x_col].astype(str).str.strip().ne("")]
        for cat, group_sub in sub.groupby(relation.x_col):
            all_cats[str(cat)] = all_cats.get(str(cat), 0) + len(group_sub)
    ordered_cats = [c for c, _ in sorted(all_cats.items(),
                                             key=lambda kv: -kv[1])]

    for g in groups:
        sub = g["df"][[relation.x_col, relation.y_col]].dropna(
            subset=[relation.y_col])
        sub = sub[sub[relation.x_col].astype(str).str.strip().ne("")]
        if len(sub) == 0:
            continue
        has_any_data = True
        fig.add_trace(go.Box(
            x=sub[relation.x_col].astype(str),
            y=sub[relation.y_col],
            name=f"{g['name']} (n={len(sub)})",
            marker_color=g["color"],
            boxpoints="outliers",     # show outliers as points
            line=dict(color=g["color"]),
        ))
        stats[g["name"]] = {
            "n": len(sub),
            "mean": float(sub[relation.y_col].mean()),
            "median": float(sub[relation.y_col].median()),
        }

    if not has_any_data:
        fig.add_annotation(
            text="No data available for this relation in the selected groups.",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="rgba(128,128,128,0.7)"),
        )

    fig.update_layout(
        height=height, margin=dict(l=60, r=20, t=40, b=80),
        xaxis=dict(
            title=relation.x_label,
            categoryorder="array", categoryarray=ordered_cats,
            showgrid=False, showline=True, linewidth=1.5,
            linecolor="rgba(80,80,80,0.8)", mirror=True, ticks="outside",
        ),
        yaxis=dict(
            title=relation.y_label,
            type=("log" if relation.default_y_type == "log" else "linear"),
            showgrid=True, gridcolor="rgba(128,128,128,0.25)",
            zeroline=False, showline=True, linewidth=1.5,
            linecolor="rgba(80,80,80,0.8)", mirror=True, ticks="outside",
        ),
        boxmode="group",
        legend=dict(orientation="h", x=0, y=1.05, yanchor="bottom",
                     xanchor="left"),
    )
    return fig, {"stats": stats, "fits": {}}
