# ============================================================
# HELASYNC CLINICIAN SMART APP
# Stage 3A
#
# This file provides the clinician-facing Smart App experience
# launched from the CDS Hooks "Additional Information" link.
#
# Prototype route:
#   GET  /referral-launch
#   POST /referrals/from-cds
#
# IMPORTANT:
# This is a prototype implementation.
# Patient/clinician context is currently passed through URL/form
# parameters. Production SMART-on-FHIR authentication and launch
# context will replace this later.
# ============================================================

import html
import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse

from referral import create_referral


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# HELASYNC CONFIGURATION
# ============================================================

HELASYNC_URL = "https://helasync.app"

RESEARCH_DASHBOARD_URL = (
    "https://helasync.onrender.com/research/referrals"
)


# ============================================================
# LOAD TRIAL DATA
# ============================================================

def load_trials() -> Dict[str, Dict[str, Any]]:
    """
    Load clinical trial JSON files from Trial_List.

    The Smart App uses the actual trial files rather than
    inventing trial information.
    """

    trial_folder = Path(__file__).parent / "Trial_List"

    trials: Dict[str, Dict[str, Any]] = {}

    if not trial_folder.exists():
        return trials

    for trial_file in sorted(trial_folder.glob("*.json")):

        try:

            with open(
                trial_file,
                "r",
                encoding="utf-8",
            ) as file:

                trial = json.load(file)

            trial_id = (
                trial.get("trial_id")
                or trial.get("id")
                or trial.get("protocolSection", {})
                .get("identificationModule", {})
                .get("nctId")
            )

            if trial_id:
                trials[str(trial_id)] = trial

        except Exception:
            continue

    return trials


TRIALS = load_trials()


# ============================================================
# TRIAL DATA HELPERS
# ============================================================

def get_trial(
    trial_id: str,
) -> Dict[str, Any]:

    """
    Return the requested trial.

    If the trial cannot be found, return a safe fallback
    containing only the supplied trial ID.
    """

    trial = TRIALS.get(trial_id)

    if trial:
        return trial

    return {
        "trial_id": trial_id,
        "trial_title": "Clinical Trial",
    }


def trial_value(
    trial: Dict[str, Any],
    *keys: str,
    default: str = "",
) -> str:

    """
    Safely retrieve a value from either the simple synthetic
    trial format or the ClinicalTrials.gov-style protocol format.
    """

    for key in keys:

        value = trial.get(key)

        if value not in (None, ""):
            return str(value)

    protocol = trial.get(
        "protocolSection",
        {},
    )

    if not isinstance(protocol, dict):
        return default

    identification = protocol.get(
        "identificationModule",
        {},
    )

    status = protocol.get(
        "statusModule",
        {},
    )

    design = protocol.get(
        "designModule",
        {},
    )

    description = protocol.get(
        "descriptionModule",
        {},
    )

    contacts = protocol.get(
        "contactsLocationsModule",
        {},
    )

    mapping = {

        "trial_id": identification.get(
            "nctId"
        ),

        "trial_title": identification.get(
            "briefTitle"
        ),

        "official_title": identification.get(
            "officialTitle"
        ),

        "status": status.get(
            "overallStatus"
        ),

        "phase": (
            ", ".join(
                design.get("phases", [])
            )
            if isinstance(
                design.get("phases"),
                list,
            )
            else design.get("phases")
        ),

        "brief_summary": description.get(
            "briefSummary"
        ),

        "detailed_description": description.get(
            "detailedDescription"
        ),

    }

    mapped = mapping.get(
        keys[0],
        None,
    )

    if mapped not in (None, ""):
        return str(mapped)

    return default


def get_protocol_section(
    trial: Dict[str, Any],
) -> Dict[str, Any]:

    protocol = trial.get(
        "protocolSection",
        {},
    )

    if isinstance(protocol, dict):
        return protocol

    return {}


def get_eligibility(
    trial: Dict[str, Any],
) -> Dict[str, Any]:

    protocol = get_protocol_section(
        trial
    )

    eligibility = protocol.get(
        "eligibilityModule",
        {},
    )

    if isinstance(eligibility, dict):
        return eligibility

    return {}


def get_locations(
    trial: Dict[str, Any],
) -> list:

    protocol = get_protocol_section(
        trial
    )

    contacts = protocol.get(
        "contactsLocationsModule",
        {},
    )

    if not isinstance(
        contacts,
        dict,
    ):
        return []

    locations = contacts.get(
        "locations",
        [],
    )

    if isinstance(
        locations,
        list,
    ):
        return locations

    return []


# ============================================================
# HTML HELPERS
# ============================================================

def esc(
    value: Any,
) -> str:

    return html.escape(
        str(value)
    )


def status_badge(
    status: str,
) -> str:

    normalized = (
        status or "UNKNOWN"
    ).upper()

    if normalized in (
        "MET",
        "NOT_PRESENT",
        "ELIGIBLE",
    ):

        label = (
            "MET"
            if normalized == "MET"
            else normalized.replace(
                "_",
                " ",
            )
        )

        return (
            '<span class="status status-met">'
            f'{esc(label)}'
            '</span>'
        )

    if normalized in (
        "NOT_MET",
        "PRESENT",
        "NOT_ELIGIBLE",
    ):

        label = normalized.replace(
            "_",
            " ",
        )

        return (
            '<span class="status status-not-met">'
            f'{esc(label)}'
            '</span>'
        )

    return (
        '<span class="status status-unknown">'
        'UNKNOWN'
        '</span>'
    )


# ============================================================
# ELIGIBILITY DEMO DATA
# ============================================================

def build_demo_eligibility(
    trial_id: str,
) -> Dict[str, list]:

    """
    Stage 3A intentionally presents a transparent prototype
    eligibility view.

    The actual Agent 4 eligibility results will be connected
    in a later Stage 3 iteration.

    We do not calculate a percentage match.
    """

    if trial_id == "NCTFAKE003":

        return {
            "inclusion": [
                {
                    "criterion": "Age ≥18",
                    "result": "MET",
                },
                {
                    "criterion": "Heart failure",
                    "result": "MET",
                },
                {
                    "criterion": "NT-proBNP >300",
                    "result": "MET",
                },
            ],
            "exclusion": [
                {
                    "criterion": "Pregnancy",
                    "result": "NOT_PRESENT",
                },
                {
                    "criterion": "eGFR <30 mL/min/1.73 m²",
                    "result": "NOT_PRESENT",
                },
            ],
        }

    return {
        "inclusion": [],
        "exclusion": [],
    }


# ============================================================
# SMART APP PAGE
# ============================================================

@router.get(
    "/referral-launch",
    response_class=HTMLResponse,
)
async def referral_launch(
    trial_id: str = Query(
        default="NCTFAKE003"
    ),
    patient_id: str = Query(
        default="helasync-test-001"
    ),
    clinician_id: str = Query(
        default="Practitioner/test-clinician"
    ),
    encounter_id: str = Query(
        default="encounter-test-001"
    ),
    hook_instance: str = Query(
        default="helasync-stage3-test"
    ),
):

    trial = get_trial(
        trial_id
    )

    title = trial_value(
        trial,
        "trial_title",
        "title",
        default="Clinical Trial",
    )

    official_title = trial_value(
        trial,
        "official_title",
        default="",
    )

    status = trial_value(
        trial,
        "status",
        default="Recruiting",
    )

    phase = trial_value(
        trial,
        "phase",
        default="Not specified",
    )

    intervention = trial.get(
        "intervention",
        trial.get(
            "interventions",
            "Not specified",
        ),
    )

    if isinstance(
        intervention,
        list,
    ):

        intervention = ", ".join(
            str(item)
            for item in intervention
        )

    if not intervention:
        intervention = "Not specified"

    disease_population = trial.get(
        "disease_population",
        trial.get(
            "conditions",
            "Not specified",
        ),
    )

    if isinstance(
        disease_population,
        list,
    ):

        disease_population = ", ".join(
            str(item)
            for item in disease_population
        )

    if not disease_population:
        disease_population = "Not specified"

    objective = trial.get(
        "study_objective",
        trial.get(
            "brief_summary",
            trial_value(
                trial,
                "brief_summary",
                default="Not specified",
            ),
        ),
    )

    study_duration = trial.get(
        "study_duration",
        "Not specified",
    )

    reimbursement = trial.get(
        "reimbursement",
        "Information not available",
    )

    pi_name = trial.get(
        "principal_investigator",
        trial.get(
            "pi_name",
            "Not specified",
        ),
    )

    locations = get_locations(
        trial
    )

    if locations:

        location_text = "<br>".join(
            esc(
                ", ".join(
                    str(
                        value
                    )
                    for value in [
                        location.get(
                            "facility"
                        ),
                        location.get(
                            "city"
                        ),
                        location.get(
                            "state"
                        ),
                    ]
                    if value
                )
            )
            for location in locations[:5]
        )

    else:

        location_text = "Not specified"

    eligibility = build_demo_eligibility(
        trial_id
    )

    inclusion_rows = ""

    for item in eligibility[
        "inclusion"
    ]:

        inclusion_rows += f"""
        <div class="criterion-row">
            <div class="criterion-text">
                {esc(item["criterion"])}
            </div>
            <div>
                {status_badge(item["result"])}
            </div>
        </div>
        """

    exclusion_rows = ""

    for item in eligibility[
        "exclusion"
    ]:

        exclusion_rows += f"""
        <div class="criterion-row">
            <div class="criterion-text">
                {esc(item["criterion"])}
            </div>
            <div>
                {status_badge(item["result"])}
            </div>
        </div>
        """

    if not inclusion_rows:

        inclusion_rows = """
        <div class="empty-state">
            Eligibility details will appear here when
            verified criteria are available.
        </div>
        """

    if not exclusion_rows:

        exclusion_rows = """
        <div class="empty-state">
            No exclusion criteria have been loaded for
            this prototype view.
        </div>
        """

    # --------------------------------------------------------
    # Preserve context for referral submission
    # --------------------------------------------------------

    referral_query = urlencode(
        {
            "trial_id": trial_id,
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "encounter_id": encounter_id,
            "hook_instance": hook_instance,
        }
    )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    page = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    HeLaSync Clinical Trial Intelligence
</title>

<style>

:root {{
    --hs-blue: #155eef;
    --hs-blue-dark: #0b4acb;
    --hs-navy: #102a43;
    --hs-text: #243b53;
    --hs-muted: #627d98;
    --hs-border: #d9e2ec;
    --hs-background: #f7f9fc;
    --hs-white: #ffffff;
    --hs-green: #16803c;
    --hs-green-bg: #e8f7ee;
    --hs-yellow: #9a6700;
    --hs-yellow-bg: #fff8e1;
    --hs-red: #b42318;
    --hs-red-bg: #fef3f2;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: var(--hs-background);
    color: var(--hs-text);
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Helvetica,
        Arial,
        sans-serif;
}}

.header {{
    background: var(--hs-white);
    border-bottom: 1px solid var(--hs-border);
    position: sticky;
    top: 0;
    z-index: 10;
}}

.header-inner {{
    max-width: 1120px;
    margin: auto;
    padding: 18px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}

.brand {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.logo {{
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: var(--hs-blue);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 18px;
}}

.brand-name {{
    font-size: 20px;
    font-weight: 750;
    color: var(--hs-navy);
}}

.brand-subtitle {{
    font-size: 12px;
    color: var(--hs-muted);
}}

.container {{
    max-width: 1120px;
    margin: 0 auto;
    padding: 32px 24px 60px;
}}

.back-link {{
    color: var(--hs-blue);
    text-decoration: none;
    font-size: 14px;
    font-weight: 600;
}}

.hero {{
    margin-top: 18px;
    background: var(--hs-white);
    border: 1px solid var(--hs-border);
    border-radius: 16px;
    padding: 28px;
}}

.hero-label {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: var(--hs-green-bg);
    color: var(--hs-green);
    border-radius: 999px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 750;
    text-transform: uppercase;
    letter-spacing: .04em;
}}

.hero h1 {{
    margin: 18px 0 8px;
    font-size: 30px;
    line-height: 1.2;
    color: var(--hs-navy);
}}

.trial-id {{
    color: var(--hs-muted);
    font-size: 14px;
}}

.grid {{
    display: grid;
    grid-template-columns: 1.4fr .8fr;
    gap: 20px;
    margin-top: 20px;
}}

.card {{
    background: var(--hs-white);
    border: 1px solid var(--hs-border);
    border-radius: 14px;
    padding: 24px;
}}

.card h2 {{
    margin: 0 0 18px;
    font-size: 19px;
    color: var(--hs-navy);
}}

.card h3 {{
    margin: 24px 0 10px;
    font-size: 15px;
    color: var(--hs-navy);
}}

.summary-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
}}

.summary-item {{
    padding: 14px;
    border: 1px solid var(--hs-border);
    border-radius: 10px;
    background: #fbfcfe;
}}

.summary-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .05em;
    color: var(--hs-muted);
    font-weight: 700;
    margin-bottom: 5px;
}}

.summary-value {{
    font-size: 14px;
    line-height: 1.4;
}}

.criterion-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    padding: 14px 0;
    border-bottom: 1px solid #edf1f5;
}}

.criterion-row:last-child {{
    border-bottom: none;
}}

.criterion-text {{
    font-size: 14px;
    line-height: 1.4;
}}

.status {{
    display: inline-flex;
    padding: 5px 9px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 800;
    white-space: nowrap;
}}

.status-met {{
    color: var(--hs-green);
    background: var(--hs-green-bg);
}}

.status-not-met {{
    color: var(--hs-red);
    background: var(--hs-red-bg);
}}

.status-unknown {{
    color: var(--hs-yellow);
    background: var(--hs-yellow-bg);
}}

.notice {{
    background: #eef5ff;
    border: 1px solid #c9dcff;
    border-radius: 10px;
    padding: 14px 16px;
    color: #174ea6;
    font-size: 13px;
    line-height: 1.5;
}}

.referral-panel {{
    margin-top: 20px;
    background: var(--hs-navy);
    color: white;
    border-radius: 16px;
    padding: 26px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
}}

.referral-panel h2 {{
    color: white;
    margin: 0 0 7px;
}}

.referral-panel p {{
    color: #d9e2ec;
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
}}

.primary-button {{
    border: none;
    border-radius: 9px;
    padding: 13px 20px;
    background: var(--hs-blue);
    color: white;
    font-size: 14px;
    font-weight: 750;
    cursor: pointer;
    text-decoration: none;
    white-space: nowrap;
}}

.primary-button:hover {{
    background: var(--hs-blue-dark);
}}

.secondary-button {{
    border: 1px solid var(--hs-border);
    border-radius: 9px;
    padding: 12px 18px;
    background: white;
    color: var(--hs-text);
    font-size: 14px;
    font-weight: 650;
    cursor: pointer;
}}

.modal {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(16, 42, 67, .45);
    z-index: 100;
    align-items: center;
    justify-content: center;
    padding: 20px;
}}

.modal-content {{
    width: 100%;
    max-width: 540px;
    background: white;
    border-radius: 16px;
    padding: 26px;
    box-shadow: 0 20px 60px rgba(0,0,0,.2);
}}

.modal-content h2 {{
    margin-top: 0;
    color: var(--hs-navy);
}}

.form-row {{
    margin-bottom: 14px;
}}

.form-row label {{
    display: block;
    font-size: 12px;
    font-weight: 700;
    color: var(--hs-muted);
    margin-bottom: 6px;
}}

.form-row input {{
    width: 100%;
    padding: 11px 12px;
    border: 1px solid var(--hs-border);
    border-radius: 8px;
    font-size: 14px;
}}

.modal-actions {{
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 22px;
}}

.footer {{
    max-width: 1120px;
    margin: 0 auto;
    padding: 0 24px 40px;
    color: var(--hs-muted);
    font-size: 12px;
    text-align: center;
}}

.empty-state {{
    color: var(--hs-muted);
    font-size: 13px;
    padding: 14px 0;
}}

@media (max-width: 800px) {{

    .grid {{
        grid-template-columns: 1fr;
    }}

    .summary-grid {{
        grid-template-columns: 1fr;
    }}

    .referral-panel {{
        flex-direction: column;
        align-items: flex-start;
    }}

    .hero h1 {{
        font-size: 24px;
    }}

    .container {{
        padding: 20px 16px 40px;
    }}

}}

</style>

</head>

<body>

<header class="header">

    <div class="header-inner">

        <div class="brand">

            <div class="logo">
                H
            </div>

            <div>

                <div class="brand-name">
                    HeLaSync
                </div>

                <div class="brand-subtitle">
                    Clinical Trial Intelligence
                </div>

            </div>

        </div>

        <div class="brand-subtitle">
            Clinician Smart App
        </div>

    </div>

</header>


<main class="container">

    <a
        class="back-link"
        href="javascript:history.back()"
    >
        ← Return to EHR
    </a>


    <section class="hero">

        <div class="hero-label">
            ● Potential Clinical Trial Match
        </div>

        <h1>
            {esc(title)}
        </h1>

        <div class="trial-id">
            {esc(trial_id)}
        </div>

    </section>


    <div class="grid">


        <!-- ==================================================
             TRIAL OVERVIEW
             ================================================== -->

        <section class="card">

            <h2>
                Trial Overview
            </h2>

            <div class="summary-grid">

                <div class="summary-item">

                    <div class="summary-label">
                        Study Phase
                    </div>

                    <div class="summary-value">
                        {esc(phase)}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Recruitment Status
                    </div>

                    <div class="summary-value">
                        {esc(status)}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Intervention
                    </div>

                    <div class="summary-value">
                        {esc(intervention)}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Disease Population
                    </div>

                    <div class="summary-value">
                        {esc(disease_population)}
                    </div>

                </div>

            </div>


            <h3>
                Study Objective
            </h3>

            <div class="summary-value">
                {esc(objective)}
            </div>

            {
                f'''
                <h3>
                    Official Study Title
                </h3>

                <div class="summary-value">
                    {esc(official_title)}
                </div>
                '''
                if official_title
                else ""
            }

        </section>


        <!-- ==================================================
             PATIENT CONTEXT
             ================================================== -->

        <section class="card">

            <h2>
                Patient Context
            </h2>

            <div class="summary-item">

                <div class="summary-label">
                    Patient
                </div>

                <div class="summary-value">
                    {esc(patient_id)}
                </div>

            </div>

            <br>

            <div class="summary-item">

                <div class="summary-label">
                    Clinician
                </div>

                <div class="summary-value">
                    {esc(clinician_id)}
                </div>

            </div>

            <br>

            <div class="notice">

                This Smart App displays information associated
                with the CDS Hooks trial match. The automated
                assessment is preliminary and does not represent
                enrollment or final eligibility determination.

            </div>

        </section>


    </div>


    <!-- ======================================================
         WHY PATIENT MATCHED
         ====================================================== -->

    <section
        class="card"
        style="margin-top:20px;"
    >

        <h2>
            Why This Patient Matched
        </h2>

        <div class="notice">

            HeLaSync identified this trial because the patient's
            available clinical information aligns with the
            documented trial population and eligibility criteria.

            <br><br>

            <strong>
                HeLaSync does not use a simple percentage score
                to determine eligibility.
            </strong>

            Criteria are reviewed individually and may be
            classified as met, not met, or unknown.

        </div>

    </section>


    <!-- ======================================================
         ELIGIBILITY REVIEW
         ====================================================== -->

    <section
        class="card"
        style="margin-top:20px;"
    >

        <h2>
            Eligibility Review
        </h2>

        <h3>
            Inclusion Criteria
        </h3>

        {inclusion_rows}


        <h3>
            Exclusion Criteria
        </h3>

        {exclusion_rows}

    </section>


    <!-- ======================================================
         STUDY DETAILS
         ====================================================== -->

    <div class="grid">

        <section class="card">

            <h2>
                Study Details
            </h2>

            <div class="summary-grid">

                <div class="summary-item">

                    <div class="summary-label">
                        Principal Investigator
                    </div>

                    <div class="summary-value">
                        {esc(pi_name)}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Study Duration
                    </div>

                    <div class="summary-value">
                        {esc(study_duration)}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Location
                    </div>

                    <div class="summary-value">
                        {location_text}
                    </div>

                </div>


                <div class="summary-item">

                    <div class="summary-label">
                        Reimbursement
                    </div>

                    <div class="summary-value">
                        {esc(reimbursement)}
                    </div>

                </div>

            </div>

        </section>


        <section class="card">

            <h2>
                What Happens Next
            </h2>

            <div class="criterion-row">

                <div class="criterion-text">
                    1. Clinician reviews trial information
                </div>

            </div>

            <div class="criterion-row">

                <div class="criterion-text">
                    2. Clinician discusses the opportunity
                    with the patient
                </div>

            </div>

            <div class="criterion-row">

                <div class="criterion-text">
                    3. Clinician submits referral if appropriate
                </div>

            </div>

            <div class="criterion-row">

                <div class="criterion-text">
                    4. Research team reviews the referral
                </div>

            </div>

        </section>

    </div>


    <!-- ======================================================
         REFERRAL ACTION
         ====================================================== -->

    <section class="referral-panel">

        <div>

            <h2>
                Ready to refer this patient?
            </h2>

            <p>
                Submitting a referral indicates patient interest.
                It does not constitute trial enrollment or final
                eligibility confirmation.
            </p>

        </div>


        <button
            class="primary-button"
            onclick="openReferralModal()"
        >
            Refer Patient
        </button>

    </section>

</main>


<footer class="footer">

    HeLaSync Clinical Trial Intelligence

    <br>

    Preliminary automated assessment — research team
    verification required.

</footer>


<!-- ========================================================
     REFERRAL MODAL
     ======================================================== -->

<div
    id="referralModal"
    class="modal"
>

    <div class="modal-content">

        <h2>
            Confirm Patient Referral
        </h2>

        <p>
            You are referring this patient to:
        </p>

        <div class="summary-item">

            <strong>
                {esc(title)}
            </strong>

            <br>

            <span class="trial-id">
                {esc(trial_id)}
            </span>

        </div>

        <br>

        <div class="notice">

            By submitting, you are indicating that the patient
            is interested in learning more about the study.

            <br><br>

            This action does not enroll the patient or establish
            final trial eligibility.

        </div>


        <form
            method="post"
            action="/referrals/from-cds"
        >

            <input
                type="hidden"
                name="trial_id"
                value="{esc(trial_id)}"
            >

            <input
                type="hidden"
                name="patient_id"
                value="{esc(patient_id)}"
            >

            <input
                type="hidden"
                name="clinician_id"
                value="{esc(clinician_id)}"
            >

            <input
                type="hidden"
                name="encounter_id"
                value="{esc(encounter_id)}"
            >

            <input
                type="hidden"
                name="hook_instance"
                value="{esc(hook_instance)}"
            >


            <div class="modal-actions">

                <button
                    type="button"
                    class="secondary-button"
                    onclick="closeReferralModal()"
                >
                    Cancel
                </button>

                <button
                    type="submit"
                    class="primary-button"
                >
                    Submit Referral
                </button>

            </div>

        </form>

    </div>

</div>


<script>

function openReferralModal() {{

    document.getElementById(
        "referralModal"
    ).style.display = "flex";

}}

function closeReferralModal() {{

    document.getElementById(
        "referralModal"
    ).style.display = "none";

}}

window.onclick = function(event) {{

    const modal =
        document.getElementById(
            "referralModal"
        );

    if (event.target === modal) {{

        closeReferralModal();

    }}

}}

</script>

</body>

</html>
"""

    return HTMLResponse(
        content=page
    )


# ============================================================
# REFERRAL SUBMISSION FROM SMART APP
# ============================================================

@router.post(
    "/referrals/from-cds",
    response_class=HTMLResponse,
)
async def referral_from_cds(
    trial_id: str = Form(...),
    patient_id: str = Form(...),
    clinician_id: str = Form(...),
    encounter_id: str = Form(...),
    hook_instance: str = Form(
        default="helasync-smart-app"
    ),
):

    # --------------------------------------------------------
    # Create referral using the existing referral engine.
    # Duplicate protection remains inside referral.py.
    # --------------------------------------------------------

    try:

        referral = create_referral(

            trial_id=trial_id,

            patient_id=patient_id,

            clinician_id=clinician_id,

            encounter_id=encounter_id,

            patient_data={
                "hook_instance": hook_instance,
                "source": "HeLaSync Smart App",
            },

        )

    except TypeError:

        # Compatibility fallback for an earlier version of
        # create_referral() that did not accept patient_data.

        referral = create_referral(

            trial_id=trial_id,

            patient_id=patient_id,

            clinician_id=clinician_id,

            encounter_id=encounter_id,

        )

    except Exception as e:

        return HTMLResponse(
            content=f"""
<!DOCTYPE html>

<html>

<head>

<title>
HeLaSync Referral Error
</title>

<style>

body {{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    background: #f7f9fc;
    padding: 40px;
    color: #243b53;
}}

.box {{
    max-width: 650px;
    margin: 80px auto;
    background: white;
    padding: 32px;
    border-radius: 16px;
    border: 1px solid #d9e2ec;
}}

h1 {{
    color: #102a43;
}}

.error {{
    background: #fef3f2;
    color: #b42318;
    padding: 14px;
    border-radius: 8px;
}}

a {{
    color: #155eef;
    font-weight: 700;
}}

</style>

</head>

<body>

<div class="box">

<h1>
Referral Could Not Be Submitted
</h1>

<div class="error">
{esc(str(e))}
</div>

<br>

<a href="javascript:history.back()">
← Return to Smart App
</a>

</div>

</body>

</html>
""",
            status_code=500,
        )

    # --------------------------------------------------------
    # Determine whether duplicate protection returned an
    # existing referral.
    # --------------------------------------------------------

    duplicate_prevented = bool(
        referral.get(
            "duplicate_prevented",
            False,
        )
    )

    referral_id = referral.get(
        "referral_id",
        "Unknown",
    )

    research_dashboard_url = (
        RESEARCH_DASHBOARD_URL
    )

    status_message = (
        "This patient already has a referral for this "
        "trial. No duplicate referral was created."
        if duplicate_prevented
        else
        "The referral has been created and is now available "
        "to the HeLaSync research workflow."
    )

    return HTMLResponse(
        content=f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
HeLaSync Referral Submitted
</title>

<style>

body {{
    margin: 0;
    background: #f7f9fc;
    color: #243b53;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        sans-serif;
}}

.container {{
    max-width: 650px;
    margin: 80px auto;
    padding: 24px;
}}

.box {{
    background: white;
    border: 1px solid #d9e2ec;
    border-radius: 18px;
    padding: 36px;
    text-align: center;
}}

.icon {{
    width: 64px;
    height: 64px;
    margin: 0 auto 20px;
    border-radius: 50%;
    background: #e8f7ee;
    color: #16803c;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    font-weight: 800;
}}

h1 {{
    color: #102a43;
    margin-bottom: 10px;
}}

.referral-id {{
    display: inline-block;
    margin: 20px 0;
    padding: 12px 18px;
    background: #f1f5f9;
    border-radius: 8px;
    font-family: monospace;
    font-weight: 700;
}}

.notice {{
    background: #eef5ff;
    border: 1px solid #c9dcff;
    color: #174ea6;
    padding: 14px;
    border-radius: 9px;
    font-size: 13px;
    line-height: 1.5;
    text-align: left;
}}

.actions {{
    margin-top: 25px;
    display: flex;
    gap: 10px;
    justify-content: center;
    flex-wrap: wrap;
}}

.button {{
    display: inline-block;
    padding: 12px 18px;
    border-radius: 9px;
    text-decoration: none;
    font-weight: 700;
    font-size: 14px;
}}

.primary {{
    background: #155eef;
    color: white;
}}

.secondary {{
    border: 1px solid #d9e2ec;
    color: #243b53;
    background: white;
}}

</style>

</head>

<body>

<div class="container">

<div class="box">

<div class="icon">
✓
</div>

<h1>
Referral Submitted
</h1>

<p>
{esc(status_message)}
</p>

<div class="referral-id">
Referral ID: {esc(referral_id)}
</div>

<div class="notice">

The referral is not an enrollment decision.
The research team must review the referral and perform
the appropriate screening process.

</div>

<div class="actions">

<a
    class="button primary"
    href="{esc(research_dashboard_url)}"
>
    View Research Queue
</a>

<a
    class="button secondary"
    href="javascript:history.back()"
>
    Return to Smart App
</a>

</div>

</div>

</div>

</body>

</html>
"""
    )
