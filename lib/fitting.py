"""Curve-fitting helpers — used by Compare filters, future Design-space
explorer, Sizing page, and Critique page.

Provides power-law fitting (Y = A · X^B) on (x, y) data with sample-size
gating: green ≥100, amber 30-99, red <30 (descriptive only).

Returns a `FitResult` dataclass with everything needed to display the fit
line and an equation label.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import pandas as pd


# Sample-size policy (locked across all pages — see v0.5.x decision)
RELIABILITY_THRESHOLDS = {"green": 100, "amber": 30}

# v0.8.27: R² quality bands (matches lib/r2_badge.py — single source of truth)
R2_THRESHOLDS = {"green": 0.85, "amber": 0.45}


def reliability_band(n: int) -> str:
    """Return one of 'green', 'amber', 'red' for a sample size."""
    if n >= RELIABILITY_THRESHOLDS["green"]:
        return "green"
    if n >= RELIABILITY_THRESHOLDS["amber"]:
        return "amber"
    return "red"


def r2_band(r2: float) -> str:
    """Return 'green', 'amber', 'red' for an R² value.

    green ≥ 0.85, amber 0.45–0.85, red < 0.45.
    """
    if r2 is None:
        return "red"
    if r2 >= R2_THRESHOLDS["green"]:
        return "green"
    if r2 >= R2_THRESHOLDS["amber"]:
        return "amber"
    return "red"


@dataclass(frozen=True)
class FitResult:
    """Result of a power-law fit Y = A · X^B.

    `n` is the number of valid (x, y) pairs that went into the fit.
    `r_squared` is on the log-log fit (since power-law is linear there).
    `equation` is a display string like 'Y = 0.94 · X^0.42'.
    `reliability` is 'green' | 'amber' | 'red' per RELIABILITY_THRESHOLDS.
    """
    A: float
    B: float
    r_squared: float
    n: int
    reliability: str
    equation: str
    x_min: float
    x_max: float


def fit_power_law(
    x: pd.Series, y: pd.Series, label: str = "Y"
) -> Optional[FitResult]:
    """Fit Y = A · X^B by linear regression in log-log space.

    Drops non-positive values (log undefined). Returns None if fewer than 5
    valid points.
    """
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    s = s[(s["x"] > 0) & (s["y"] > 0)]
    n = len(s)
    if n < 5:
        return None

    lx = np.log10(s["x"].values)
    ly = np.log10(s["y"].values)

    B, intercept = np.polyfit(lx, ly, 1)
    A = 10 ** intercept

    # R² on the log-log fit
    pred = intercept + B * lx
    ss_res = np.sum((ly - pred) ** 2)
    ss_tot = np.sum((ly - ly.mean()) ** 2)
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    eq = f"{label} = {A:,.3g} · X^{B:.3f}"

    return FitResult(
        A=A, B=B, r_squared=r_sq, n=n,
        reliability=reliability_band(n),
        equation=eq,
        x_min=float(s["x"].min()), x_max=float(s["x"].max()),
    )


def fit_line_xy(fit: FitResult, n_points: int = 50) -> Tuple[np.ndarray, np.ndarray]:
    """Return (xs, ys) for drawing the fit line across its x-range."""
    xs = np.geomspace(fit.x_min, fit.x_max, n_points)
    ys = fit.A * xs ** fit.B
    return xs, ys


def fit_power_law_with_ci(
    x, y, n_bootstrap: int = 200, seed: int = 42, label: str = "Y"
):
    """Fit Y = A·X^B AND return a bootstrap confidence interval for the
    exponent B. Used to recompute live verdicts in v0.8.34b+c.

    v0.8.34c-fix3: also returns the bootstrap samples (list of (A, B)
    pairs) so callers can compute pointwise CI bands at arbitrary X.

    Returns dict with keys:
        coef, exp, r_squared, n, ci_lo, ci_hi, bootstrap_samples
    or None if fewer than 5 valid points.
    """
    import numpy as np
    import pandas as pd
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    s = s[(s["x"] > 0) & (s["y"] > 0)]
    n = len(s)
    if n < 5:
        return None
    lx = np.log10(s["x"].values)
    ly = np.log10(s["y"].values)
    B, intercept = np.polyfit(lx, ly, 1)
    A = 10 ** intercept
    pred = intercept + B * lx
    ss_res = np.sum((ly - pred) ** 2)
    ss_tot = np.sum((ly - ly.mean()) ** 2)
    r_sq = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    # Bootstrap CI for the exponent — sample with replacement
    rng = np.random.default_rng(seed)
    exps = []
    samples = []   # (A, B) pairs for pointwise CI
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        b_sample, a_sample_log = np.polyfit(lx[idx], ly[idx], 1)
        exps.append(b_sample)
        samples.append((10 ** a_sample_log, b_sample))
    ci_lo = float(np.percentile(exps, 2.5))
    ci_hi = float(np.percentile(exps, 97.5))
    return {
        "coef": float(A),
        "exp": float(B),
        "r_squared": r_sq,
        "n": n,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "bootstrap_samples": samples,
    }


def pointwise_ci_band(samples, x_values, percentile_lo: float = 2.5,
                        percentile_hi: float = 97.5):
    """[DEPRECATED in v0.8.34c-fix4] Bootstrap-CI band for the regression
    LINE itself. Width depends on N and is roughly independent of R²,
    so it looked similar for high and low R² fits (user observation).
    Kept for backward compatibility but not used by the new prediction
    band toggle.

    Given bootstrap (A, B) samples and an array of X values, return
    pointwise lower and upper CI bounds for predicted Y = A · X^B.
    """
    import numpy as np
    x_arr = np.asarray(x_values, dtype=float)
    predictions = np.array([A * x_arr ** B for (A, B) in samples])
    y_lo = np.percentile(predictions, percentile_lo, axis=0)
    y_hi = np.percentile(predictions, percentile_hi, axis=0)
    return y_lo, y_hi


def prediction_band(x, y, coef, exp, x_values,
                      confidence: float = 0.95):
    """[NEW in v0.8.34c-fix4] 95% PREDICTION band around a fitted power
    law in log-log space.

    Unlike CI-on-line (which describes where the LINE is), this describes
    where INDIVIDUAL UAVs scatter around the line — which is what the
    user expects to see and what visually tracks R²:
      - High R² + tight cluster → narrow band
      - Low R² + messy cluster  → wide band

    Math:
      σ = std of log10 residuals (ddof=2 for 2-parameter model)
      band edges in log space: log10(Y_pred) ± z · σ
      converted back: y_lo = Y_pred / 10^(z·σ), y_hi = Y_pred · 10^(z·σ)

    Parameters
    ----------
    x, y : the actual data used to compute the fit (for residual stdev)
    coef, exp : the fitted Y = coef · X^exp
    x_values : array of X positions at which to evaluate the band
    confidence : 0.95 default (z=1.96)

    Returns (y_lo, y_hi, sigma_log)
        where sigma_log is the residual standard deviation in log10 space.
        sigma_log is also useful for the badge ("residual spread = ±x dex").
    """
    import numpy as np
    import pandas as pd
    # z-multiplier for confidence (1.96 for 95%, 1.645 for 90%, etc.)
    if confidence == 0.95:
        z = 1.96
    elif confidence == 0.90:
        z = 1.645
    elif confidence == 0.99:
        z = 2.576
    else:
        # Generic via inverse standard normal — but most users want 95%
        from scipy.stats import norm
        z = norm.ppf(1 - (1 - confidence) / 2)
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    s = s[(s["x"] > 0) & (s["y"] > 0)]
    if len(s) < 5:
        return None, None, None
    lx = np.log10(s["x"].values)
    ly = np.log10(s["y"].values)
    # Predicted log10(Y) at the DATA points
    pred_ly = np.log10(coef) + exp * lx
    residuals = ly - pred_ly
    # ddof=2 accounts for the two fitted parameters (A, B)
    sigma_log = float(np.std(residuals, ddof=2))
    # Apply band at requested X values
    x_arr = np.asarray(x_values, dtype=float)
    y_pred = coef * x_arr ** exp
    factor = 10 ** (z * sigma_log)
    y_lo = y_pred / factor
    y_hi = y_pred * factor
    return y_lo, y_hi, sigma_log


def literature_r2_on_data(coef: float, exp: float, x, y) -> Optional[float]:
    """Compute the R² of a given literature equation Y = coef · X^exp
    against the supplied (x, y) data. Used in v0.8.34b+c to evaluate
    the published equation against the CURRENT filter rather than the
    frozen inventory snapshot.

    Returns None if fewer than 5 valid points or if the residual sum
    of squares is undefined.
    """
    import numpy as np
    import pandas as pd
    s = pd.DataFrame({"x": x, "y": y}).dropna()
    s = s[(s["x"] > 0) & (s["y"] > 0)]
    n = len(s)
    if n < 5:
        return None
    lx = np.log10(s["x"].values)
    ly = np.log10(s["y"].values)
    # Apply literature equation in log space: log Y = log coef + exp · log X
    pred_ly = np.log10(coef) + exp * lx
    ss_res = np.sum((ly - pred_ly) ** 2)
    ss_tot = np.sum((ly - ly.mean()) ** 2)
    # R² can be negative if the fit is worse than just predicting the mean —
    # that's mathematically valid and informative (means equation is a poor fit).
    if ss_tot == 0:
        return None
    return float(1 - ss_res / ss_tot)


def derive_verdict(lit_exp: float, your_exp: float,
                    ci_lo: float, ci_hi: float,
                    your_r2: Optional[float]) -> str:
    """Decide a verdict label from a live refit + literature comparison.

    Conventions (v0.8.34b+c; labels clarified in v0.8.34c-fix1):
      - "Slope matches the literature"  if literature exponent is inside
                                         the bootstrap CI of the dataset's
                                         fitted exponent (CI overlap = no
                                         significant slope difference)
      - "Slope differs from the literature" if the literature exponent
                                             falls outside the dataset's
                                             CI
      - "Poor fit (low R²)"              if your_r2 < 0.45 (red band);
                                         both dataset's own fit AND the
                                         literature equation are
                                         unreliable on this filter

    NOTE: the verdict is about SLOPE EQUALITY, not R². Two equations can
    achieve similar R² on the same data with different slopes when the
    x-range is narrow. R² measures variance explained; the verdict
    measures whether the slope is statistically the same.
    """
    if your_r2 is not None and your_r2 < 0.45:
        return "Poor fit (low R²)"
    if ci_lo is None or ci_hi is None:
        return "Slope differs from the literature"
    if ci_lo <= lit_exp <= ci_hi:
        return "Slope matches the literature"
    return "Slope differs from the literature"
