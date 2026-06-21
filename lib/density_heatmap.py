"""2D density heatmap for a sizing relation.

For dense scatter plots (e.g. 1,344 platforms), individual markers overlap
heavily and obscure where the cloud is actually thick vs sparse. A binned
heatmap counts points per cell and renders that count as color intensity.

This is the ATSV "binned plots" capability adapted to our project.
"""
from typing import Optional, List
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .relations import SizingRelation


def _build_bin_edges(values: np.ndarray, axis_type: str,
                       n_bins: int) -> np.ndarray:
    """Return log-spaced or linear-spaced bin edges spanning the data."""
    values = values[np.isfinite(values)]
    values = values[values > 0] if axis_type == "log" else values
    if len(values) == 0:
        return np.linspace(0, 1, n_bins + 1)
    lo, hi = values.min(), values.max()
    # padding so the extreme points sit inside a bin, not on the edge
    if axis_type == "log":
        lo = lo * 0.9
        hi = hi * 1.1
        return np.geomspace(lo, hi, n_bins + 1)
    pad = (hi - lo) * 0.05 if hi > lo else 1.0
    return np.linspace(lo - pad, hi + pad, n_bins + 1)


def make_density_heatmap(
    relation: SizingRelation,
    groups: list,
    x_type: str = "log",
    y_type: str = "log",
    n_bins: int = 30,
    show_canonical_fit: bool = False,
    height: int = 440,
):
    """Render a 2D density heatmap for the sizing relation.

    `groups` follows the same shape as for make_sizing_scatter:
    a list of dicts with keys "df", "name", "color".

    Returns (fig, info) where info carries the bin counts for the caller
    to surface in a small caption.

    Behavior notes:
    - When 1 group: single heatmap.
    - When 2 groups: side-by-side subplots (A | B) with shared color scale
      so cell-counts are directly comparable.
    - Bin edges share between A and B so the binning is identical.
    """
    valid_groups = [g for g in groups if len(g.get("df", [])) > 0]
    if not valid_groups:
        fig = go.Figure()
        fig.add_annotation(text="No data to display", x=0.5, y=0.5,
                            xref="paper", yref="paper", showarrow=False,
                            font=dict(size=14, color="gray"))
        fig.update_layout(height=height)
        return fig, {"max_count": 0, "n_total": 0}

    # Combine all groups' data to compute shared bin edges
    all_x = np.concatenate([
        g["df"][relation.x_col].to_numpy() for g in valid_groups
    ])
    all_y = np.concatenate([
        g["df"][relation.y_col].to_numpy() for g in valid_groups
    ])
    all_x = all_x[np.isfinite(all_x)]
    all_y = all_y[np.isfinite(all_y)]

    x_edges = _build_bin_edges(all_x, x_type, n_bins)
    y_edges = _build_bin_edges(all_y, y_type, n_bins)

    # Compute counts per group
    counts_by_group = []
    max_global = 0
    for g in valid_groups:
        df_g = g["df"].dropna(subset=[relation.x_col, relation.y_col])
        x_g = df_g[relation.x_col].to_numpy()
        y_g = df_g[relation.y_col].to_numpy()
        if x_type == "log":
            x_g = x_g[x_g > 0]
            y_g = y_g[: len(x_g)] if len(x_g) == len(y_g) else y_g
        H, _, _ = np.histogram2d(x_g, y_g, bins=[x_edges, y_edges])
        counts_by_group.append(H)
        if H.max() > max_global:
            max_global = int(H.max())

    # x/y bin centers — geometric mean for log axes, arithmetic for linear
    def bin_centers(edges, axis_type):
        if axis_type == "log":
            return np.sqrt(edges[:-1] * edges[1:])
        return 0.5 * (edges[:-1] + edges[1:])

    x_centers = bin_centers(x_edges, x_type)
    y_centers = bin_centers(y_edges, y_type)

    # Build the figure — use subplots when 2+ groups
    n_g = len(valid_groups)
    if n_g == 1:
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1)
    else:
        from plotly.subplots import make_subplots
        subplot_titles = tuple(f"<b style='color:{g['color']}'>{g['name']}</b>"
                                 + f" (n={int(counts_by_group[i].sum())})"
                                 for i, g in enumerate(valid_groups))
        fig = make_subplots(rows=1, cols=n_g, shared_yaxes=True,
                              horizontal_spacing=0.08,
                              subplot_titles=subplot_titles)

    for i, (g, H) in enumerate(zip(valid_groups, counts_by_group)):
        # Mask zero cells so they render as the page background, not as a
        # bottom-of-colorscale tint. This makes "where there is data" pop.
        Z = H.T.astype(float)
        Z[Z == 0] = np.nan

        # Per-group colorscale matching the group's accent color, going
        # from low (very pale) to high (saturated accent).
        accent = g["color"]
        cscale = [
            [0.0, _hex_with_alpha(accent, 0.05)],
            [0.15, _hex_with_alpha(accent, 0.25)],
            [0.45, _hex_with_alpha(accent, 0.55)],
            [0.80, _hex_with_alpha(accent, 0.85)],
            [1.0, accent],
        ]

        heatmap = go.Heatmap(
            x=x_centers, y=y_centers, z=Z,
            colorscale=cscale,
            zmin=0, zmax=max_global,
            showscale=(i == n_g - 1),  # only one colorbar
            colorbar=dict(
                title=dict(text="UAVs per cell", side="right",
                            font=dict(size=11)),
                len=0.85, thickness=14,
            ) if i == n_g - 1 else None,
            hovertemplate=(
                f"{relation.x_label}: %{{x:,.3g}}<br>"
                f"{relation.y_label}: %{{y:,.3g}}<br>"
                f"<b>%{{z:.0f}} UAVs in this cell</b><extra></extra>"
            ),
        )
        col_idx = i + 1
        fig.add_trace(heatmap, row=1, col=col_idx)

        # Apply log/linear axis types
        fig.update_xaxes(type=x_type, row=1, col=col_idx,
                          title_text=relation.x_label if i == 0 or n_g == 1 else None,
                          gridcolor="rgba(120,120,120,0.18)",
                          showgrid=True, minor=dict(showgrid=False))
        fig.update_yaxes(type=y_type, row=1, col=col_idx,
                          title_text=relation.y_label if i == 0 else None,
                          gridcolor="rgba(120,120,120,0.18)",
                          showgrid=True, minor=dict(showgrid=False))

    # Canonical literature line overlay — drawn on top of each subplot
    if (show_canonical_fit
        and relation.canonical_coefficient is not None
        and relation.canonical_exponent is not None):
        coef = relation.canonical_coefficient
        exp = relation.canonical_exponent
        # Use x edges for the line domain
        x_line_min, x_line_max = x_edges[0], x_edges[-1]
        if x_line_min > 0:
            xs = np.geomspace(x_line_min, x_line_max, 60)
            ys = coef * xs ** exp
            if abs(exp) < 1e-9:
                eq_str = f"Y = {coef:g} (mean)"
            else:
                eq_str = f"Y = {coef:g} · X^{exp:.3f}"
            for col_idx in range(1, n_g + 1):
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines",
                    name=f"{relation.canonical_source}: {eq_str}",
                    line=dict(color="#1A1A1A", width=2.5, dash="dash"),
                    hoverinfo="skip",
                    showlegend=(col_idx == 1),
                ), row=1, col=col_idx)

    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=50, b=50),
        plot_bgcolor="#FAFAF7",
        showlegend=(show_canonical_fit
                     and relation.canonical_coefficient is not None),
        legend=dict(orientation="h", x=0, y=-0.18, yanchor="top",
                     font=dict(size=10)),
    )

    return fig, {
        "max_count": int(max_global),
        "n_total": int(sum(int(H.sum()) for H in counts_by_group)),
        "n_bins_x": n_bins,
        "n_bins_y": n_bins,
    }


def _hex_with_alpha(hex_color: str, alpha: float) -> str:
    """Convert a #RRGGBB hex to an rgba(...) string with the given alpha."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except ValueError:
        r = g = b = 128
    return f"rgba({r},{g},{b},{alpha})"
