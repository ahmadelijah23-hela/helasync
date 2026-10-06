from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


# ============================================================
# CLINICAL TRIAL ROUTING
# ============================================================

TRIAL_ROUTING = {
    "NCTFAKE001": {
        "trial_id": "NCTFAKE001",
        "trial_name": "Type 2 Diabetes Cardiovascular Study",
        "research_team": "HeLaSync Research Team A",
        "contact": "research-team-a@helasync.org",
    },
    "NCTFAKE002": {
        "trial_id": "NCTFAKE002",
        "trial_name": "Cardiac Amyloidosis Heart Failure Study",
        "research_team": "HeLaSync Research Team B",
        "contact": "research-team-b@helasync.org",
    },
    "NCTFAKE003": {
        "trial_id": "NCTFAKE003",
        "trial_name": "HeLaSync Heart Failure Treatment Study",
        "research_team": "HeLaSync Research Team C",
        "contact": "research-team-c@helasync.org",
    },
}


# ============================================================
# IN-MEMORY REFERRAL STORE
# ============================================================

REFERRALS: Dict[str, Dict[str, Any]] = {}


# ============================================================
# TRIAL LOOKUP
# ============================================================

def get_trial_routing(
    trial_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return routing information for a clinical trial.
    """

    return TRIAL_ROUTING.get(trial_id)


# ============================================================
# DUPLICATE REFERRAL CHECK
# ============================================================

def find_existing_referral(
    trial_id: str,
    patient_id: str,
    clinician_id: Optional[str] = None,
    encounter_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check whether an active referral already exists for
    the same patient, clinical trial, and encounter.

    This prevents accidental duplicate referrals when a
    clinician clicks Submit Referral more than once.

    Duplicate matching logic:

        Same trial
        +
        Same patient
        +
        Same encounter

    If an encounter ID is not available, the system falls
    back to matching patient + trial.
    """

    for referral in REFERRALS.values():

        referral_trial_id = (
            referral.get("trial", {}).get("trial_id")
        )

        referral_patient_id = (
            referral.get("patient", {}).get("patient_id")
        )

        referral_encounter_id = (
            referral.get("encounter_id")
        )

        if referral_trial_id != trial_id:
            continue

        if referral_patient_id != patient_id:
            continue

        # ----------------------------------------------------
        # Strongest duplicate check:
        # patient + trial + encounter
        # ----------------------------------------------------

        if encounter_id:

            if referral_encounter_id == encounter_id:
                return referral

            continue

        # ----------------------------------------------------
        # Fallback:
        # patient + trial
        # ----------------------------------------------------

        if not encounter_id:
            return referral

    return None


# ============================================================
# CREATE REFERRAL
# ============================================================

def create_referral(
    trial_id: str,
    patient_id: str,
    clinician_id: Optional[str] = None,
    encounter_id: Optional[str] = None,
    source: str = "CDS Hooks",
    patient_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    # --------------------------------------------------------
    # Verify trial exists
    # --------------------------------------------------------

    trial = get_trial_routing(trial_id)

    if trial is None:
        raise ValueError(
            f"Unknown clinical trial: {trial_id}"
        )


    # --------------------------------------------------------
    # Check for existing referral
    # --------------------------------------------------------

    existing_referral = find_existing_referral(
        trial_id=trial_id,
        patient_id=patient_id,
        clinician_id=clinician_id,
        encounter_id=encounter_id,
    )

    if existing_referral is not None:

        # Add a flag so the caller knows this was
        # an existing referral rather than a new one.

        existing_referral["duplicate_prevented"] = True

        return existing_referral


    # --------------------------------------------------------
    # Generate unique referral ID
    # --------------------------------------------------------

    referral_id = (
        f"HSR-{uuid4().hex[:12].upper()}"
    )


    # --------------------------------------------------------
    # Create referral record
    # --------------------------------------------------------

    referral = {

        "referral_id": referral_id,

        "trial": {
            "trial_id": trial["trial_id"],
            "trial_name": trial["trial_name"],
        },

        "status": "INTERESTED",

        "patient": {
            "patient_id": patient_id,
        },

        "clinician": {
            "clinician_id": clinician_id,
        },

        "encounter_id": encounter_id,

        "routing": {
            "research_team": trial["research_team"],
            "contact": trial["contact"],
        },

        "source": source,

        "created_at": (
            datetime.now(timezone.utc).isoformat()
        ),

        "patient_data": patient_data or {},

        "duplicate_prevented": False,
    }


    # --------------------------------------------------------
    # Store referral
    # --------------------------------------------------------

    REFERRALS[referral_id] = referral


    return referral


# ============================================================
# GET SINGLE REFERRAL
# ============================================================

def get_referral(
    referral_id: str,
) -> Optional[Dict[str, Any]]:

    return REFERRALS.get(
        referral_id
    )


# ============================================================
# LIST ALL REFERRALS
# ============================================================

def list_referrals():

    return list(
        REFERRALS.values()
    )
