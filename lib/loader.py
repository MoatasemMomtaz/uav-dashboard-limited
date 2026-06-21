"""Data loader. Single source of truth for the dataset and acronyms."""
from pathlib import Path
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent.parent / "data"

NUM_COLS = [
    "MTOW_kg", "Endurance_h", "Range_km", "ActualRange_km",
    "MaxSpeed_kmh", "CruiseSpeed_kmh",
    "Payload_kg", "AnchorPayload_kg",
    "PayloadEnduranceProduct_kgh", "PayloadEnduranceProduct_kgh_derived",
    "Wingspan_m", "Length_m", "Height_m",
    "EngPower_hp", "Ceiling_km",
    "PayloadFraction", "PowerLoading_hp_per_kg",
]

CAT_COLS = [
    "Country", "Producer", "OperationalRole", "SizeClass", "Mission",
    "LaunchMethod", "EngineType", "Airframe",
    "TailConfig", "WingForm", "WingConfig", "BodyConfig",
]

NAME_COL = "System Designation "  # trailing space comes from source


@st.cache_data(show_spinner=False)
def load_uav() -> pd.DataFrame:
    # v1.0.0-limited: prefer parquet if it exists (fast), otherwise fall
    # back to CSV and cache a parquet alongside for next load. This makes
    # the loader robust to fresh checkouts that ship only the CSV (e.g.
    # the limited GitHub release): the first run takes ~1s longer to
    # build the parquet, every subsequent run is fast.
    parquet_path = DATA_DIR / "uav_clean.parquet"
    csv_path = DATA_DIR / "uav_clean.csv"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
        # Try to cache the parquet for next time. If write fails (e.g.
        # read-only filesystem or missing pyarrow), just continue — the
        # CSV read worked, which is what matters.
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass
    else:
        raise FileNotFoundError(
            f"Dataset file not found. Expected {parquet_path} or {csv_path}. "
            f"If you just cloned the repo, make sure the data/ folder is intact."
        )
    # Recompute SizeClassStd in-place so HAPS (solar/legit-high-endurance)
    # and Suspect (questionable data) are separated from MALE/HALE.
    # This keeps the standard size taxonomy clean of statistical outliers.
    df["SizeClassStd"] = df.apply(_compute_size_class_std, axis=1)
    # Recompute BestRange + RangeKind using the new rule that prefers
    # derived (cruise×endurance) over Range_km when Range_km looks like
    # the data-link radius. See _compute_best_range for the decision logic.
    df["DerivedRange_km"] = df.apply(_compute_derived_range, axis=1)
    br_kind = df.apply(_compute_best_range, axis=1, result_type="expand")
    df["BestRange_km"] = br_kind[0]
    df["RangeKind"] = br_kind[1]
    # PayloadEnduranceProduct: prefer the verified anchor payload (the
    # payload at which the stated endurance was achieved) over the max
    # payload capacity. This makes the kg·h product reflect actual mission
    # capability rather than theoretical maximum.
    # For platforms with AnchorPayload_kg set (from the payload-endurance
    # sheet), use Anchor × Endurance. Otherwise fall back to Payload × Endurance.
    df["PayloadEnduranceProduct_kgh"] = df.apply(_compute_payload_endurance, axis=1)
    # v0.8.32: Mission productivity metrics — Speed × Endurance × Payload.
    # Units: km/h × h × kg = km · kg (payload-distance equivalent).
    # Like PayloadEnduranceProduct, prefer AnchorPayload when set so the
    # number reflects realized mission capacity, not theoretical max.
    # Two flavors: cruise-based (typical mission speed) and max-based
    # (best-case dash productivity).
    df["MissionProductivity_Cruise_kgkm"] = df.apply(
        lambda r: _compute_mission_productivity(r, "CruiseSpeed_kmh"),
        axis=1,
    )
    df["MissionProductivity_Max_kgkm"] = df.apply(
        lambda r: _compute_mission_productivity(r, "MaxSpeed_kmh"),
        axis=1,
    )
    # v0.8.34b+c: Two-tier display for Mission Productivity (Cruise).
    # Many small drones (5–10 kg ISR class) publish only MaxSpeed in their
    # datasheets, not CruiseSpeed. Empirical analysis on the 472 UAVs with
    # both speeds shows median Cruise/Max ratio = 0.706 (NOT folklore 0.85),
    # with structure by engine type:
    #   Electric  0.658  (n=172)
    #   Piston    0.714  (n=195)
    #   Hybrid    0.714  (n=45)
    #   Turbojet  0.757  (n=17)
    #   Turbofan  0.816  (n=15)
    # For platforms missing CruiseSpeed but having MaxSpeed, we ESTIMATE
    # cruise as MaxSpeed × class median ratio, then compute the FOM.
    # `_estimated` boolean column marks which rows carry an estimate so
    # downstream charts can show them with open markers / "≈" prefix.
    PER_CLASS_CRUISE_MAX_RATIO = {
        "E": 0.658,    # Electric
        "P": 0.714,    # Piston / IC
        "H": 0.714,    # Hybrid
        "TJ": 0.757,   # Turbojet
        "Turbojet": 0.757,
        "TF": 0.816,   # Turbofan
        "Turbofan": 0.816,
        "TP": 0.700,   # Turboprop (approx; thin data, n=13 in evidence set)
        "Turboprop": 0.700,
        "S": 0.740,    # Solar
    }
    # Global fallback when engine type unknown or not in the table
    DEFAULT_RATIO = 0.706
    df["MissionProductivity_Cruise_kgkm_estimated"] = False

    def _fill_cruise_estimate(r):
        # Only act on rows where cruise FOM is currently missing but max FOM is present
        if pd.notna(r["MissionProductivity_Cruise_kgkm"]):
            return pd.Series([r["MissionProductivity_Cruise_kgkm"], False])
        max_speed = r.get("MaxSpeed_kmh")
        endurance = r.get("Endurance_h")
        if pd.isna(max_speed) or max_speed <= 0:
            return pd.Series([None, False])
        if pd.isna(endurance) or endurance <= 0:
            return pd.Series([None, False])
        anchor = r.get("AnchorPayload_kg")
        if pd.notna(anchor) and anchor > 0:
            payload = float(anchor)
        else:
            payload = r.get("Payload_kg")
            if pd.isna(payload) or payload <= 0:
                return pd.Series([None, False])
            payload = float(payload)
        eng = r.get("EngineType")
        ratio = PER_CLASS_CRUISE_MAX_RATIO.get(eng, DEFAULT_RATIO)
        est_cruise = float(max_speed) * ratio
        est_fom = est_cruise * float(endurance) * payload
        return pd.Series([est_fom, True])

    _filled = df.apply(_fill_cruise_estimate, axis=1)
    df["MissionProductivity_Cruise_kgkm"] = _filled[0]
    df["MissionProductivity_Cruise_kgkm_estimated"] = _filled[1].fillna(False).astype(bool)
    # v0.8.34b+c: 8 calculated columns (A4 pre-defined recipes). Vectorized
    # for speed — computed once at load, available across all picker UIs.
    # NaN-safe: divisions guard against zero/missing denominators.
    import numpy as _np
    def _safe_div(a, b):
        a_arr = _np.asarray(a, dtype=float)
        b_arr = _np.asarray(b, dtype=float)
        with _np.errstate(divide='ignore', invalid='ignore'):
            result = _np.divide(a_arr, b_arr)
            result[~_np.isfinite(result)] = _np.nan
            # Also NaN out where either input is NaN
            mask = _np.isnan(a_arr) | _np.isnan(b_arr) | (b_arr <= 0)
            result[mask] = _np.nan
        return result

    # 1. Endurance per kg of MTOW — efficient-persistence proxy
    df["Calc_EndurancePerMTOW_h_per_kg"] = _safe_div(
        df["Endurance_h"], df["MTOW_kg"])
    # 2. Range per kg of MTOW — range-efficiency proxy
    df["Calc_RangePerMTOW_km_per_kg"] = _safe_div(
        df["BestRange_km"], df["MTOW_kg"])
    # 3. Payload × Range / MTOW — mass-normalized mission productivity
    df["Calc_PayloadRangePerMTOW_km"] = _safe_div(
        df["Payload_kg"] * df["BestRange_km"], df["MTOW_kg"])
    # 4. Wing loading proxy — MTOW / Wingspan² (kg/m²). Real wing loading
    #    uses wing AREA, which we don't have; Wingspan² is a serviceable
    #    geometric proxy that scales correctly for aspect-ratio-normalised
    #    wings. Caveat: rough estimate, not a true wing loading.
    df["Calc_WingLoadingProxy_kg_per_m2"] = _safe_div(
        df["MTOW_kg"], df["Wingspan_m"] ** 2)
    # 5. Power-to-weight — hp per kg
    df["Calc_PowerToWeight_hp_per_kg"] = _safe_div(
        df["EngPower_hp"], df["MTOW_kg"])
    # 6. Anchor PayloadEndurance per kg of MTOW — anchored productivity / mass
    df["Calc_PEPerMTOW_h"] = _safe_div(
        df["PayloadEnduranceProduct_kgh"], df["MTOW_kg"])
    # 7. Endurance × Cruise — derived range cross-check (km).
    #    NOTE: NOT the same as BestRange; useful for spotting inconsistencies
    #    between published range and the cruise×endurance product.
    df["Calc_EnduranceXCruise_km"] = _safe_div(
        df["Endurance_h"] * df["CruiseSpeed_kmh"], 1.0)
    # 8. Empty-mass fraction (rough) — (MTOW - Payload) / MTOW. Not true
    #    empty mass (since structural+fuel mass collapses with payload),
    #    but a workable lower-bound proxy.
    df["Calc_StructuralFraction"] = _safe_div(
        df["MTOW_kg"] - df["Payload_kg"], df["MTOW_kg"])
    return df


def _compute_mission_productivity(row, speed_col: str):
    """Speed × Endurance × Payload, returning km·kg, anchored when possible.

    Returns None if any factor is missing or non-positive."""
    speed = row.get(speed_col)
    end = row.get("Endurance_h")
    if pd.isna(speed) or speed <= 0:
        return None
    if pd.isna(end) or end <= 0:
        return None
    anchor = row.get("AnchorPayload_kg")
    if pd.notna(anchor) and anchor > 0:
        payload = float(anchor)
    else:
        payload = row.get("Payload_kg")
        if pd.isna(payload) or payload <= 0:
            return None
        payload = float(payload)
    return float(speed) * float(end) * payload


def _compute_payload_endurance(row):
    """Anchor payload × Endurance if available, else max payload × Endurance.
    Returns None if either factor is missing."""
    end = row.get("Endurance_h")
    if pd.isna(end) or end <= 0:
        return None
    anchor = row.get("AnchorPayload_kg")
    if pd.notna(anchor) and anchor > 0:
        return float(anchor) * float(end)
    payload = row.get("Payload_kg")
    if pd.notna(payload) and payload > 0:
        return float(payload) * float(end)
    return None


CRUISE_FROM_MAX_FRACTION = 0.65   # typical for fixed-wing UAV


def _compute_derived_range(row) -> float:
    """Cruise × Endurance if both present, else None."""
    cruise = row.get("CruiseSpeed_kmh")
    endur = row.get("Endurance_h")
    if pd.notna(cruise) and pd.notna(endur) and cruise > 0 and endur > 0:
        return cruise * endur
    return None


def _compute_best_range(row):
    """Return (BestRange_km, RangeKind) using the v0.8.9 rule.

    The old rule (v0.6.2) blindly fell back to Range_km when no cruise speed
    was available. This caused many rows like Algeria 55 (Range_km = 260 km
    is actually the data-link radius, true ferry range ~3,380 km) to show
    misleading BestRange values.

    New rule, in priority order:
      1. If ActualRange_km is present → trust it (user-verified).
      2. If CruiseSpeed × Endurance is computable → derived_cruise. Compare
         to Range_km: if Range >> derived, trust Range (range_supports_ferry);
         if Range << derived, derived is real (Range was data-link); otherwise
         agree.
      3. If only MaxSpeed + Endurance available → derived_max = max × 0.65 ×
         endurance. Same comparison vs Range_km logic.
      4. Else fall back to Range_km but mark low-confidence.

    Returns (value, RangeKind label).
    """
    actual = row.get("ActualRange_km")
    range_km = row.get("Range_km")
    cruise = row.get("CruiseSpeed_kmh")
    max_spd = row.get("MaxSpeed_kmh")
    endur = row.get("Endurance_h")

    if pd.notna(actual):
        return actual, "actual"

    # Derived candidates
    derived_cruise = None
    if pd.notna(cruise) and pd.notna(endur) and cruise > 0 and endur > 0:
        derived_cruise = cruise * endur
    derived_max = None
    if pd.notna(max_spd) and pd.notna(endur) and max_spd > 0 and endur > 0:
        derived_max = max_spd * CRUISE_FROM_MAX_FRACTION * endur

    # Cruise-derived: most accurate
    if derived_cruise is not None:
        if pd.notna(range_km):
            if range_km > 1.5 * derived_cruise:
                # Range > derived endurance limit — likely a verified ferry value
                # Use range_km but flag that derived is lower
                return range_km, "range_supports_ferry"
            elif range_km < 0.5 * derived_cruise:
                # Range << derived — Range_km is almost certainly data-link
                return derived_cruise, "derived_cruise_datalink_likely"
            else:
                # They agree to within ~2x — average them
                return (range_km + derived_cruise) / 2, "derived_cruise_agrees"
        return derived_cruise, "derived_cruise"

    # Max-speed-derived: less accurate but better than nothing
    if derived_max is not None:
        if pd.notna(range_km):
            if range_km > derived_max:
                return range_km, "range_supports_ferry"
            elif range_km < 0.3 * derived_max:
                return derived_max, "derived_max_datalink_likely"
            else:
                # Use larger of the two — both are credible
                return max(range_km, derived_max), "derived_max_or_range"
        return derived_max, "derived_max_estimated"

    # No way to compute derived
    if pd.notna(range_km):
        return range_km, "range_only_low_conf"

    return None, "none"


def _compute_size_class_std(row) -> str:
    """Derive SizeClassStd from MTOW + engine + endurance + endurance flag.

    Classes:
      - Nano/Micro (<2 kg), Mini (2-20), Small (20-150), Tactical (150-600),
        MALE (600-2000), HALE (>=2000) — pure MTOW-based
      - HAPS — high-altitude pseudo-satellite: solar engine + endurance >24 h,
        OR explicitly flagged "high-solar-ok". These are excluded from
        MALE/HALE so their extreme endurance doesn't pollute class statistics.
      - Suspect — endurance values flagged "high-suspect" (e.g. Odysseus
        44,000 h). Quarantined so they don't enter ANY class.

    Returns None when MTOW is missing AND the row isn't HAPS/Suspect.
    """
    flag = row.get("EnduranceFlag", "normal")
    # Quarantine suspect first
    if flag == "high-suspect":
        return "Suspect"
    # HAPS: explicit flag, or solar + extended endurance
    if flag == "high-solar-ok":
        return "HAPS"
    eng = row.get("EngineType")
    end = row.get("Endurance_h")
    if eng == "S" and pd.notna(end) and end > 24:
        return "HAPS"
    # Standard MTOW-based
    mtow = row.get("MTOW_kg")
    if pd.isna(mtow):
        return None
    if mtow < 2: return "Nano/Micro"
    if mtow < 20: return "Mini"
    if mtow < 150: return "Small"
    if mtow < 600: return "Tactical"
    if mtow < 2000: return "MALE"
    return "HALE"


@st.cache_data(show_spinner=False)
def load_acronyms() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "acronyms.csv")


def acronym_lookup(category: str = None) -> dict:
    """Return code -> expansion dict, optionally filtered by category."""
    a = load_acronyms()
    if category:
        a = a[a["category"] == category]
    return dict(zip(a["code"], a["expansion"]))


def expand(code: str, category: str = None) -> str:
    """Pretty-print a code: 'P (Piston)'. Returns code unchanged if unknown."""
    if not isinstance(code, str):
        return code
    lut = acronym_lookup(category)
    exp = lut.get(code)
    return f"{code} ({exp})" if exp else code
