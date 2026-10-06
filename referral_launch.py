from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import urlencode
from pathlib import Path
import json
import html
from datetime import datetime, timezone

from referral import create_referral


router = APIRouter()


# ============================================================
# CONFIGURATION
# ============================================================

TRIAL_DIR = Path(__file__).parent / "Trial_List"

# In-memory storage for "Patient Not Interested" responses.
# This intentionally does NOT create a research referral.
PATIENT_NOT_INTERESTED_RESPONSES = []


# ============================================================
# TRIAL DATA HELPERS
# ============================================================

def load_trials():
    """
    Load all clinical trial JSON files from Trial_List/.
    """
    trials = []

    if not TRIAL_DIR.exists():
        return trials

    for file_path in sorted(TRIAL_DIR.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                trial = json.load(f)

            trials.append(trial)

        except Exception as exc:
            print(f"Could not load trial file {file_path}: {exc}")

    return trials


def get_trial(trial_id: str):
    """
    Find a trial by NCT/trial ID.
    """
    if not trial_id:
        return None

    trial_id = trial_id.strip().upper()

    for trial in load_trials():

        trial_identifier = (
            trial.get("protocolSection", {})
            .get("identificationModule", {})
            .get("nctId")
        )

        if trial_identifier and trial_identifier.upper() == trial_id:
            return trial

        # Also support simpler JSON structures.
        simple_id = (
            trial.get("trial_id")
            or trial.get("trialId")
            or trial.get("nct_id")
            or trial.get("nctId")
            or trial.get("id")
        )

        if simple_id and str(simple_id).upper() == trial_id:
            return trial

    return None


def get_protocol_section(trial):
    return trial.get("protocolSection", {}) if trial else {}


def get_identification(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("identificationModule", {})


def get_status(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("statusModule", {})


def get_conditions(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("conditionsModule", {})


def get_design(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("designModule", {})


def get_intervention(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("armsInterventionsModule", {})


def get_eligibility(trial):
    protocol = get_protocol_section(trial)

    return protocol.get("eligibilityModule", {})


def get_locations(trial):
    protocol = get_protocol_section(trial)

    location_module = protocol.get("contactsLocationsModule", {})

    locations = location_module.get("locations", [])

    if isinstance(locations, list):
        return locations

    return []


# ============================================================
# SAFE VALUE HELPERS
# ============================================================

def first_non_empty(*values, default=""):
    """
    Return the first non-empty value.
    """
    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            if value.strip():
                return value.strip()

        elif value:
            return value

    return default


def as_text(value, default=""):
    """
    Safely convert values into displayable text.
    """
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        return ", ".join(str(v) for v in value)

    return str(value)


def escape(value):
    return html.escape(as_text(value))


# ============================================================
# TRIAL PRESENTATION DATA
# ============================================================

def build_trial_display_data(trial_id, trial):
    """
    Build the information displayed in the Smart App.

    IMPORTANT:
    Trial JSON data is used first.

    If PI, reimbursement, or other fields are not present
    in the synthetic trial JSON, clearly labeled DEMO values
    are used instead.
    """

    identification = get_identification(trial)
    status = get_status(trial)
    conditions = get_conditions(trial)
    design = get_design(trial)
    interventions = get_intervention(trial)
    eligibility = get_eligibility(trial)
    locations = get_locations(trial)

    # --------------------------------------------------------
    # Trial name
    # --------------------------------------------------------

    trial_name = first_non_empty(
        identification.get("briefTitle"),
        identification.get("officialTitle"),
        trial.get("trial_name") if trial else None,
        trial.get("title") if trial else None,
        default=trial_id,
    )

    # --------------------------------------------------------
    # Official title
    # --------------------------------------------------------

    official_title = first_non_empty(
        identification.get("officialTitle"),
        trial.get("official_title") if trial else None,
        default=trial_name,
    )

    # --------------------------------------------------------
    # Trial status
    # --------------------------------------------------------

    trial_status = first_non_empty(
        status.get("overallStatus"),
        trial.get("status") if trial else None,
        default="RECRUITING",
    )

    # --------------------------------------------------------
    # Disease population
    # --------------------------------------------------------

    condition_list = conditions.get("conditions", [])

    if not isinstance(condition_list, list):
        condition_list = []

    disease_population = first_non_empty(
        ", ".join(str(x) for x in condition_list),
        trial.get("disease_population") if trial else None,
        trial.get("population") if trial else None,
        default="Clinical trial population defined by protocol.",
    )

    # --------------------------------------------------------
    # Study objective / summary
    # --------------------------------------------------------

    study_summary = first_non_empty(
        trial.get("study_summary") if trial else None,
        trial.get("summary") if trial else None,
        trial.get("description") if trial else None,
        default=(
            "This study is evaluating an investigational treatment "
            "and its potential effect on patients with the conditions "
            "specified in the study protocol."
        ),
    )

    study_objective = first_non_empty(
        trial.get("study_objective") if trial else None,
        trial.get("objective") if trial else None,
        trial.get("primary_purpose") if trial else None,
        default=(
            "The goal of this study is to evaluate the safety, "
            "effectiveness, and clinical outcomes associated with "
            "the study intervention in the eligible patient population."
        ),
    )

    # --------------------------------------------------------
    # PI
    # --------------------------------------------------------

    pi_name = first_non_empty(
        trial.get("principal_investigator") if trial else None,
        trial.get("pi_name") if trial else None,
        trial.get("principalInvestigator") if trial else None,
        trial.get("investigator") if trial else None,
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

    # --------------------------------------------------------
    # Intervention
    # --------------------------------------------------------

    intervention_names = []

    interventions_list = interventions.get("interventions", [])

    if isinstance(interventions_list, list):

        for intervention in interventions_list:

            if isinstance(intervention, dict):

                name = first_non_empty(
                    intervention.get("name"),
                    intervention.get("interventionName"),
                )

                if name:
                    intervention_names.append(name)

    intervention = first_non_empty(
        ", ".join(intervention_names),
        trial.get("intervention") if trial else None,
        trial.get("intervention_name") if trial else None,
        default="Investigational study intervention",
    )

    # --------------------------------------------------------
    # Study duration
    # --------------------------------------------------------

    study_duration = first_non_empty(
        trial.get("study_duration") if trial else None,
        trial.get("duration") if trial else None,
        design.get("studyDuration"),
        default="Approximately 12–24 months",
    )

    # --------------------------------------------------------
    # Reimbursement
    # --------------------------------------------------------

    reimbursement = first_non_empty(
        trial.get("reimbursement") if trial else None,
        trial.get("participant_reimbursement") if trial else None,
        trial.get("compensation") if trial else None,
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
    # Inclusion criteria
    # --------------------------------------------------------

    inclusion_criteria = []

    eligibility_text = eligibility.get("eligibilityCriteria", "")

    # First try structured eligibility criteria.
    structured_inclusion = eligibility.get("inclusionCriteria")

    if isinstance(structured_inclusion, list):

        inclusion_criteria = [
            str(item)
            for item in structured_inclusion
            if item
        ]

    # Fallback to parsing our synthetic eligibility text.
    if not inclusion_criteria and eligibility_text:

        lines = str(eligibility_text).splitlines()

        for line in lines:

            cleaned = line.strip()

            if not cleaned:
                continue

            lower = cleaned.lower()

            if (
                "inclusion" in lower
                or "age >=" in lower
                or "age ≥" in lower
                or "heart failure" in lower
                or "diabetes" in lower
                or "amyloidosis" in lower
                or "nt-probnp" in lower
                or "hba1c" in lower
            ):
                inclusion_criteria.append(cleaned)

    if not inclusion_criteria:

        inclusion_criteria = [
            "Patient must meet the age requirement specified by the protocol.",
            "Patient must have the protocol-defined disease condition.",
            "Additional laboratory or clinical criteria may apply.",
        ]

    # --------------------------------------------------------
    # Exclusion criteria
    # --------------------------------------------------------

    exclusion_criteria = []

    structured_exclusion = eligibility.get("exclusionCriteria")

    if isinstance(structured_exclusion, list):

        exclusion_criteria = [
            str(item)
            for item in structured_exclusion
            if item
        ]

    if not exclusion_criteria and eligibility_text:

        lines = str(eligibility_text).splitlines()

        for line in lines:

            cleaned = line.strip()

            if not cleaned:
                continue

            lower = cleaned.lower()

            if (
                "exclusion" in lower
                or "pregnan" in lower
                or "egfr <" in lower
                or "heart failure" in lower
            ):
                exclusion_criteria.append(cleaned)

    if not exclusion_criteria:

        exclusion_criteria = [
            "Patients meeting protocol-defined exclusion criteria are not eligible.",
            "Additional safety exclusions may apply.",
        ]

    # --------------------------------------------------------
    # Locations
    # --------------------------------------------------------

    location_display = []

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

        pieces = [
            x for x in [facility, city, state, country]
            if x
        ]

        if pieces:
            location_display.append(", ".join(pieces))

    if not location_display:

        location_display = [
            "Participating research site — location to be confirmed"
        ]

    return {
        "trial_id": trial_id,
        "trial_name": trial_name,
        "official_title": official_title,
        "status": trial_status,
        "pi_name": pi_name,
        "pi_demo": pi_demo,
        "study_summary": study_summary,
        "study_objective": study_objective,
        "disease_population": disease_population,
        "intervention": intervention,
        "study_duration": study_duration,
        "reimbursement": reimbursement,
        "reimbursement_demo": reimbursement_demo,
        "inclusion_criteria": inclusion_criteria,
        "exclusion_criteria": exclusion_criteria,
        "locations": location_display,
    }


# ============================================================
# DEMO ELIGIBILITY
# ============================================================

def build_demo_eligibility(trial_id):
    """
    Demo eligibility display for the current prototype.

    This is intentionally labeled as prototype/demo data.
    Agent 4 should become the source of truth in the next
    implementation stage.
    """

    trial_id = (trial_id or "").upper()

    if trial_id == "NCTFAKE003":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
            },
            {
                "criterion": "Heart failure",
                "status": "MET",
                "detail": "Heart failure condition documented.",
            },
            {
                "criterion": "NT-proBNP >300 pg/mL",
                "status": "MET",
                "detail": "NT-proBNP = 1,200 pg/mL.",
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
            },
        ]

    if trial_id == "NCTFAKE002":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
            },
            {
                "criterion": "Heart failure",
                "status": "MET",
                "detail": "Heart failure condition documented.",
            },
            {
                "criterion": "Confirmed cardiac amyloidosis",
                "status": "UNKNOWN",
                "detail": "No confirmed cardiac amyloidosis documented.",
            },
            {
                "criterion": "NT-proBNP >300 pg/mL",
                "status": "MET",
                "detail": "NT-proBNP = 1,200 pg/mL.",
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
            },
        ]

    if trial_id == "NCTFAKE001":

        return [
            {
                "criterion": "Age ≥18",
                "status": "MET",
                "detail": "Patient is 65 years old.",
            },
            {
                "criterion": "Type 2 diabetes",
                "status": "UNKNOWN",
                "detail": "No type 2 diabetes diagnosis documented.",
            },
            {
                "criterion": "HbA1c 6.5–8.0%",
                "status": "UNKNOWN",
                "detail": "HbA1c value not available.",
            },
            {
                "criterion": "Heart failure exclusion",
                "status": "NOT PRESENT",
                "detail": "No heart failure exclusion identified.",
            },
            {
                "criterion": "Pregnancy",
                "status": "NOT PRESENT",
                "detail": "No pregnancy finding identified.",
            },
            {
                "criterion": "eGFR <30",
                "status": "NOT PRESENT",
                "detail": "eGFR = 65 mL/min/1.73m².",
            },
        ]

    return []


# ============================================================
# PATIENT NOT INTERESTED
# ============================================================

def save_patient_not_interested(
    trial_id,
    patient_id,
    clinician_id,
    encounter_id,
    comment,
):
    """
    Store a clinician's patient-not-interested response.

    IMPORTANT:
    This function DOES NOT create a research referral.
    """

    response = {
        "response_id": (
            f"PNI-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "PATIENT_NOT_INTERESTED",
        "trial_id": trial_id,
        "patient_id": patient_id,
        "clinician_id": clinician_id,
        "encounter_id": encounter_id,
        "comment": comment.strip(),
        "source": "SMART_APP",
    }

    PATIENT_NOT_INTERESTED_RESPONSES.append(response)

    print(
        "Patient Not Interested response saved:",
        response,
    )

    return response


# ============================================================
# HTML HELPERS
# ============================================================

def criteria_html(criteria, kind="include"):

    if kind == "include":
        bullet_class = "include"
    else:
        bullet_class = "exclude"

    output = ""

    for criterion in criteria:

        output += f"""
        <li class="{bullet_class}">
            {escape(criterion)}
        </li>
        """

    return output


def locations_html(locations):

    output = ""

    for location in locations:

        output += f"""
        <div class="location-item">
            <span class="location-icon">📍</span>
            <span>{escape(location)}</span>
        </div>
        """

    return output


def eligibility_html(eligibility):

    if not eligibility:

        return """
        <div class="empty-state">
            Eligibility details are not available in this prototype.
        </div>
        """

    output = ""

    for item in eligibility:

        status = item.get("status", "UNKNOWN")

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

        output += f"""
        <div class="eligibility-row">

            <div class="eligibility-icon {status_class}">
                {icon}
            </div>

            <div class="eligibility-content">

                <div class="eligibility-title">
                    {escape(item.get("criterion"))}
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


# ============================================================
# SMART APP PAGE
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
            <head>
                <title>HeLaSync - Trial Not Found</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        padding: 50px;
                        background: #f5f7fa;
                    }}

                    .error {{
                        max-width: 700px;
                        margin: auto;
                        background: white;
                        padding: 30px;
                        border-radius: 12px;
                        box-shadow: 0 4px 20px rgba(0,0,0,.08);
                    }}
                </style>
            </head>

            <body>

                <div class="error">

                    <h1>Trial Not Found</h1>

                    <p>
                        HeLaSync could not find trial
                        <strong>{escape(trial_id)}</strong>.
                    </p>

                    <p>
                        Please return to the CDS Hooks card and try again.
                    </p>

                </div>

            </body>
            </html>
            """,
            status_code=404,
        )

    display = build_trial_display_data(
        trial_id,
        trial,
    )

    eligibility = build_demo_eligibility(trial_id)

    # --------------------------------------------------------
    # Referral POST URL
    # --------------------------------------------------------

    referral_form_url = "/referrals/from-cds"

    # --------------------------------------------------------
    # Patient Not Interested endpoint
    # --------------------------------------------------------

    not_interested_url = "/patient-feedback/not-interested"

    # --------------------------------------------------------
    # Success message
    # --------------------------------------------------------

    success_message = ""

    if message == "referred":

        success_message = """
        <div class="success-banner">
            <div class="success-icon">✓</div>

            <div>
                <strong>Referral submitted</strong>
                <div>
                    The patient has been added to the HeLaSync research referral queue.
                </div>
            </div>
        </div>
        """

    elif message == "not-interested":

        success_message = """
        <div class="success-banner neutral">
            <div class="success-icon">✓</div>

            <div>
                <strong>Response saved</strong>
                <div>
                    The patient's decision was recorded. No research referral was created.
                </div>
            </div>
        </div>
        """

    # --------------------------------------------------------
    # Demo labels
    # --------------------------------------------------------

    pi_demo_badge = ""

    if display["pi_demo"]:

        pi_demo_badge = """
        <span class="demo-badge">
            DEMO EXAMPLE
        </span>
        """

    reimbursement_demo_badge = ""

    if display["reimbursement_demo"]:

        reimbursement_demo_badge = """
        <span class="demo-badge">
            DEMO EXAMPLE
        </span>
        """

    # --------------------------------------------------------
    # Refer form hidden fields
    # --------------------------------------------------------

    hidden_fields = f"""
        <input
            type="hidden"
            name="trial_id"
            value="{escape(trial_id)}"
        />

        <input
            type="hidden"
            name="patient_id"
            value="{escape(patient_id)}"
        />

        <input
            type="hidden"
            name="clinician_id"
            value="{escape(clinician_id)}"
        />

        <input
            type="hidden"
            name="encounter_id"
            value="{escape(encounter_id)}"
        />

        <input
            type="hidden"
            name="hook_instance"
            value="{escape(hook_instance)}"
        />

        <input
            type="hidden"
            name="source"
            value="CDS_HOOKS"
        />
    """

    # --------------------------------------------------------
    # Patient Not Interested hidden fields
    # --------------------------------------------------------

    not_interested_hidden = f"""
        <input
            type="hidden"
            name="trial_id"
            value="{escape(trial_id)}"
        />

        <input
            type="hidden"
            name="patient_id"
            value="{escape(patient_id)}"
        />

        <input
            type="hidden"
            name="clinician_id"
            value="{escape(clinician_id)}"
        />

        <input
            type="hidden"
            name="encounter_id"
            value="{escape(encounter_id)}"
        />

        <input
            type="hidden"
            name="hook_instance"
            value="{escape(hook_instance)}"
        />
    """

    # ========================================================
    # HTML
    # ========================================================

    page = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
/>

<title>
    HeLaSync Clinical Trial Information
</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Arial,
        sans-serif;

    background: #f4f7fb;
    color: #172033;
}}

.header {{
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 18px 32px;

    display: flex;
    justify-content: space-between;
    align-items: center;
}}

.brand {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.logo {{
    width: 42px;
    height: 42px;
    border-radius: 10px;

    background: #173f5f;
    color: white;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
    font-size: 18px;
}}

.brand-title {{
    font-weight: 800;
    font-size: 20px;
}}

.brand-subtitle {{
    color: #64748b;
    font-size: 12px;
}}

.header-badge {{
    background: #eef6ff;
    color: #1769aa;
    border: 1px solid #cce5ff;
    padding: 7px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
}}

.container {{
    max-width: 1120px;
    margin: 0 auto;
    padding: 32px 22px 60px;
}}

.hero {{
    margin-bottom: 24px;
}}

.hero-label {{
    color: #1769aa;
    font-size: 13px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 8px;
}}

.hero h1 {{
    margin: 0 0 8px;
    font-size: 32px;
    line-height: 1.2;
}}

.hero p {{
    color: #64748b;
    margin: 0;
}}

.card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;

    box-shadow:
        0 3px 12px rgba(15, 23, 42, .04);
}}

.card-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
    margin-bottom: 20px;
}}

.card-title {{
    font-size: 19px;
    font-weight: 800;
    margin: 0;
}}

.card-subtitle {{
    color: #64748b;
    font-size: 13px;
    margin-top: 5px;
}}

.status {{
    background: #ecfdf3;
    color: #15803d;
    border: 1px solid #bbf7d0;
    border-radius: 20px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 800;
}}

.grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
}}

.grid-three {{
    display: grid;
    grid-template-columns:
        repeat(3, minmax(0, 1fr));
    gap: 18px;
}}

.info-box {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px;
}}

.info-label {{
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: .04em;
}}

.info-value {{
    font-size: 15px;
    font-weight: 650;
    line-height: 1.45;
}}

.demo-badge {{
    display: inline-block;
    margin-left: 7px;
    background: #fff7ed;
    color: #c2410c;
    border: 1px solid #fed7aa;
    border-radius: 12px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 800;
    vertical-align: middle;
}}

.section-text {{
    color: #475569;
    line-height: 1.65;
    font-size: 14px;
}}

.criteria-list {{
    margin: 0;
    padding-left: 0;
    list-style: none;
}}

.criteria-list li {{
    padding: 10px 12px 10px 36px;
    margin-bottom: 8px;
    border-radius: 10px;
    position: relative;
    background: #f8fafc;
    color: #334155;
    line-height: 1.45;
    font-size: 14px;
}}

.criteria-list li::before {{
    position: absolute;
    left: 13px;
    top: 10px;
    font-weight: 900;
}}

.criteria-list li.include::before {{
    content: "✓";
    color: #15803d;
}}

.criteria-list li.exclude::before {{
    content: "!";
    color: #dc2626;
}}

.location-item {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 12px;
    background: #f8fafc;
    border-radius: 10px;
    margin-bottom: 8px;
    color: #334155;
    font-size: 14px;
}}

.location-icon {{
    font-size: 16px;
}}

.eligibility-row {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 15px 0;
    border-bottom: 1px solid #edf2f7;
}}

.eligibility-row:last-child {{
    border-bottom: none;
}}

.eligibility-icon {{
    width: 30px;
    height: 30px;
    border-radius: 50%;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 900;
    flex-shrink: 0;
}}

.eligibility-icon.met,
.eligibility-icon.not-present {{
    background: #dcfce7;
    color: #15803d;
}}

.eligibility-icon.unknown {{
    background: #fef3c7;
    color: #a16207;
}}

.eligibility-icon.blocked {{
    background: #fee2e2;
    color: #b91c1c;
}}

.eligibility-content {{
    flex: 1;
}}

.eligibility-title {{
    font-weight: 750;
    font-size: 14px;
}}

.eligibility-detail {{
    color: #64748b;
    font-size: 12px;
    margin-top: 3px;
}}

.eligibility-status {{
    font-size: 11px;
    font-weight: 800;
    border-radius: 15px;
    padding: 5px 9px;
}}

.eligibility-status.met,
.eligibility-status.not-present {{
    color: #15803d;
    background: #f0fdf4;
}}

.eligibility-status.unknown {{
    color: #a16207;
    background: #fffbeb;
}}

.eligibility-status.blocked {{
    color: #b91c1c;
    background: #fef2f2;
}}

.actions {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
}}

button,
.button {{
    border: none;
    border-radius: 10px;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: 800;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}}

.primary {{
    background: #1769aa;
    color: white;
}}

.primary:hover {{
    background: #12578e;
}}

.secondary {{
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
}}

.secondary:hover {{
    background: #f8fafc;
}}

.danger {{
    background: #ffffff;
    color: #b91c1c;
    border: 1px solid #fecaca;
}}

.danger:hover {{
    background: #fff7f7;
}}

.success-banner {{
    display: flex;
    align-items: center;
    gap: 13px;

    background: #ecfdf3;
    border: 1px solid #bbf7d0;
    color: #166534;

    padding: 15px 18px;
    border-radius: 12px;

    margin-bottom: 20px;
}}

.success-banner.neutral {{
    background: #eff6ff;
    border-color: #bfdbfe;
    color: #1e40af;
}}

.success-icon {{
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: white;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 900;
}}

.next-step {{
    display: flex;
    gap: 14px;
    align-items: flex-start;
}}

.step-number {{
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: #e0f2fe;
    color: #0369a1;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 900;
    flex-shrink: 0;
}}

.step-text {{
    color: #475569;
    line-height: 1.55;
    font-size: 14px;
}}

.modal {{
    display: none;
    position: fixed;
    inset: 0;

    background: rgba(15, 23, 42, .55);

    align-items: center;
    justify-content: center;

    padding: 20px;

    z-index: 1000;
}}

.modal.open {{
    display: flex;
}}

.modal-card {{
    background: white;
    border-radius: 16px;
    width: min(600px, 100%);
    padding: 26px;

    box-shadow:
        0 20px 60px rgba(0,0,0,.2);
}}

.modal-title {{
    font-size: 21px;
    font-weight: 800;
    margin-bottom: 7px;
}}

.modal-description {{
    color: #64748b;
    font-size: 14px;
    line-height: 1.55;
    margin-bottom: 20px;
}}

textarea {{
    width: 100%;
    min-height: 130px;
    resize: vertical;

    border: 1px solid #cbd5e1;
    border-radius: 10px;

    padding: 12px;

    font-family: inherit;
    font-size: 14px;
}}

textarea:focus {{
    outline: none;
    border-color: #1769aa;
    box-shadow: 0 0 0 3px rgba(23,105,170,.1);
}}

.form-actions {{
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 15px;
}}

.warning {{
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 12px;
    padding: 14px 16px;

    color: #9a3412;
    font-size: 12px;
    line-height: 1.55;
}}

.footer {{
    text-align: center;
    color: #94a3b8;
    font-size: 11px;
    padding: 25px 0;
}}

.empty-state {{
    color: #64748b;
    padding: 20px;
    text-align: center;
    background: #f8fafc;
    border-radius: 10px;
}}

@media (max-width: 800px) {{

    .grid,
    .grid-three {{
        grid-template-columns: 1fr;
    }}

    .header {{
        padding: 15px 18px;
    }}

    .container {{
        padding: 24px 15px 45px;
    }}

    .hero h1 {{
        font-size: 26px;
    }}

    .card {{
        padding: 18px;
    }}

    .card-header {{
        flex-direction: column;
    }}

    .actions {{
        flex-direction: column;
    }}

    button,
    .button {{
        width: 100%;
    }}

}}

</style>

</head>


<body>


<!-- ===================================================== -->
<!-- HEADER -->
<!-- ===================================================== -->

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
                Clinical Trial Referral Platform
            </div>

        </div>

    </div>


    <div class="header-badge">
        Clinician View
    </div>

</header>


<!-- ===================================================== -->
<!-- MAIN -->
<!-- ===================================================== -->

<main class="container">


    <section class="hero">

        <div class="hero-label">
            Potential Clinical Trial Match
        </div>

        <h1>
            {escape(display["trial_name"])}
        </h1>

        <p>
            Review the study information and determine whether
            the patient should be referred to the research team.
        </p>

    </section>


    {success_message}


    <!-- ================================================= -->
    <!-- TRIAL OVERVIEW -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Trial Overview
                </h2>

                <div class="card-subtitle">
                    {escape(trial_id)}
                </div>

            </div>

            <div class="status">
                {escape(display["status"])}
            </div>

        </div>


        <div class="grid">

            <div class="info-box">

                <div class="info-label">
                    Trial Name
                </div>

                <div class="info-value">
                    {escape(display["trial_name"])}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Principal Investigator
                </div>

                <div class="info-value">

                    {escape(display["pi_name"])}

                    {pi_demo_badge}

                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Disease Population
                </div>

                <div class="info-value">
                    {escape(display["disease_population"])}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Study Duration
                </div>

                <div class="info-value">
                    {escape(display["study_duration"])}
                </div>

            </div>

        </div>

    </section>


    <!-- ================================================= -->
    <!-- STUDY SNAPSHOT -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Study Snapshot
                </h2>

                <div class="card-subtitle">
                    High-level information for clinician review
                </div>

            </div>

        </div>


        <p class="section-text">

            {escape(display["study_summary"])}

        </p>

    </section>


    <!-- ================================================= -->
    <!-- STUDY GOALS -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Goals & Objective
                </h2>

                <div class="card-subtitle">
                    What the study is designed to evaluate
                </div>

            </div>

        </div>


        <p class="section-text">

            {escape(display["study_objective"])}

        </p>

    </section>


    <!-- ================================================= -->
    <!-- STUDY DETAILS -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Study Details
                </h2>

            </div>

        </div>


        <div class="grid-three">


            <div class="info-box">

                <div class="info-label">
                    Intervention
                </div>

                <div class="info-value">
                    {escape(display["intervention"])}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Study Duration
                </div>

                <div class="info-value">
                    {escape(display["study_duration"])}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Participant Reimbursement
                </div>

                <div class="info-value">

                    {escape(display["reimbursement"])}

                    {reimbursement_demo_badge}

                </div>

            </div>


        </div>

    </section>


    <!-- ================================================= -->
    <!-- ELIGIBILITY -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Eligibility Review
                </h2>

                <div class="card-subtitle">
                    Prototype eligibility assessment
                </div>

            </div>

        </div>


        <div class="warning">

            <strong>Prototype notice:</strong>

            This eligibility display is currently using
            synthetic/demo patient data. Agent 4 should remain
            the source of truth for production eligibility
            determination.

        </div>


        <div style="height:16px;"></div>


        {eligibility_html(eligibility)}

    </section>


    <!-- ================================================= -->
    <!-- INCLUSION / EXCLUSION -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Protocol Criteria
                </h2>

                <div class="card-subtitle">
                    Key inclusion and exclusion criteria
                </div>

            </div>

        </div>


        <div class="grid">


            <div>

                <h3 style="font-size:15px;">
                    Key Inclusion Criteria
                </h3>

                <ul class="criteria-list">

                    {criteria_html(
                        display["inclusion_criteria"],
                        "include"
                    )}

                </ul>

            </div>


            <div>

                <h3 style="font-size:15px;">
                    Key Exclusion Criteria
                </h3>

                <ul class="criteria-list">

                    {criteria_html(
                        display["exclusion_criteria"],
                        "exclude"
                    )}

                </ul>

            </div>


        </div>

    </section>


    <!-- ================================================= -->
    <!-- LOCATIONS -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Study Locations
                </h2>

                <div class="card-subtitle">
                    Research sites participating in the study
                </div>

            </div>

        </div>


        {locations_html(display["locations"])}

    </section>


    <!-- ================================================= -->
    <!-- PATIENT CONTEXT -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    Patient Context
                </h2>

                <div class="card-subtitle">
                    Information associated with this CDS Hooks launch
                </div>

            </div>

        </div>


        <div class="grid">


            <div class="info-box">

                <div class="info-label">
                    Patient
                </div>

                <div class="info-value">
                    {escape(patient_id or "Not provided")}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Clinician
                </div>

                <div class="info-value">
                    {escape(clinician_id or "Not provided")}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Encounter
                </div>

                <div class="info-value">
                    {escape(encounter_id or "Not provided")}
                </div>

            </div>


            <div class="info-box">

                <div class="info-label">
                    Source
                </div>

                <div class="info-value">
                    CDS Hooks / HeLaSync
                </div>

            </div>


        </div>

    </section>


    <!-- ================================================= -->
    <!-- WHAT HAPPENS NEXT -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
                    What Happens Next?
                </h2>

            </div>

        </div>


        <div class="next-step">

            <div class="step-number">
                1
            </div>

            <div class="step-text">

                <strong>Refer Patient</strong>

                <br>

                If the patient is interested, select
                <strong>Refer Patient</strong> below.

            </div>

        </div>


        <div style="height:15px;"></div>


        <div class="next-step">

            <div class="step-number">
                2
            </div>

            <div class="step-text">

                HeLaSync records the research referral and
                routes the referral to the appropriate
                research team.

            </div>

        </div>


        <div style="height:15px;"></div>


        <div class="next-step">

            <div class="step-number">
                3
            </div>

            <div class="step-text">

                The research team can review the referral
                and proceed with the appropriate screening
                workflow.

            </div>

        </div>


    </section>


    <!-- ================================================= -->
    <!-- ACTIONS -->
    <!-- ================================================= -->

    <section class="card">

        <div class="card-header">

            <div>

                <h2 class="card-title">
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
                action="{referral_form_url}"
                style="display:inline;"
            >

                {hidden_fields}

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


            <!-- CLOSE -->

            <a
                href="/"
                class="button secondary"
            >
                Close
            </a>


        </div>


        <div style="margin-top:15px;">

            <div class="warning">

                <strong>Important:</strong>

                Selecting
                <strong>Patient Not Interested</strong>
                records the patient's decision and clinician
                comment only. It does
                <strong>not</strong>
                create a research referral.

            </div>

        </div>

    </section>


    <!-- ================================================= -->
    <!-- DASHBOARD -->
    <!-- ================================================= -->

    <section class="card">

        <div class="actions">

            <a
                href="/research/referrals"
                class="button secondary"
            >
                Open Research Referral Dashboard
            </a>

        </div>

    </section>


    <!-- ================================================= -->
    <!-- PROTOTYPE NOTICE -->
    <!-- ================================================= -->

    <div class="footer">

        HeLaSync Clinical Trial Matching Prototype

        <br><br>

        This Smart App is a prototype and is not currently
        a production SMART-on-FHIR application.

        <br>

        Clinical trial eligibility should be confirmed
        according to the official study protocol and
        appropriate research-site screening procedures.

    </div>


</main>


<!-- ===================================================== -->
<!-- PATIENT NOT INTERESTED MODAL -->
<!-- ===================================================== -->

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

            This response will be saved for HeLaSync workflow
            and quality-improvement purposes. It will not create
            a research referral.

        </div>


        <form
            method="POST"
            action="{not_interested_url}"
        >

            {not_interested_hidden}


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
            document.getElementById("comment");

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

            if (
                event.target === this
            ) {{
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

    return HTMLResponse(content=page)


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

    This is the ONLY action in this Smart App that creates
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
    Save a Patient Not Interested response.

    IMPORTANT:
    This endpoint DOES NOT call create_referral().
    Therefore it does NOT create a research referral.
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

    save_patient_not_interested(
        trial_id=trial_id.strip().upper(),
        patient_id=patient_id,
        clinician_id=clinician_id,
        encounter_id=encounter_id or hook_instance,
        comment=comment,
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
# OPTIONAL DEBUG ENDPOINT
# ============================================================

@router.get(
    "/patient-feedback/not-interested"
)
async def get_patient_not_interested():

    """
    Prototype-only endpoint allowing the stored
    Patient Not Interested responses to be inspected.

    This is NOT a production endpoint.
    """

    return PATIENT_NOT_INTERESTED_RESPONSES
