from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from html import escape
import json
import uuid

from referral import create_referral


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# CONFIGURATION
# ============================================================

TRIAL_DIR = Path(__file__).resolve().parent / "Trial_List"

# Prototype-only storage.
# This does not survive a Render restart.
PATIENT_NOT_INTERESTED_RESPONSES: List[Dict[str, Any]] = []


# ============================================================
# GENERAL HELPERS
# ============================================================

def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def esc(value: Any, default: str = "") -> str:
    return escape(safe_text(value, default))


def first_non_empty(*values: Any, default: str = "") -> str:
    for value in values:
        text = safe_text(value)

        if text:
            return text

    return default


def normalize_list(value: Any) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def extract_text_list(value: Any) -> List[str]:
    results = []

    for item in normalize_list(value):

        if isinstance(item, str):

            if item.strip():
                results.append(item.strip())

        elif isinstance(item, dict):

            text_value = first_non_empty(
                item.get("text"),
                item.get("description"),
                item.get("name"),
                item.get("label"),
            )

            if text_value:
                results.append(text_value)

    return results


# ============================================================
# LOAD TRIALS
# ============================================================

def load_trials() -> List[Dict[str, Any]]:

    trials = []

    if not TRIAL_DIR.exists():
        return trials

    for path in sorted(TRIAL_DIR.glob("*.json")):

        try:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if isinstance(data, dict):
                trials.append(data)

        except Exception as exc:

            print(
                f"Could not load trial file "
                f"{path.name}: {exc}"
            )

    return trials


def get_protocol(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return trial.get(
        "protocolSection",
        trial
    )


def get_identification(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "identificationModule",
        {}
    )


def get_status_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "statusModule",
        {}
    )


def get_conditions_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "conditionsModule",
        {}
    )


def get_design_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "designModule",
        {}
    )


def get_intervention_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "armsInterventionsModule",
        {}
    )


def get_eligibility_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "eligibilityModule",
        {}
    )


def get_contacts_locations_module(
    trial: Dict[str, Any]
) -> Dict[str, Any]:

    return get_protocol(trial).get(
        "contactsLocationsModule",
        {}
    )


# ============================================================
# FIND TRIAL
# ============================================================

def get_trial(
    trial_id: str
) -> Optional[Dict[str, Any]]:

    requested_id = safe_text(
        trial_id
    ).upper()

    for trial in load_trials():

        identification = get_identification(
            trial
        )

        candidates = [
            identification.get("nctId"),
            identification.get("trialId"),
            trial.get("trial_id"),
            trial.get("nctId"),
            trial.get("id"),
        ]

        for candidate in candidates:

            if (
                safe_text(candidate)
                .upper()
                == requested_id
            ):
                return trial

    return None


# ============================================================
# LOCATIONS
# ============================================================

def parse_locations(
    contacts: Dict[str, Any]
) -> List[str]:

    locations = contacts.get(
        "locations",
        []
    )

    results = []

    for location in normalize_list(
        locations
    ):

        if not isinstance(
            location,
            dict
        ):
            continue

        facility = first_non_empty(
            location.get("facility"),
            location.get("facilityName"),
            location.get("name"),
        )

        city = safe_text(
            location.get("city")
        )

        state = safe_text(
            location.get("state")
        )

        country = safe_text(
            location.get("country")
        )

        parts = [
            part
            for part in [
                facility,
                city,
                state,
                country,
            ]
            if part
        ]

        if parts:
            results.append(
                ", ".join(parts)
            )

    return results


# ============================================================
# ELIGIBILITY PARSER
# ============================================================

def parse_inclusion_exclusion(
    eligibility: Dict[str, Any]
) -> Dict[str, List[str]]:

    inclusion = []
    exclusion = []

    criteria_text = first_non_empty(
        eligibility.get(
            "eligibilityCriteria"
        ),
        eligibility.get(
            "criteria"
        ),
        eligibility.get(
            "eligibility"
        ),
    )

    if criteria_text:

        lines = [
            line.strip()
            for line in criteria_text.splitlines()
            if line.strip()
        ]

        current_category = None

        for line in lines:

            lower = line.lower()

            if (
                "inclusion criteria"
                in lower
            ):
                current_category = "inclusion"
                continue

            if (
                "exclusion criteria"
                in lower
            ):
                current_category = "exclusion"
                continue

            if current_category == "inclusion":
                inclusion.append(line)

            elif current_category == "exclusion":
                exclusion.append(line)

    if not inclusion:

        inclusion = extract_text_list(
            eligibility.get(
                "inclusionCriteria"
            )
        )

    if not exclusion:

        exclusion = extract_text_list(
            eligibility.get(
                "exclusionCriteria"
            )
        )

    return {
        "inclusion":
            list(dict.fromkeys(inclusion)),
        "exclusion":
            list(dict.fromkeys(exclusion)),
    }


# ============================================================
# DEMO PATIENT-SPECIFIC ELIGIBILITY
# ============================================================

def build_demo_eligibility(
    trial_id: str
) -> List[Dict[str, str]]:

    """
    Stage 3A prototype display only.

    Agent 4 remains the eligibility source of truth.
    This section is intentionally labeled as a
    prototype/demo representation.
    """

    trial_id = safe_text(
        trial_id
    ).upper()

    common = [
        {
            "criterion": "Age ≥18",
            "status": "MET",
            "category": "Gating",
            "evidence":
                "Synthetic patient age is 65.",
        }
    ]

    if trial_id == "NCTFAKE003":

        return common + [

            {
                "criterion":
                    "Heart failure",
                "status":
                    "MET",
                "category":
                    "Gating",
                "evidence":
                    "Heart failure is documented.",
            },

            {
                "criterion":
                    "NT-proBNP >300",
                "status":
                    "MET",
                "category":
                    "Secondary",
                "evidence":
                    "NT-proBNP is documented at "
                    "1200 pg/mL.",
            },

            {
                "criterion":
                    "Pregnancy",
                "status":
                    "CLEAR",
                "category":
                    "Exclusion",
                "evidence":
                    "Pregnancy is not present.",
            },

            {
                "criterion":
                    "eGFR <30",
                "status":
                    "CLEAR",
                "category":
                    "Exclusion",
                "evidence":
                    "eGFR is documented at 65.",
            },
        ]

    if trial_id == "NCTFAKE002":

        return common + [

            {
                "criterion":
                    "Heart failure",
                "status":
                    "MET",
                "category":
                    "Gating",
                "evidence":
                    "Heart failure is documented.",
            },

            {
                "criterion":
                    "Confirmed cardiac amyloidosis",
                "status":
                    "BLOCKED",
                "category":
                    "Gating",
                "evidence":
                    "Confirmed cardiac amyloidosis "
                    "is not documented.",
            },

            {
                "criterion":
                    "NT-proBNP >300",
                "status":
                    "MET",
                "category":
                    "Secondary",
                "evidence":
                    "NT-proBNP is documented at "
                    "1200 pg/mL.",
            },

            {
                "criterion":
                    "Pregnancy",
                "status":
                    "CLEAR",
                "category":
                    "Exclusion",
                "evidence":
                    "Pregnancy is not present.",
            },

            {
                "criterion":
                    "eGFR <30",
                "status":
                    "CLEAR",
                "category":
                    "Exclusion",
                "evidence":
                    "eGFR is documented at 65.",
            },
        ]

    if trial_id == "NCTFAKE001":

        return common + [

            {
                "criterion":
                    "Type 2 diabetes",
                "status":
                    "NOT_MET",
                "category":
                    "Gating",
                "evidence":
                    "Type 2 diabetes is not "
                    "documented.",
            },

            {
                "criterion":
                    "HbA1c 6.5–8.0%",
                "status":
                    "UNKNOWN",
                "category":
                    "Secondary",
                "evidence":
                    "HbA1c is not documented.",
            },

            {
                "criterion":
                    "Heart failure exclusion",
                "status":
                    "NOT_MET",
                "category":
                    "Exclusion",
                "evidence":
                    "Heart failure is documented.",
            },
        ]

    return common


# ============================================================
# BUILD TRIAL INFORMATION
# ============================================================

def build_trial_information(
    trial_id: str,
    trial: Dict[str, Any],
) -> Dict[str, Any]:

    identification = (
        get_identification(trial)
    )

    status = (
        get_status_module(trial)
    )

    conditions = (
        get_conditions_module(trial)
    )

    design = (
        get_design_module(trial)
    )

    interventions = (
        get_intervention_module(trial)
    )

    eligibility = (
        get_eligibility_module(trial)
    )

    contacts = (
        get_contacts_locations_module(trial)
    )

    # --------------------------------------------------------
    # TRIAL NAME
    # --------------------------------------------------------

    trial_name = first_non_empty(
        identification.get(
            "briefTitle"
        ),
        trial.get(
            "trial_name"
        ),
        trial.get(
            "title"
        ),
        default=trial_id,
    )

    official_title = first_non_empty(
        identification.get(
            "officialTitle"
        ),
        trial.get(
            "official_title"
        ),
        default=trial_name,
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    study_status = first_non_empty(
        status.get(
            "overallStatus"
        ),
        trial.get(
            "status"
        ),
        default="Information not available",
    )

    study_type = first_non_empty(
        design.get(
            "studyType"
        ),
        trial.get(
            "study_type"
        ),
        default="Information not available",
    )

    phase = first_non_empty(
        *normalize_list(
            design.get(
                "phases"
            )
        ),
        design.get(
            "phase"
        ),
        trial.get(
            "phase"
        ),
        default="Information not available",
    )

    # --------------------------------------------------------
    # DISEASE POPULATION
    # --------------------------------------------------------

    disease_population = (
        conditions.get(
            "conditions",
            []
        )
    )

    if not disease_population:

        disease_population = (
            trial.get(
                "conditions",
                []
            )
        )

    disease_population = (
        extract_text_list(
            disease_population
        )
    )

    if not disease_population:

        disease_population = [
            "Information not available"
        ]

    # --------------------------------------------------------
    # INTERVENTIONS
    # --------------------------------------------------------

    intervention_items = (
        interventions.get(
            "interventions",
            []
        )
    )

    intervention_names = []
    intervention_types = []
    arms = []

    for item in normalize_list(
        intervention_items
    ):

        if not isinstance(
            item,
            dict
        ):
            continue

        name = first_non_empty(
            item.get("name"),
            item.get(
                "interventionName"
            ),
        )

        intervention_type = (
            first_non_empty(
                item.get("type"),
                item.get(
                    "interventionType"
                ),
            )
        )

        description = (
            first_non_empty(
                item.get(
                    "description"
                ),
                item.get(
                    "interventionDescription"
                ),
            )
        )

        if name:
            intervention_names.append(
                name
            )

        if intervention_type:
            intervention_types.append(
                intervention_type
            )

        if description:
            arms.append(
                description
            )

    if not intervention_names:

        fallback = trial.get(
            "intervention"
        )

        if (
            isinstance(
                fallback,
                str
            )
            and fallback.strip()
        ):
            intervention_names = [
                fallback
            ]

    # --------------------------------------------------------
    # PI / RESEARCH SITE
    # --------------------------------------------------------

    overall_officials = (
        contacts.get(
            "overallOfficials",
            []
        )
    )

    central_contacts = (
        contacts.get(
            "centralContacts",
            []
        )
    )

    pi_name = ""

    if overall_officials:

        if isinstance(
            overall_officials[0],
            dict
        ):

            pi_name = first_non_empty(
                overall_officials[0].get(
                    "name"
                ),
                overall_officials[0].get(
                    "officialName"
                ),
            )

    if not pi_name and trial.get(
        "pi_name"
    ):

        pi_name = safe_text(
            trial.get(
                "pi_name"
            )
        )

    pi_demo = not bool(
        pi_name
    )

    if not pi_name:

        pi_name = (
            "Dr. Sarah Mitchell, MD"
        )

    institution = first_non_empty(
        trial.get(
            "institution"
        ),
        trial.get(
            "research_site"
        ),
        default="University Hospital Colorado",
    )

    research_team = first_non_empty(
        trial.get(
            "research_team"
        ),
        default=(
            "HeLaSync Heart Failure "
            "Research Team"
        ),
    )

    research_email = first_non_empty(
        trial.get(
            "research_email"
        ),
        default="research@helasync.org",
    )

    # --------------------------------------------------------
    # OBJECTIVES
    # --------------------------------------------------------

    objectives = extract_text_list(
        trial.get(
            "objectives"
        )
        or trial.get(
            "study_objectives"
        )
    )

    if not objectives:

        objectives = [

            (
                "Evaluate the study intervention "
                "in the defined disease population."
            ),

            (
                "Assess safety and clinical outcomes "
                "during the study period."
            ),
        ]

    # --------------------------------------------------------
    # DURATION
    # --------------------------------------------------------

    duration = first_non_empty(
        trial.get(
            "study_duration"
        ),
        trial.get(
            "duration"
        ),
        default=(
            "Approximately 12–24 months"
        ),
    )

    duration_demo = not bool(
        trial.get(
            "study_duration"
        )
        or trial.get(
            "duration"
        )
    )

    # --------------------------------------------------------
    # REIMBURSEMENT
    # --------------------------------------------------------

    reimbursement = first_non_empty(
        trial.get(
            "reimbursement"
        ),
        trial.get(
            "participant_reimbursement"
        ),
        default=(
            "Up to $500 total "
            "participant reimbursement"
        ),
    )

    reimbursement_demo = not bool(
        trial.get(
            "reimbursement"
        )
        or trial.get(
            "participant_reimbursement"
        )
    )

    # --------------------------------------------------------
    # PROCEDURES
    # --------------------------------------------------------

    procedures = extract_text_list(
        trial.get(
            "procedures"
        )
        or trial.get(
            "study_procedures"
        )
    )

    if not procedures:

        procedures = [

            (
                "Clinical evaluation and review "
                "of medical history."
            ),

            (
                "Study-specific laboratory or "
                "diagnostic assessments as required "
                "by protocol."
            ),

            (
                "Follow-up visits during the "
                "study period."
            ),
        ]

    # --------------------------------------------------------
    # TIMELINE
    # --------------------------------------------------------

    timeline = extract_text_list(
        trial.get(
            "timeline"
        )
        or trial.get(
            "study_timeline"
        )
    )

    if not timeline:

        timeline = [

            "Screening and eligibility review",

            (
                "Study enrollment if eligibility "
                "is confirmed"
            ),

            "Treatment / study participation",

            "Protocol-defined follow-up",
        ]

    # --------------------------------------------------------
    # RISKS
    # --------------------------------------------------------

    risks = extract_text_list(
        trial.get(
            "risks"
        )
        or trial.get(
            "risks_and_considerations"
        )
    )

    if not risks:

        risks = [

            (
                "Study-specific risks should be "
                "reviewed with the research team."
            ),

            (
                "Participation may involve additional "
                "visits, procedures, or testing."
            ),
        ]

    # --------------------------------------------------------
    # BENEFITS
    # --------------------------------------------------------

    benefits = extract_text_list(
        trial.get(
            "benefits"
        )
        or trial.get(
            "potential_benefits"
        )
    )

    if not benefits:

        benefits = [

            (
                "Potential access to the study "
                "intervention or research procedures."
            ),

            "Contribution to clinical research.",
        ]

    # --------------------------------------------------------
    # LOCATIONS
    # --------------------------------------------------------

    locations = parse_locations(
        contacts
    )

    if not locations:

        locations = extract_text_list(
            trial.get(
                "locations"
            )
        )

    if not locations:

        locations = [
            institution
        ]

    # --------------------------------------------------------
    # ELIGIBILITY
    # --------------------------------------------------------

    criteria = (
        parse_inclusion_exclusion(
            eligibility
        )
    )

    return {

        "trial_id":
            trial_id,

        "trial_name":
            trial_name,

        "official_title":
            official_title,

        "status":
            study_status,

        "study_type":
            study_type,

        "phase":
            phase,

        "disease_population":
            disease_population,

        "pi_name":
            pi_name,

        "pi_demo":
            pi_demo,

        "institution":
            institution,

        "research_team":
            research_team,

        "research_email":
            research_email,

        "objectives":
            objectives,

        "interventions":
            intervention_names
            or ["Information not available"],

        "intervention_types":
            intervention_types,

        "arms":
            arms,

        "duration":
            duration,

        "duration_demo":
            duration_demo,

        "reimbursement":
            reimbursement,

        "reimbursement_demo":
            reimbursement_demo,

        "procedures":
            procedures,

        "timeline":
            timeline,

        "locations":
            locations,

        "risks":
            risks,

        "benefits":
            benefits,

        "inclusion":
            criteria["inclusion"],

        "exclusion":
            criteria["exclusion"],
    }


# ============================================================
# MATCH EXPLANATION
# ============================================================

def build_match_explanation(
    trial_id: str
) -> Dict[str, str]:

    trial_id = safe_text(
        trial_id
    ).upper()

    if trial_id == "NCTFAKE003":

        return {

            "headline":
                "Core trial population appears to fit.",

            "body":
                (
                    "The available synthetic patient "
                    "information documents heart failure "
                    "and an NT-proBNP value above the study "
                    "threshold. No blocking exclusion "
                    "criterion is identified in the "
                    "prototype review."
                ),
        }

    if trial_id == "NCTFAKE002":

        return {

            "headline":
                "Review blocked by a gating criterion.",

            "body":
                (
                    "Heart failure is documented, but "
                    "confirmed cardiac amyloidosis is not "
                    "documented. Because this is a core "
                    "gating criterion, the trial should "
                    "not be presented as a potential match."
                ),
        }

    if trial_id == "NCTFAKE001":

        return {

            "headline":
                "A required disease criterion is not documented.",

            "body":
                (
                    "Type 2 diabetes is not documented "
                    "for the synthetic patient, so the "
                    "trial is not presented as a potential "
                    "match."
                ),
        }

    return {

        "headline":
            "Potential match identified.",

        "body":
            (
                "The available information was sufficient "
                "to surface this trial for clinician review."
            ),
    }


# ============================================================
# RENDER HELPERS
# ============================================================

def render_bullets(
    items: List[str]
) -> str:

    if not items:

        return (
            "<p class='muted'>"
            "Information not available."
            "</p>"
        )

    return (
        "<ul class='bullet-list'>"
        + "".join(
            f"<li>{esc(item)}</li>"
            for item in items
        )
        + "</ul>"
    )


def render_info_box(
    label: str,
    value: str,
    demo: bool = False,
) -> str:

    demo_html = ""

    if demo:

        demo_html = (
            "<span class='demo-badge'>"
            "DEMO EXAMPLE"
            "</span>"
        )

    return f"""
    <div class="info-box">

        <div class="info-label">
            {esc(label)}
        </div>

        <div class="info-value">

            {esc(value)}

            {demo_html}

        </div>

    </div>
    """


def render_eligibility(
    criteria: List[Dict[str, str]]
) -> str:

    if not criteria:

        return (
            "<div class='empty-state'>"
            "Detailed patient-specific eligibility "
            "information is not available in this "
            "prototype view."
            "</div>"
        )

    rows = []

    status_classes = {

        "MET":
            "status-met",

        "CLEAR":
            "status-clear",

        "BLOCKED":
            "status-blocked",

        "NOT_MET":
            "status-not-met",

        "UNKNOWN":
            "status-unknown",
    }

    for item in criteria:

        status = safe_text(
            item.get(
                "status"
            ),
            "UNKNOWN",
        ).upper()

        css_class = status_classes.get(
            status,
            "status-unknown",
        )

        rows.append(
            f"""
            <div class="eligibility-row">

                <div class="eligibility-main">

                    <div class="eligibility-criterion">
                        {esc(item.get("criterion"))}
                    </div>

                    <div class="eligibility-evidence">
                        {esc(item.get("evidence"))}
                    </div>

                </div>

                <div class="eligibility-meta">

                    <span class="category-pill">
                        {esc(item.get("category"))}
                    </span>

                    <span class="status-pill {css_class}">
                        {esc(
                            status.replace(
                                "_",
                                " "
                            )
                        )}
                    </span>

                </div>

            </div>
            """
        )

    return "".join(rows)


def render_collapsible(
    title: str,
    content: str,
    section_id: str,
) -> str:

    return f"""
    <details
        class="collapsible-section"
        id="{esc(section_id)}">

        <summary>

            <span class="summary-title">
                {esc(title)}
            </span>

            <span class="summary-chevron">
                ⌄
            </span>

        </summary>

        <div class="collapsible-content">

            {content}

        </div>

    </details>
    """


# ============================================================
# SMART APP
# ============================================================

def render_smart_app(
    trial_info: Dict[str, Any],
    patient_id: str,
    clinician_id: str,
    encounter_id: str,
    hook_instance: str,
) -> str:

    trial_id = trial_info[
        "trial_id"
    ]

    match = build_match_explanation(
        trial_id
    )

    eligibility = (
        build_demo_eligibility(
            trial_id
        )
    )

    inclusion = (
        trial_info.get(
            "inclusion",
            []
        )
    )

    exclusion = (
        trial_info.get(
            "exclusion",
            []
        )
    )

    if not inclusion:

        inclusion = [
            "See the patient-specific eligibility review above."
        ]

    if not exclusion:

        exclusion = [
            "See the patient-specific eligibility review above."
        ]

    # ========================================================
    # SECTION 1 — ALWAYS VISIBLE
    # ========================================================

    trial_overview = f"""

    <div class="overview-grid">

        {render_info_box(
            "Study status",
            trial_info["status"]
        )}

        {render_info_box(
            "Study type",
            trial_info["study_type"]
        )}

        {render_info_box(
            "Phase",
            trial_info["phase"]
        )}

        {render_info_box(
            "Disease population",
            ", ".join(
                trial_info[
                    "disease_population"
                ]
            )
        )}

    </div>

    <div class="official-title">

        <div class="mini-label">
            Official study title
        </div>

        <div class="official-title-text">
            {esc(
                trial_info[
                    "official_title"
                ]
            )}
        </div>

    </div>
    """

    # ========================================================
    # SECTION 4 — ALWAYS VISIBLE
    # PRINCIPAL INVESTIGATOR
    # ========================================================

    pi_demo_html = ""

    if trial_info["pi_demo"]:

        pi_demo_html = (
            "<span class='demo-badge'>"
            "DEMO EXAMPLE"
            "</span>"
        )

    pi_section = f"""

    <div class="pi-card">

        <div class="pi-avatar">
            PI
        </div>

        <div class="pi-content">

            <div class="mini-label">
                Principal Investigator
            </div>

            <div class="pi-name">

                {esc(
                    trial_info[
                        "pi_name"
                    ]
                )}

                {pi_demo_html}

            </div>

            <div class="pi-institution">
                {esc(
                    trial_info[
                        "institution"
                    ]
                )}
            </div>

            <div class="pi-team">
                {esc(
                    trial_info[
                        "research_team"
                    ]
                )}
            </div>

            <div class="pi-email">
                {esc(
                    trial_info[
                        "research_email"
                    ]
                )}
            </div>

        </div>

    </div>
    """

    # ========================================================
    # SECTION 8 — ALWAYS VISIBLE
    # PATIENT-SPECIFIC ELIGIBILITY
    # ========================================================

    patient_eligibility = f"""

    <div class="eligibility-summary">

        {render_eligibility(
            eligibility
        )}

    </div>

    <div class="eligibility-note">

        <strong>Important:</strong>

        This is a preliminary automated assessment.
        A potential match does not mean confirmed
        eligibility or enrollment. Final eligibility
        must be verified by the clinician and research team.

    </div>
    """

    # ========================================================
    # SECTION 9 — ALWAYS VISIBLE
    # WHY THIS PATIENT MATCHED
    # ========================================================

    why_match = f"""

    <div class="match-callout">

        <div class="match-icon">
            ✓
        </div>

        <div>

            <div class="match-headline">
                {esc(
                    match["headline"]
                )}
            </div>

            <div class="match-body">
                {esc(
                    match["body"]
                )}
            </div>

        </div>

    </div>
    """

    # ========================================================
    # COLLAPSIBLE CONTENT
    # ========================================================

    study_snapshot = f"""

    <div class="info-grid">

        {render_info_box(
            "Trial ID",
            trial_info["trial_id"]
        )}

        {render_info_box(
            "Study duration",
            trial_info["duration"],
            trial_info["duration_demo"]
        )}

        {render_info_box(
            "Reimbursement",
            trial_info["reimbursement"],
            trial_info["reimbursement_demo"]
        )}

    </div>
    """

    goals = render_bullets(
        trial_info["objectives"]
    )

    disease_population = render_bullets(
        trial_info[
            "disease_population"
        ]
    )

    intervention_content = (
        render_bullets(
            trial_info[
                "interventions"
            ]
        )
    )

    if trial_info[
        "intervention_types"
    ]:

        intervention_content += """

        <div class="subsection-label">
            Intervention type
        </div>

        """

        intervention_content += (
            render_bullets(
                trial_info[
                    "intervention_types"
                ]
            )
        )

    if trial_info["arms"]:

        intervention_content += """

        <div class="subsection-label">
            Treatment / study arm details
        </div>

        """

        intervention_content += (
            render_bullets(
                trial_info[
                    "arms"
                ]
            )
        )

    eligibility_criteria = f"""

    <div class="criteria-columns">

        <div>

            <div class="subsection-label">
                Inclusion criteria
            </div>

            {render_bullets(
                inclusion
            )}

        </div>

        <div>

            <div class="subsection-label">
                Exclusion criteria
            </div>

            {render_bullets(
                exclusion
            )}

        </div>

    </div>
    """

    procedures = render_bullets(
        trial_info[
            "procedures"
        ]
    )

    timeline = render_bullets(
        trial_info[
            "timeline"
        ]
    )

    locations = render_bullets(
        trial_info[
            "locations"
        ]
    )

    reimbursement = render_info_box(
        "Participant reimbursement",
        trial_info[
            "reimbursement"
        ],
        trial_info[
            "reimbursement_demo"
        ],
    )

    risks = render_bullets(
        trial_info[
            "risks"
        ]
    )

    benefits = render_bullets(
        trial_info[
            "benefits"
        ]
    )

    what_happens_next = """

    <ol class="next-steps">

        <li>
            Clinician reviews the trial information
            and patient-specific assessment.
        </li>

        <li>
            Clinician may choose to refer the patient
            to the research team.
        </li>

        <li>
            The research team performs study-specific
            screening and confirms eligibility.
        </li>

        <li>
            If eligible and interested, the research
            team discusses enrollment and informed consent.
        </li>

    </ol>
    """

    # ========================================================
    # NOT INTERESTED MODAL
    # ========================================================

    not_interested_modal = f"""

    <div
        class="modal-backdrop"
        id="notInterestedModal">

        <div class="modal-card">

            <button
                class="modal-close"
                type="button"
                onclick="closeNotInterestedModal()">
                ×
            </button>

            <div class="modal-title">
                Patient Not Interested
            </div>

            <div class="modal-description">

                Record the patient's decision regarding
                research participation.

                <strong>
                    This does not create a research referral.
                </strong>

            </div>

            <form
                method="post"
                action="/patient-feedback/not-interested">

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

                <label class="form-label">
                    Optional clinician comment
                </label>

                <textarea
                    name="comment"
                    class="comment-box"
                    placeholder="Reason or additional context..."
                ></textarea>

                <div class="modal-actions">

                    <button
                        type="button"
                        class="btn btn-secondary"
                        onclick="closeNotInterestedModal()">
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="btn btn-danger">
                        Record Not Interested
                    </button>

                </div>

            </form>

        </div>

    </div>
    """

    # ========================================================
    # REFER PATIENT MODAL
    # ========================================================

    refer_modal = f"""

    <div
        class="modal-backdrop"
        id="referModal">

        <div class="modal-card">

            <button
                class="modal-close"
                type="button"
                onclick="closeReferModal()">
                ×
            </button>

            <div class="modal-title">
                Refer Patient
            </div>

            <div class="modal-description">

                This will create a HeLaSync research
                referral for the displayed clinical trial.

            </div>

            <div class="confirm-box">

                <strong>
                    {esc(
                        trial_info[
                            "trial_name"
                        ]
                    )}
                </strong>

                <br>

                <span>
                    Trial ID:
                    {esc(trial_id)}
                </span>

            </div>

            <form
                method="post"
                action="/referrals/from-cds">

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

                <input
                    type="hidden"
                    name="source"
                    value="CDS_HOOKS"
                >

                <div class="modal-actions">

                    <button
                        type="button"
                        class="btn btn-secondary"
                        onclick="closeReferModal()">
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="btn btn-primary">
                        Confirm Referral
                    </button>

                </div>

            </form>

        </div>

    </div>
    """

    # ========================================================
    # FULL PAGE
    # ========================================================

    return f"""<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    {esc(
        trial_info["trial_name"]
    )}
    | HeLaSync
</title>

<style>

/* =========================================================
   BASE
   ========================================================= */

* {{
    box-sizing: border-box;
}}

html {{
    scroll-behavior: smooth;
}}

body {{

    margin: 0;

    padding: 0 0 100px 0;

    background: #f5f8fc;

    color: #172033;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Helvetica,
        Arial,
        sans-serif;

    line-height: 1.5;
}}


/* =========================================================
   PAGE
   ========================================================= */

.page {{

    max-width: 1120px;

    margin: 0 auto;

    padding:
        28px 20px 60px;
}}

.header {{
    margin-bottom: 20px;
}}

.brand {{

    color: #1769aa;

    font-weight: 800;

    font-size: 13px;

    letter-spacing: .05em;

    text-transform: uppercase;

    margin-bottom: 8px;
}}

.page-title {{

    margin: 0;

    color: #172033;

    font-size: 30px;

    line-height: 1.2;
}}

.page-subtitle {{

    margin-top: 7px;

    color: #5d6b82;

    font-size: 14px;
}}

.status-banner {{

    display: inline-flex;

    align-items: center;

    gap: 7px;

    margin-top: 15px;

    padding: 7px 12px;

    border-radius: 999px;

    background: #eaf5ee;

    color: #176b3a;

    font-size: 12px;

    font-weight: 800;
}}


/* =========================================================
   CARDS
   ========================================================= */

.card {{

    background: white;

    border:
        1px solid #dfe7f0;

    border-radius: 14px;

    margin-bottom: 14px;

    box-shadow:
        0 2px 8px
        rgba(15, 23, 42, .04);
}}

.card-header {{

    display: flex;

    align-items: center;

    gap: 10px;

    padding:
        19px 22px 8px;
}}

.section-number {{

    width: 28px;

    height: 28px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 8px;

    background: #eaf3fb;

    color: #1769aa;

    font-size: 12px;

    font-weight: 800;
}}

.card-title {{

    margin: 0;

    color: #1f2d43;

    font-size: 18px;
}}

.card-content {{

    padding:
        8px 22px 22px;
}}


/* =========================================================
   TRIAL OVERVIEW
   ========================================================= */

.overview-grid {{

    display: grid;

    grid-template-columns:
        repeat(4, minmax(0, 1fr));

    gap: 12px;
}}

.info-box {{

    padding: 13px;

    border:
        1px solid #e3eaf2;

    border-radius: 10px;

    background: #fbfcfe;
}}

.info-label,
.mini-label {{

    color: #718096;

    font-size: 10px;

    font-weight: 800;

    letter-spacing: .05em;

    text-transform: uppercase;
}}

.info-value {{

    margin-top: 4px;

    color: #243447;

    font-weight: 700;

    font-size: 13px;
}}

.official-title {{

    margin-top: 13px;

    padding: 13px;

    border-radius: 10px;

    background: #f8fafc;

    border:
        1px solid #e5ebf2;
}}

.official-title-text {{

    margin-top: 4px;

    color: #334155;

    font-size: 13px;
}}

.demo-badge {{

    display: inline-block;

    margin-left: 6px;

    padding: 2px 6px;

    border-radius: 4px;

    background: #fff4df;

    color: #9a5b00;

    font-size: 8px;

    font-weight: 800;

    letter-spacing: .04em;
}}


/* =========================================================
   PI CARD
   ========================================================= */

.pi-card {{

    display: flex;

    gap: 16px;

    align-items: flex-start;

    padding: 16px;

    border:
        1px solid #dce7f1;

    border-radius: 12px;

    background:
        linear-gradient(
            135deg,
            #f8fbff,
            #ffffff
        );
}}

.pi-avatar {{

    width: 54px;

    height: 54px;

    flex: 0 0 54px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 50%;

    background: #e7f1fa;

    color: #1769aa;

    font-weight: 800;

    font-size: 12px;
}}

.pi-name {{

    margin-top: 3px;

    color: #172033;

    font-size: 17px;

    font-weight: 800;
}}

.pi-institution {{

    margin-top: 3px;

    color: #334155;

    font-size: 13px;

    font-weight: 600;
}}

.pi-team {{

    margin-top: 8px;

    color: #64748b;

    font-size: 12px;
}}

.pi-email {{

    margin-top: 2px;

    color: #1769aa;

    font-size: 12px;
}}


/* =========================================================
   ELIGIBILITY
   ========================================================= */

.eligibility-summary {{

    border:
        1px solid #e0e7ef;

    border-radius: 12px;

    overflow: hidden;
}}

.eligibility-row {{

    display: flex;

    justify-content: space-between;

    gap: 18px;

    padding: 13px 15px;

    border-bottom:
        1px solid #e8edf3;
}}

.eligibility-row:last-child {{
    border-bottom: none;
}}

.eligibility-criterion {{

    color: #25354b;

    font-weight: 700;

    font-size: 13px;
}}

.eligibility-evidence {{

    margin-top: 3px;

    color: #64748b;

    font-size: 11px;
}}

.eligibility-meta {{

    display: flex;

    align-items: flex-start;

    gap: 6px;

    flex-wrap: wrap;

    justify-content: flex-end;
}}

.category-pill,
.status-pill {{

    display: inline-flex;

    align-items: center;

    padding:
        4px 8px;

    border-radius: 999px;

    font-size: 9px;

    font-weight: 800;

    white-space: nowrap;
}}

.category-pill {{

    background: #eef2f7;

    color: #536174;
}}

.status-met {{

    background: #eaf7ef;

    color: #18723e;
}}

.status-clear {{

    background: #edf7f1;

    color: #247345;
}}

.status-blocked {{

    background: #fff3df;

    color: #9a5b00;
}}

.status-not-met {{

    background: #fdecec;

    color: #b42318;
}}

.status-unknown {{

    background: #eef2f6;

    color: #59677a;
}}

.eligibility-note {{

    margin-top: 11px;

    padding:
        11px 13px;

    border-radius: 9px;

    background: #fff8eb;

    border:
        1px solid #f1d8a6;

    color: #6f4c0b;

    font-size: 11px;
}}


/* =========================================================
   WHY MATCHED
   ========================================================= */

.match-callout {{

    display: flex;

    gap: 14px;

    padding: 16px;

    border-radius: 12px;

    background: #eff8f2;

    border:
        1px solid #cfe8d7;
}}

.match-icon {{

    width: 34px;

    height: 34px;

    flex: 0 0 34px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 50%;

    background: #d9f0df;

    color: #1c7c43;

    font-weight: 900;
}}

.match-headline {{

    color: #1c5f38;

    font-weight: 800;

    font-size: 14px;
}}

.match-body {{

    margin-top: 3px;

    color: #42614d;

    font-size: 12px;
}}


/* =========================================================
   COLLAPSIBLE SECTIONS
   ========================================================= */

.collapsible-section {{

    background: white;

    border:
        1px solid #dfe7f0;

    border-radius: 12px;

    margin-bottom: 10px;

    box-shadow:
        0 1px 4px
        rgba(15, 23, 42, .03);
}}

.collapsible-section summary {{

    list-style: none;

    cursor: pointer;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 12px;

    padding: 16px 20px;

    color: #243447;

    font-weight: 750;
}}

.collapsible-section summary::-webkit-details-marker {{
    display: none;
}}

.collapsible-section summary:hover {{
    background: #f9fbfd;
}}

.summary-title {{
    font-size: 14px;
}}

.summary-chevron {{

    color: #64748b;

    font-size: 18px;

    transition:
        transform .15s ease;
}}

.collapsible-section[open]
.summary-chevron {{

    transform:
        rotate(180deg);
}}

.collapsible-content {{

    padding:
        0 20px 20px;

    border-top:
        1px solid #edf1f5;
}}

.collapsible-content > *:first-child {{
    margin-top: 16px;
}}


/* =========================================================
   COLLAPSIBLE CONTENT
   ========================================================= */

.info-grid {{

    display: grid;

    grid-template-columns:
        repeat(3, minmax(0, 1fr));

    gap: 12px;
}}

.criteria-columns {{

    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 20px;
}}

.subsection-label {{

    margin-bottom: 8px;

    color: #64748b;

    font-size: 10px;

    font-weight: 800;

    letter-spacing: .05em;

    text-transform: uppercase;
}}

.bullet-list {{

    margin: 0;

    padding-left: 20px;

    color: #475569;

    font-size: 13px;
}}

.bullet-list li {{
    margin-bottom: 7px;
}}

.next-steps {{

    margin: 0;

    padding-left: 22px;

    color: #475569;

    font-size: 13px;
}}

.next-steps li {{
    margin-bottom: 9px;
}}

.muted {{

    color: #7a8798;

    font-size: 12px;
}}

.empty-state {{

    padding: 14px;

    border-radius: 8px;

    background: #f8fafc;

    color: #64748b;

    font-size: 12px;
}}


/* =========================================================
   EXPAND / COLLAPSE
   ========================================================= */

.controls {{

    display: flex;

    justify-content: flex-end;

    gap: 12px;

    margin:
        8px 0 12px;
}}

.text-button {{

    border: none;

    background: transparent;

    color: #1769aa;

    cursor: pointer;

    font-size: 11px;

    font-weight: 700;
}}


/* =========================================================
   PROTOTYPE NOTICE
   ========================================================= */

.prototype-notice {{

    margin-top: 18px;

    padding:
        13px 15px;

    border-radius: 10px;

    background: #f8fafc;

    border:
        1px solid #e1e8f0;

    color: #64748b;

    font-size: 10px;
}}

.context {{

    margin-top: 12px;

    color: #94a3b8;

    font-size: 9px;
}}


/* =========================================================
   STICKY ACTION BAR
   ========================================================= */

.sticky-action-bar {{

    position: fixed;

    left: 0;

    right: 0;

    bottom: 0;

    z-index: 1000;

    background:
        rgba(
            255,
            255,
            255,
            .97
        );

    backdrop-filter:
        blur(10px);

    border-top:
        1px solid #d9e2ec;

    box-shadow:
        0 -4px 18px
        rgba(15,23,42,.10);

    padding:
        10px 20px;
}}

.sticky-action-inner {{

    max-width: 1120px;

    margin: 0 auto;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 18px;
}}

.action-label {{

    display: flex;

    flex-direction: column;

    gap: 1px;
}}

.action-title {{

    color: #243447;

    font-size: 13px;

    font-weight: 800;
}}

.action-subtitle {{

    color: #718096;

    font-size: 10px;
}}

.action-buttons {{

    display: flex;

    align-items: center;

    gap: 9px;
}}

.btn {{

    border:
        1px solid transparent;

    border-radius: 8px;

    padding:
        9px 16px;

    cursor: pointer;

    font-size: 12px;

    font-weight: 800;

    text-decoration: none;
}}

.btn-primary {{

    background: #1670b8;

    border-color: #1670b8;

    color: white;
}}

.btn-primary:hover {{
    background: #125d99;
}}

.btn-secondary {{

    background: white;

    border-color: #cbd5e1;

    color: #334155;
}}

.btn-secondary:hover {{
    background: #f8fafc;
}}

.btn-danger {{

    background: white;

    border-color: #efaaa4;

    color: #b42318;
}}

.btn-danger:hover {{
    background: #fff5f4;
}}


/* =========================================================
   MODALS
   ========================================================= */

.modal-backdrop {{

    position: fixed;

    inset: 0;

    z-index: 2000;

    display: none;

    align-items: center;

    justify-content: center;

    padding: 20px;

    background:
        rgba(
            15,
            23,
            42,
            .48
        );
}}

.modal-backdrop.active {{
    display: flex;
}}

.modal-card {{

    position: relative;

    width:
        min(
            520px,
            100%
        );

    background: white;

    border-radius: 14px;

    padding: 24px;

    box-shadow:
        0 18px 50px
        rgba(15,23,42,.22);
}}

.modal-close {{

    position: absolute;

    top: 10px;

    right: 12px;

    border: none;

    background: transparent;

    color: #64748b;

    font-size: 24px;

    cursor: pointer;
}}

.modal-title {{

    color: #172033;

    font-size: 20px;

    font-weight: 800;
}}

.modal-description {{

    margin-top: 7px;

    color: #64748b;

    font-size: 12px;
}}

.confirm-box {{

    margin-top: 16px;

    padding: 12px;

    border-radius: 9px;

    background: #f7fafd;

    border:
        1px solid #e0e8f0;

    color: #334155;

    font-size: 12px;
}}

.form-label {{

    display: block;

    margin-top: 18px;

    margin-bottom: 7px;

    color: #334155;

    font-size: 11px;

    font-weight: 800;
}}

.comment-box {{

    width: 100%;

    min-height: 110px;

    resize: vertical;

    border:
        1px solid #cbd5e1;

    border-radius: 8px;

    padding: 10px;

    font: inherit;

    font-size: 12px;
}}

.modal-actions {{

    display: flex;

    justify-content: flex-end;

    gap: 9px;

    margin-top: 18px;
}}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media (max-width: 850px) {{

    .overview-grid {{

        grid-template-columns:
            repeat(
                2,
                minmax(0, 1fr)
            );
    }}

    .info-grid {{

        grid-template-columns:
            1fr;
    }}

    .criteria-columns {{

        grid-template-columns:
            1fr;
    }}

}}

@media (max-width: 650px) {{

    body {{
        padding-bottom: 78px;
    }}

    .page {{

        padding:
            20px 12px 40px;
    }}

    .page-title {{
        font-size: 24px;
    }}

    .overview-grid {{

        grid-template-columns:
            1fr 1fr;
    }}

    .eligibility-row {{

        flex-direction: column;
    }}

    .eligibility-meta {{

        justify-content:
            flex-start;
    }}

    .sticky-action-inner {{

        justify-content:
            center;
    }}

    .action-label {{
        display: none;
    }}

    .action-buttons {{
        width: 100%;
    }}

    .action-buttons .btn {{

        flex: 1;

        text-align:
            center;
    }}

}}

</style>

</head>


<body>


<div class="page">


    <!-- =====================================================
         HEADER
         ===================================================== -->

    <div class="header">

        <div class="brand">
            HeLaSync Clinical Research
        </div>

        <h1 class="page-title">
            {esc(
                trial_info[
                    "trial_name"
                ]
            )}
        </h1>

        <div class="page-subtitle">
            Clinician-facing clinical trial review
        </div>

        <div class="status-banner">
            ● Potential Match
        </div>

    </div>


    <!-- =====================================================
         ALWAYS VISIBLE #1
         TRIAL OVERVIEW
         ===================================================== -->

    <section class="card">

        <div class="card-header">

            <div class="section-number">
                1
            </div>

            <h2 class="card-title">
                Trial Overview
            </h2>

        </div>

        <div class="card-content">

            {trial_overview}

        </div>

    </section>


    <!-- =====================================================
         ALWAYS VISIBLE #2
         PRINCIPAL INVESTIGATOR & RESEARCH SITE
         ===================================================== -->

    <section class="card">

        <div class="card-header">

            <div class="section-number">
                4
            </div>

            <h2 class="card-title">
                Principal Investigator &amp; Research Site
            </h2>

        </div>

        <div class="card-content">

            {pi_section}

        </div>

    </section>


    <!-- =====================================================
         ALWAYS VISIBLE #3
         PATIENT-SPECIFIC ELIGIBILITY
         ===================================================== -->

    <section class="card">

        <div class="card-header">

            <div class="section-number">
                8
            </div>

            <h2 class="card-title">
                Patient-Specific Eligibility
            </h2>

        </div>

        <div class="card-content">

            {patient_eligibility}

        </div>

    </section>


    <!-- =====================================================
         ALWAYS VISIBLE #4
         WHY THIS PATIENT MATCHED
         ===================================================== -->

    <section class="card">

        <div class="card-header">

            <div class="section-number">
                9
            </div>

            <h2 class="card-title">
                Why This Patient Matched
            </h2>

        </div>

        <div class="card-content">

            {why_match}

        </div>

    </section>


    <!-- =====================================================
         EXPAND / COLLAPSE CONTROLS
         ===================================================== -->

    <div class="controls">

        <button
            type="button"
            class="text-button"
            onclick="expandAll()">
            Expand all
        </button>

        <button
            type="button"
            class="text-button"
            onclick="collapseAll()">
            Collapse all
        </button>

    </div>


    <!-- =====================================================
         COLLAPSIBLE SECTION 3
         ===================================================== -->

    {
        render_collapsible(
            "Study Snapshot",
            study_snapshot,
            "study-snapshot"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 4
         ===================================================== -->

    {
        render_collapsible(
            "Study Goals & Objectives",
            goals,
            "study-goals"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 5
         ===================================================== -->

    {
        render_collapsible(
            "Disease Population",
            disease_population,
            "disease-population"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 6
         ===================================================== -->

    {
        render_collapsible(
            "Intervention / Treatment",
            intervention_content,
            "intervention"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 7
         ===================================================== -->

    {
        render_collapsible(
            "Eligibility Criteria",
            eligibility_criteria,
            "eligibility-criteria"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 10
         ===================================================== -->

    {
        render_collapsible(
            "Study Procedures",
            procedures,
            "study-procedures"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 11
         ===================================================== -->

    {
        render_collapsible(
            "Study Timeline",
            timeline,
            "study-timeline"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 12
         ===================================================== -->

    {
        render_collapsible(
            "Study Locations",
            locations,
            "study-locations"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 13
         ===================================================== -->

    {
        render_collapsible(
            "Participant Reimbursement",
            reimbursement,
            "reimbursement"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 14
         ===================================================== -->

    {
        render_collapsible(
            "Risks & Considerations",
            risks,
            "risks"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 15
         ===================================================== -->

    {
        render_collapsible(
            "Potential Benefits",
            benefits,
            "benefits"
        )
    }


    <!-- =====================================================
         COLLAPSIBLE SECTION 16
         ===================================================== -->

    {
        render_collapsible(
            "What Happens Next",
            what_happens_next,
            "what-happens-next"
        )
    }


    <!-- =====================================================
         PROTOTYPE NOTICE
         ===================================================== -->

    <div class="prototype-notice">

        <strong>
            Prototype notice:
        </strong>

        This Smart App is a clinician-facing
        research workflow prototype.

        A potential match is not confirmed
        eligibility or enrollment.

        Final eligibility, informed consent,
        and enrollment decisions remain with
        the clinician, patient, and research team.

    </div>


    <div class="context">

        Trial:
        {esc(trial_id)}

        &nbsp;•&nbsp;

        Patient context received

        &nbsp;•&nbsp;

        Clinician context received

    </div>


</div>


<!-- =========================================================
     STICKY CLINICIAN ACTION BAR
     ========================================================= -->

<div class="sticky-action-bar">

    <div class="sticky-action-inner">

        <div class="action-label">

            <div class="action-title">
                Research Decision
            </div>

            <div class="action-subtitle">
                Potential match — final eligibility requires verification
            </div>

        </div>

        <div class="action-buttons">

            <button
                type="button"
                class="btn btn-danger"
                onclick="openNotInterestedModal()">

                Not Interested

            </button>

            <button
                type="button"
                class="btn btn-primary"
                onclick="openReferModal()">

                Refer Patient

            </button>

        </div>

    </div>

</div>


{not_interested_modal}

{refer_modal}


<script>


// =========================================================
// MODAL CONTROLS
// =========================================================

function openNotInterestedModal() {{

    document
        .getElementById(
            "notInterestedModal"
        )
        .classList.add(
            "active"
        );
}}


function closeNotInterestedModal() {{

    document
        .getElementById(
            "notInterestedModal"
        )
        .classList.remove(
            "active"
        );
}}


function openReferModal() {{

    document
        .getElementById(
            "referModal"
        )
        .classList.add(
            "active"
        );
}}


function closeReferModal() {{

    document
        .getElementById(
            "referModal"
        )
        .classList.remove(
            "active"
        );
}}


// =========================================================
// EXPAND / COLLAPSE
// =========================================================

function expandAll() {{

    document
        .querySelectorAll(
            ".collapsible-section"
        )
        .forEach(
            function(section) {{

                section.open = true;

            }}
        );
}}


function collapseAll() {{

    document
        .querySelectorAll(
            ".collapsible-section"
        )
        .forEach(
            function(section) {{

                section.open = false;

            }}
        );
}}


// =========================================================
// CLOSE MODAL WHEN BACKDROP IS CLICKED
// =========================================================

document.addEventListener(
    "click",
    function(event) {{

        if (
            event.target.classList.contains(
                "modal-backdrop"
            )
        ) {{

            event.target.classList.remove(
                "active"
            );

        }}

    }}
);


</script>


</body>

</html>
"""


# ============================================================
# GET SMART APP
# ============================================================

@router.get(
    "/referral-launch",
    response_class=HTMLResponse,
)
async def referral_launch(

    trial_id: str = Query(...),

    patient_id: str = Query(
        ""
    ),

    clinician_id: str = Query(
        ""
    ),

    encounter_id: str = Query(
        ""
    ),

    hook_instance: str = Query(
        ""
    ),

):

    trial = get_trial(
        trial_id
    )

    if trial is None:

        return HTMLResponse(

            content=f"""
            <html>

            <body
                style="
                    font-family:Arial;
                    padding:40px;
                "
            >

                <h2>
                    HeLaSync Smart App
                </h2>

                <p>
                    Trial
                    <strong>
                        {esc(trial_id)}
                    </strong>
                    was not found.
                </p>

                <p>
                    Verify that the trial JSON exists
                    in the Trial_List directory.
                </p>

            </body>

            </html>
            """,

            status_code=404,
        )

    trial_info = (
        build_trial_information(
            trial_id=trial_id,
            trial=trial,
        )
    )

    return HTMLResponse(

        content=render_smart_app(

            trial_info=trial_info,

            patient_id=patient_id,

            clinician_id=clinician_id,

            encounter_id=encounter_id,

            hook_instance=hook_instance,
        )
    )


# ============================================================
# CREATE RESEARCH REFERRAL
# ============================================================

@router.post(
    "/referrals/from-cds"
)
async def referral_from_cds(

    trial_id: str = Form(...),

    patient_id: str = Form(...),

    clinician_id: str = Form(
        ""
    ),

    encounter_id: str = Form(
        ""
    ),

    hook_instance: str = Form(
        ""
    ),

    source: str = Form(
        "CDS_HOOKS"
    ),

):

    try:

        try:

            referral = create_referral(

                trial_id=trial_id,

                patient_id=patient_id,

                clinician_id=clinician_id,

                encounter_id=encounter_id,

                source=source,

                patient_data={

                    "hook_instance":
                        hook_instance,

                    "source":
                        "HeLaSync Smart App",

                },
            )

        except TypeError:

            # Compatibility fallback for an older
            # referral.py signature.

            referral = create_referral(

                trial_id,

                patient_id,

                clinician_id,

                encounter_id,

                source,
            )

        referral_id = ""

        if isinstance(
            referral,
            dict
        ):

            referral_id = safe_text(
                referral.get(
                    "referral_id"
                )
            )

        if referral_id:

            query = urlencode({

                "created":
                    referral_id

            })

            return RedirectResponse(

                url=(
                    "/research/referrals?"
                    + query
                ),

                status_code=303,
            )

        return RedirectResponse(

            url="/research/referrals",

            status_code=303,
        )

    except Exception as exc:

        return HTMLResponse(

            content=f"""

            <html>

            <body
                style="
                    font-family:Arial;
                    padding:40px;
                "
            >

                <h2>
                    HeLaSync Referral Error
                </h2>

                <p>
                    The referral could not be created.
                </p>

                <pre>
                    {esc(str(exc))}
                </pre>

                <p>

                    <a
                        href="/referral-launch?{urlencode({
                            'trial_id':
                                trial_id,
                            'patient_id':
                                patient_id,
                            'clinician_id':
                                clinician_id,
                            'encounter_id':
                                encounter_id,
                            'hook_instance':
                                hook_instance,
                        })}"
                    >
                        Return to Smart App
                    </a>

                </p>

            </body>

            </html>

            """,

            status_code=500,
        )


# ============================================================
# PATIENT NOT INTERESTED
# ============================================================

@router.post(
    "/patient-feedback/not-interested"
)
async def patient_not_interested(

    trial_id: str = Form(...),

    patient_id: str = Form(
        ""
    ),

    clinician_id: str = Form(
        ""
    ),

    encounter_id: str = Form(
        ""
    ),

    hook_instance: str = Form(
        ""
    ),

    comment: str = Form(
        ""
    ),

):

    response = {

        "response_id":
            (
                "HSNI-"
                + uuid.uuid4()
                .hex[:8]
                .upper()
            ),

        "timestamp":
            current_timestamp(),

        "event":
            "PATIENT_NOT_INTERESTED",

        "trial_id":
            trial_id,

        "patient_id":
            patient_id,

        "clinician_id":
            clinician_id,

        "encounter_id":
            encounter_id,

        "hook_instance":
            hook_instance,

        "comment":
            comment.strip(),

        "creates_research_referral":
            False,
    }

    PATIENT_NOT_INTERESTED_RESPONSES.append(
        response
    )

    query = urlencode({

        "trial_id":
            trial_id,

        "patient_id":
            patient_id,

        "clinician_id":
            clinician_id,

        "encounter_id":
            encounter_id,

        "hook_instance":
            hook_instance,

        "feedback":
            "not-interested",

    })

    return RedirectResponse(

        url=(
            "/referral-launch?"
            + query
        ),

        status_code=303,
    )


# ============================================================
# DEBUG ENDPOINT
# ============================================================

@router.get(
    "/patient-feedback/not-interested"
)
async def get_patient_not_interested():

    return {

        "count":
            len(
                PATIENT_NOT_INTERESTED_RESPONSES
            ),

        "responses":
            PATIENT_NOT_INTERESTED_RESPONSES,

    }
