"""Shared acronym → full-name mappings for categorical columns.

Single source of truth used by Data Admin, Compare Filters, Design-space,
and Compare Platforms so the same friendly labels appear everywhere.

Each *_NAMES dict maps the short code stored in the dataset to a human
label. Use code_to_label(col, code) and label_to_code(col, label) for the
bidirectional translation, and friendly_options(col, codes) to build a
selectbox/multiselect option list that displays full names but returns codes.
"""

SIZE_CLASS_STD_NAMES = {
    "Nano/Micro": "Nano/Micro (<2 kg)",
    "Mini": "Mini (2–20 kg)",
    "Small": "Small (20–150 kg)",
    "Tactical": "Tactical (150–600 kg)",
    "MALE": "MALE — Medium-Altitude Long-Endurance (600–2000 kg)",
    "HALE": "HALE — High-Altitude Long-Endurance (≥2000 kg)",
    "HAPS": "HAPS — High-Altitude Pseudo-Satellite (solar)",
    "Suspect": "Suspect (quarantined data)",
}

OPERATIONAL_ROLE_NAMES = {
    "M": "Military (M)",
    "DP": "Dual-Purpose military/civilian (DP)",
    "CC": "Civilian / Commercial (CC)",
    "DV": "Developmental / Demonstrator (DV)",
    "RA": "Research / Academic (RA)",
    "ML": "Maritime / Law-enforcement (ML)",
}

AIRFRAME_NAMES = {
    "FW": "Fixed-Wing (FW)",
    "FW/RW": "Hybrid Fixed/Rotary-Wing (FW/RW)",
    "FW/TR": "Fixed-Wing with Tilt-Rotor (FW/TR)",
    "TW": "Tilt-Wing (TW)",
    "TS": "Tail-Sitter (TS)",
}

TAIL_CONFIG_NAMES = {
    "tail-less": "Tail-less (no horizontal & no vertical tail)",
    "vtail-only": "Vertical rudder only (no horizontal tail)",
    "V": "V-tail",
    "boom": "Single boom-mounted tail",
    "C": "Conventional tail (C)",
    "inv-V": "Inverted V-tail",
    "T": "T-tail",
    "H-boom": "Twin-boom H-tail",
    "cruciform": "Cruciform tail",
    "dual-tail": "Dual vertical tail",
    "winglets": "Wingtip winglets/fins (no rear tail)",
    "Y": "Y-tail",
    "tailsitter": "Tailsitter (vertical-stance airframe)",
    "inv-winglets": "Inverted winglets",
    "inv-Y": "Inverted Y-tail",
    "triple-tail": "Triple vertical tail",
    "conventional": "Conventional rectangular tail",
}

WING_FORM_NAMES = {
    "T": "Tapered (T)",
    "swept": "Swept-back",
    "R": "Rectangular (R)",
    "e": "Elliptical (e)",
    "Polyhedral": "Polyhedral",
    "d": "Delta (d)",
    "boxW": "Box-wing (boxW)",
    "swept-fwd": "Forward-swept",
}

WING_CONFIG_NAMES = {
    "H": "High-wing (H)",
    "L": "Low-wing (L)",
    "M": "Mid-wing (M)",
    "canard": "Canard configuration",
    "cruciform": "Cruciform wing",
    "Joined-wing": "Joined-wing",
    "TW": "Tandem-wing (TW)",
    "parasol": "Parasol wing",
    "biplane": "Biplane",
    "Gull": "Gull wing",
}

BODY_CONFIG_NAMES = {
    "WT": "Wing-tube fuselage (WT)",
    "Tboom": "Twin-boom (Tboom)",
    "FW": "Flying-wing (FW)",
    "BW": "Blended-wing-body (BW)",
    "boxW": "Box-wing body (boxW)",
}

ENGINE_TYPE_NAMES = {
    "E": "Electric (E)",
    "P": "Piston / Internal Combustion (P)",
    "H": "Hybrid electric (H)",
    "Turbojet": "Turbojet",
    "Turbofan": "Turbofan",
    "Turboprop": "Turboprop",
    "S": "Solar (S)",
    "DF": "Ducted-Fan (DF)",
    "G": "Glider / Powerless (G)",
    "FC": "Fuel Cell (FC)",
}

LAUNCH_METHOD_NAMES = {
    "CTOL": "Conventional Take-Off & Landing / runway (CTOL)",
    "Catapult": "Catapult (pneumatic or elastic)",
    "VTOL": "Vertical Take-Off & Landing (VTOL)",
    "Hand": "Hand-launched",
    "RATO": "Rocket-Assisted Take-Off (RATO / booster)",
    "Tube": "Tube-launched",
    "AirLaunched": "Air-launched (from carrier aircraft)",
    "CartAssisted": "Cart-assisted launch",
    "Skid": "Skid-launched",
    "WaterTOL": "Water Take-Off & Landing (WaterTOL)",
}

MISSION_NAMES = {
    "ISR": "Intelligence, Surveillance, Reconnaissance (ISR)",
    "LM": "Loitering Munition / Kamikaze (LM)",
    "UCAV": "Unmanned Combat (UCAV)",
    "cargo": "Cargo / logistics",
    "Target": "Target drone / threat emulation",
    "Passengers": "Passenger transport",
    "R&D": "Research / Demonstrator",
    "CUAV": "Counter-UAV / interceptor (CUAV)",
    "tanker": "Aerial refueling tanker",
}

# Master registry: column name → its code→label dict
COLUMN_LABEL_MAPS = {
    "SizeClassStd": SIZE_CLASS_STD_NAMES,
    "OperationalRole": OPERATIONAL_ROLE_NAMES,
    "Airframe": AIRFRAME_NAMES,
    "TailConfig": TAIL_CONFIG_NAMES,
    "WingForm": WING_FORM_NAMES,
    "WingConfig": WING_CONFIG_NAMES,
    "BodyConfig": BODY_CONFIG_NAMES,
    "EngineType": ENGINE_TYPE_NAMES,
    "LaunchMethod": LAUNCH_METHOD_NAMES,
    "Mission": MISSION_NAMES,
}


def code_to_label(col: str, code) -> str:
    """Return the friendly label for a code in a given column.
    Falls back to the code itself if no mapping exists."""
    if code is None:
        return "(none)"
    mapping = COLUMN_LABEL_MAPS.get(col, {})
    return mapping.get(str(code), str(code))


def label_to_code(col: str, label: str):
    """Reverse lookup: friendly label → stored code."""
    mapping = COLUMN_LABEL_MAPS.get(col, {})
    for code, lbl in mapping.items():
        if lbl == label:
            return code
    return label    # already a code, or unmapped


def friendly_format_func(col: str):
    """Return a function suitable for st.selectbox/multiselect format_func
    that maps a stored code to its friendly label for the given column."""
    def _fmt(code):
        return code_to_label(col, code)
    return _fmt
