from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


# ============================================================
# HElaSYNC TRIAL ROUTING REGISTRY
# ============================================================
#
# Stage 2 prototype:
#
# trial ID → research team
#
# In production this should eventually come from a secure
# database/configuration service rather than hard-coded values.
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
#
# Stage 2 prototype only.
#
# Render instances are ephemeral, so this is NOT production
# persistence.
#
# Later we will replace this with a database.
# ============================================================

REFERRALS = {}


# ============================================================
# GET TRIAL ROUTING
# ============================================================

def get_trial_routing(trial_id: str) -> Optional[Dict[str, Any]]:
    """
    Return routing information for a specific trial.
    """

    return TRIAL_ROUTING.get(trial_id)


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
    # Validate trial
    # --------------------------------------------------------

    trial = get_trial_routing(trial_id)

    if trial is None:
        raise ValueError(
            f"Unknown clinical trial: {trial_id}"
        )


    # --------------------------------------------------------
    # Generate referral ID
    # --------------------------------------------------------

    referral_id = f"HSR-{uuid4().hex[:12].upper()}"


    # --------------------------------------------------------
    # Create referral
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

        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Patient data should NOT be placed here until it has
        # passed through the Privacy Gateway.
        # ----------------------------------------------------

        "patient_data": patient_data or {},
    }


    # --------------------------------------------------------
    # Store referral
    # --------------------------------------------------------

    REFERRALS[referral_id] = referral


    return referral


# ============================================================
# GET REFERRAL
# ============================================================

def get_referral(
    referral_id: str,
) -> Optional[Dict[str, Any]]:

    return REFERRALS.get(
        referral_id
    )


# ============================================================
# LIST REFERRALS
# ============================================================

def list_referrals():

    return list(
        REFERRALS.values()
    )
