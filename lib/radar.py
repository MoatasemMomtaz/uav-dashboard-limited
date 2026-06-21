"""Capability-radar helpers shared by UAV profile and Compare platforms.

Three display modes are supported:

- **Percentile** — % of baseline UAVs with a smaller value on this axis. 0-100
  scale. Answers "where does this UAV rank?"
- **Ratio to median** — UAV value divided by baseline median. Capped at 3.0 for
  display so an outlier doesn't squash the rest. Answers "is this UAV typical
  or unusual for its class?"
- **Ratio to max** — UAV value divided by some max (baseline max OR pick-set
  max, depending on caller). 0-1 scale. Answers "how close to the best is this
  UAV?"

For Compare platforms, ratio-to-max uses the maximum among picked UAVs, which
is the genuinely informative version: it shows who leads on each axis.
"""
from typing import Optional, Tuple, Iterable
import pandas as pd
import numpy as np
import plotly.graph_objects as go


RADAR_AXES: Tuple[Tuple[str, str], ...] = (
    ("MTOW_kg", "MTOW"),
    ("Payload_kg", "Payload"),
    ("Endurance_h", "Endurance"),
    ("BestRange_km", "Best range"),
    ("MaxSpeed_kmh", "Max speed"),
    ("Wingspan_m", "Wingspan"),
)

DISPLAY_MODES = ("percentile", "ratio_to_median", "ratio_to_max",
                  "ratio_to_class_mean")
MODE_LABELS = {
    "percentile":          "Percentile rank",
    "ratio_to_median":     "Ratio to median",
    "ratio_to_max":        "Ratio to maximum",
    "ratio_to_class_mean": "Ratio to size-class mean",
}
MODE_AXIS_RANGE = {
    "percentile":          (0, 100),
    "ratio_to_median":     (0, 3),     # cap display at 3× median
    "ratio_to_max":        (0, 1),
    "ratio_to_class_mean": (0, 3),     # cap display at 3× class mean
}
MODE_REFERENCE = {                  # value of the dotted reference ring
    "percentile":          50,
    "ratio_to_median":     1,
    "ratio_to_max":        1,
    "ratio_to_class_mean": 1,
}


def axes_present(uav: pd.Series) -> int:
    """Return how many of the radar axes are non-null for a UAV row."""
    return sum(1 for col, _ in RADAR_AXES if pd.notna(uav.get(col)))


def filter_complete_radar(df: pd.DataFrame) -> pd.DataFrame:
    """Return only rows that have non-null values on all six radar axes."""
    mask = pd.Series(True, index=df.index)
    for col, _ in RADAR_AXES:
        if col in df.columns:
            mask &= df[col].notna()
    return df[mask]


def percentile_rank(value, series: pd.Series) -> Optional[float]:
    """% of `series` strictly less than `value`. None if undefined."""
    if pd.isna(value):
        return None
    clean = series.dropna()
    if len(clean) < 5:
        return None
    return 100.0 * (clean < value).sum() / len(clean)


def ratio_to_median(value, series: pd.Series, cap: float = 3.0) -> Optional[float]:
    """UAV value divided by baseline median. Capped at `cap` for display."""
    if pd.isna(value):
        return None
    clean = series.dropna()
    if len(clean) < 5:
        return None
    med = clean.median()
    if med <= 0 or pd.isna(med):
        return None
    return min(value / med, cap)


def ratio_to_max(value, max_series_or_value) -> Optional[float]:
    """UAV value divided by the supplied maximum."""
    if pd.isna(value):
        return None
    if isinstance(max_series_or_value, pd.Series):
        clean = max_series_or_value.dropna()
        if len(clean) == 0:
            return None
        maxv = clean.max()
    else:
        maxv = max_series_or_value
    if maxv is None or pd.isna(maxv) or maxv <= 0:
        return None
    return value / maxv


def ratio_to_class_mean(value, series: pd.Series, cap: float = 3.0) -> Optional[float]:
    """UAV value divided by the mean of the supplied class-restricted series.

    Caller is responsible for filtering `series` to the UAV's size class.
    Capped at `cap` for display.

    NOTE on outliers: when used for Endurance, the caller should drop solar /
    "high-suspect" endurance flagged rows BEFORE passing `series`, otherwise a
    single 44,000-hour Odysseus row will inflate the mean and make every
    normal UAV look like ratio≈0.
    """
    if pd.isna(value):
        return None
    clean = series.dropna()
    if len(clean) < 5:
        return None
    mean = clean.mean()
    if mean <= 0 or pd.isna(mean):
        return None
    return min(value / mean, cap)


def baseline_set(
    df: pd.DataFrame,
    uav: pd.Series,
    mode: str,                # "global" | "class"
) -> Tuple[pd.DataFrame, str, bool]:
    """Build the baseline dataframe.

    Returns (baseline_df, label, fellback_to_global).
    The 'complete data only' restriction is applied at the *picker* level now,
    not here, so baseline doesn't restrict it.
    """
    fellback = False
    if mode == "class":
        sc = uav.get("SizeClassStd")
        if pd.isna(sc):
            base = df
            mode = "global"
            fellback = True
        else:
            base = df[df["SizeClassStd"] == sc]
    else:
        base = df

    if mode == "class" and not fellback:
        sc = uav.get("SizeClassStd")
        label = f"{sc} class · n={len(base)}"
    else:
        label = f"All UAVs · n={len(base)}"
    return base, label, fellback


def percentile_explanation_md() -> str:
    return (
        "**Three display modes are available:**\n\n"
        "- **Percentile rank** — % of UAVs in the baseline with a *smaller* "
        "value on this axis. Scale 0-100. *Answers: where does this UAV rank?*\n"
        "- **Ratio to median** — UAV value divided by the baseline median. "
        "Reference ring at 1.0 (median). >1 means above-typical; <1 means "
        "below-typical. Display capped at 3× for readability. *Answers: is this "
        "UAV typical or unusual for its class?*\n"
        "- **Ratio to maximum** — UAV value divided by the maximum in the "
        "comparison set. Scale 0-1. *Answers: how close to the best is this "
        "UAV?* On **Compare platforms**, 'max' means the maximum among picked "
        "UAVs (so the leader on each axis touches 1.0). On **UAV Profile**, "
        "'max' means the maximum within the baseline group.\n\n"
        "**Baselines (Percentile and Ratio-to-median):**\n\n"
        "- **Global** — all UAVs in the dataset that have a value on this "
        "axis.\n"
        "- **Class-relative** — only UAVs in the same SizeClassStd "
        "(Nano/Micro <2 kg · Mini 2-20 · Small 20-150 · Tactical 150-600 · "
        "MALE 600-1500 · HALE >1500).\n\n"
        "**Complete radar data filter** — when ticked, only UAVs with values "
        "on *all six* radar axes appear in the picker. The radar comparison is "
        "more meaningful when nothing is missing."
    )


def compute_radial_value(
    value, baseline_series: pd.Series, mode: str,
    max_value: Optional[float] = None,
) -> Optional[float]:
    """Single entry point for per-axis radial value computation."""
    if mode == "percentile":
        return percentile_rank(value, baseline_series)
    if mode == "ratio_to_median":
        return ratio_to_median(value, baseline_series)
    if mode == "ratio_to_max":
        if max_value is not None:
            return ratio_to_max(value, max_value)
        return ratio_to_max(value, baseline_series)
    if mode == "ratio_to_class_mean":
        # baseline_series is expected to be already class-filtered by caller
        return ratio_to_class_mean(value, baseline_series)
    return None


def make_radar_figure(
    name: str,
    uav: pd.Series,
    base_df: pd.DataFrame,
    mode: str = "percentile",
    line_color: str = "#534AB7",
    pick_set_maxes: Optional[dict] = None,   # for ratio_to_max with pick-set max
) -> Tuple[go.Figure, list, list]:
    """Build a single-UAV radar figure for the given display mode."""
    thetas = [label for _, label in RADAR_AXES]
    r_vals: list = []
    missing: list = []
    for col, label in RADAR_AXES:
        v = uav.get(col)
        if col not in base_df.columns:
            r_vals.append(None)
            missing.append(label)
            continue
        baseline = base_df[col]
        # For the class-mean mode on Endurance, trim solar/HAPS outliers from
        # the baseline so the mean isn't dominated by Odysseus (44,000 h) and
        # similar atmospheric-satellite UAVs.
        if mode == "ratio_to_class_mean" and col == "Endurance_h" \
           and "EnduranceFlag" in base_df.columns:
            normal_mask = base_df["EnduranceFlag"] == "normal"
            baseline = base_df.loc[normal_mask, col]
        max_val = pick_set_maxes.get(col) if pick_set_maxes else None
        r = compute_radial_value(v, baseline, mode, max_val)
        if r is None:
            r_vals.append(None)
            missing.append(label)
        else:
            r_vals.append(r)

    lo, hi = MODE_AXIS_RANGE[mode]
    ref_val = MODE_REFERENCE[mode]

    fig = go.Figure()
    # Reference ring
    fig.add_trace(go.Scatterpolar(
        r=[ref_val] * (len(thetas) + 1),
        theta=thetas + [thetas[0]],
        name=f"reference ({ref_val})",
        line=dict(color="rgba(128,128,128,0.4)", width=1, dash="dot"),
        showlegend=True,
    ))
    # Main polygon with gaps for missing
    fig.add_trace(go.Scatterpolar(
        r=r_vals + [r_vals[0]],
        theta=thetas + [thetas[0]],
        fill="toself",
        name=name,
        line=dict(color=line_color, width=2),
        fillcolor=line_color,
        opacity=0.35,
        connectgaps=False,
    ))
    # Missing-axis marker
    if missing:
        fig.add_trace(go.Scatterpolar(
            r=[hi] * len(missing),
            theta=missing,
            mode="markers+text",
            marker=dict(color="rgba(200,80,80,0.6)", size=8, symbol="x"),
            text=["no data"] * len(missing),
            textposition="top center",
            textfont=dict(size=9, color="rgba(200,80,80,0.85)"),
            name="missing axis",
            hoverinfo="skip",
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[lo, hi], visible=True)),
        height=420,
        margin=dict(l=40, r=40, t=20, b=20),
        legend=dict(orientation="h", yanchor="top", y=-0.05),
        title=dict(text=f"Display: {MODE_LABELS[mode]}", font=dict(size=11),
                   x=0, xanchor="left"),
    )
    return fig, r_vals, missing


def overlay_radar(
    entries: list,    # list of (name, uav_row, base_df, color)
    mode: str = "percentile",
) -> Tuple[go.Figure, list]:
    """Multi-UAV radar overlay. Each entry uses its own baseline.

    For ratio-to-max mode, 'max' is computed across the *picked UAVs* per axis,
    not the baseline — so the leader on each axis touches 1.0.
    """
    thetas = [label for _, label in RADAR_AXES]

    # For ratio_to_max in overlay, the reference is the pick-set max
    pick_set_maxes = {}
    if mode == "ratio_to_max":
        for col, _ in RADAR_AXES:
            vals = [uav.get(col) for _, uav, _, _ in entries]
            vals = [v for v in vals if pd.notna(v)]
            pick_set_maxes[col] = max(vals) if vals else None

    fig = go.Figure()
    lo, hi = MODE_AXIS_RANGE[mode]
    ref_val = MODE_REFERENCE[mode]
    fig.add_trace(go.Scatterpolar(
        r=[ref_val] * (len(thetas) + 1),
        theta=thetas + [thetas[0]],
        name=f"reference ({ref_val})",
        line=dict(color="rgba(128,128,128,0.4)", width=1, dash="dot"),
    ))

    all_missing_marks = []
    for name, uav, base_df, color in entries:
        r_vals: list = []
        missing: list = []
        for col, label in RADAR_AXES:
            v = uav.get(col)
            if col not in base_df.columns:
                r_vals.append(None)
                missing.append(label)
                continue
            baseline_series = base_df[col]
            # For the class-mean mode, trim solar/HAPS-flagged rows from the
            # Endurance baseline so the class mean isn't dominated by outliers.
            # (Most pages also have HAPS / Suspect now separated from
            # SizeClassStd, but the safety trim doesn't hurt.)
            if mode == "ratio_to_class_mean" and col == "Endurance_h" \
               and "EnduranceFlag" in base_df.columns:
                normal_mask = base_df["EnduranceFlag"] == "normal"
                baseline_series = base_df.loc[normal_mask, col]
            max_val = pick_set_maxes.get(col) if pick_set_maxes else None
            r = compute_radial_value(v, baseline_series, mode, max_val)
            if r is None:
                r_vals.append(None)
                missing.append(label)
            else:
                r_vals.append(r)
        fig.add_trace(go.Scatterpolar(
            r=r_vals + [r_vals[0]],
            theta=thetas + [thetas[0]],
            fill="toself",
            name=name,
            line=dict(color=color, width=2),
            fillcolor=color,
            opacity=0.22,
            connectgaps=False,
        ))
        if missing:
            all_missing_marks.append((name, missing))

    fig.update_layout(
        polar=dict(radialaxis=dict(range=[lo, hi], visible=True)),
        height=460,
        margin=dict(l=40, r=40, t=20, b=20),
        legend=dict(orientation="h", yanchor="top", y=-0.05),
        title=dict(text=f"Display: {MODE_LABELS[mode]}", font=dict(size=11),
                   x=0, xanchor="left"),
    )
    return fig, all_missing_marks


def small_multiples_radar(
    entries: list,    # list of (name, uav_row, base_df, color)
    mode: str = "percentile",
) -> Tuple[go.Figure, list]:
    """One radar per UAV, arranged in a grid. Better readability when 4+ UAVs.

    Ratio-to-max uses the pick-set max for cross-comparability.
    """
    from plotly.subplots import make_subplots
    thetas = [label for _, label in RADAR_AXES]
    n = len(entries)
    if n == 0:
        return go.Figure(), []

    # Grid: try to keep ≤3 columns wide for readability
    n_cols = min(3, n)
    n_rows = (n + n_cols - 1) // n_cols

    fig = make_subplots(
        rows=n_rows, cols=n_cols,
        specs=[[{"type": "polar"} for _ in range(n_cols)] for _ in range(n_rows)],
        subplot_titles=[name for name, _, _, _ in entries],
        horizontal_spacing=0.08, vertical_spacing=0.12,
    )

    # Pre-compute pick-set max for ratio_to_max
    pick_set_maxes = {}
    if mode == "ratio_to_max":
        for col, _ in RADAR_AXES:
            vals = [uav.get(col) for _, uav, _, _ in entries]
            vals = [v for v in vals if pd.notna(v)]
            pick_set_maxes[col] = max(vals) if vals else None

    lo, hi = MODE_AXIS_RANGE[mode]
    ref_val = MODE_REFERENCE[mode]
    all_missing_marks = []

    for i, (name, uav, base_df, color) in enumerate(entries):
        row = i // n_cols + 1
        col = i % n_cols + 1

        # Reference ring
        fig.add_trace(go.Scatterpolar(
            r=[ref_val] * (len(thetas) + 1),
            theta=thetas + [thetas[0]],
            line=dict(color="rgba(128,128,128,0.4)", width=1, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ), row=row, col=col)

        # UAV polygon
        r_vals = []
        missing = []
        for c, label in RADAR_AXES:
            v = uav.get(c)
            if c not in base_df.columns:
                r_vals.append(None)
                missing.append(label)
                continue
            baseline_series = base_df[c]
            if mode == "ratio_to_class_mean" and c == "Endurance_h" \
               and "EnduranceFlag" in base_df.columns:
                normal_mask = base_df["EnduranceFlag"] == "normal"
                baseline_series = base_df.loc[normal_mask, c]
            max_val = pick_set_maxes.get(c) if pick_set_maxes else None
            r = compute_radial_value(v, baseline_series, mode, max_val)
            if r is None:
                r_vals.append(None)
                missing.append(label)
            else:
                r_vals.append(r)

        fig.add_trace(go.Scatterpolar(
            r=r_vals + [r_vals[0]],
            theta=thetas + [thetas[0]],
            fill="toself",
            name=name,
            line=dict(color=color, width=2),
            fillcolor=color, opacity=0.30,
            connectgaps=False,
            showlegend=False,
        ), row=row, col=col)

        if missing:
            all_missing_marks.append((name, missing))

    # Configure each polar subplot's radial range
    for i in range(1, n + 1):
        polar_key = f"polar{i}" if i > 1 else "polar"
        fig.update_layout({polar_key: dict(radialaxis=dict(range=[lo, hi]))})

    fig.update_layout(
        height=300 * n_rows,
        margin=dict(l=20, r=20, t=40, b=20),
        title=dict(text=f"Display: {MODE_LABELS[mode]}", font=dict(size=11),
                   x=0, xanchor="left"),
    )
    return fig, all_missing_marks
