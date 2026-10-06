"""
HeLaSync Research Referral Dashboard
-------------------------------------

Stage 3A Research Referral Dashboard.

Purpose:
- Display referrals created through the HeLaSync CDS Hooks workflow.
- Allow the research team to review referral details.
- Allow research staff to update referral status.
- Display referral history and duplicate referral attempts.

Important:
This is a prototype dashboard. Referral data is currently stored
in-memory by referral.py and will reset when the Render service restarts.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from html import escape

from referral import (
    list_referrals,
    get_referral,
    update_referral_status,
)


router = APIRouter()


# ============================================================
# STATUS CONFIGURATION
# ============================================================

ALLOWED_STATUSES = {
    "INTERESTED",
    "UNDER_REVIEW",
    "CONTACTED",
    "SCREENING",
    "ENROLLED",
    "NOT_ELIGIBLE",
}


STATUS_LABELS = {
    "INTERESTED": "Interested",
    "UNDER_REVIEW": "Under Review",
    "CONTACTED": "Contacted",
    "SCREENING": "Screening",
    "ENROLLED": "Enrolled",
    "NOT_ELIGIBLE": "Not Eligible",
}


STATUS_CLASSES = {
    "INTERESTED": "status-interested",
    "UNDER_REVIEW": "status-review",
    "CONTACTED": "status-contacted",
    "SCREENING": "status-screening",
    "ENROLLED": "status-enrolled",
    "NOT_ELIGIBLE": "status-not-eligible",
}


# ============================================================
# REQUEST MODEL
# ============================================================

class ReferralStatusUpdate(BaseModel):
    status: str


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe(value) -> str:
    """
    Convert a value to a safely escaped string for HTML.
    """
    if value is None:
        return "—"

    text = str(value).strip()

    if not text:
        return "—"

    return escape(text)


def get_status_class(status: str) -> str:
    return STATUS_CLASSES.get(
        status,
        "status-default"
    )


def get_status_label(status: str) -> str:
    return STATUS_LABELS.get(
        status,
        status.replace("_", " ").title()
    )


def count_duplicate_attempts(referral: dict) -> int:
    history = referral.get("referral_history", [])

    if not isinstance(history, list):
        return 0

    return sum(
        1
        for event in history
        if isinstance(event, dict)
        and event.get("event") == "DUPLICATE_REFERRAL_ATTEMPT"
    )


def render_history(referral: dict) -> str:
    """
    Render referral history as HTML.
    """

    history = referral.get("referral_history", [])

    if not isinstance(history, list) or not history:
        return """
        <div class="empty-history">
            No referral history available.
        </div>
        """

    rows = []

    for event in history:
        if not isinstance(event, dict):
            continue

        timestamp = safe(event.get("timestamp"))
        event_name = safe(
            str(event.get("event", "UNKNOWN"))
            .replace("_", " ")
            .title()
        )

        source = safe(event.get("source"))
        clinician = safe(event.get("clinician_id"))
        encounter = safe(event.get("encounter_id"))
        status = safe(event.get("status"))

        rows.append(
            f"""
            <div class="history-row">
                <div class="history-main">
                    <strong>{event_name}</strong>
                    <span class="history-time">{timestamp}</span>
                </div>

                <div class="history-details">
                    <span>Source: {source}</span>
                    <span>Clinician: {clinician}</span>
                    <span>Encounter: {encounter}</span>
                    <span>Status: {status}</span>
                </div>
            </div>
            """
        )

    return "\n".join(rows)


def render_status_options(current_status: str) -> str:
    options = []

    for status in [
        "INTERESTED",
        "UNDER_REVIEW",
        "CONTACTED",
        "SCREENING",
        "ENROLLED",
        "NOT_ELIGIBLE",
    ]:
        selected = "selected" if status == current_status else ""

        options.append(
            f"""
            <option value="{escape(status)}" {selected}>
                {escape(get_status_label(status))}
            </option>
            """
        )

    return "\n".join(options)


def render_referral_card(referral: dict) -> str:
    """
    Render one referral card directly from server-side data.
    """

    referral_id = referral.get("referral_id", "")
    trial_id = referral.get("trial_id", "")
    trial_name = referral.get("trial_name", "")
    patient_id = referral.get("patient_id", "")
    clinician_id = referral.get("clinician_id", "")
    encounter_id = referral.get("encounter_id", "")
    research_team = referral.get("research_team", "")
    research_email = referral.get("research_email", "")
    status = referral.get("status", "INTERESTED")
    source = referral.get("source", "")
    created_at = referral.get("created_at", "")
    updated_at = referral.get("updated_at", "")

    duplicate_count = count_duplicate_attempts(referral)

    status_class = get_status_class(status)
    status_label = get_status_label(status)

    history_html = render_history(referral)
    status_options = render_status_options(status)

    duplicate_html = ""

    if duplicate_count > 0:
        duplicate_html = f"""
        <div class="duplicate-warning">
            <div class="duplicate-icon">!</div>
            <div>
                <strong>Duplicate referral activity detected</strong>
                <div>
                    This referral has been submitted or opened
                    {duplicate_count} additional time{"s" if duplicate_count != 1 else ""}.
                    The existing referral was preserved.
                </div>
            </div>
        </div>
        """

    return f"""
    <article class="referral-card">

        <!-- HEADER -->

        <div class="card-header">

            <div class="trial-header">

                <div class="trial-icon">
                    HS
                </div>

                <div>
                    <div class="eyebrow">
                        CLINICAL TRIAL REFERRAL
                    </div>

                    <h2>
                        {safe(trial_name)}
                    </h2>

                    <div class="trial-id">
                        {safe(trial_id)}
                    </div>
                </div>

            </div>

            <div class="status-area">

                <span class="status-badge {status_class}">
                    {safe(status_label)}
                </span>

                <div class="status-controls">

                    <select
                        id="status-{safe(referral_id)}"
                        class="status-select"
                    >
                        {status_options}
                    </select>

                    <button
                        class="update-button"
                        onclick="updateReferralStatus('{safe(referral_id)}')"
                    >
                        Update
                    </button>

                </div>

            </div>

        </div>


        {duplicate_html}


        <!-- REFERRAL IDENTIFIERS -->

        <div class="section">

            <div class="section-title">
                Referral Information
            </div>

            <div class="info-grid">

                <div class="info-item">
                    <div class="info-label">
                        Referral ID
                    </div>
                    <div class="info-value mono">
                        {safe(referral_id)}
                    </div>
                </div>

                <div class="info-item">
                    <div class="info-label">
                        Source
                    </div>
                    <div class="info-value">
                        {safe(source)}
                    </div>
                </div>

                <div class="info-item">
                    <div class="info-label">
                        Created
                    </div>
                    <div class="info-value">
                        {safe(created_at)}
                    </div>
                </div>

                <div class="info-item">
                    <div class="info-label">
                        Last Updated
                    </div>
                    <div class="info-value">
                        {safe(updated_at)}
                    </div>
                </div>

            </div>

        </div>


        <!-- PATIENT -->

        <div class="section">

            <div class="section-title">
                Patient
            </div>

            <div class="patient-box">

                <div class="patient-avatar">
                    P
                </div>

                <div>

                    <div class="patient-id">
                        {safe(patient_id)}
                    </div>

                    <div class="patient-label">
                        Patient Identifier
                    </div>

                </div>

            </div>

        </div>


        <!-- CLINICIAN / ENCOUNTER -->

        <div class="section">

            <div class="section-title">
                Referring Clinician & Encounter
            </div>

            <div class="info-grid">

                <div class="info-item">
                    <div class="info-label">
                        Referring Clinician
                    </div>

                    <div class="info-value">
                        {safe(clinician_id)}
                    </div>
                </div>


                <div class="info-item">

                    <div class="info-label">
                        Encounter
                    </div>

                    <div class="info-value mono">
                        {safe(encounter_id)}
                    </div>

                </div>

            </div>

        </div>


        <!-- RESEARCH ROUTING -->

        <div class="section">

            <div class="section-title">
                Research Routing
            </div>

            <div class="research-routing">

                <div class="routing-item">

                    <div class="routing-label">
                        Research Team
                    </div>

                    <div class="routing-value">
                        {safe(research_team)}
                    </div>

                </div>

                <div class="routing-item">

                    <div class="routing-label">
                        Research Email
                    </div>

                    <div class="routing-value">
                        {safe(research_email)}
                    </div>

                </div>

            </div>

        </div>


        <!-- HISTORY -->

        <details class="history-section">

            <summary>
                <span>
                    Referral History
                </span>

                <span class="history-count">
                    {len(referral.get("referral_history", []))}
                </span>
            </summary>

            <div class="history-content">
                {history_html}
            </div>

        </details>


    </article>
    """


# ============================================================
# DASHBOARD PAGE
# ============================================================

@router.get(
    "/research/referrals",
    response_class=HTMLResponse
)
def research_referral_dashboard():

    referrals = list_referrals()

    if not isinstance(referrals, list):
        referrals = []

    if referrals:

        referral_cards = "\n".join(
            render_referral_card(referral)
            for referral in referrals
            if isinstance(referral, dict)
        )

    else:

        referral_cards = """
        <div class="empty-state">

            <div class="empty-icon">
                HS
            </div>

            <h2>
                No referrals yet
            </h2>

            <p>
                Clinical trial referrals created through
                the HeLaSync CDS Hooks workflow will appear here.
            </p>

        </div>
        """


    total = len(referrals)

    interested = sum(
        1
        for referral in referrals
        if referral.get("status") == "INTERESTED"
    )

    screening = sum(
        1
        for referral in referrals
        if referral.get("status") == "SCREENING"
    )

    enrolled = sum(
        1
        for referral in referrals
        if referral.get("status") == "ENROLLED"
    )

    return f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
    HeLaSync Research Referrals
</title>


<style>

/* =========================================================
   GLOBAL
   ========================================================= */

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        Helvetica,
        Arial,
        sans-serif;

    background: #f4f7fb;
    color: #172033;
}}


/* =========================================================
   HEADER
   ========================================================= */

.topbar {{
    background: #ffffff;
    border-bottom: 1px solid #e4e9f0;
    padding: 18px 32px;

    display: flex;
    align-items: center;
    justify-content: space-between;

    position: sticky;
    top: 0;
    z-index: 10;
}}

.brand {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.brand-mark {{
    width: 42px;
    height: 42px;

    border-radius: 12px;

    background: #172033;
    color: #ffffff;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
    letter-spacing: -0.5px;
}}

.brand-name {{
    font-size: 19px;
    font-weight: 750;
}}

.brand-subtitle {{
    font-size: 12px;
    color: #6d7788;
    margin-top: 2px;
}}

.header-actions {{
    display: flex;
    gap: 10px;
    align-items: center;
}}

.refresh-button {{
    border: 1px solid #d7dee8;
    background: #ffffff;
    color: #172033;

    border-radius: 9px;
    padding: 9px 14px;

    font-size: 13px;
    font-weight: 650;

    cursor: pointer;
}}

.refresh-button:hover {{
    background: #f6f8fb;
}}


/* =========================================================
   PAGE
   ========================================================= */

.container {{
    width: min(1180px, calc(100% - 40px));
    margin: 0 auto;
    padding: 36px 0 70px;
}}

.page-heading {{
    margin-bottom: 24px;
}}

.eyebrow {{
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
    color: #637084;
    text-transform: uppercase;
}}

.page-heading h1 {{
    margin: 6px 0 8px;

    font-size: 30px;
    line-height: 1.15;

    letter-spacing: -0.7px;
}}

.page-heading p {{
    margin: 0;
    color: #687386;
    font-size: 14px;
}}


/* =========================================================
   STATS
   ========================================================= */

.stats {{
    display: grid;
    grid-template-columns:
        repeat(4, minmax(0, 1fr));

    gap: 14px;

    margin-bottom: 26px;
}}

.stat-card {{
    background: #ffffff;

    border: 1px solid #e3e8ef;
    border-radius: 13px;

    padding: 18px;
}}

.stat-label {{
    color: #697589;
    font-size: 12px;
    font-weight: 650;
}}

.stat-number {{
    margin-top: 7px;

    font-size: 27px;
    font-weight: 780;

    letter-spacing: -0.5px;
}}


/* =========================================================
   REFERRAL CARD
   ========================================================= */

.referral-card {{
    background: #ffffff;

    border: 1px solid #dfe5ed;
    border-radius: 15px;

    margin-bottom: 18px;

    overflow: hidden;

    box-shadow:
        0 2px 8px rgba(20, 35, 60, 0.035);
}}

.card-header {{
    padding: 22px 24px;

    display: flex;
    align-items: flex-start;
    justify-content: space-between;

    gap: 20px;

    border-bottom: 1px solid #e9edf3;
}}

.trial-header {{
    display: flex;
    gap: 14px;
    align-items: flex-start;
}}

.trial-icon {{
    flex: 0 0 auto;

    width: 46px;
    height: 46px;

    border-radius: 12px;

    background: #eef2ff;
    color: #3f51b5;

    display: flex;
    align-items: center;
    justify-content: center;

    font-size: 13px;
    font-weight: 800;
}}

.card-header h2 {{
    margin: 3px 0 5px;

    font-size: 19px;
    line-height: 1.3;

    color: #172033;
}}

.trial-id {{
    color: #697589;
    font-family: monospace;
    font-size: 12px;
}}

.status-area {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 10px;
}}

.status-badge {{
    display: inline-flex;
    align-items: center;

    border-radius: 999px;

    padding: 6px 11px;

    font-size: 11px;
    font-weight: 750;

    white-space: nowrap;
}}

.status-interested {{
    background: #eaf7ef;
    color: #187443;
}}

.status-review {{
    background: #fff5dc;
    color: #8a6200;
}}

.status-contacted {{
    background: #eaf2ff;
    color: #2c5fa8;
}}

.status-screening {{
    background: #eeeaff;
    color: #5a43a4;
}}

.status-enrolled {{
    background: #dff5ed;
    color: #087454;
}}

.status-not-eligible {{
    background: #fcebea;
    color: #a33a36;
}}

.status-default {{
    background: #edf0f4;
    color: #556070;
}}

.status-controls {{
    display: flex;
    gap: 7px;
}}

.status-select {{
    border: 1px solid #d8dfe8;
    background: #ffffff;

    border-radius: 8px;

    padding: 7px 9px;

    font-size: 12px;
    color: #2d3748;
}}

.update-button {{
    border: 0;

    background: #172033;
    color: #ffffff;

    border-radius: 8px;

    padding: 7px 12px;

    font-size: 12px;
    font-weight: 700;

    cursor: pointer;
}}

.update-button:hover {{
    background: #29364e;
}}


/* =========================================================
   DUPLICATE WARNING
   ========================================================= */

.duplicate-warning {{
    margin: 18px 24px 0;

    display: flex;
    gap: 11px;

    padding: 12px 14px;

    border: 1px solid #f0d9a1;
    border-radius: 10px;

    background: #fff9e9;

    color: #735a1b;

    font-size: 12px;
    line-height: 1.5;
}}

.duplicate-icon {{
    flex: 0 0 auto;

    width: 22px;
    height: 22px;

    border-radius: 50%;

    background: #e8b849;
    color: #ffffff;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
}}


/* =========================================================
   SECTIONS
   ========================================================= */

.section {{
    padding: 20px 24px;

    border-bottom: 1px solid #edf0f4;
}}

.section-title {{
    font-size: 12px;
    font-weight: 800;

    text-transform: uppercase;
    letter-spacing: 0.7px;

    color: #687386;

    margin-bottom: 14px;
}}

.info-grid {{
    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 16px;
}}

.info-item {{
    min-width: 0;
}}

.info-label {{
    color: #7a8493;

    font-size: 11px;
    font-weight: 650;

    margin-bottom: 5px;
}}

.info-value {{
    color: #222c3c;

    font-size: 13px;
    line-height: 1.45;

    overflow-wrap: anywhere;
}}

.mono {{
    font-family: monospace;
    font-size: 12px;
}}


/* =========================================================
   PATIENT
   ========================================================= */

.patient-box {{
    display: flex;
    align-items: center;
    gap: 12px;
}}

.patient-avatar {{
    width: 38px;
    height: 38px;

    border-radius: 50%;

    background: #eef2f6;
    color: #465365;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
    font-size: 13px;
}}

.patient-id {{
    font-size: 14px;
    font-weight: 700;
}}

.patient-label {{
    margin-top: 2px;

    font-size: 11px;
    color: #7a8493;
}}


/* =========================================================
   RESEARCH ROUTING
   ========================================================= */

.research-routing {{
    display: grid;

    grid-template-columns:
        repeat(2, minmax(0, 1fr));

    gap: 16px;
}}

.routing-item {{
    background: #f8fafc;

    border: 1px solid #e7ebf1;

    border-radius: 9px;

    padding: 12px;
}}

.routing-label {{
    color: #7a8493;

    font-size: 11px;
    font-weight: 650;

    margin-bottom: 5px;
}}

.routing-value {{
    color: #252f40;

    font-size: 13px;

    overflow-wrap: anywhere;
}}


/* =========================================================
   HISTORY
   ========================================================= */

.history-section {{
    padding: 0 24px;
}}

.history-section summary {{
    cursor: pointer;

    list-style: none;

    padding: 18px 0;

    display: flex;
    justify-content: space-between;
    align-items: center;

    font-size: 13px;
    font-weight: 750;
}}

.history-section summary::-webkit-details-marker {{
    display: none;
}}

.history-count {{
    min-width: 23px;
    height: 23px;

    border-radius: 50%;

    background: #eef1f5;
    color: #596578;

    display: flex;
    align-items: center;
    justify-content: center;

    font-size: 11px;
}}

.history-content {{
    padding-bottom: 18px;
}}

.history-row {{
    padding: 13px;

    border: 1px solid #e5e9ef;

    border-radius: 9px;

    margin-bottom: 9px;

    background: #fafbfd;
}}

.history-main {{
    display: flex;
    justify-content: space-between;
    gap: 15px;

    font-size: 12px;
}}

.history-time {{
    color: #7a8493;
    font-family: monospace;
    font-size: 10px;
}}

.history-details {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;

    margin-top: 7px;

    color: #697589;

    font-size: 10px;
}}


/* =========================================================
   EMPTY STATE
   ========================================================= */

.empty-state {{
    background: #ffffff;

    border: 1px dashed #d4dbe5;

    border-radius: 14px;

    padding: 65px 30px;

    text-align: center;
}}

.empty-icon {{
    width: 54px;
    height: 54px;

    border-radius: 15px;

    background: #eef2f7;
    color: #536175;

    margin: 0 auto 14px;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
}}

.empty-state h2 {{
    margin: 0 0 7px;

    font-size: 18px;
}}

.empty-state p {{
    margin: 0 auto;

    max-width: 500px;

    color: #737e8e;

    font-size: 13px;
    line-height: 1.6;
}}


/* =========================================================
   FOOTER
   ========================================================= */

.footer {{
    margin-top: 30px;

    color: #8992a0;

    font-size: 11px;

    text-align: center;
}}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media (max-width: 800px) {{

    .topbar {{
        padding: 15px 18px;
    }}

    .container {{
        width: min(100% - 24px, 1180px);
        padding-top: 25px;
    }}

    .stats {{
        grid-template-columns:
            repeat(2, minmax(0, 1fr));
    }}

    .card-header {{
        flex-direction: column;
    }}

    .status-area {{
        align-items: flex-start;
    }}

    .info-grid,
    .research-routing {{
        grid-template-columns: 1fr;
    }}

}}

@media (max-width: 520px) {{

    .stats {{
        grid-template-columns: 1fr;
    }}

    .header-actions {{
        display: none;
    }}

    .card-header {{
        padding: 18px;
    }}

    .section {{
        padding: 18px;
    }}

    .history-section {{
        padding: 0 18px;
    }}

}}

</style>

</head>


<body>


<!-- =======================================================
     TOP BAR
     ======================================================= -->

<header class="topbar">

    <div class="brand">

        <div class="brand-mark">
            HS
        </div>

        <div>

            <div class="brand-name">
                HeLaSync
            </div>

            <div class="brand-subtitle">
                Research Referral Management
            </div>

        </div>

    </div>


    <div class="header-actions">

        <button
            class="refresh-button"
            onclick="window.location.reload()"
        >
            Refresh Queue
        </button>

    </div>

</header>


<!-- =======================================================
     MAIN
     ======================================================= -->

<main class="container">


    <section class="page-heading">

        <div class="eyebrow">
            RESEARCH OPERATIONS
        </div>

        <h1>
            Referral Queue
        </h1>

        <p>
            Clinical trial referrals generated through the
            HeLaSync CDS Hooks workflow.
        </p>

    </section>


    <!-- ===================================================
         STATISTICS
         =================================================== -->

    <section class="stats">

        <div class="stat-card">

            <div class="stat-label">
                Total Referrals
            </div>

            <div class="stat-number">
                {total}
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Interested
            </div>

            <div class="stat-number">
                {interested}
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Screening
            </div>

            <div class="stat-number">
                {screening}
            </div>

        </div>


        <div class="stat-card">

            <div class="stat-label">
                Enrolled
            </div>

            <div class="stat-number">
                {enrolled}
            </div>

        </div>

    </section>


    <!-- ===================================================
         REFERRALS
         =================================================== -->

    <section>

        {referral_cards}

    </section>


    <div class="footer">

        HeLaSync Research Referral Dashboard · Prototype

    </div>


</main>


<script>

async function updateReferralStatus(referralId) {{

    var selectElement =
        document.getElementById("status-" + referralId);

    if (!selectElement) {{
        alert("Unable to find the selected status.");
        return;
    }}

    var newStatus = selectElement.value;

    if (!newStatus) {{
        alert("Please select a status.");
        return;
    }}

    var button =
        selectElement.parentElement.querySelector(".update-button");

    if (button) {{
        button.disabled = true;
        button.textContent = "Updating...";
    }}

    try {{

        var response = await fetch(
            "/referrals/" +
            encodeURIComponent(referralId) +
            "/status",
            {{
                method: "PATCH",

                headers: {{
                    "Content-Type": "application/json"
                }},

                body: JSON.stringify({{
                    status: newStatus
                }})

            }}
        );


        if (!response.ok) {{

            var errorText = await response.text();

            throw new Error(
                errorText ||
                "Unable to update referral status."
            );

        }}


        /*
         * Reload the page so the server-rendered dashboard
         * reflects the updated referral state.
         */

        window.location.reload();

    }} catch (error) {{

        console.error(error);

        alert(
            "Unable to update referral status. " +
            "Please try again."
        );

        if (button) {{
            button.disabled = false;
            button.textContent = "Update";
        }}

    }}

}}

</script>


</body>

</html>
"""


# ============================================================
# SINGLE REFERRAL JSON VIEW
# ============================================================

@router.get("/research/referrals/{referral_id}")
def research_referral_detail(referral_id: str):

    referral = get_referral(referral_id)

    if not referral:
        raise HTTPException(
            status_code=404,
            detail="Referral not found"
        )

    return referral
