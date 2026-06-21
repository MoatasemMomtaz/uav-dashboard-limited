"""Filter engine. Applies sidebar filter state to the dataset.

Returns the filtered subset plus an attribution dict explaining how many rows
were cut by which filter — feeds the coverage gauge in the sidebar.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd


@dataclass
class FilterState:
    """All sidebar filter values. Default = no filtering."""
    mtow_range: Optional[Tuple[float, float]] = None       # in kg, log-aware UI but linear values
    endurance_range: Optional[Tuple[float, float]] = None  # hours

    countries: List[str] = field(default_factory=list)
    producers: List[str] = field(default_factory=list)
    missions: List[str] = field(default_factory=list)
    engines: List[str] = field(default_factory=list)
    launches: List[str] = field(default_factory=list)
    size_classes_std: List[str] = field(default_factory=list)
    op_roles: List[str] = field(default_factory=list)

    coverage_required: List[str] = field(default_factory=list)

    hide_outliers: bool = False
    include_unknown_in_categoricals: bool = False
    use_overlay_edits: bool = True
    exclude_solar: bool = False                              # v0.8.22


def _apply_categorical(
    df: pd.DataFrame, col: str, selected: List[str], include_unknown: bool
) -> Tuple[pd.DataFrame, int]:
    if not selected:
        return df, 0
    n_before = len(df)
    if include_unknown:
        mask = df[col].isin(selected) | df[col].isna()
    else:
        mask = df[col].isin(selected)
    out = df[mask]
    return out, n_before - len(out)


def _apply_range(
    df: pd.DataFrame, col: str, rng: Optional[Tuple[float, float]]
) -> Tuple[pd.DataFrame, int]:
    """Apply a numeric range filter. Rows with NaN in the column are
    EXCLUDED when a range is active.

    v1.0.0-limited / v0.8.34c-fix6: previously the filter kept NaN rows
    in via `| df[col].isna()` — the intent was "don't drop UAVs just
    because they have no MTOW", but the side effect was that picking a
    MTOW class preset (e.g. Nano/Micro) leaked in ALL NaN-MTOW rows,
    even if their actual size was much larger. That caused Passenger/
    Cargo/LM missions to appear in the Nano filter alongside the actual
    Nano UAVs. Now NaN rows are correctly excluded when a range filter
    is active.
    """
    if rng is None:
        return df, 0
    n_before = len(df)
    lo, hi = rng
    # No |isna() here: when the user picks a numeric range, they're
    # asking for rows with values in that range. Rows with no value
    # in the column can't be in any range, so they're excluded.
    mask = df[col].between(lo, hi)
    out = df[mask]
    return out, n_before - len(out)


def _apply_coverage_gate(
    df: pd.DataFrame, required: List[str]
) -> Tuple[pd.DataFrame, int]:
    if not required:
        return df, 0
    n_before = len(df)
    mask = pd.Series(True, index=df.index)
    for col in required:
        if col in df.columns:
            mask &= df[col].notna()
    out = df[mask]
    return out, n_before - len(out)


def _apply_outlier_clip(
    df: pd.DataFrame, hide: bool, percentile: float = 0.99
) -> Tuple[pd.DataFrame, int]:
    if not hide:
        return df, 0
    # Only clip headline numerics
    headline = ["MTOW_kg", "Endurance_h", "Range_km", "Wingspan_m", "Payload_kg"]
    n_before = len(df)
    mask = pd.Series(True, index=df.index)
    for c in headline:
        if c in df.columns:
            s = df[c]
            if s.notna().sum() < 50:
                continue
            lo, hi = s.quantile(1 - percentile), s.quantile(percentile)
            within = s.between(lo, hi) | s.isna()
            # Solar UAVs with very long endurance are valid
            if c == "Endurance_h" and "EnduranceFlag" in df.columns:
                within = within | (df["EnduranceFlag"] == "high-solar-ok")
            mask &= within
    out = df[mask]
    return out, n_before - len(out)


def apply_filters(df: pd.DataFrame, fs: FilterState) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Apply all filters and return (subset, attribution_dict)."""
    cuts: Dict[str, int] = {}
    cur = df

    cur, cuts["MTOW range"] = _apply_range(cur, "MTOW_kg", fs.mtow_range)
    cur, cuts["Endurance range"] = _apply_range(cur, "Endurance_h", fs.endurance_range)

    inc = fs.include_unknown_in_categoricals
    cur, cuts["Country"] = _apply_categorical(cur, "Country", fs.countries, inc)
    cur, cuts["Producer"] = _apply_categorical(cur, "Producer", fs.producers, inc)
    cur, cuts["Mission"] = _apply_categorical(cur, "Mission", fs.missions, inc)
    cur, cuts["Engine"] = _apply_categorical(cur, "EngineType", fs.engines, inc)
    cur, cuts["Launch"] = _apply_categorical(cur, "LaunchMethod", fs.launches, inc)
    cur, cuts["Size class"] = _apply_categorical(cur, "SizeClassStd", fs.size_classes_std, inc)
    cur, cuts["Op. role"] = _apply_categorical(cur, "OperationalRole", fs.op_roles, inc)

    cur, cuts["Coverage gate"] = _apply_coverage_gate(cur, fs.coverage_required)
    cur, cuts["Outlier clip"] = _apply_outlier_clip(cur, fs.hide_outliers)

    # v0.8.22: Exclude solar UAVs (EngineType='S' OR SizeClassStd='HAPS').
    # HAPS captures the solar-powered very-long-endurance class even when
    # EngineType isn't explicitly 'S'.
    if fs.exclude_solar:
        n_before = len(cur)
        mask = ~(
            (cur["EngineType"].astype(str).str.strip().str.upper() == "S") |
            (cur["SizeClassStd"].astype(str) == "HAPS")
        )
        cur = cur[mask]
        cuts["Exclude solar"] = n_before - len(cur)

    cuts = {k: v for k, v in cuts.items() if v > 0}
    return cur, cuts


def mtow_class_preset(df: pd.DataFrame, preset: str) -> Tuple[float, float]:
    """Return (lo, hi) MTOW range for a preset class name."""
    presets = {
        "Nano":   (0, 0.5),
        "Micro":  (0.5, 2),
        "Mini":   (2, 25),
        "Small":  (25, 150),
        "Medium": (150, 600),
        "Large":  (600, 1e6),
    }
    return presets.get(preset, (0, 1e6))
