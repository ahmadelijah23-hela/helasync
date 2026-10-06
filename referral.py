# ============================================================
# HeLaSync Referral Management
# Stage 3A.5
#
# Purpose:
# - Create clinical trial referrals
# - Prevent duplicate referrals for the same patient + trial
# - Retrieve individual referrals
# - List research referrals
# - Update referral status
#
# Prototype storage:
# - In-memory dictionary
# - Data will reset when the Render service restarts
# ============================================================

from datetime import datetime
from typing import Any, Dict, Optional
import uuid


# ============================================================
# TRIAL ROUTING
# ============================================================

TRIAL_ROUTING = {
    "NCTFAKE001": {
        "trial_title": "Type 2 Diabetes Cardiovascular Study",
        "research_team": "HeLaSync Research Team A",
        "research_email": "research-team-a@helasync.org",
    },

    "NCTFAKE002": {
        "trial_title": "Cardiac Amyloidosis Heart Failure Study",
        "research_team": "HeLaSync Research Team B",
        "research_email": "research-team-b@helasync.org",
    },

    "NCTFAKE003": {
        "trial_title": "HeLaSync Heart Failure Treatment Study",
        "research_team": "HeLaSync Research Team C",
        "research_email": "research-team-c@helasync.org",
    },
}


# ============================================================
# IN-MEMORY REFERRAL STORAGE
# ============================================================

REFERRALS: Dict[str, Dict[str, Any]] = {}


# ============================================================
# ALLOWED REFERRAL STATUSES
# ============================================================

ALLOWED_STATUSES = {
    "INTERESTED",
    "UNDER_REVIEW",
    "CONTACTED",
    "SCREENING",
    "ENROLLED",
    "NOT_ELIGIBLE",
}


# ============================================================
# HELPER: GENERATE REFERRAL ID
# ============================================================

def generate_referral_id() -> str:
    """
    Generate a short human-readable HeLaSync referral ID.
    """

    return (
        "HSR-"
        + uuid.uuid4()
        .hex[:12]
        .upper()
    )


# ============================================================
# HELPER: CURRENT TIMESTAMP
# ============================================================

def current_timestamp() -> str:
    """
    Return the current UTC timestamp in ISO format.
    """

    return datetime.utcnow().isoformat() + "Z"


# ============================================================
# HELPER: FIND EXISTING REFERRAL
# ============================================================

def find_existing_referral(
    trial_id: str,
    patient_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Find an existing referral using the HeLaSync
    uniqueness rule:

        ONE REFERRAL PER PATIENT + TRIAL

    Encounter ID and clinician ID are intentionally
    NOT part of the duplicate key.

    This prevents the same patient from appearing
    multiple times in the research queue for the
    same clinical trial simply because the referral
    originated from a different encounter or clinician.
    """

    normalized_trial_id = str(
        trial_id
    ).strip().upper()

    normalized_patient_id = str(
        patient_id
    ).strip()

    for referral in REFERRALS.values():

        existing_trial_id = str(
            referral.get(
                "trial_id",
                "",
            )
        ).strip().upper()

        existing_patient_id = str(
            referral.get(
                "patient_id",
                "",
            )
        ).strip()

        if (
            existing_trial_id
            == normalized_trial_id
            and existing_patient_id
            == normalized_patient_id
        ):
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
    """
    Create a new HeLaSync clinical trial referral.

    IMPORTANT DUPLICATE RULE:

        trial_id + patient_id

    identifies a unique referral.

    Therefore:

        Same patient
        +
        Same clinical trial

    will return the existing referral instead of
    creating another referral.

    Different encounters do NOT create duplicate
    referrals.
    """

    # --------------------------------------------------------
    # Validate required fields
    # --------------------------------------------------------

    if not trial_id:
        raise ValueError(
            "trial_id is required"
        )

    if not patient_id:
        raise ValueError(
            "patient_id is required"
        )

    trial_id = str(
        trial_id
    ).strip().upper()

    patient_id = str(
        patient_id
    ).strip()

    if not trial_id:
        raise ValueError(
            "trial_id cannot be empty"
        )

    if not patient_id:
        raise ValueError(
            "patient_id cannot be empty"
        )

    # --------------------------------------------------------
    # Validate trial
    # --------------------------------------------------------

    trial_info = TRIAL_ROUTING.get(
        trial_id
    )

    if trial_info is None:

        raise ValueError(
            f"Unknown clinical trial: {trial_id}"
        )

    # --------------------------------------------------------
    # DUPLICATE CHECK
    #
    # One referral per patient + trial.
    # --------------------------------------------------------

    existing_referral = (
        find_existing_referral(
            trial_id=trial_id,
            patient_id=patient_id,
        )
    )

    if existing_referral is not None:

        # ----------------------------------------------------
        # Preserve the original referral but record that
        # another referral attempt occurred.
        # ----------------------------------------------------

        referral_history = (
            existing_referral.setdefault(
                "referral_history",
                [],
            )
        )

        referral_history.append(
            {
                "timestamp":
                    current_timestamp(),

                "event":
                    "DUPLICATE_REFERRAL_ATTEMPT",

                "source":
                    source,

                "clinician_id":
                    clinician_id,

                "encounter_id":
                    encounter_id,
            }
        )

        # ----------------------------------------------------
        # Update last-seen information without creating
        # another research queue entry.
        # ----------------------------------------------------

        existing_referral[
            "last_seen_at"
        ] = current_timestamp()

        existing_referral[
            "last_seen_clinician_id"
        ] = clinician_id

        existing_referral[
            "last_seen_encounter_id"
        ] = encounter_id

        existing_referral[
            "last_seen_source"
        ] = source

        return existing_referral

    # ========================================================
    # CREATE NEW REFERRAL
    # ========================================================

    referral_id = generate_referral_id()

    timestamp = current_timestamp()

    referral = {

        # ----------------------------------------------------
        # Referral identity
        # ----------------------------------------------------

        "referral_id":
            referral_id,

        "status":
            "INTERESTED",

        # ----------------------------------------------------
        # Trial information
        # ----------------------------------------------------

        "trial_id":
            trial_id,

        "trial_title":
            trial_info[
                "trial_title"
            ],

        # ----------------------------------------------------
        # Patient
        # ----------------------------------------------------

        "patient_id":
            patient_id,

        # ----------------------------------------------------
        # Referring clinician
        # ----------------------------------------------------

        "clinician_id":
            clinician_id,

        # ----------------------------------------------------
        # Original encounter
        # ----------------------------------------------------

        "encounter_id":
            encounter_id,

        # ----------------------------------------------------
        # Research routing
        # ----------------------------------------------------

        "research_team":
            trial_info[
                "research_team"
            ],

        "research_email":
            trial_info[
                "research_email"
            ],

        # ----------------------------------------------------
        # Source
        # ----------------------------------------------------

        "source":
            source,

        # ----------------------------------------------------
        # Timestamps
        # ----------------------------------------------------

        "created_at":
            timestamp,

        "updated_at":
            timestamp,

        "last_seen_at":
            timestamp,

        # ----------------------------------------------------
        # Patient data
        #
        # Kept for prototype workflow compatibility.
        # Do not place unnecessary PHI here in production.
        # ----------------------------------------------------

        "patient_data":
            patient_data or {},

        # ----------------------------------------------------
        # Referral history
        # ----------------------------------------------------

        "referral_history": [
            {
                "timestamp":
                    timestamp,

                "event":
                    "REFERRAL_CREATED",

                "source":
                    source,

                "clinician_id":
                    clinician_id,

                "encounter_id":
                    encounter_id,
            }
        ],
    }

    # --------------------------------------------------------
    # Store referral
    # --------------------------------------------------------

    REFERRALS[
        referral_id
    ] = referral

    return referral


# ============================================================
# GET SINGLE REFERRAL
# ============================================================

def get_referral(
    referral_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a referral by referral ID.
    """

    if not referral_id:
        return None

    return REFERRALS.get(
        referral_id
    )


# ============================================================
# LIST REFERRALS
# ============================================================

def list_referrals() -> Dict[str, Any]:
    """
    Return all current referrals.

    The dashboard expects the referral records
    to be returned in a JSON-compatible structure.
    """

    referrals = list(
        REFERRALS.values()
    )

    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    referrals.sort(
        key=lambda referral:
            referral.get(
                "created_at",
                "",
            ),
        reverse=True,
    )

    return {
        "count":
            len(referrals),

        "referrals":
            referrals,
    }


# ============================================================
# UPDATE REFERRAL STATUS
# ============================================================

def update_referral_status(
    referral_id: str,
    status: str,
) -> Dict[str, Any]:
    """
    Update the status of an existing referral.

    Supported statuses:

        INTERESTED
        UNDER_REVIEW
        CONTACTED
        SCREENING
        ENROLLED
        NOT_ELIGIBLE
    """

    if not referral_id:
        raise ValueError(
            "referral_id is required"
        )

    if not status:
        raise ValueError(
            "status is required"
        )

    normalized_status = str(
        status
    ).strip().upper()

    if normalized_status not in ALLOWED_STATUSES:

        raise ValueError(
            "Invalid referral status. "
            f"Allowed statuses: "
            f"{', '.join(sorted(ALLOWED_STATUSES))}"
        )

    referral = REFERRALS.get(
        referral_id
    )

    if referral is None:

        raise ValueError(
            f"Referral not found: {referral_id}"
        )

    previous_status = referral.get(
        "status"
    )

    # --------------------------------------------------------
    # Update status
    # --------------------------------------------------------

    referral[
        "status"
    ] = normalized_status

    referral[
        "updated_at"
    ] = current_timestamp()

    # --------------------------------------------------------
    # Add status history
    # --------------------------------------------------------

    referral_history = (
        referral.setdefault(
            "referral_history",
            [],
        )
    )

    referral_history.append(
        {
            "timestamp":
                current_timestamp(),

            "event":
                "STATUS_CHANGED",

            "previous_status":
                previous_status,

            "new_status":
                normalized_status,
        }
    )

    return referral


# ============================================================
# OPTIONAL: FIND REFERRAL BY PATIENT + TRIAL
# ============================================================

def get_referral_by_patient_trial(
    patient_id: str,
    trial_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve the single referral associated with:

        patient_id + trial_id

    This is useful for future Smart App or
    EHR integrations.
    """

    return find_existing_referral(
        trial_id=trial_id,
        patient_id=patient_id,
    )
