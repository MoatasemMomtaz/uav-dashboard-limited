"""Whitespace-insensitive name/country/producer search.

The dataset has values like 'CH -4 ' (Cyrillic-y-naming quirks, trailing
spaces, spaces around hyphens). A naive `str.contains` requires the user to
match the dataset's exact spacing. This helper does two normalization passes
and unions the results so 'ch-4', 'CH-4', 'ch 4', 'ch4' all find the same row.
"""
import re
import pandas as pd


def _norm_strict(s) -> str:
    """Lowercase, collapse runs of whitespace, drop spaces around hyphens."""
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    return s


def _norm_fuzzy(s) -> str:
    """Strip everything except a-z and 0-9 — picks up TB2 vs tb-2, MQ-9 vs mq9."""
    if pd.isna(s):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def search_mask(
    df: pd.DataFrame,
    query: str,
    cols: list[str],
) -> pd.Series:
    """Build a boolean mask over df where any of `cols` matches `query`.

    Returns an all-False mask if query is empty so callers can skip filtering.
    """
    if not query or not query.strip():
        return pd.Series(False, index=df.index)

    q_strict = _norm_strict(query)
    q_fuzzy = _norm_fuzzy(query)
    mask = pd.Series(False, index=df.index)

    for col in cols:
        if col not in df.columns:
            continue
        series = df[col].astype(str)
        # Strict normalised match
        ns = series.apply(_norm_strict)
        mask |= ns.str.contains(q_strict, regex=False, na=False)
        # Alphanumeric-only fallback (only if query had any alphanumerics)
        if q_fuzzy:
            nf = series.apply(_norm_fuzzy)
            mask |= nf.str.contains(q_fuzzy, regex=False, na=False)

    return mask
