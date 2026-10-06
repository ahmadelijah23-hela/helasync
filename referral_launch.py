from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import urlencode
from pathlib import Path
from datetime import datetime, timezone
import html
import json
import uuid

from referral import create_referral


router = APIRouter()


# ============================================================
# CONFIGURATION
# ============================================================

TRIAL_DIR = Path(__file__).parent / "Trial_List"

# Prototype-only storage for Patient Not Interested responses.
# IMPORTANT: This does NOT create a research referral.
PATIENT_NOT_INTERESTED_RESPONSES = []


# ============================================================
# GENERAL HELPERS
# ============================================================

def escape(value):
    if value is None:
        return ""

    if isinstance(value, list):
        value = ", ".join(str(x) for x in value)

    return html.escape(str(value))


def first_non_empty(*values, default=""):
    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            if value.strip():
                return value.strip()

        elif value:
            return value

    return default


def load_trials():
    trials = []

    if not TRIAL_DIR.exists():
        print(f"Trial directory not found: {TRIAL_DIR}")
        return trials

    for file_path in sorted(TRIAL_DIR.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                trials.append(json.load(f))
        except Exception as exc:
            print(f"Could not load trial file {file_path}: {exc}")

    print(f"Loaded {len(trials)} clinical trial files.")

    return trials


def get_trial(trial_id):
    if not trial_id:
        return None

    requested_id = trial_id.strip().upper()

    for trial in load_trials():

        protocol = trial.get("protocolSection", {})

        identification = protocol.get(
            "identificationModule",
            {},
        )

        nct_id = identification.get("nctId")

        if nct_id and str(nct_id).upper() == requested_id:
            return trial

        simple_id = first_non_empty(
            trial.get("trial_id"),
            trial.get("trialId"),
            trial.get("nct_id"),
            trial.get("nctId"),
            trial.get("id"),
        )

        if simple_id and str(simple_id).upper() == requested_id:
            return trial

    return None


def get_protocol(trial):
    return trial.get("protocolSection", {}) if trial else {}


def get_identification(trial):
    return get_protocol(trial).get(
        "identificationModule",
        {},
    )


def get_status_module(trial):
    return get_protocol(trial).get(
        "statusModule",
        {},
    )


def get_conditions_module(trial):
    return get_protocol(trial).get(
        "conditionsModule",
        {},
    )


def get_design_module(trial):
    return get_protocol(trial).get(
        "designModule",
        {},
    )


def get_intervention_module(trial):
    return get_protocol(trial).get(
        "armsInterventionsModule",
        {},
    )


def get_eligibility_module(trial):
    return get_protocol(trial).get(
        "eligibilityModule",
        {},
    )


def get_contacts_locations_module(trial):
    return get_protocol(trial).get(
        "contactsLocationsModule",
        {},
    )


# ============================================================
# TRIAL INFORMATION
# ============================================================

def build_trial_information(trial_id, trial):

    identification = get_identification(trial)
    status_module = get_status_module(trial)
    conditions_module = get_conditions_module(trial)
    design_module = get_design_module(trial)
    intervention_module = get_intervention_module(trial)
    eligibility_module = get_eligibility_module(trial)
    contacts_module = get_contacts_locations_module(trial)

    # --------------------------------------------------------
    # Trial overview
    # --------------------------------------------------------

    trial_name = first_non_empty(
        identification.get("briefTitle"),
        trial.get("trial_name"),
        trial.get("title"),
        default=trial_id,
    )

    official_title = first_non_empty(
        identification.get("officialTitle"),
        trial.get("official_title"),
        default=trial_name,
    )

    trial_status = first_non_empty(
        status_module.get("overallStatus"),
        trial.get("status"),
        default="RECRUITING",
    )

    study_type = first_non_empty(
        design_module.get("studyType"),
        trial.get("study_type"),
        default="Interventional",
    )

    phase = first_non_empty(
        design_module.get("phases"),
        trial.get("phase"),
        default="Not specified",
    )

    if isinstance(phase, list):
        phase = ", ".join(str(x) for x in phase)

    # --------------------------------------------------------
    # Disease population
    # --------------------------------------------------------

    conditions = conditions_module.get(
        "conditions",
        [],
    )

    if not isinstance(conditions, list):
        conditions = []

    disease_population = first_non_empty(
        ", ".join(str(x) for x in conditions),
        trial.get("disease_population"),
        trial.get("population"),
        default="Protocol-defined clinical trial population",
    )

    # --------------------------------------------------------
    # PI
    # --------------------------------------------------------

    pi_name = first_non_empty(
        trial.get("principal_investigator"),
        trial.get("pi_name"),
        trial.get("principalInvestigator"),
        trial.get("investigator"),
        default="Dr. Sarah Mitchell, MD",
    )

    pi_demo = not any(
        trial.get(key)
        for key in [
            "principal_investigator",
            "pi_name",
            "principalInvestigator",
            "investigator",
        ]
    )

    pi_credentials = first_non_empty(
        trial.get("pi_credentials"),
        trial.get("principal_investigator_credentials"),
        default="MD",
    )

    institution = first_non_empty(
        trial.get("research_institution"),
        trial.get("institution"),
        trial.get("sponsor"),
        default="HeLaSync Research Network",
    )

    research_team = first_non_empty(
        trial.get("research_team"),
        default="HeLaSync Heart Failure Research Team",
    )

    research_email = first_non_empty(
        trial.get("research_email"),
        default="research@helasync.org",
    )

    # --------------------------------------------------------
    # Study snapshot
    # --------------------------------------------------------

    study_snapshot = first_non_empty(
        trial.get("study_summary"),
        trial.get("summary"),
        trial.get("description"),
        default=(
            "This study is evaluating an investigational "
            "treatment in patients who meet the clinical "
            "criteria defined by the study protocol."
        ),
    )

    # --------------------------------------------------------
    # Goals / objective
    # --------------------------------------------------------

    study_objective = first_non_empty(
        trial.get("study_objective"),
        trial.get("objective"),
        trial.get("primary_purpose"),
        default=(
            "The goal of this study is to evaluate the safety, "
            "effectiveness, and clinical outcomes associated "
            "with the study intervention."
        ),
    )

    secondary_objectives = first_non_empty(
        trial.get("secondary_objectives"),
        trial.get("secondaryObjectives"),
        default=(
            "Additional study objectives may include evaluating "
            "clinical outcomes, treatment response, and safety."
        ),
    )

    # --------------------------------------------------------
    # Intervention
    # --------------------------------------------------------

    intervention_names = []

    interventions = intervention_module.get(
        "interventions",
        [],
    )

    if isinstance(interventions, list):

        for intervention in interventions:

            if not isinstance(intervention, dict):
                continue

            name = first_non_empty(
                intervention.get("name"),
                intervention.get("interventionName"),
            )

            if name:
                intervention_names.append(name)

    intervention = first_non_empty(
        ", ".join(intervention_names),
        trial.get("intervention"),
        trial.get("intervention_name"),
        default="Investigational study intervention",
    )

    intervention_type = first_non_empty(
        trial.get("intervention_type"),
        default="Investigational intervention",
    )

    treatment_arms = trial.get("treatment_arms")

    if not treatment_arms:
        treatment_arms = [
            "Study intervention arm",
            "Comparator/control arm if applicable",
        ]

    # --------------------------------------------------------
    # Duration
    # --------------------------------------------------------

    study_duration = first_non_empty(
        trial.get("study_duration"),
        trial.get("duration"),
        design_module.get("studyDuration"),
        default="Approximately 12–24 months",
    )

    duration_demo = not any(
        trial.get(key)
        for key in [
            "study_duration",
            "duration",
        ]
    )

    # --------------------------------------------------------
    # Reimbursement
    # --------------------------------------------------------

    reimbursement = first_non_empty(
        trial.get("reimbursement"),
        trial.get("participant_reimbursement"),
        trial.get("compensation"),
        default="Up to $500 total participant reimbursement",
    )

    reimbursement_demo = not any(
        trial.get(key)
        for key in [
            "reimbursement",
            "participant_reimbursement",
            "compensation",
        ]
    )

    # --------------------------------------------------------
    # Procedures
    # --------------------------------------------------------

    procedures = trial.get("study_procedures")

    if not procedures:
        procedures = [
            "Screening and eligibility review",
            "Baseline clinical assessments",
            "Protocol-required laboratory testing",
            "Study treatment/intervention visits",
            "Follow-up assessments",
        ]

    # --------------------------------------------------------
    # Timeline
    # --------------------------------------------------------

    timeline = trial.get("study_timeline")

    if not timeline:
        timeline = [
            {
                "stage": "Screening",
                "description": "Confirm protocol eligibility.",
            },
            {
                "stage": "Enrollment",
                "description": "Complete informed consent and enrollment.",
            },
            {
                "stage": "Treatment",
                "description": "Receive study intervention and complete protocol visits.",
            },
            {
                "stage": "Follow-up",
                "description": "Complete required clinical follow-up assessments.",
            },
            {
                "stage": "Study Completion",
                "description": "Complete final study assessments.",
            },
        ]

    # --------------------------------------------------------
    # Risks
    # --------------------------------------------------------

    risks = trial.get("risks")

    if not risks:
        risks = [
            "Potential risks associated with the investigational intervention.",
            "Potential risks associated with study procedures.",
            "Time and visit requirements associated with participation.",
            "Individual risks should be reviewed with the research team.",
        ]

    # --------------------------------------------------------
    # Benefits
    # --------------------------------------------------------

    benefits = trial.get("potential_benefits")

    if not benefits:
        benefits = [
            "Potential access to an investigational treatment.",
            "Potential contribution to clinical research.",
            "Potential clinical benefit cannot be guaranteed.",
        ]

    # --------------------------------------------------------
    # Locations
    # --------------------------------------------------------

    locations = contacts_module.get(
        "locations",
        [],
    )

    if not isinstance(locations, list):
        locations = []

    formatted_locations = []

    for location in locations:

        if not isinstance(location, dict):
            continue

        facility = first_non_empty(
            location.get("facility"),
            location.get("facilityName"),
        )

        city = location.get("city")
        state = location.get("state")
        country = location.get("country")

        parts = [
            x
            for x in [
                facility,
                city,
                state,
                country,
            ]
            if x
        ]

        if parts:
            formatted_locations.append(
                ", ".join(parts)
            )

    if not formatted_locations:

        formatted_locations = [
            "Participating research site — location to be confirmed"
        ]

    # --------------------------------------------------------
    # Eligibility text
    # --------------------------------------------------------

    eligibility_text = eligibility_module.get(
        "eligibilityCriteria",
        "",
    )

    inclusion = eligibility_module.get(
        "inclusionCriteria"
    )

    exclusion = eligibility_module.get(
        "exclusionCriteria"
    )

    if not isinstance(inclusion, list):
        inclusion = []

    if not isinstance(exclusion, list):
        exclusion = []

    # If structured criteria aren't available,
    # preserve the protocol text for display.
    if not inclusion and not exclusion and eligibility_text:

        lines = [
            line.strip()
            for line in str(
                eligibility_text
            ).splitlines()
            if line.strip()
        ]

        for line in lines:

            lower = line.lower()

            if (
                "exclude" in lower
                or "pregnan" in lower
                or "egfr <" in lower
            ):
                exclusion.append(line)

            else:
                inclusion.append(line)

    if not inclusion:

        inclusion = [
            "Patient must meet the protocol-defined age requirement.",
            "Patient must meet the protocol-defined disease criteria.",
            "Additional clinical or laboratory criteria may apply.",
        ]

    if not exclusion:

        exclusion = [
            "Patients meeting protocol-defined exclusion criteria are not eligible.",
            "Additional safety exclusions may apply.",
        ]

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {
        "trial_id": trial_id,
        "trial_name": trial_name,
        "official_title": official_title,
        "status": trial_status,
        "study_type": study_type,
        "phase": phase,
        "pi_name": pi_name,
        "pi_credentials": pi_credentials,
        "pi_demo": pi_demo,
        "institution": institution,
        "research_team": research_team,
        "research_email": research_email,
        "study_snapshot": study_snapshot,
        "study_objective": study_objective,
        "secondary_objectives": secondary_objectives,
        "disease_population": disease_population,
        "intervention": intervention,
        "intervention_type": intervention_type,
        "treatment_arms": treatment_arms,
        "study_duration": study_duration,
        "duration_demo": duration_demo,
        "reimbursement": reimbursement,
        "reimbursement_demo": reimbursement_demo,
        "procedures": procedures,
        "timeline": timeline,
        "risks": risks,
        "benefits": benefits,
        "locations": formatted_locations,
        "inclusion": inclusion,
        "exclusion": exclusion,
        "eligibility_text": eligibility_text,
    }


# ============================================================
# DEMO PATIENT-SPECIFIC ELIGIBILITY
# ============================================================

def build_demo_eligibility(trial_id):

    trial_id = (trial_id or "").upper()

    if trial_id == "NCTFAKE003":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
                "gating": True,
            },
            {
                "criterion": "Heart failure",
                "status": "MET",
                "detail": "Heart failure condition documented.",
                "gating": True,
            },
            {
                "criterion": "NT-proBNP >300 pg/mL",
                "status": "MET",
                "detail": "NT-proBNP = 1,200 pg/mL.",
                "gating": False,
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
                "gating": False,
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
                "gating": False,
            },
        ]

    if trial_id == "NCTFAKE002":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
                "gating": True,
            },
            {
                "criterion": "Heart failure",
                "status": "MET",
                "detail": "Heart failure condition documented.",
                "gating": True,
            },
            {
                "criterion": "Confirmed cardiac amyloidosis",
                "status": "UNKNOWN",
                "detail": "No confirmed cardiac amyloidosis documented.",
                "gating": True,
            },
            {
                "criterion": "NT-proBNP >300 pg/mL",
                "status": "MET",
                "detail": "NT-proBNP = 1,200 pg/mL.",
                "gating": False,
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
                "gating": False,
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
                "gating": False,
            },
        ]

    if trial_id == "NCTFAKE001":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
                "gating": True,
            },
            {
                "criterion": "Type 2 diabetes",
                "status": "UNKNOWN",
                "detail": "No type 2 diabetes diagnosis documented.",
                "gating": True,
            },
            {
                "criterion": "HbA1c 6.5–8.0%",
                "status": "UNKNOWN",
                "detail": "HbA1c value not available.",
                "gating": False,
            },
            {
                "criterion": "Heart failure exclusion",
                "status": "NOT PRESENT",
                "detail": "No heart failure exclusion identified.",
                "gating": False,
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
                "gating": False,
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
                "gating": False,
            },
        ]

    return []


# ============================================================
# WHY THIS PATIENT MATCHED
# ============================================================

def build_match_explanation(trial_id, eligibility):

    trial_id = (trial_id or "").upper()

    met = [
        item
        for item in eligibility
        if item.get("status") == "MET"
    ]

    unknown = [
        item
        for item in eligibility
        if item.get("status") == "UNKNOWN"
    ]

    not_present = [
        item
        for item in eligibility
        if item.get("status") == "NOT PRESENT"
    ]

    gating_unknown = [
        item
        for item in unknown
        if item.get("gating")
    ]

    if trial_id == "NCTFAKE003":

        summary = (
            "HeLaSync identified this study because the patient "
            "has documented heart failure and an NT-proBNP value "
            "above the protocol threshold."
        )

    elif trial_id == "NCTFAKE002":

        summary = (
            "The patient has heart failure and an elevated "
            "NT-proBNP value, but confirmed cardiac amyloidosis "
            "has not been established in the available information."
        )

    elif trial_id == "NCTFAKE001":

        summary = (
            "The patient's available information does not establish "
            "the required type 2 diabetes diagnosis."
        )

    else:

        summary = (
            "HeLaSync identified this study based on the "
            "available patient and protocol information."
        )

    return {
        "summary": summary,
        "met": met,
        "unknown": unknown,
        "not_present": not_present,
        "gating_unknown": gating_unknown,
    }


# ============================================================
# HTML HELPERS
# ============================================================

def render_info_box(label, value, badge=""):

    return f"""
    <div class="info-box">

        <div class="info-label">
            {escape(label)}
        </div>

        <div class="info-value">
            {escape(value)}
            {badge}
        </div>

    </div>
    """


def render_bullet_list(items, style="normal"):

    output = '<div class="bullet-list">'

    for item in items:

        output += f"""
        <div class="bullet-item {style}">
            <span class="bullet-symbol">
                {"!" if style == "exclude" else "•"}
            </span>

            <span>
                {escape(item)}
            </span>
        </div>
        """

    output += "</div>"

    return output


def render_eligibility(eligibility):

    if not eligibility:

        return """
        <div class="empty-state">
            Patient-specific eligibility information is not available.
        </div>
        """

    output = ""

    for item in eligibility:

        status = item.get(
            "status",
            "UNKNOWN",
        )

        if status == "MET":

            status_class = "met"
            icon = "✓"

        elif status == "NOT PRESENT":

            status_class = "not-present"
            icon = "✓"

        elif status == "UNKNOWN":

            status_class = "unknown"
            icon = "?"

        else:

            status_class = "blocked"
            icon = "!"

        gating_badge = ""

        if item.get("gating"):

            gating_badge = """
            <span class="gating-badge">
                CORE CRITERION
            </span>
            """

        output += f"""
        <div class="eligibility-row">

            <div class="eligibility-icon {status_class}">
                {icon}
            </div>

            <div class="eligibility-content">

                <div class="eligibility-title">

                    {escape(item.get("criterion"))}

                    {gating_badge}

                </div>

                <div class="eligibility-detail">
                    {escape(item.get("detail"))}
                </div>

            </div>

            <div class="eligibility-status {status_class}">
                {escape(status)}
            </div>

        </div>
        """

    return output


def render_timeline(timeline):

    output = ""

    for index, item in enumerate(timeline, start=1):

        if isinstance(item, dict):

            stage = first_non_empty(
                item.get("stage"),
                item.get("name"),
                default=f"Step {index}",
            )

            description = first_non_empty(
                item.get("description"),
                default="Study milestone.",
            )

        else:

            stage = f"Step {index}"
            description = str(item)

        output += f"""
        <div class="timeline-item">

            <div class="timeline-number">
                {index}
            </div>

            <div class="timeline-content">

                <div class="timeline-title">
                    {escape(stage)}
                </div>

                <div class="timeline-description">
                    {escape(description)}
                </div>

            </div>

        </div>
        """

    return output


def render_locations(locations):

    output = ""

    for location in locations:

        output += f"""
        <div class="location-item">

            <div class="location-icon">
                📍
            </div>

            <div>
                {escape(location)}
            </div>

        </div>
        """

    return output


def render_procedures(procedures):

    output = ""

    for procedure in procedures:

        output += f"""
        <div class="procedure-item">

            <div class="procedure-check">
                ✓
            </div>

            <div>
                {escape(procedure)}
            </div>

        </div>
        """

    return output


# ============================================================
# SMART APP
# ============================================================

@router.get(
    "/referral-launch",
    response_class=HTMLResponse,
)
async def referral_launch(
    trial_id: str = Query(...),
    patient_id: str = Query(""),
    clinician_id: str = Query(""),
    encounter_id: str = Query(""),
    hook_instance: str = Query(""),
    message: str = Query(""),
):

    trial_id = trial_id.strip().upper()

    trial = get_trial(trial_id)

    if trial is None:

        return HTMLResponse(
            content=f"""
            <html>
            <body style="
                font-family:Arial;
                padding:50px;
                background:#f4f7fb;
            ">

            <div style="
                max-width:700px;
                margin:auto;
                background:white;
                padding:30px;
                border-radius:16px;
            ">

                <h1>Trial Not Found</h1>

                <p>
                    HeLaSync could not find trial
                    <strong>{escape(trial_id)}</strong>.
                </p>

            </div>

            </body>
            </html>
            """,
            status_code=404,
        )

    information = build_trial_information(
        trial_id,
        trial,
    )

    eligibility = build_demo_eligibility(
        trial_id,
    )

    match = build_match_explanation(
        trial_id,
        eligibility,
    )

    # --------------------------------------------------------
    # Demo badges
    # --------------------------------------------------------

    pi_badge = ""

    if information["pi_demo"]:

        pi_badge = """
        <span class="demo-badge">
            DEMO EXAMPLE
        </span>
        """

    reimbursement_badge = ""

    if information["reimbursement_demo"]:

        reimbursement_badge = """
        <span class="demo-badge">
            DEMO EXAMPLE
        </span>
        """

    duration_badge = ""

    if information["duration_demo"]:

        duration_badge = """
        <span class="demo-badge">
            DEMO EXAMPLE
        </span>
        """

    # --------------------------------------------------------
    # Success banner
    # --------------------------------------------------------

    success_banner = ""

    if message == "referred":

        success_banner = """
        <div class="success-banner">

            <div class="success-icon">
                ✓
            </div>

            <div>

                <strong>
                    Research referral submitted
                </strong>

                <div>
                    The patient has been added to the
                    HeLaSync research referral queue.
                </div>

            </div>

        </div>
        """

    elif message == "not-interested":

        success_banner = """
        <div class="success-banner blue">

            <div class="success-icon">
                ✓
            </div>

            <div>

                <strong>
                    Patient decision recorded
                </strong>

                <div>
                    The patient's response was saved.
                    No research referral was created.
                </div>

            </div>

        </div>
        """

    # --------------------------------------------------------
    # Hidden fields
    # --------------------------------------------------------

    referral_hidden_fields = f"""
        <input type="hidden"
            name="trial_id"
            value="{escape(trial_id)}">

        <input type="hidden"
            name="patient_id"
            value="{escape(patient_id)}">

        <input type="hidden"
            name="clinician_id"
            value="{escape(clinician_id)}">

        <input type="hidden"
            name="encounter_id"
            value="{escape(encounter_id)}">

        <input type="hidden"
            name="hook_instance"
            value="{escape(hook_instance)}">

        <input type="hidden"
            name="source"
            value="CDS_HOOKS">
    """

    feedback_hidden_fields = f"""
        <input type="hidden"
            name="trial_id"
            value="{escape(trial_id)}">

        <input type="hidden"
            name="patient_id"
            value="{escape(patient_id)}">

        <input type="hidden"
            name="clinician_id"
            value="{escape(clinician_id)}">

        <input type="hidden"
            name="encounter_id"
            value="{escape(encounter_id)}">

        <input type="hidden"
            name="hook_instance"
            value="{escape(hook_instance)}">
    """

    # ========================================================
    # PAGE
    # ========================================================

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
    HeLaSync | Clinical Trial Information
</title>


<style>

/* ==========================================================
   GLOBAL
   ========================================================== */

* {{
    box-sizing:border-box;
}}

body {{
    margin:0;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Arial,
        sans-serif;

    background:#f4f7fb;
    color:#172033;
}}


/* ==========================================================
   HEADER
   ========================================================== */

.header {{

    background:white;

    border-bottom:
        1px solid #e2e8f0;

    padding:
        17px 32px;

    display:flex;

    justify-content:space-between;

    align-items:center;
}}

.brand {{

    display:flex;

    align-items:center;

    gap:12px;
}}

.logo {{

    width:42px;
    height:42px;

    border-radius:10px;

    background:#173f5f;

    color:white;

    display:flex;

    align-items:center;

    justify-content:center;

    font-weight:800;

    font-size:17px;
}}

.brand-title {{

    font-weight:800;
    font-size:20px;
}}

.brand-subtitle {{

    color:#64748b;

    font-size:12px;

    margin-top:2px;
}}

.header-badge {{

    background:#eef6ff;

    color:#1769aa;

    border:1px solid #cce5ff;

    padding:7px 12px;

    border-radius:20px;

    font-size:12px;

    font-weight:800;
}}


/* ==========================================================
   CONTAINER
   ========================================================== */

.container {{

    max-width:1120px;

    margin:auto;

    padding:
        32px 22px 60px;
}}


/* ==========================================================
   HERO
   ========================================================== */

.hero {{
    margin-bottom:22px;
}}

.hero-label {{

    color:#1769aa;

    font-size:12px;

    font-weight:800;

    text-transform:uppercase;

    letter-spacing:.07em;

    margin-bottom:8px;
}}

.hero h1 {{

    margin:0 0 8px;

    font-size:31px;

    line-height:1.2;
}}

.hero p {{

    margin:0;

    color:#64748b;

    line-height:1.55;
}}


/* ==========================================================
   GENERAL CARD
   ========================================================== */

.card {{

    background:white;

    border:
        1px solid #e2e8f0;

    border-radius:16px;

    padding:24px;

    margin-bottom:20px;

    box-shadow:
        0 3px 12px
        rgba(15,23,42,.04);
}}

.card-header {{

    display:flex;

    justify-content:space-between;

    align-items:flex-start;

    gap:20px;

    margin-bottom:19px;
}}

.card-title {{

    margin:0;

    font-size:19px;

    font-weight:800;
}}

.card-subtitle {{

    color:#64748b;

    font-size:13px;

    margin-top:5px;
}}


/* ==========================================================
   SECTION NUMBER
   ========================================================== */

.section-number {{

    display:inline-flex;

    align-items:center;

    justify-content:center;

    width:28px;
    height:28px;

    border-radius:8px;

    background:#eaf4fb;

    color:#1769aa;

    font-size:12px;

    font-weight:900;

    margin-right:8px;
}}


/* ==========================================================
   STATUS
   ========================================================== */

.status {{

    background:#ecfdf3;

    color:#15803d;

    border:
        1px solid #bbf7d0;

    border-radius:20px;

    padding:6px 12px;

    font-size:11px;

    font-weight:800;
}}


/* ==========================================================
   INFO BOXES
   ========================================================== */

.grid-2 {{

    display:grid;

    grid-template-columns:
        repeat(2,minmax(0,1fr));

    gap:16px;
}}

.grid-3 {{

    display:grid;

    grid-template-columns:
        repeat(3,minmax(0,1fr));

    gap:16px;
}}

.info-box {{

    background:#f8fafc;

    border:
        1px solid #e2e8f0;

    border-radius:12px;

    padding:16px;
}}

.info-label {{

    color:#64748b;

    font-size:10px;

    font-weight:800;

    text-transform:uppercase;

    letter-spacing:.06em;

    margin-bottom:7px;
}}

.info-value {{

    font-size:14px;

    font-weight:650;

    line-height:1.5;

    color:#172033;
}}

.large-info {{

    background:#f8fafc;

    border:
        1px solid #e2e8f0;

    border-radius:12px;

    padding:19px;

    margin-bottom:14px;
}}

.large-info:last-child {{
    margin-bottom:0;
}}

.large-info .info-value {{
    font-weight:500;

    color:#475569;

    line-height:1.7;
}}


/* ==========================================================
   DEMO BADGE
   ========================================================== */

.demo-badge {{

    display:inline-block;

    margin-left:6px;

    background:#fff7ed;

    color:#c2410c;

    border:
        1px solid #fed7aa;

    border-radius:12px;

    padding:2px 7px;

    font-size:9px;

    font-weight:900;

    vertical-align:middle;
}}


/* ==========================================================
   TEXT
   ========================================================== */

.section-text {{

    color:#475569;

    font-size:14px;

    line-height:1.7;

    margin:0;
}}


/* ==========================================================
   BULLET LIST
   ========================================================== */

.bullet-list {{
    display:flex;
    flex-direction:column;
    gap:9px;
}}

.bullet-item {{

    display:flex;

    gap:10px;

    align-items:flex-start;

    padding:11px 12px;

    border-radius:10px;

    background:#f8fafc;

    color:#475569;

    font-size:13px;

    line-height:1.5;
}}

.bullet-symbol {{

    font-weight:900;

    color:#1769aa;
}}

.bullet-item.exclude .bullet-symbol {{
    color:#dc2626;
}}


/* ==========================================================
   ELIGIBILITY
   ========================================================== */

.eligibility-row {{

    display:flex;

    align-items:center;

    gap:13px;

    padding:15px 0;

    border-bottom:
        1px solid #edf2f7;
}}

.eligibility-row:last-child {{
    border-bottom:none;
}}

.eligibility-icon {{

    width:31px;
    height:31px;

    border-radius:50%;

    display:flex;

    align-items:center;

    justify-content:center;

    font-weight:900;

    flex-shrink:0;
}}

.eligibility-icon.met,
.eligibility-icon.not-present {{

    background:#dcfce7;

    color:#15803d;
}}

.eligibility-icon.unknown {{

    background:#fef3c7;

    color:#a16207;
}}

.eligibility-icon.blocked {{

    background:#fee2e2;

    color:#b91c1c;
}}

.eligibility-content {{
    flex:1;
}}

.eligibility-title {{

    font-weight:750;

    font-size:14px;

    color:#172033;
}}

.eligibility-detail {{

    color:#64748b;

    font-size:12px;

    margin-top:3px;

    line-height:1.4;
}}

.eligibility-status {{

    font-size:10px;

    font-weight:900;

    border-radius:15px;

    padding:5px 9px;
}}

.eligibility-status.met,
.eligibility-status.not-present {{

    color:#15803d;

    background:#f0fdf4;
}}

.eligibility-status.unknown {{

    color:#a16207;

    background:#fffbeb;
}}

.eligibility-status.blocked {{

    color:#b91c1c;

    background:#fef2f2;
}}

.gating-badge {{

    display:inline-block;

    margin-left:7px;

    background:#f1f5f9;

    color:#475569;

    border:
        1px solid #cbd5e1;

    border-radius:10px;

    padding:2px 6px;

    font-size:8px;

    font-weight:900;

    vertical-align:middle;
}}


/* ==========================================================
   MATCH
   ========================================================== */

.match-box {{

    background:#eff6ff;

    border:
        1px solid #bfdbfe;

    border-radius:13px;

    padding:18px;
}}

.match-title {{

    color:#1e40af;

    font-weight:800;

    margin-bottom:8px;
}}

.match-text {{

    color:#334155;

    font-size:14px;

    line-height:1.6;
}}

.match-grid {{

    display:grid;

    grid-template-columns:
        repeat(3,minmax(0,1fr));

    gap:10px;

    margin-top:15px;
}}

.match-stat {{

    background:white;

    border:
        1px solid #dbeafe;

    border-radius:10px;

    padding:12px;
}}

.match-stat-number {{

    font-size:20px;

    font-weight:900;
}}

.match-stat-label {{

    color:#64748b;

    font-size:10px;

    margin-top:2px;
}}


/* ==========================================================
   PROCEDURES
   ========================================================== */

.procedure-list {{

    display:flex;

    flex-direction:column;

    gap:9px;
}}

.procedure-item {{

    display:flex;

    gap:11px;

    align-items:center;

    background:#f8fafc;

    border:
        1px solid #e2e8f0;

    border-radius:10px;

    padding:12px;

    color:#475569;

    font-size:13px;
}}

.procedure-check {{

    width:25px;
    height:25px;

    border-radius:50%;

    background:#e0f2fe;

    color:#0369a1;

    display:flex;

    align-items:center;

    justify-content:center;

    font-weight:900;

    flex-shrink:0;
}}


/* ==========================================================
   TIMELINE
   ========================================================== */

.timeline {{

    display:flex;

    flex-direction:column;

    gap:0;
}}

.timeline-item {{

    display:flex;

    gap:15px;

    position:relative;

    padding-bottom:22px;
}}

.timeline-item:not(:last-child)::after {{

    content:"";

    position:absolute;

    left:15px;

    top:31px;

    bottom:0;

    width:2px;

    background:#dbeafe;
}}

.timeline-number {{

    width:31px;
    height:31px;

    border-radius:50%;

    background:#1769aa;

    color:white;

    display:flex;

    align-items:center;

    justify-content:center;

    font-weight:900;

    font-size:12px;

    flex-shrink:0;

    z-index:1;
}}

.timeline-content {{
    padding-top:3px;
}}

.timeline-title {{

    font-weight:800;

    font-size:14px;
}}

.timeline-description {{

    color:#64748b;

    font-size:13px;

    margin-top:4px;

    line-height:1.5;
}}


/* ==========================================================
   LOCATION
   ========================================================== */

.location-item {{

    display:flex;

    gap:11px;

    align-items:flex-start;

    padding:13px;

    background:#f8fafc;

    border:
        1px solid #e2e8f0;

    border-radius:10px;

    margin-bottom:8px;

    color:#475569;

    font-size:13px;
}}

.location-icon {{
    font-size:17px;
}}


/* ==========================================================
   WARNING
   ========================================================== */

.warning {{

    background:#fff7ed;

    border:
        1px solid #fed7aa;

    border-radius:11px;

    padding:13px 15px;

    color:#9a3412;

    font-size:12px;

    line-height:1.55;
}}


/* ==========================================================
   ACTIONS
   ========================================================== */

.actions {{

    display:flex;

    gap:11px;

    flex-wrap:wrap;
}}

button,
.button {{

    border:none;

    border-radius:10px;

    padding:12px 18px;

    font-size:13px;

    font-weight:800;

    cursor:pointer;

    text-decoration:none;

    display:inline-flex;

    align-items:center;

    justify-content:center;
}}

.primary {{

    background:#1769aa;

    color:white;
}}

.primary:hover {{
    background:#12578e;
}}

.secondary {{

    background:white;

    color:#334155;

    border:
        1px solid #cbd5e1;
}}

.secondary:hover {{
    background:#f8fafc;
}}

.danger {{

    background:white;

    color:#b91c1c;

    border:
        1px solid #fecaca;
}}

.danger:hover {{
    background:#fff7f7;
}}


/* ==========================================================
   SUCCESS
   ========================================================== */

.success-banner {{

    display:flex;

    align-items:center;

    gap:13px;

    background:#ecfdf3;

    border:
        1px solid #bbf7d0;

    color:#166534;

    padding:15px 18px;

    border-radius:12px;

    margin-bottom:20px;
}}

.success-banner.blue {{

    background:#eff6ff;

    border-color:#bfdbfe;

    color:#1e40af;
}}

.success-icon {{

    width:30px;
    height:30px;

    border-radius:50%;

    background:white;

    display:flex;

    align-items:center;

    justify-content:center;

    font-weight:900;
}}


/* ==========================================================
   MODAL
   ========================================================== */

.modal {{

    display:none;

    position:fixed;

    inset:0;

    background:
        rgba(15,23,42,.55);

    align-items:center;

    justify-content:center;

    padding:20px;

    z-index:1000;
}}

.modal.open {{
    display:flex;
}}

.modal-card {{

    background:white;

    border-radius:16px;

    width:min(600px,100%);

    padding:26px;

    box-shadow:
        0 20px 60px
        rgba(0,0,0,.2);
}}

.modal-title {{

    font-size:21px;

    font-weight:800;

    margin-bottom:7px;
}}

.modal-description {{

    color:#64748b;

    font-size:14px;

    line-height:1.55;

    margin-bottom:20px;
}}

textarea {{

    width:100%;

    min-height:130px;

    resize:vertical;

    border:
        1px solid #cbd5e1;

    border-radius:10px;

    padding:12px;

    font-family:inherit;

    font-size:14px;
}}

textarea:focus {{

    outline:none;

    border-color:#1769aa;

    box-shadow:
        0 0 0 3px
        rgba(23,105,170,.1);
}}

.form-actions {{

    display:flex;

    justify-content:flex-end;

    gap:10px;

    margin-top:15px;
}}


/* ==========================================================
   FOOTER
   ========================================================== */

.footer {{

    text-align:center;

    color:#94a3b8;

    font-size:11px;

    line-height:1.6;

    padding:25px 0;
}}


/* ==========================================================
   RESPONSIVE
   ========================================================== */

@media(max-width:800px) {{

    .grid-2,
    .grid-3,
    .match-grid {{

        grid-template-columns:1fr;
    }}

    .header {{
        padding:15px 18px;
    }}

    .container {{
        padding:24px 15px 45px;
    }}

    .hero h1 {{
        font-size:26px;
    }}

    .card {{
        padding:18px;
    }}

    .card-header {{
        flex-direction:column;
    }}

    .actions {{
        flex-direction:column;
    }}

    button,
    .button {{
        width:100%;
    }}
}}

</style>

</head>


<body>


<!-- ========================================================
     HEADER
     ======================================================== -->

<header class="header">

    <div class="brand">

        <div class="logo">
            HS
        </div>

        <div>

            <div class="brand-title">
                HeLaSync
            </div>

            <div class="brand-subtitle">
                Clinical Trial Information
            </div>

        </div>

    </div>

    <div class="header-badge">
        Clinician View
    </div>

</header>


<!-- ========================================================
     MAIN
     ======================================================== -->

<main class="container">


    <!-- HERO -->

    <section class="hero">

        <div class="hero-label">
            Potential Clinical Trial Match
        </div>

        <h1>
            {escape(information["trial_name"])}
        </h1>

        <p>
            Review study information, patient-specific eligibility,
            and available next steps.
        </p>

    </section>


    {success_banner}


    <!-- ====================================================
         1. TRIAL OVERVIEW
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">1</span>
                    Trial Overview
                </h2>

                <div class="card-subtitle">
                    Core information about the clinical trial
                </div>

            </div>

            <div class="status">
                {escape(information["status"])}
            </div>

        </div>


        <div class="grid-3">

            {render_info_box(
                "Trial Name",
                information["trial_name"]
            )}

            {render_info_box(
                "Trial ID",
                information["trial_id"]
            )}

            {render_info_box(
                "Study Status",
                information["status"]
            )}

            {render_info_box(
                "Study Type",
                information["study_type"]
            )}

            {render_info_box(
                "Study Phase",
                information["phase"]
            )}

            {render_info_box(
                "Official Study Title",
                information["official_title"]
            )}

        </div>

    </section>


    <!-- ====================================================
         2. PI & RESEARCH SITE
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">2</span>
                    Principal Investigator & Research Site
                </h2>

                <div class="card-subtitle">
                    Research leadership and site information
                </div>

            </div>

        </div>


        <div class="grid-2">

            {render_info_box(
                "Principal Investigator",
                information["pi_name"],
                pi_badge
            )}

            {render_info_box(
                "Credentials",
                information["pi_credentials"]
            )}

            {render_info_box(
                "Research Institution",
                information["institution"]
            )}

            {render_info_box(
                "Research Team",
                information["research_team"]
            )}

            {render_info_box(
                "Research Contact",
                information["research_email"]
            )}

        </div>

    </section>


    <!-- ====================================================
         3. STUDY SNAPSHOT
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">3</span>
                    Study Snapshot
                </h2>

                <div class="card-subtitle">
                    What this study is about
                </div>

            </div>

        </div>


        <div class="large-info">

            <div class="info-label">
                Study Summary
            </div>

            <div class="info-value">
                {escape(information["study_snapshot"])}
            </div>

        </div>

    </section>


    <!-- ====================================================
         4. GOALS
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">4</span>
                    Study Goals & Objectives
                </h2>

                <div class="card-subtitle">
                    What the investigators are trying to determine
                </div>

            </div>

        </div>


        <div class="large-info">

            <div class="info-label">
                Primary Objective
            </div>

            <div class="info-value">
                {escape(information["study_objective"])}
            </div>

        </div>


        <div class="large-info">

            <div class="info-label">
                Additional Objectives
            </div>

            <div class="info-value">
                {escape(information["secondary_objectives"])}
            </div>

        </div>

    </section>


    <!-- ====================================================
         5. DISEASE POPULATION
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">5</span>
                    Disease Population
                </h2>

                <div class="card-subtitle">
                    Conditions and patient population being studied
                </div>

            </div>

        </div>


        <div class="grid-2">

            {render_info_box(
                "Target Disease / Condition",
                information["disease_population"]
            )}

            {render_info_box(
                "Population",
                information["disease_population"]
            )}

        </div>

    </section>


    <!-- ====================================================
         6. INTERVENTION
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">6</span>
                    Intervention / Treatment
                </h2>

                <div class="card-subtitle">
                    Treatment or intervention being evaluated
                </div>

            </div>

        </div>


        <div class="grid-2">

            {render_info_box(
                "Intervention",
                information["intervention"]
            )}

            {render_info_box(
                "Intervention Type",
                information["intervention_type"]
            )}

        </div>


        <div style="height:14px;"></div>


        <div class="info-box">

            <div class="info-label">
                Treatment Arms
            </div>

            {render_bullet_list(
                information["treatment_arms"]
            )}

        </div>

    </section>


    <!-- ====================================================
         7. ELIGIBILITY CRITERIA
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">7</span>
                    Eligibility Criteria
                </h2>

                <div class="card-subtitle">
                    Protocol-defined inclusion and exclusion criteria
                </div>

            </div>

        </div>


        <div class="grid-2">

            <div>

                <h3 style="
                    font-size:15px;
                    margin-top:0;
                ">
                    Key Inclusion Criteria
                </h3>

                {render_bullet_list(
                    information["inclusion"]
                )}

            </div>


            <div>

                <h3 style="
                    font-size:15px;
                    margin-top:0;
                ">
                    Key Exclusion Criteria
                </h3>

                {render_bullet_list(
                    information["exclusion"],
                    "exclude"
                )}

            </div>

        </div>

    </section>


    <!-- ====================================================
         8. PATIENT-SPECIFIC ELIGIBILITY
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">8</span>
                    Patient-Specific Eligibility
                </h2>

                <div class="card-subtitle">
                    Current information available from the patient record
                </div>

            </div>

        </div>


        <div class="warning">

            <strong>Prototype notice:</strong>

            Patient-specific eligibility displayed here is
            currently using synthetic prototype data. Agent 4
            remains the intended source of truth for the
            production eligibility engine.

        </div>


        <div style="height:15px;"></div>


        {render_eligibility(eligibility)}

    </section>


    <!-- ====================================================
         9. WHY THIS PATIENT MATCHED
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">9</span>
                    Why This Patient Matched
                </h2>

                <div class="card-subtitle">
                    Explanation of why HeLaSync surfaced this study
                </div>

            </div>

        </div>


        <div class="match-box">

            <div class="match-title">
                Potential Match Identified
            </div>

            <div class="match-text">
                {escape(match["summary"])}
            </div>


            <div class="match-grid">

                <div class="match-stat">

                    <div class="match-stat-number">
                        {len(match["met"])}
                    </div>

                    <div class="match-stat-label">
                        Criteria currently met
                    </div>

                </div>


                <div class="match-stat">

                    <div class="match-stat-number">
                        {len(match["unknown"])}
                    </div>

                    <div class="match-stat-label">
                        Criteria unknown
                    </div>

                </div>


                <div class="match-stat">

                    <div class="match-stat-number">
                        {len(match["not_present"])}
                    </div>

                    <div class="match-stat-label">
                        Exclusions not identified
                    </div>

                </div>

            </div>

        </div>


        <div style="height:14px;"></div>


        <div class="warning">

            <strong>Important:</strong>

            A potential match is not a determination of
            trial eligibility or enrollment. Final eligibility
            must be confirmed through the study's formal
            research screening process.

        </div>

    </section>


    <!-- ====================================================
         10. STUDY PROCEDURES
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">10</span>
                    Study Procedures
                </h2>

                <div class="card-subtitle">
                    Expected activities during participation
                </div>

            </div>

        </div>


        <div class="procedure-list">

            {render_procedures(
                information["procedures"]
            )}

        </div>

    </section>


    <!-- ====================================================
         11. STUDY TIMELINE
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">11</span>
                    Study Timeline
                </h2>

                <div class="card-subtitle">
                    General study participation workflow
                </div>

            </div>

        </div>


        <div class="grid-2" style="margin-bottom:18px;">

            {render_info_box(
                "Expected Study Duration",
                information["study_duration"],
                duration_badge
            )}

            {render_info_box(
                "Study Type",
                information["study_type"]
            )}

        </div>


        <div class="timeline">

            {render_timeline(
                information["timeline"]
            )}

        </div>

    </section>


    <!-- ====================================================
         12. LOCATIONS
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">12</span>
                    Study Locations
                </h2>

                <div class="card-subtitle">
                    Participating research locations
                </div>

            </div>

        </div>


        {render_locations(
            information["locations"]
        )}

    </section>


    <!-- ====================================================
         13. REIMBURSEMENT
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">13</span>
                    Participant Reimbursement
                </h2>

                <div class="card-subtitle">
                    Compensation information, when available
                </div>

            </div>

        </div>


        <div class="grid-2">

            {render_info_box(
                "Participant Reimbursement",
                information["reimbursement"],
                reimbursement_badge
            )}

            {render_info_box(
                "Reimbursement Information",
                "Final reimbursement details should be confirmed with the research team."
            )}

        </div>

    </section>


    <!-- ====================================================
         14. RISKS
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">14</span>
                    Risks & Considerations
                </h2>

                <div class="card-subtitle">
                    Important considerations before referral
                </div>

            </div>

        </div>


        {render_bullet_list(
            information["risks"],
            "exclude"
        )}

    </section>


    <!-- ====================================================
         15. BENEFITS
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">15</span>
                    Potential Benefits
                </h2>

                <div class="card-subtitle">
                    Potential benefits associated with participation
                </div>

            </div>

        </div>


        {render_bullet_list(
            information["benefits"]
        )}

    </section>


    <!-- ====================================================
         16. WHAT HAPPENS NEXT
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">16</span>
                    What Happens Next
                </h2>

                <div class="card-subtitle">
                    HeLaSync referral workflow
                </div>

            </div>

        </div>


        <div class="timeline">


            <div class="timeline-item">

                <div class="timeline-number">
                    1
                </div>

                <div class="timeline-content">

                    <div class="timeline-title">
                        Clinician refers patient
                    </div>

                    <div class="timeline-description">
                        The clinician selects Refer Patient
                        after discussing the opportunity with
                        the patient.
                    </div>

                </div>

            </div>


            <div class="timeline-item">

                <div class="timeline-number">
                    2
                </div>

                <div class="timeline-content">

                    <div class="timeline-title">
                        HeLaSync records the referral
                    </div>

                    <div class="timeline-description">
                        The referral is added to the HeLaSync
                        research referral workflow.
                    </div>

                </div>

            </div>


            <div class="timeline-item">

                <div class="timeline-number">
                    3
                </div>

                <div class="timeline-content">

                    <div class="timeline-title">
                        Research team reviews
                    </div>

                    <div class="timeline-description">
                        The appropriate research team reviews
                        the referral and available study information.
                    </div>

                </div>

            </div>


            <div class="timeline-item">

                <div class="timeline-number">
                    4
                </div>

                <div class="timeline-content">

                    <div class="timeline-title">
                        Formal research screening
                    </div>

                    <div class="timeline-description">
                        The research team performs formal
                        protocol screening and determines whether
                        the patient can proceed.
                    </div>

                </div>

            </div>


        </div>


        <div class="warning">

            <strong>HeLaSync does not determine enrollment.</strong>

            A HeLaSync potential match or referral does not
            guarantee eligibility, enrollment, or clinical benefit.

        </div>

    </section>


    <!-- ====================================================
         17. PATIENT DECISION
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    <span class="section-number">17</span>
                    Patient Decision
                </h2>

                <div class="card-subtitle">
                    Record the patient's decision regarding research participation
                </div>

            </div>

        </div>


        <div class="actions">


            <!-- REFER PATIENT -->

            <form
                method="POST"
                action="/referrals/from-cds"
                style="display:inline;"
            >

                {referral_hidden_fields}

                <button
                    type="submit"
                    class="primary"
                >
                    Refer Patient
                </button>

            </form>


            <!-- PATIENT NOT INTERESTED -->

            <button
                type="button"
                class="danger"
                onclick="openNotInterested()"
            >
                Patient Not Interested
            </button>


            <a
                href="/research/referrals"
                class="button secondary"
            >
                Research Referral Dashboard
            </a>

        </div>


        <div style="margin-top:15px;">

            <div class="warning">

                <strong>Patient Not Interested:</strong>

                Selecting this option records the patient's
                decision and clinician comment only.

                <strong>
                    It does not create a research referral.
                </strong>

            </div>

        </div>

    </section>


    <!-- ====================================================
         PATIENT CONTEXT
         ==================================================== -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Patient & Launch Context
                </h2>

                <div class="card-subtitle">
                    Context associated with this CDS Hooks launch
                </div>

            </div>

        </div>


        <div class="grid-3">

            {render_info_box(
                "Patient ID",
                patient_id or "Not provided"
            )}

            {render_info_box(
                "Clinician ID",
                clinician_id or "Not provided"
            )}

            {render_info_box(
                "Encounter ID",
                encounter_id or "Not provided"
            )}

            {render_info_box(
                "Hook Instance",
                hook_instance or "Not provided"
            )}

            {render_info_box(
                "Source",
                "CDS Hooks"
            )}

            {render_info_box(
                "Platform",
                "HeLaSync Smart App"
            )}

        </div>

    </section>


    <!-- ====================================================
         PROTOTYPE NOTICE
         ==================================================== -->

    <section class="card">

        <div class="warning">

            <strong>Prototype Notice:</strong>

            This Smart App is a clinical-trial information
            and referral prototype. Some displayed information,
            including certain PI, reimbursement, duration,
            procedure, risk, benefit, and workflow examples,
            may be synthetic demonstration content when those
            fields are not present in the underlying trial JSON.

            Final study information should be confirmed against
            the official study protocol and research site.

        </div>

    </section>


    <div class="footer">

        HeLaSync Clinical Trial Matching Prototype

        <br>

        Potential match ≠ confirmed eligibility ≠ enrollment

        <br><br>

        Clinical trial eligibility should be confirmed through
        the formal research screening process.

    </div>


</main>


<!-- ========================================================
     PATIENT NOT INTERESTED MODAL
     ======================================================== -->

<div
    id="notInterestedModal"
    class="modal"
>

    <div class="modal-card">


        <div class="modal-title">
            Patient Not Interested
        </div>


        <div class="modal-description">

            Please document why the patient was not interested
            in participating in this clinical trial.

            <br><br>

            This response will be recorded separately from the
            research referral workflow.

            <strong>
                No research referral will be created.
            </strong>

        </div>


        <form
            method="POST"
            action="/patient-feedback/not-interested"
        >

            {feedback_hidden_fields}


            <label
                for="comment"
                style="
                    display:block;
                    font-weight:800;
                    font-size:13px;
                    margin-bottom:7px;
                "
            >
                Clinician Comment
            </label>


            <textarea
                id="comment"
                name="comment"
                required
                placeholder="Example: Patient declined because of time commitment..."
            ></textarea>


            <div class="form-actions">


                <button
                    type="button"
                    class="secondary"
                    onclick="closeNotInterested()"
                >
                    Cancel
                </button>


                <button
                    type="submit"
                    class="danger"
                >
                    Save Response
                </button>


            </div>


        </form>

    </div>

</div>


<script>

function openNotInterested() {{

    const modal =
        document.getElementById(
            "notInterestedModal"
        );

    modal.classList.add("open");

    setTimeout(function() {{

        const textarea =
            document.getElementById(
                "comment"
            );

        if (textarea) {{
            textarea.focus();
        }}

    }}, 100);

}}


function closeNotInterested() {{

    const modal =
        document.getElementById(
            "notInterestedModal"
        );

    modal.classList.remove("open");

}}


document
    .getElementById("notInterestedModal")
    .addEventListener(
        "click",
        function(event) {{

            if (event.target === this) {{
                closeNotInterested();
            }}

        }}
    );


document.addEventListener(
    "keydown",
    function(event) {{

        if (event.key === "Escape") {{
            closeNotInterested();
        }}

    }}
);

</script>


</body>

</html>
"""

    return HTMLResponse(
        content=page
    )


# ============================================================
# REFER PATIENT
# ============================================================

@router.post(
    "/referrals/from-cds"
)
async def referral_from_cds(
    trial_id: str = Form(...),
    patient_id: str = Form(...),
    clinician_id: str = Form(""),
    encounter_id: str = Form(""),
    hook_instance: str = Form(""),
    source: str = Form("CDS_HOOKS"),
):

    """
    Create the actual HeLaSync research referral.

    This is the ONLY Smart App action that creates
    a research referral.
    """

    trial_id = trial_id.strip().upper()

    referral = create_referral(
        trial_id=trial_id,
        patient_id=patient_id,
        clinician_id=clinician_id,
        encounter_id=encounter_id or hook_instance,
        source=source,
        patient_data={
            "hook_instance": hook_instance,
            "source": "HeLaSync Smart App",
        },
    )

    params = urlencode(
        {
            "trial_id": trial_id,
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "encounter_id": encounter_id,
            "hook_instance": hook_instance,
            "message": "referred",
        }
    )

    return RedirectResponse(
        url=f"/referral-launch?{params}",
        status_code=303,
    )


# ============================================================
# PATIENT NOT INTERESTED
# ============================================================

@router.post(
    "/patient-feedback/not-interested"
)
async def patient_not_interested(
    trial_id: str = Form(...),
    patient_id: str = Form(""),
    clinician_id: str = Form(""),
    encounter_id: str = Form(""),
    hook_instance: str = Form(""),
    comment: str = Form(...),
):

    """
    Record Patient Not Interested.

    IMPORTANT:
    This function intentionally does NOT call create_referral().
    """

    comment = comment.strip()

    if not comment:

        params = urlencode(
            {
                "trial_id": trial_id,
                "patient_id": patient_id,
                "clinician_id": clinician_id,
                "encounter_id": encounter_id,
                "hook_instance": hook_instance,
            }
        )

        return RedirectResponse(
            url=f"/referral-launch?{params}",
            status_code=303,
        )

    response = {
        "response_id": f"PNI-{uuid.uuid4().hex[:12].upper()}",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": "PATIENT_NOT_INTERESTED",
        "trial_id": trial_id.strip().upper(),
        "patient_id": patient_id,
        "clinician_id": clinician_id,
        "encounter_id": encounter_id or hook_instance,
        "comment": comment,
        "source": "SMART_APP",
    }

    PATIENT_NOT_INTERESTED_RESPONSES.append(
        response
    )

    print(
        "Patient Not Interested response saved:",
        response,
    )

    params = urlencode(
        {
            "trial_id": trial_id,
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "encounter_id": encounter_id,
            "hook_instance": hook_instance,
            "message": "not-interested",
        }
    )

    return RedirectResponse(
        url=f"/referral-launch?{params}",
        status_code=303,
    )


# ============================================================
# PROTOTYPE DEBUG ENDPOINT
# ============================================================

@router.get(
    "/patient-feedback/not-interested"
)
async def get_patient_not_interested():

    """
    Prototype-only endpoint for viewing saved
    Patient Not Interested responses.

    This should not be exposed in production.
    """

    return PATIENT_NOT_INTERESTED_RESPONSES
