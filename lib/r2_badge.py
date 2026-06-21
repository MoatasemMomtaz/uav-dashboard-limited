"""R² color badge + plain-English verdict mapping.

Tier thresholds (match the analysis report):
  green ≥ 0.85 — "tight, dependable relationship"
  amber 0.45–0.85 — "real but loose relationship"
  red   < 0.45 — "essentially uncorrelated with this predictor"

v0.8.29: rewrote inventory's terse verdict tags into reader-friendly
sentences. The internal label is mapped here so we don't carry the
inventory's parenthetical jargon ("anchor-corrected — more honest",
"DIFFERS Verstraete pooled", etc.) into the UI.
"""
from typing import Optional


_BG_GREEN = "#1B7A2A"
_BG_AMBER = "#B8870B"
_BG_RED = "#A23A2A"
_BG_DARK_RED = "#7A1B1B"
_BG_NAVY = "#1F4E7A"
_BG_GREY = "#555555"


def r2_color(r2: Optional[float]) -> str:
    """Return the hex background color for an R² value."""
    if r2 is None:
        return _BG_GREY
    if r2 >= 0.85:
        return _BG_GREEN
    if r2 >= 0.45:
        return _BG_AMBER
    return _BG_RED


def r2_text_color(r2: Optional[float]) -> str:
    """Return a text color (for dataframe cells) matching the R² tier."""
    return r2_color(r2)


def r2_badge_html(r2: Optional[float], prefix: str = "R²") -> str:
    """HTML pill for st.markdown(..., unsafe_allow_html=True)."""
    if r2 is None:
        return (
            f'<span style="display:inline-block;padding:1px 6px;'
            f'border-radius:6px;background:{_BG_GREY};color:white;font-size:11px;">'
            f'{prefix} = n/a</span>'
        )
    bg = r2_color(r2)
    return (
        f'<span style="display:inline-block;padding:1px 6px;'
        f'border-radius:6px;background:{bg};color:white;font-size:11px;'
        f'font-weight:600;">{prefix} = {r2:.2f}</span>'
    )


# v0.8.29: plain-English verdict mapping. Match against lower-cased
# verdict string from the inventory; first matching keyword wins.
# v0.8.34c-fix1: verdict labels clarified to say SLOPE explicitly.
# Previously "Differs from the literature" was ambiguous — readers
# assumed it meant R² differs, when in fact the verdict checks whether
# the literature's exponent (slope in log-log) falls inside the
# dataset's 95% bootstrap CI. The R² and the slope-test are
# orthogonal: two equations can both produce decent R² on the same
# data with very different slopes if the x-range is narrow.
_VERDICT_MAP = [
    ("within envelope",  "Within the published envelope",                _BG_GREEN),
    ("matches the lit",  "Slope matches the literature",                 _BG_GREEN),
    ("slope matches",    "Slope matches the literature",                 _BG_GREEN),
    ("confirms",         "Slope matches the literature",                 _BG_GREEN),
    ("slope differs",    "Slope differs from the literature",            _BG_DARK_RED),
    ("differs from the lit", "Slope differs from the literature",        _BG_DARK_RED),
    ("differs",          "Slope differs from the literature",            _BG_DARK_RED),
    ("poor fit",         "Poor fit (low R²)",                            _BG_DARK_RED),
    ("close",            "Close to the literature",                      _BG_AMBER),
    ("flat",             "Flat — mass is not a predictor",               _BG_AMBER),
    ("weak",             "Weak — mass alone doesn't predict this well",  _BG_AMBER),
    ("not testable",     "Cannot be tested in this dataset",             _BG_GREY),
    ("novel",            "Novel — no published reference",               _BG_NAVY),
    ("manned reference", "Manned-aircraft reference",                    _BG_GREY),
    ("turbine class",    "Turbine class mean",                           _BG_GREY),
    ("piston-class",     "Piston-class mean",                            _BG_GREY),
    ("lm-only",          "LM-only published fit",                        _BG_GREY),
]


def friendly_verdict(verdict: Optional[str]) -> Optional[str]:
    """Map inventory verdict to plain-English sentence."""
    if not verdict:
        return None
    v = str(verdict).lower()
    for keyword, friendly, _bg in _VERDICT_MAP:
        if keyword in v:
            return friendly
    return verdict


def verdict_badge_html(verdict: Optional[str]) -> str:
    """Color-coded ribbon for a verdict, rendered in plain English."""
    if not verdict:
        return ""
    v = str(verdict).lower()
    friendly = None
    bg = _BG_GREY
    for keyword, fr, bgc in _VERDICT_MAP:
        if keyword in v:
            friendly = fr
            bg = bgc
            break
    if friendly is None:
        friendly = str(verdict)
    return (
        f'<span style="display:inline-block;padding:1px 6px;'
        f'border-radius:6px;background:{bg};color:white;font-size:11px;'
        f'font-weight:600;">{friendly}</span>'
    )
