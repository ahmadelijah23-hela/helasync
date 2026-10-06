"""
HeLaSync Referral Management
----------------------------

Stage 3A / 3B referral backend.

Responsibilities:
- Route referrals to the appropriate research team.
- Create clinical trial referrals.
- Prevent duplicate referrals for the same patient + trial.
- Preserve duplicate referral attempts in referral_history.
- Track referral status.
- Support the Research Dashboard.
- Maintain an in-memory referral store for the prototype.

IMPORTANT:
This is prototype infrastructure only.
Referral data is stored in memory and will be lost when the
Render service restarts or redeploys.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


# ============================================================
# TRIAL ROUTING
# ============================================================

TRIAL_ROUTING: Dict[str, Dict[str, Any]] = {

    "NCTFAKE001": {
        "trial_id": "NCTFAKE001",
        "trial_name": "Type 2 Diabetes Cardiovascular Study",
        "research_team": "HeLaSync Diabetes Research Team",
        "research_email": "research@helasync.org",
    },

    "NCTFAKE002": {
        "trial_id": "NCTFAKE002",
        "trial_name": "Cardiac Amyloidosis Heart Failure Study",
        "research_team": "HeLaSync Cardiac Amyloidosis Research Team",
        "research_email": "research@helasync.org",
    },

    "NCTFAKE003": {
        "trial_id": "NCTFAKE003",
        "trial_name": "HeLaSync Heart Failure Treatment Study",
        "research_team": "HeLaSync Heart Failure Research Team",
        "research_email": "research@helasync.org",
    },
}


# ============================================================
# IN-MEMORY REFERRAL DATABASE
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
# HELPERS
# ============================================================

def current_timestamp() -> str:
    """
    Return the current UTC timestamp in ISO-8601 format.
    """
    return datetime.now(timezone.utc).isoformat()


def normalize_trial_id(trial_id: Any) -> str:
    """
    Normalize a clinical trial ID for comparisons.
    """
    return str(trial_id or "").strip().upper()


def normalize_patient_id(patient_id: Any) -> str:
    """
    Normalize a patient ID for comparisons.
    """
    return str(patient_id or "").strip()


def generate_referral_id() -> str:
    """
    Generate a unique HeLaSync referral ID.

    Example:
        HSR-A1B2C3D4
    """
    return f"HSR-{uuid.uuid4().hex[:8].upper()}"


# ============================================================
# TRIAL LOOKUP
# ============================================================

def get_trial_routing(trial_id: str) -> Optional[Dict[str, Any]]:
    """
    Return routing information for a clinical trial.

    Returns:
        Trial routing dictionary or None if the trial is not configured.
    """

    normalized_trial_id = normalize_trial_id(trial_id)

    return TRIAL_ROUTING.get(normalized_trial_id)


# ============================================================
# DUPLICATE REFERRAL DETECTION
# ============================================================

def find_existing_referral(
    trial_id: str,
    patient_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Find an existing referral for the same patient + trial.

    IMPORTANT:
    The encounter ID and clinician ID are intentionally NOT part
    of the duplicate key.

    This means:

        Patient A + Trial X

    can only have one referral.

    A second CDS Hooks encounter, clinician, or launch attempt
    does not create another referral.
    """

    normalized_trial_id = normalize_trial_id(trial_id)
    normalized_patient_id = normalize_patient_id(patient_id)

    for referral in REFERRALS.values():

        existing_trial_id = normalize_trial_id(
            referral.get("trial_id")
        )

        existing_patient_id = normalize_patient_id(
            referral.get("patient_id")
        )

        if (
            existing_trial_id == normalized_trial_id
            and existing_patient_id == normalized_patient_id
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
    source: str = "CDS_HOOKS",
    patient_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a new clinical trial referral.

    Duplicate behavior:
    -------------------

    If the same patient has already been referred to the same
    clinical trial, a second referral is NOT created.

    Instead:
    - The existing referral is returned.
    - The duplicate attempt is recorded in referral_history.
    - Last-seen clinician / encounter information is updated.

    This prevents duplicate research referrals when:
    - CDS Hooks fires more than once.
    - The clinician opens the card again.
    - A different clinician sees the same patient.
    - A different encounter generates the same referral.
    """

    normalized_trial_id = normalize_trial_id(trial_id)
    normalized_patient_id = normalize_patient_id(patient_id)

    # --------------------------------------------------------
    # Validate trial
    # --------------------------------------------------------

    if not normalized_trial_id:
        raise ValueError("trial_id is required.")

    if not normalized_patient_id:
        raise ValueError("patient_id is required.")

    trial = get_trial_routing(normalized_trial_id)

    if trial is None:
        raise ValueError(
            f"Trial '{normalized_trial_id}' is not configured "
            "for referral routing."
        )

    # --------------------------------------------------------
    # Check for existing referral
    # --------------------------------------------------------

    existing_referral = find_existing_referral(
        trial_id=normalized_trial_id,
        patient_id=normalized_patient_id,
    )

    if existing_referral is not None:

        duplicate_event = {
            "timestamp": current_timestamp(),
            "event": "DUPLICATE_REFERRAL_ATTEMPT",
            "source": source,
            "clinician_id": clinician_id,
            "encounter_id": encounter_id,
        }

        existing_referral.setdefault(
            "referral_history",
            [],
        ).append(duplicate_event)

        # Track most recent interaction without creating
        # another referral.
        existing_referral["last_seen_at"] = current_timestamp()

        existing_referral["last_seen_clinician_id"] = (
            clinician_id
        )

        existing_referral["last_seen_encounter_id"] = (
            encounter_id
        )

        existing_referral["last_seen_source"] = source

        return existing_referral

    # --------------------------------------------------------
    # Create new referral
    # --------------------------------------------------------

    referral_id = generate_referral_id()

    timestamp = current_timestamp()

    referral = {

        # ----------------------------------------------------
        # Referral identity
        # ----------------------------------------------------

        "referral_id": referral_id,

        "trial_id": normalized_trial_id,

        "trial_name": trial.get(
            "trial_name",
            normalized_trial_id,
        ),

        # ----------------------------------------------------
        # Patient
        # ----------------------------------------------------

        "patient_id": normalized_patient_id,

        # ----------------------------------------------------
        # Clinician / encounter
        # ----------------------------------------------------

        "clinician_id": clinician_id,

        "encounter_id": encounter_id,

        # ----------------------------------------------------
        # Referral status
        # ----------------------------------------------------

        "status": "INTERESTED",

        # ----------------------------------------------------
        # Research routing
        # ----------------------------------------------------

        "research_team": trial.get(
            "research_team",
            "HeLaSync Research Team",
        ),

        "research_email": trial.get(
            "research_email",
            "research@helasync.org",
        ),

        # ----------------------------------------------------
        # Source
        # ----------------------------------------------------

        "source": source,

        # ----------------------------------------------------
        # Timestamps
        # ----------------------------------------------------

        "created_at": timestamp,

        "updated_at": timestamp,

        "last_seen_at": timestamp,

        "last_seen_clinician_id": clinician_id,

        "last_seen_encounter_id": encounter_id,

        "last_seen_source": source,

        # ----------------------------------------------------
        # Optional patient context
        # ----------------------------------------------------

        "patient_data": patient_data or {},

        # ----------------------------------------------------
        # Audit history
        # ----------------------------------------------------

        "referral_history": [
            {
                "timestamp": timestamp,
                "event": "REFERRAL_CREATED",
                "source": source,
                "clinician_id": clinician_id,
                "encounter_id": encounter_id,
                "status": "INTERESTED",
            }
        ],
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
    """
    Retrieve a referral by referral ID.
    """

    if not referral_id:
        return None

    return REFERRALS.get(
        str(referral_id).strip()
    )


# ============================================================
# LIST REFERRALS
# ============================================================

def list_referrals() -> List[Dict[str, Any]]:
    """
    Return all current referrals.

    IMPORTANT:
    This intentionally returns a LIST rather than:

        {
            "count": ...,
            "referrals": [...]
        }

    The existing HeLaSync Research Dashboard expects the
    /referrals endpoint to return a JSON array directly.

    This preserves dashboard compatibility.
    """

    referrals = list(
        REFERRALS.values()
    )

    # Newest referrals first.
    referrals.sort(
        key=lambda referral:
            referral.get(
                "created_at",
                "",
            ),
        reverse=True,
    )

    return referrals


# ============================================================
# FIND REFERRALS FOR PATIENT
# ============================================================

def get_patient_referrals(
    patient_id: str,
) -> List[Dict[str, Any]]:
    """
    Return all referrals associated with a patient.
    """

    normalized_patient_id = normalize_patient_id(
        patient_id
    )

    referrals = []

    for referral in REFERRALS.values():

        existing_patient_id = normalize_patient_id(
            referral.get("patient_id")
        )

        if existing_patient_id == normalized_patient_id:
            referrals.append(referral)

    referrals.sort(
        key=lambda referral:
            referral.get(
                "created_at",
                "",
            ),
        reverse=True,
    )

    return referrals


# ============================================================
# FIND REFERRALS FOR TRIAL
# ============================================================

def get_trial_referrals(
    trial_id: str,
) -> List[Dict[str, Any]]:
    """
    Return all referrals associated with a clinical trial.
    """

    normalized_trial_id = normalize_trial_id(
        trial_id
    )

    referrals = []

    for referral in REFERRALS.values():

        existing_trial_id = normalize_trial_id(
            referral.get("trial_id")
        )

        if existing_trial_id == normalized_trial_id:
            referrals.append(referral)

    referrals.sort(
        key=lambda referral:
            referral.get(
                "created_at",
                "",
            ),
        reverse=True,
    )

    return referrals


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
            "referral_id is required."
        )

    normalized_referral_id = str(
        referral_id
    ).strip()

    referral = REFERRALS.get(
        normalized_referral_id
    )

    if referral is None:
        raise ValueError(
            f"Referral '{normalized_referral_id}' "
            "was not found."
        )

    normalized_status = str(
        status or ""
    ).strip().upper()

    if normalized_status not in ALLOWED_STATUSES:
        raise ValueError(
            f"Invalid referral status "
            f"'{normalized_status}'. "
            f"Allowed statuses: "
            f"{', '.join(sorted(ALLOWED_STATUSES))}"
        )

    previous_status = referral.get(
        "status"
    )

    timestamp = current_timestamp()

    # --------------------------------------------------------
    # Update current status
    # --------------------------------------------------------

    referral["status"] = normalized_status

    referral["updated_at"] = timestamp

    # --------------------------------------------------------
    # Preserve status history
    # --------------------------------------------------------

    referral.setdefault(
        "referral_history",
        [],
    ).append(
        {
            "timestamp": timestamp,
            "event": "STATUS_CHANGED",
            "previous_status": previous_status,
            "new_status": normalized_status,
        }
    )

    return referral


# ============================================================
# DELETE / RESET REFERRALS
# ============================================================

def clear_referrals() -> Dict[str, Any]:
    """
    Clear all in-memory referrals.

    Intended for prototype testing only.

    Returns:
        Confirmation and number of deleted referrals.
    """

    count = len(REFERRALS)

    REFERRALS.clear()

    return {
        "status": "cleared",
        "deleted_count": count,
    }


# ============================================================
# DUPLICATE CHECK
# ============================================================

def referral_exists(
    trial_id: str,
    patient_id: str,
) -> bool:
    """
    Return True if the patient already has a referral
    for the specified clinical trial.
    """

    return (
        find_existing_referral(
            trial_id=trial_id,
            patient_id=patient_id,
        )
        is not None
    )


# ============================================================
# REFERRAL SUMMARY
# ============================================================

def referral_summary(
    referral_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return a compact referral summary.

    Useful for future CDS Hooks / Smart App integrations.
    """

    referral = get_referral(
        referral_id
    )

    if referral is None:
        return None

    return {
        "referral_id": referral.get(
            "referral_id"
        ),
        "trial_id": referral.get(
            "trial_id"
        ),
        "trial_name": referral.get(
            "trial_name"
        ),
        "patient_id": referral.get(
            "patient_id"
        ),
        "status": referral.get(
            "status"
        ),
        "research_team": referral.get(
            "research_team"
        ),
        "created_at": referral.get(
            "created_at"
        ),
        "updated_at": referral.get(
            "updated_at"
        ),
    }
