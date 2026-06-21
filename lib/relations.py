"""Sizing relations library.

Each relation describes how a Y variable scales with a reference X (typically
MTOW). Captures: column names, display labels, recommended axis types, and
the canonical power-law exponent from the literature (Verstraete 2017 et al.)
for reference comparison.

v0.8.26: extended with a `literature_fits` list — multiple per-source/per-
scope variants per relation (e.g. Verstraete-All + Verstraete-Piston +
Verstraete-Turbine + Voskuijl-LM-Conventional). Each entry carries the
reference fit, R², N, and the pre-computed fleet refit (exp, CI, R²,
verdict) from UAV_Sizing_Equation_Inventory.xlsx. The single-canonical
fields stay for backward compatibility — pages that don't yet consume
the list fall back to canonical_*.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple


@dataclass(frozen=True)
class LiteratureFit:
    """One published power-law fit applicable to a SizingRelation.

    `scope` captures when this variant is the right one to show — used by
    pages to auto-pick the default based on the active filter:
      scope = {
          "engines": list[str] | None,    # e.g. ["P"] for Piston-only
          "missions": list[str] | None,   # e.g. ["LM"] for LM-only
          "all": bool,                    # True = "All UAV" baseline
          "label": str,                   # human-readable short tag
      }

    `verdict` is the CONFIRMS/DIFFERS/CLOSE/WEAK/NOT TESTABLE/NOVEL string
    from the inventory's adjudication against this dataset.
    `your_exp`, `your_ci`, `your_r2`, `your_n` are the pre-computed refit
    on this dataset (from inventory's YourData_* columns).
    """
    source: str                 # e.g. "Verstraete Table 5 (All)"
    scope: Dict                  # see above
    coef: float                  # A in Y = A * X^B
    exp: float                   # B
    r2_ref: Optional[float] = None
    n_ref: Optional[int] = None
    your_exp: Optional[float] = None
    your_ci: Tuple[Optional[float], Optional[float]] = (None, None)
    your_r2: Optional[float] = None
    your_n: Optional[int] = None
    verdict: Optional[str] = None


@dataclass(frozen=True)
class SizingRelation:
    """One sizing relation, e.g. Wingspan vs MTOW.

    `default_x_type` / `default_y_type` are the recommended axis types for
    the relation across the full dataset (log-log for power laws, linear for
    bounded variables). Users can override per-page.

    `canonical_exponent`, `canonical_coefficient`, `canonical_source` capture
    a reference power-law fit (Y = A * X^B) from the literature, when one
    exists. None if no published reference.

    `literature_fits` (v0.8.26+) lists ALL published variants applicable to
    this relation. Pages with the literature-fit selector iterate this list,
    auto-filter by the active scope, and let the user pick which to overlay.
    """
    key: str                      # short id
    label: str                    # display label
    x_col: str                    # source column for X
    y_col: str                    # source column for Y
    x_label: str
    y_label: str
    default_x_type: str           # "log" | "linear"
    default_y_type: str           # "log" | "linear"
    canonical_coefficient: Optional[float] = None
    canonical_exponent: Optional[float] = None
    canonical_source: Optional[str] = None
    notes: str = ""
    literature_fits: List[LiteratureFit] = field(default_factory=list)
    # v0.8.34b+c: optional sibling column that flags whether the Y value
    # is ESTIMATED (e.g. Mission Productivity Cruise filled from
    # MaxSpeed × class-median when CruiseSpeed missing). When present,
    # the scatter renders estimated points with open markers and the
    # tooltip notes the fallback.
    y_estimated_col: Optional[str] = None


# Reference coefficients are from Verstraete et al. (2017), "Preliminary Sizing
# Correlations for Fixed-Wing UAV Characteristics", J. Aircraft 55(2).
# Where the paper splits by propulsion, we use the all-UAV combined fit.
SIZING_RELATIONS = {
    "wingspan_mtow": SizingRelation(
        key="wingspan_mtow",
        label="Wingspan vs MTOW",
        x_col="MTOW_kg", y_col="Wingspan_m",
        x_label="MTOW (kg)", y_label="Wingspan (m)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=0.828, canonical_exponent=0.370,
        canonical_source="Verstraete 2017 (all UAV)",
        notes="Power law on log-log. b = 0.828 · m^0.370 in the reference.",
    ),
    "endurance_mtow": SizingRelation(
        key="endurance_mtow",
        label="Endurance vs MTOW",
        x_col="MTOW_kg", y_col="Endurance_h",
        x_label="MTOW (kg)", y_label="Endurance (h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=0.976, canonical_exponent=0.369,
        canonical_source="Verstraete 2017 (piston)",
        notes="Power law (R²=0.44 across full dataset). Linear may fit "
              "better within a narrow mass band (e.g. MALE-only).",
    ),
    "range_mtow": SizingRelation(
        key="range_mtow",
        label="Range vs MTOW (as published)",
        x_col="MTOW_kg", y_col="Range_km",
        x_label="MTOW (kg)", y_label="Range (km)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=12.4, canonical_exponent=0.41,
        canonical_source="DSTO-TR-2122",
        notes="Power law on log-log; uses Range_km column as published. "
              "WARNING: for many UAVs this is the data-link range rather than "
              "the endurance-limited range. Try **Best range vs MTOW** for the "
              "data-cleaned version.",
    ),
    "best_range_mtow": SizingRelation(
        key="best_range_mtow",
        label="Best range vs MTOW (data-cleaned)",
        x_col="MTOW_kg", y_col="BestRange_km",
        x_label="MTOW (kg)", y_label="Best-estimate range (km)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Uses ActualRange_km when available; otherwise picks between "
              "the published Range_km and CruiseSpeed × Endurance based on "
              "the RangeKind heuristic. Recommended over the as-published "
              "Range column.",
    ),
    "derived_range_mtow": SizingRelation(
        key="derived_range_mtow",
        label="Derived range vs MTOW (cruise × endurance)",
        x_col="MTOW_kg", y_col="DerivedRange_km",
        x_label="MTOW (kg)", y_label="Derived range (km)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Purely derived: CruiseSpeed × Endurance. Represents the "
              "endurance-limited maximum range, independent of data-link "
              "constraints.",
    ),
    "payload_mtow": SizingRelation(
        key="payload_mtow",
        label="Payload vs MTOW",
        x_col="MTOW_kg", y_col="Payload_kg",
        x_label="MTOW (kg)", y_label="Payload (kg)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=0.21, canonical_exponent=0.94,
        canonical_source="Verstraete 2017",
        notes="Nearly linear on log-log (exponent ≈ 0.94). Implies roughly "
              "constant payload fraction across UAV mass classes.",
    ),
    "speed_mtow": SizingRelation(
        key="speed_mtow",
        label="Max speed vs MTOW",
        x_col="MTOW_kg", y_col="MaxSpeed_kmh",
        x_label="MTOW (kg)", y_label="Max speed (km/h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=38.0, canonical_exponent=0.18,
        canonical_source="DSTO-TR-2122",
        notes="Mild positive slope — larger UAVs trend faster but the "
              "spread is wide. Use log-log to compress the long tail.",
    ),
    "cruise_mtow": SizingRelation(
        key="cruise_mtow",
        label="Cruise speed vs MTOW",
        x_col="MTOW_kg", y_col="CruiseSpeed_kmh",
        x_label="MTOW (kg)", y_label="Cruise speed (km/h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Cruise speed scaling with mass — companion to max-speed-vs-"
              "MTOW. Same dataset coverage as cruise speed column.",
    ),
    "pe_product_mtow": SizingRelation(
        key="pe_product_mtow",
        label="Payload·Endurance vs MTOW",
        x_col="MTOW_kg", y_col="PayloadEnduranceProduct_kgh",
        x_label="MTOW (kg)", y_label="Payload × Endurance (kg·h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Mission figure-of-merit; no published reference. "
              "Visualises mission productivity vs mass.",
    ),
    # v0.8.32: Mission productivity = Speed × Endurance × Payload (km·kg).
    # No published power-law in the project's literature inventory, so
    # canonical_* are None — this dataset's fit will surface from the
    # per-group / per-category fit machinery but no literature overlay.
    # Anchored payload preferred when AnchorPayload_kg is set, matching the
    # PE-product convention.
    "mission_prod_cruise_mtow": SizingRelation(
        key="mission_prod_cruise_mtow",
        label="Mission productivity (Cruise) vs MTOW",
        x_col="MTOW_kg", y_col="MissionProductivity_Cruise_kgkm",
        x_label="MTOW (kg)",
        y_label="Cruise Speed × Endurance × Payload (km·kg)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Mission productivity FOM = CruiseSpeed × Endurance × Payload. "
              "Units km·kg (payload-distance equivalent). Uses AnchorPayload "
              "when set, otherwise max payload. Open markers indicate cruise "
              "speed was estimated from MaxSpeed × per-engine-class median "
              "ratio (empirical from 472 evidence rows) — see Overview tab "
              "for coverage details. No published reference fit.",
        y_estimated_col="MissionProductivity_Cruise_kgkm_estimated",
    ),
    "mission_prod_max_mtow": SizingRelation(
        key="mission_prod_max_mtow",
        label="Mission productivity (Max speed) vs MTOW",
        x_col="MTOW_kg", y_col="MissionProductivity_Max_kgkm",
        x_label="MTOW (kg)",
        y_label="Max speed × Endurance × Payload (km·kg)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Mission productivity FOM at max speed = MaxSpeed × Endurance "
              "× Payload. Units km·kg. Uses AnchorPayload when set, "
              "otherwise max payload. No published reference fit.",
    ),
    # Secondary relations — supported but lower coverage
    "length_mtow": SizingRelation(
        key="length_mtow",
        label="Length vs MTOW",
        x_col="MTOW_kg", y_col="Length_m",
        x_label="MTOW (kg)", y_label="Length (m)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=0.665, canonical_exponent=0.339,
        canonical_source="Verstraete 2017",
        notes="Power law; coverage ~54%.",
    ),
    "engpower_mtow": SizingRelation(
        key="engpower_mtow",
        label="Eng power vs MTOW",
        x_col="MTOW_kg", y_col="EngPower_hp",
        x_label="MTOW (kg)", y_label="Eng power (hp)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=0.0995, canonical_exponent=0.951,
        canonical_source="Verstraete 2017 (piston)",
        notes="Coverage only ~15% — fits below the green sample-size "
              "threshold for many filters.",
    ),
    "ceiling_mtow": SizingRelation(
        key="ceiling_mtow",
        label="Ceiling vs MTOW",
        x_col="MTOW_kg", y_col="Ceiling_km",
        x_label="MTOW (kg)", y_label="Ceiling (km)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Coverage ~9% — very sparse. Y is bounded (most UAVs "
              "operate <20 km) so linear Y is more readable than log.",
    ),
    # Power loading and payload fraction relations (added v0.8.18).
    # PowerLoading_hp_per_kg is sparse (~15% coverage); PayloadFraction is
    # better populated (~66%). Both are bounded ratios, so we use linear Y
    # axes — log would compress the variation that matters.
    "powerloading_mtow": SizingRelation(
        key="powerloading_mtow",
        label="Power loading vs MTOW",
        x_col="MTOW_kg", y_col="PowerLoading_hp_per_kg",
        x_label="MTOW (kg)", y_label="Power loading (hp / kg)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="PowerLoading_hp_per_kg = EngPower_hp / MTOW_kg, computed at "
              "load. Coverage ~15% (only platforms with published engine "
              "power and MTOW). Lower values = bigger/heavier UAVs need "
              "proportionally less installed power per kg.",
    ),
    "powerloading_wingspan": SizingRelation(
        key="powerloading_wingspan",
        label="Power loading vs Wingspan",
        x_col="Wingspan_m", y_col="PowerLoading_hp_per_kg",
        x_label="Wingspan (m)", y_label="Power loading (hp / kg)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Sparse (~15% coverage). Larger wings tend to accompany "
              "lower power loading, since aero efficiency reduces the "
              "thrust-per-kg requirement.",
    ),
    "payloadfraction_mtow": SizingRelation(
        key="payloadfraction_mtow",
        label="Payload fraction vs MTOW",
        x_col="MTOW_kg", y_col="PayloadFraction",
        x_label="MTOW (kg)", y_label="Payload fraction (Payload / MTOW)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="PayloadFraction = Payload_kg / MTOW_kg. Coverage ~66%. "
              "Bounded 0–1 (typically 0.05–0.4). Linear Y axis is "
              "appropriate for a ratio.",
    ),
    "payloadfraction_wingspan": SizingRelation(
        key="payloadfraction_wingspan",
        label="Payload fraction vs Wingspan",
        x_col="Wingspan_m", y_col="PayloadFraction",
        x_label="Wingspan (m)", y_label="Payload fraction (Payload / MTOW)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Bounded ratio against wingspan. Coverage limited by "
              "Wingspan_m availability on rows with valid Payload/MTOW.",
    ),
    # v0.8.19 additions for Compare Filters sizing-relation scatter.
    "powerloading_endurance": SizingRelation(
        key="powerloading_endurance",
        label="Power loading vs Endurance",
        x_col="Endurance_h", y_col="PowerLoading_hp_per_kg",
        x_label="Endurance (h)", y_label="Power loading (hp / kg)",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Sparse on Y (~15% coverage on PowerLoading). Longer-endurance "
              "platforms tend to have lower power loading.",
    ),
    # v0.8.20 aerodynamic-subset relations (~6-15 platforms each, very
    # sparse). All linear-Y since the variables are not power-law scaling.
    "aspectratio_mtow": SizingRelation(
        key="aspectratio_mtow",
        label="Aspect ratio vs MTOW",
        x_col="MTOW_kg", y_col="AspectRatio_NTNU",
        x_label="MTOW (kg)", y_label="Aspect ratio",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Aerodynamic subset (~15 platforms with aspect-ratio data). "
              "Higher-endurance UAVs typically use higher AR.",
    ),
    "aspectratio_endurance": SizingRelation(
        key="aspectratio_endurance",
        label="Aspect ratio vs Endurance",
        x_col="Endurance_h", y_col="AspectRatio_NTNU",
        x_label="Endurance (h)", y_label="Aspect ratio",
        default_x_type="log", default_y_type="linear",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Aerodynamic subset. Demonstrates the AR/endurance link.",
    ),
    "stallspeed_mtow": SizingRelation(
        key="stallspeed_mtow",
        label="Stall speed vs MTOW",
        x_col="MTOW_kg", y_col="StallSpeed_kmh",
        x_label="MTOW (kg)", y_label="Stall speed (km/h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Sparse (~9 platforms with published stall speed).",
    ),
    "chord_mtow": SizingRelation(
        key="chord_mtow",
        label="Chord vs MTOW",
        x_col="MTOW_kg", y_col="Chord_est_m_NTNU",
        x_label="MTOW (kg)", y_label="Chord (m, estimated)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Aerodynamic subset (~15 platforms with chord estimates).",
    ),
    "stallspeed_cruise": SizingRelation(
        key="stallspeed_cruise",
        label="Stall speed vs Cruise speed",
        x_col="CruiseSpeed_kmh", y_col="StallSpeed_kmh",
        x_label="Cruise speed (km/h)", y_label="Stall speed (km/h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Very sparse (~6 platforms with both speeds). The cruise/"
              "stall ratio is encoded by distance below the 1:1 diagonal.",
    ),
    "stallspeed_maxspeed": SizingRelation(
        key="stallspeed_maxspeed",
        label="Stall speed vs Max speed",
        x_col="MaxSpeed_kmh", y_col="StallSpeed_kmh",
        x_label="Max speed (km/h)", y_label="Stall speed (km/h)",
        default_x_type="log", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Very sparse (~8 platforms). Max/stall ratio is the speed "
              "envelope width — large ratio = wide operating regime.",
    ),
    # v0.8.22: categorical-vs-MTOW box plots. Compare Filters auto-routes
    # categorical-X relations through make_categorical_box (added v0.8.19).
    # 8 design-meaningful categorical columns. All show MTOW distribution
    # per category — useful to see which categories are heavy/light.
    "launchmethod_mtow": SizingRelation(
        key="launchmethod_mtow",
        label="Launch method vs MTOW (box plot)",
        x_col="LaunchMethod", y_col="MTOW_kg",
        x_label="Launch method", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Categorical X — rendered as a box plot of MTOW per launch "
              "method category. Shows the size distribution per launch "
              "technique (e.g. hand-launched UAVs cluster at small MTOW; "
              "CTOL spans the full range).",
    ),
    "enginetype_mtow": SizingRelation(
        key="enginetype_mtow",
        label="Engine type vs MTOW (box plot)",
        x_col="EngineType", y_col="MTOW_kg",
        x_label="Engine type", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Box plot of MTOW per engine type. Confirms regime split "
              "(electric → small, turbofan/turbojet → large, piston → "
              "the broad middle).",
    ),
    "mission_mtow": SizingRelation(
        key="mission_mtow",
        label="Mission vs MTOW (box plot)",
        x_col="Mission", y_col="MTOW_kg",
        x_label="Mission", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="MTOW distribution per mission class.",
    ),
    "sizeclassstd_mtow": SizingRelation(
        key="sizeclassstd_mtow",
        label="Size class vs MTOW (box plot)",
        x_col="SizeClassStd", y_col="MTOW_kg",
        x_label="Size class (standard)", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="Box plot of MTOW per standard size class. By construction "
              "boxes should sit in non-overlapping bands; useful sanity "
              "check on the size-class assignment.",
    ),
    "wingform_mtow": SizingRelation(
        key="wingform_mtow",
        label="Wing form vs MTOW (box plot)",
        x_col="WingForm", y_col="MTOW_kg",
        x_label="Wing form", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="MTOW distribution per planform (rectangular, tapered, "
              "swept, delta, etc.).",
    ),
    "wingconfig_mtow": SizingRelation(
        key="wingconfig_mtow",
        label="Wing configuration vs MTOW (box plot)",
        x_col="WingConfig", y_col="MTOW_kg",
        x_label="Wing configuration", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="MTOW distribution per wing position/arrangement (high, "
              "low, mid, canard, tandem, etc.).",
    ),
    "bodyconfig_mtow": SizingRelation(
        key="bodyconfig_mtow",
        label="Body configuration vs MTOW (box plot)",
        x_col="BodyConfig", y_col="MTOW_kg",
        x_label="Body configuration", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="MTOW distribution per fuselage architecture (wing-tube, "
              "twin-boom, flying-wing, etc.).",
    ),
    "tailconfig_mtow": SizingRelation(
        key="tailconfig_mtow",
        label="Tail configuration vs MTOW (box plot)",
        x_col="TailConfig", y_col="MTOW_kg",
        x_label="Tail configuration", y_label="MTOW (kg)",
        default_x_type="linear", default_y_type="log",
        canonical_coefficient=None, canonical_exponent=None,
        canonical_source=None,
        notes="MTOW distribution per empennage type.",
    ),
}

# Default selection shown by user-facing pages (most useful first)
DEFAULT_RELATIONS = [
    "wingspan_mtow",
    "endurance_mtow",
    "best_range_mtow",
    "payload_mtow",
    "speed_mtow",
    "pe_product_mtow",
    # v0.8.32: mission productivity FOMs (speed × endurance × payload)
    "mission_prod_cruise_mtow",
    "mission_prod_max_mtow",
]


def list_relations() -> list:
    """Return the canonical ordering of all available relations."""
    return list(SIZING_RELATIONS.keys())


def get_relation(key: str) -> SizingRelation:
    return SIZING_RELATIONS[key]


# ============================================================================
# Literature fits (v0.8.26) — populated from UAV_Sizing_Equation_Inventory.
# After the inventory's Palmer-where-alternative-exists filter. Each entry
# is a LiteratureFit attached to its parent SizingRelation. Pages with the
# literature-fit selector auto-pick the right variant via scope + filter.
#
# Scope conventions:
#   scope["engines"]  — list of EngineType codes this variant is calibrated on
#   scope["missions"] — list of Mission codes this variant is for
#   scope["all"]      — True for "All UAV" baseline variants
#   scope["label"]    — short tag shown in the dropdown
# ============================================================================
import dataclasses as _dc


def _lit(source, scope_label, engines, missions, all_flag,
          coef, exp, r2_ref=None, n_ref=None,
          your_exp=None, your_ci=(None, None),
          your_r2=None, your_n=None, verdict=None):
    return LiteratureFit(
        source=source,
        scope={"engines": engines, "missions": missions, "all": all_flag,
                "label": scope_label},
        coef=coef, exp=exp, r2_ref=r2_ref, n_ref=n_ref,
        your_exp=your_exp, your_ci=your_ci, your_r2=your_r2, your_n=your_n,
        verdict=verdict,
    )


_LITERATURE_FITS_BY_RELATION = {
    # ===== wingspan_mtow =====
    "wingspan_mtow": [
        _lit("Verstraete 2017 — general", "general",
             None, None, True,
             coef=0.828, exp=0.370, r2_ref=0.76, n_ref=836,
             your_exp=0.324, your_ci=(0.312, 0.335),
             your_r2=0.79, your_n=1208,
             verdict="CONFIRMS"),
        _lit("Verstraete 2017 — piston engines", "piston",
             ["P"], None, False,
             coef=0.642, exp=0.421, r2_ref=0.81, n_ref=421,
             your_exp=0.380, your_ci=(0.36, 0.41),
             your_r2=0.81, your_n=421,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — battery / electric", "battery / electric",
             ["E"], None, False,
             coef=0.822, exp=0.572, r2_ref=0.83, n_ref=227,
             your_exp=0.365, your_ci=(0.34, 0.39),
             your_r2=0.77, your_n=227,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — turbine (jet / fan / prop)",
             "turbine (jet / fan / prop)",
             ["Turbojet", "Turbofan", "Turboprop"], None, False,
             coef=0.200, exp=0.496, r2_ref=0.69, n_ref=105,
             your_exp=0.480, your_ci=(0.40, 0.55),
             your_r2=0.70, your_n=105,
             verdict="CONFIRMS"),
        _lit("Verstraete 2017 — fuel cell", "fuel cell",
             ["FC"], None, False,
             coef=0.973, exp=0.583, r2_ref=0.92, n_ref=31,
             your_n=4, verdict="NOT TESTABLE"),
        _lit("Verstraete 2017 — solar", "solar",
             ["S"], None, False,
             coef=2.331, exp=0.502, r2_ref=0.90, n_ref=37,
             your_n=6, verdict="NOT TESTABLE"),
        _lit("Palmer 2014 — manned baseline", "manned baseline",
             None, None, False,
             coef=0.989, exp=0.3333,
             verdict="Manned reference"),
    ],
    # ===== length_mtow =====
    "length_mtow": [
        _lit("Palmer 2014 — UAV (ICE)", "UAV (ICE)", None, None, True,
             coef=0.710, exp=0.333,
             your_exp=0.333, your_ci=(0.324, 0.342),
             your_r2=0.88, your_n=953,
             verdict="CONFIRMS"),
        _lit("Palmer 2014 — manned baseline", "manned baseline",
             None, None, False,
             coef=0.878, exp=0.333,
             verdict="Manned reference"),
    ],
    # ===== range_mtow =====
    "range_mtow": [
        _lit("Palmer 2014 — manned envelope, upper", "manned envelope, upper",
             None, None, True,
             coef=20.0, exp=0.667,
             your_exp=0.570, your_ci=(0.546, 0.594),
             your_r2=0.63, your_n=1191,
             verdict="DIFFERS"),
        _lit("Palmer 2014 — manned envelope, lower", "manned envelope, lower",
             None, None, True,
             coef=7.0, exp=0.833,
             verdict="DIFFERS"),
    ],
    # ===== endurance_mtow =====
    "endurance_mtow": [
        _lit("Palmer 2014 — manned envelope, upper", "manned envelope, upper",
             None, None, True,
             coef=0.9, exp=0.5,
             your_exp=0.371, your_ci=(0.348, 0.394),
             your_r2=0.45, your_n=1183,
             verdict="WITHIN ENVELOPE"),
        _lit("Palmer 2014 — manned envelope, lower", "manned envelope, lower",
             None, None, True,
             coef=0.6, exp=0.333,
             verdict="Manned reference"),
        _lit("Voskuijl 2021 — loitering munition, conventional",
             "loitering munition, conventional",
             None, ["LM"], False,
             coef=0.25217, exp=0.663, r2_ref=0.543, n_ref=17,
             your_exp=0.371, your_ci=(0.348, 0.394),
             your_r2=0.45, your_n=1183,
             verdict="WEAK"),
        _lit("Voskuijl 2021 — loitering munition, cruciform",
             "loitering munition, cruciform",
             None, ["LM"], False,
             coef=0.23883, exp=0.545, r2_ref=0.919, n_ref=8,
             verdict="LM-only fit"),
    ],
    # ===== payload_mtow =====
    # The 5 Verstraete entries are inverted algebraically from
    # MTOM = A·PL^B → PL = (1/A)^(1/B) · MTOM^(1/B).
    # Solar skipped (extreme inverted exp ~1.45, N=3 in fleet).
    "payload_mtow": [
        _lit("Verstraete 2017 — general (inverted)", "general",
             None, None, True,
             coef=0.2018, exp=0.999, r2_ref=0.945, n_ref=654),
        _lit("Verstraete 2017 — piston engines (inverted)", "piston",
             ["P"], None, False,
             coef=0.2193, exp=0.999, r2_ref=0.884, n_ref=385,
             verdict="CLOSE"),
        _lit("Verstraete 2017 — battery / electric (inverted)",
             "battery / electric", ["E"], None, False,
             coef=0.1452, exp=1.178, r2_ref=0.843, n_ref=151,
             verdict="CONFIRMS"),
        _lit("Verstraete 2017 — turbine (jet / fan / prop) (inverted)",
             "turbine (jet / fan / prop)",
             ["Turbojet", "Turbofan", "Turboprop"], None, False,
             coef=0.2349, exp=0.929, r2_ref=0.932, n_ref=82,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — fuel cell (inverted)", "fuel cell",
             ["FC"], None, False,
             coef=0.2484, exp=0.974, r2_ref=0.825, n_ref=15,
             verdict="NOT TESTABLE"),
        _lit("Voskuijl 2021 — loitering munition, conventional",
             "loitering munition, conventional",
             None, ["LM"], False,
             coef=0.229, exp=0.942, r2_ref=0.911, n_ref=18,
             your_exp=1.001, your_ci=(0.95, 1.05),
             your_r2=0.945, your_n=654,
             verdict="CONFIRMS"),
        _lit("Voskuijl 2021 — loitering munition, cruciform",
             "loitering munition, cruciform",
             None, ["LM"], False,
             coef=0.117, exp=1.294, r2_ref=0.968, n_ref=9,
             verdict="LM-only fit"),
        _lit("Voskuijl 2021 — loitering munition, delta",
             "loitering munition, delta",
             None, ["LM"], False,
             coef=0.289, exp=0.857, r2_ref=0.945, n_ref=4,
             verdict="LM-only fit"),
    ],
    # ===== engpower_mtow =====
    # IMPORTANT: Y column is EngPower_HP. Inventory & Palmer coefficients
    # are in WATTS. Coefficients shown here are W → hp = (W coef) / 745.7.
    "engpower_mtow": [
        _lit("Verstraete 2017 — general", "general", None, None, True,
             coef=0.12147, exp=1.099, r2_ref=0.922, n_ref=408,
             your_exp=0.83, your_ci=(0.78, 0.88),
             your_r2=0.66, your_n=185,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — piston engines", "piston",
             ["P"], None, False,
             coef=0.38809, exp=0.874, r2_ref=0.848, n_ref=284,
             your_exp=0.83, your_ci=(0.78, 0.88),
             your_r2=0.84, your_n=146,
             verdict="CLOSE"),
        _lit("Verstraete 2017 — battery / electric", "battery / electric",
             ["E"], None, False,
             coef=0.10452, exp=1.096, r2_ref=0.866, n_ref=69,
             your_n=7, verdict="NOT TESTABLE"),
        _lit("Palmer 2014 — manned, propeller", "manned, propeller",
             None, None, False,
             coef=0.09293, exp=1.13,
             verdict="Manned reference"),
        _lit("Palmer 2014 — manned, jet", "manned, jet",
             None, None, False,
             coef=1.59582, exp=0.977,
             verdict="Manned reference"),
        _lit("Verstraete 2017 — general (mean only)", "general (mean only)",
             None, None, True,
             coef=0.18774, exp=0.0, n_ref=408,
             verdict="CONFIRMS (mean ≈ 140 W/kg)"),
        _lit("Verstraete 2017 — turbine (mean only)", "turbine (mean only)",
             ["Turbojet", "Turbofan", "Turboprop"], None, False,
             coef=0.29502, exp=0.0, n_ref=13,
             verdict="Turbine class mean"),
    ],
    # ===== pe_product_mtow =====
    "pe_product_mtow": [
        _lit("Verstraete 2017 — general", "general", None, None, True,
             coef=0.107, exp=1.487, r2_ref=0.878, n_ref=597,
             your_exp=1.360, your_ci=(1.326, 1.391),
             your_r2=0.86, your_n=1100,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — piston engines", "piston",
             ["P"], None, False,
             coef=0.080, exp=1.603, r2_ref=0.83, n_ref=363,
             verdict="DIFFERS"),
        _lit("Verstraete 2017 — battery / electric", "battery / electric",
             ["E"], None, False,
             coef=0.096, exp=1.615, r2_ref=0.827, n_ref=139,
             verdict="DIFFERS"),
        _lit("Voskuijl 2021 — loitering munition, conventional",
             "loitering munition, conventional",
             None, ["LM"], False,
             coef=0.06055, exp=1.583, r2_ref=0.7947, n_ref=17,
             verdict="CONFIRMS"),
        _lit("Voskuijl 2021 — loitering munition, cruciform",
             "loitering munition, cruciform",
             None, ["LM"], False,
             coef=0.02745, exp=1.841, r2_ref=0.9803, n_ref=8,
             verdict="LM-only fit"),
    ],
    # ===== payloadfraction_mtow (flat-line means) =====
    "payloadfraction_mtow": [
        _lit("Verstraete 2017 — general (mean only)", "general (mean only)",
             None, None, True,
             coef=0.224, exp=0.0, n_ref=654,
             verdict="CONFIRMS"),
        _lit("Verstraete 2017 — piston (mean only)", "piston (mean only)",
             ["P"], None, False,
             coef=0.24, exp=0.0, n_ref=385,
             verdict="Piston-class mean"),
    ],
    # ===== powerloading_mtow =====
    # Y column is PowerLoading_hp_per_kg. Coefficients converted W/kg → hp/kg.
    "powerloading_mtow": [
        _lit("Verstraete 2017 — general (mean only)", "general (mean only)",
             None, None, True,
             coef=0.18774, exp=0.0, n_ref=408,
             verdict="FLAT"),
        _lit("Verstraete 2017 — turbine (mean only)", "turbine (mean only)",
             ["Turbojet", "Turbofan", "Turboprop"], None, False,
             coef=0.29502, exp=0.0, n_ref=13,
             verdict="Turbine class mean"),
        _lit("Palmer 2014 — manned, propeller", "manned, propeller",
             None, None, False,
             coef=0.09293, exp=1.13,
             verdict="Manned reference"),
        _lit("Palmer 2014 — manned, jet", "manned, jet",
             None, None, False,
             coef=1.59582, exp=0.977,
             verdict="Manned reference"),
    ],
}


# Inject the literature-fits lists into the SIZING_RELATIONS entries.
# Frozen dataclass → use dataclasses.replace to build new instances.
for _key, _fits in _LITERATURE_FITS_BY_RELATION.items():
    if _key in SIZING_RELATIONS:
        SIZING_RELATIONS[_key] = _dc.replace(SIZING_RELATIONS[_key],
                                                literature_fits=list(_fits))


def applicable_literature_fits(
    rel: SizingRelation,
    active_engines: Optional[list] = None,
    active_missions: Optional[list] = None,
) -> List[LiteratureFit]:
    """Return the literature-fit variants applicable to the user's current
    Filter A scope.

    Rule:
      - If `active_missions` is exactly ["LM"] → return ONLY LM variants
        (auto-default to Voskuijl when LM is the only selected mission).
      - Else if `active_engines` is a single engine → return the matching
        engine variant plus the All-UAV variant.
      - Else (no filter, or mixed filter) → return only the All-UAV variants
        per user rule "if mixed, default to All UAV".
    """
    fits = list(rel.literature_fits or [])
    if not fits:
        return []

    # LM-only auto-switch
    if active_missions and len(active_missions) == 1 \
       and active_missions[0] == "LM":
        return [f for f in fits if f.scope.get("missions") == ["LM"]]

    # Single engine selected
    if active_engines and len(active_engines) == 1:
        eng = active_engines[0]
        out = []
        # Engine-specific variant first (if exists for this engine)
        for f in fits:
            if f.scope.get("engines") and eng in f.scope["engines"]:
                out.append(f)
        # Plus the All-UAV variant for reference
        for f in fits:
            if f.scope.get("all"):
                out.append(f)
        return out if out else fits

    # Default scope: All-UAV variants only (per user scenario-3 ruling).
    # If the relation has no All-UAV variant (e.g. endurance_mtow,
    # payload_mtow which only have Voskuijl LM variants), return empty —
    # offering Voskuijl LM by default when LM isn't selected would be
    # misleading. The dropdown will show only "(none)".
    all_variants = [f for f in fits if f.scope.get("all")]
    if all_variants:
        return all_variants
    # If single-engine filter is active but no engine-matching variant exists,
    # also return empty — same principle: don't surface a misleading default.
    return []


def all_literature_fits(rel: SizingRelation) -> List[LiteratureFit]:
    """Return every literature-fit variant for a relation, regardless of
    scope. Used by pages that want to populate the dropdown with EVERY
    option so the user can manually pick (e.g. Compare Platforms which
    has no Filter A context, and Compare Filters/Design-space which still
    let the user reach LM variants manually even without a Mission=LM
    filter).
    """
    return list(rel.literature_fits or [])


# ============================================================================
# v0.8.34c-fix3: Envelope-pair grouping for Palmer 2014 — manned envelope.
# Palmer's published envelope has upper and lower curves. In the inventory
# these are stored as two separate LiteratureFit entries; the picker now
# groups them into a single dropdown selection and the renderer draws both
# curves + a filled translucent band between them.
# ============================================================================

@dataclass(frozen=True)
class EnvelopePair:
    """A grouped envelope: two LiteratureFits representing upper/lower
    boundaries of a published data envelope (e.g. Palmer 2014 manned).
    The dropdown shows ONE entry; the renderer draws both curves with a
    filled band between them."""
    source: str            # e.g. "Palmer 2014 — manned envelope"
    upper: LiteratureFit
    lower: LiteratureFit
    caveat: str = ""       # optional UI caveat


def group_envelope_pairs(fits: List[LiteratureFit]):
    """Group LiteratureFit entries with matching upper/lower bounds into
    EnvelopePair objects. Items without a pair are returned unchanged.

    Returns a mixed list of EnvelopePair and LiteratureFit. Order preserved
    relative to the input (envelope pair takes the position of its upper).

    Pair detection: looks for entries whose source ends in "upper" or
    matches a partner ending in "lower" with otherwise-identical source
    prefix. e.g. "Palmer 2014 — manned envelope, upper" pairs with
    "Palmer 2014 — manned envelope, lower".
    """
    items = []
    used = set()
    for i, f in enumerate(fits):
        if i in used:
            continue
        src = f.source
        is_upper = "upper" in src.lower()
        is_lower = "lower" in src.lower()
        if not (is_upper or is_lower):
            items.append(f)
            continue
        # Build the partner source string
        if is_upper:
            partner_src = src.lower().replace("upper", "lower")
        else:
            partner_src = src.lower().replace("lower", "upper")
        # Find partner
        partner_idx = None
        for j, g in enumerate(fits):
            if j == i or j in used:
                continue
            if g.source.lower() == partner_src:
                partner_idx = j
                break
        if partner_idx is None:
            items.append(f)
            continue
        upper = f if is_upper else fits[partner_idx]
        lower = fits[partner_idx] if is_upper else f
        # Combined source label: drop ", upper" / ", lower" suffix
        base_source = src.rsplit(",", 1)[0].strip() + " (boundary)"
        items.append(EnvelopePair(
            source=base_source,
            upper=upper, lower=lower,
            caveat=(
                "Palmer's envelope is approximated by two power-law fits in "
                "this inventory. The intersection point may not exactly match "
                "Palmer's Fig 13 — refine coefficients in lib/relations.py if "
                "needed."
            ),
        ))
        used.add(i)
        used.add(partner_idx)
    return items
