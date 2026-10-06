"""
HeLaSync Research Referral Dashboard
-------------------------------------

Clinician/research-team referral work queue.

This dashboard reads referral records from the
HeLaSync in-memory referral service and provides:

- Referral queue
- Trial information
- Patient identifier
- Referring clinician
- Encounter
- Research team
- Referral ID
- Referral status
- Status updates
- Referral history
- Duplicate referral visibility

Prototype only.

Referral persistence is currently in-memory and is
lost when the Render service restarts or redeploys.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from referral import (
    list_referrals,
    get_referral,
    update_referral_status,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# STATUS MODEL
# ============================================================

class ReferralStatusUpdate(BaseModel):
    status: str


# ============================================================
# ALLOWED STATUS VALUES
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
# HTML ESCAPING
# ============================================================

def escape_html(value: Any) -> str:
    """
    Safely escape values before placing them into HTML.
    """

    if value is None:
        return ""

    text = str(value)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


# ============================================================
# STATUS DISPLAY
# ============================================================

def status_class(status: str) -> str:
    """
    Convert referral status into a CSS class.
    """

    normalized = str(
        status or ""
    ).strip().upper()

    mapping = {
        "INTERESTED": "status-interested",
        "UNDER_REVIEW": "status-under-review",
        "CONTACTED": "status-contacted",
        "SCREENING": "status-screening",
        "ENROLLED": "status-enrolled",
        "NOT_ELIGIBLE": "status-not-eligible",
    }

    return mapping.get(
        normalized,
        "status-default",
    )


def status_label(status: str) -> str:
    """
    Convert internal status into human-readable text.
    """

    normalized = str(
        status or ""
    ).strip().upper()

    mapping = {
        "INTERESTED": "Interested",
        "UNDER_REVIEW": "Under Review",
        "CONTACTED": "Contacted",
        "SCREENING": "Screening",
        "ENROLLED": "Enrolled",
        "NOT_ELIGIBLE": "Not Eligible",
    }

    return mapping.get(
        normalized,
        normalized.replace("_", " ").title(),
    )


# ============================================================
# REFERRAL HISTORY SUMMARY
# ============================================================

def duplicate_attempt_count(
    referral: Dict[str, Any],
) -> int:
    """
    Count duplicate referral attempts.
    """

    history = referral.get(
        "referral_history",
        [],
    )

    if not isinstance(history, list):
        return 0

    return sum(
        1
        for event in history
        if isinstance(event, dict)
        and event.get("event")
        == "DUPLICATE_REFERRAL_ATTEMPT"
    )


# ============================================================
# DASHBOARD
# ============================================================

@router.get(
    "/research/referrals",
    response_class=HTMLResponse,
)
async def research_referrals_dashboard():

    return HTMLResponse(
        content="""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
/>

<title>
    HeLaSync Research Referrals
</title>

<style>

    * {
        box-sizing: border-box;
    }

    body {

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

        color: #1f2937;
    }


    /* =====================================================
       HEADER
       ===================================================== */

    .header {

        background: #111827;

        color: white;

        padding:
            26px
            34px;
    }

    .header h1 {

        margin: 0;

        font-size: 28px;

        font-weight: 700;
    }

    .header p {

        margin:
            5px
            0
            0;

        color: #cbd5e1;

        font-size: 14px;
    }


    /* =====================================================
       PAGE
       ===================================================== */

    .container {

        max-width: 1100px;

        margin:
            0
            auto;

        padding:
            30px
            20px;
    }


    /* =====================================================
       TOP BAR
       ===================================================== */

    .queue-header {

        display: flex;

        align-items: center;

        justify-content: space-between;

        margin-bottom: 18px;
    }

    .queue-header h2 {

        margin: 0;

        font-size: 24px;
    }

    .queue-subtitle {

        margin-top: 4px;

        color: #64748b;

        font-size: 14px;
    }

    .refresh-button {

        border: none;

        background: #2563eb;

        color: white;

        border-radius: 6px;

        padding:
            9px
            18px;

        font-weight: 600;

        cursor: pointer;
    }

    .refresh-button:hover {

        background: #1d4ed8;
    }

    .refresh-button:disabled {

        opacity: 0.6;

        cursor: wait;
    }


    /* =====================================================
       SUMMARY
       ===================================================== */

    .summary-bar {

        display: flex;

        gap: 12px;

        margin-bottom: 18px;

        flex-wrap: wrap;
    }

    .summary-box {

        background: white;

        border: 1px solid #e2e8f0;

        border-radius: 8px;

        padding:
            12px
            16px;

        min-width: 150px;
    }

    .summary-label {

        font-size: 12px;

        color: #64748b;

        margin-bottom: 4px;
    }

    .summary-value {

        font-size: 22px;

        font-weight: 700;

        color: #111827;
    }


    /* =====================================================
       REFERRAL CARD
       ===================================================== */

    .referral-card {

        background: white;

        border-radius: 10px;

        border: 1px solid #e2e8f0;

        margin-bottom: 20px;

        padding: 22px;

        box-shadow:
            0
            2px
            8px
            rgba(15, 23, 42, 0.05);
    }


    /* =====================================================
       CARD HEADER
       ===================================================== */

    .card-header {

        display: flex;

        justify-content: space-between;

        align-items: flex-start;

        gap: 20px;

        margin-bottom: 20px;
    }

    .trial-title {

        margin: 0;

        font-size: 21px;

        color: #111827;
    }

    .trial-id {

        margin-top: 5px;

        font-size: 13px;

        color: #64748b;

        font-family: monospace;
    }


    /* =====================================================
       STATUS
       ===================================================== */

    .status-badge {

        display: inline-block;

        padding:
            6px
            12px;

        border-radius: 999px;

        font-size: 12px;

        font-weight: 700;

        text-transform: uppercase;

        white-space: nowrap;
    }

    .status-interested {

        background: #dbeafe;

        color: #1d4ed8;
    }

    .status-under-review {

        background: #fef3c7;

        color: #92400e;
    }

    .status-contacted {

        background: #dcfce7;

        color: #166534;
    }

    .status-screening {

        background: #ede9fe;

        color: #6d28d9;
    }

    .status-enrolled {

        background: #dcfce7;

        color: #15803d;
    }

    .status-not-eligible {

        background: #fee2e2;

        color: #b91c1c;
    }

    .status-default {

        background: #e2e8f0;

        color: #475569;
    }


    /* =====================================================
       INFORMATION GRID
       ===================================================== */

    .info-grid {

        display: grid;

        grid-template-columns:
            repeat(
                2,
                minmax(
                    0,
                    1fr
                )
            );

        gap: 14px;

        margin-bottom: 18px;
    }

    .info-box {

        background: #f8fafc;

        border-radius: 6px;

        padding:
            12px
            14px;
    }

    .info-label {

        font-size: 11px;

        color: #64748b;

        margin-bottom: 5px;
    }

    .info-value {

        font-size: 14px;

        font-weight: 500;

        color: #1e293b;

        word-break: break-word;
    }

    .monospace {

        font-family: monospace;

        font-size: 13px;
    }


    /* =====================================================
       REFERRAL ID
       ===================================================== */

    .referral-id {

        display: inline-block;

        background: #f1f5f9;

        padding:
            7px
            10px;

        border-radius: 5px;

        font-family: monospace;

        font-size: 13px;

        color: #334155;

        margin-bottom: 16px;
    }


    /* =====================================================
       DUPLICATE NOTICE
       ===================================================== */

    .duplicate-notice {

        background: #fff7ed;

        border: 1px solid #fed7aa;

        color: #9a3412;

        border-radius: 6px;

        padding:
            10px
            12px;

        margin-bottom: 16px;

        font-size: 13px;
    }


    /* =====================================================
       STATUS CONTROLS
       ===================================================== */

    .status-controls {

        display: flex;

        flex-wrap: wrap;

        gap: 8px;

        margin-top: 4px;
    }

    .status-button {

        border: none;

        color: white;

        border-radius: 6px;

        padding:
            9px
            14px;

        font-size: 12px;

        font-weight: 600;

        cursor: pointer;
    }

    .status-button:hover {

        opacity: 0.9;
    }

    .status-button:disabled {

        opacity: 0.45;

        cursor: not-allowed;
    }

    .button-review {

        background: #2563eb;
    }

    .button-contacted {

        background: #059669;
    }

    .button-screening {

        background: #7c3aed;
    }

    .button-enrolled {

        background: #16a34a;
    }

    .button-not-eligible {

        background: #dc2626;
    }


    /* =====================================================
       HISTORY
       ===================================================== */

    .history-section {

        margin-top: 20px;

        border-top:
            1px
            solid
            #e2e8f0;

        padding-top: 16px;
    }

    .history-title {

        font-size: 14px;

        font-weight: 700;

        margin-bottom: 10px;
    }

    .history-event {

        padding:
            8px
            0;

        border-bottom:
            1px
            solid
            #f1f5f9;

        font-size: 12px;

        color: #475569;
    }

    .history-event:last-child {

        border-bottom: none;
    }

    .history-event strong {

        color: #1e293b;
    }


    /* =====================================================
       EMPTY STATE
       ===================================================== */

    .empty-state {

        background: white;

        border:
            1px
            solid
            #e2e8f0;

        border-radius: 10px;

        padding:
            50px
            20px;

        text-align: center;

        color: #64748b;
    }


    /* =====================================================
       ERROR
       ===================================================== */

    .error-state {

        background: #fef2f2;

        border:
            1px
            solid
            #fecaca;

        color: #b91c1c;

        border-radius: 8px;

        padding: 20px;

        margin-bottom: 20px;
    }


    /* =====================================================
       LOADING
       ===================================================== */

    .loading {

        background: white;

        border:
            1px
            solid
            #e2e8f0;

        border-radius: 10px;

        padding:
            35px;

        text-align: center;

        color: #64748b;
    }


    /* =====================================================
       RESPONSIVE
       ===================================================== */

    @media (
        max-width: 700px
    ) {

        .info-grid {

            grid-template-columns: 1fr;
        }

        .card-header {

            flex-direction: column;
        }

        .container {

            padding:
                20px
                14px;
        }

        .header {

            padding:
                22px
                18px;
        }

    }

</style>

</head>


<body>


<!-- =====================================================
     HEADER
     ===================================================== -->

<header class="header">

    <h1>
        HeLaSync Research Referrals
    </h1>

    <p>
        Clinical trial referral work queue
    </p>

</header>


<!-- =====================================================
     MAIN
     ===================================================== -->

<main class="container">


    <!-- =================================================
         QUEUE HEADER
         ================================================= -->

    <div class="queue-header">

        <div>

            <h2>
                Referral Queue
            </h2>

            <div
                class="queue-subtitle"
                id="last-updated"
            >
                Loading referrals...
            </div>

        </div>


        <button
            id="refresh-button"
            class="refresh-button"
            onclick="loadReferrals()"
        >
            Refresh
        </button>

    </div>


    <!-- =================================================
         SUMMARY
         ================================================= -->

    <div
        id="summary-bar"
        class="summary-bar"
        style="display:none;"
    ></div>


    <!-- =================================================
         REFERRAL CONTENT
         ================================================= -->

    <div id="content">

        <div class="loading">

            Loading referral queue...

        </div>

    </div>


</main>


<script>


// ========================================================
// CONFIGURATION
// ========================================================

const REFERRALS_ENDPOINT = "/referrals";

const STATUS_ENDPOINT = "/referrals";


// ========================================================
// HTML ESCAPE
// ========================================================

function escapeHtml(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";

    }

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


// ========================================================
// STATUS LABEL
// ========================================================

function statusLabel(status) {

    const labels = {

        "INTERESTED":
            "Interested",

        "UNDER_REVIEW":
            "Under Review",

        "CONTACTED":
            "Contacted",

        "SCREENING":
            "Screening",

        "ENROLLED":
            "Enrolled",

        "NOT_ELIGIBLE":
            "Not Eligible"

    };

    return labels[status]
        || String(status || "")
            .replaceAll("_", " ")
            .replace(
                /\b\w/g,
                c => c.toUpperCase()
            );
}


// ========================================================
// STATUS CSS
// ========================================================

function statusClass(status) {

    const classes = {

        "INTERESTED":
            "status-interested",

        "UNDER_REVIEW":
            "status-under-review",

        "CONTACTED":
            "status-contacted",

        "SCREENING":
            "status-screening",

        "ENROLLED":
            "status-enrolled",

        "NOT_ELIGIBLE":
            "status-not-eligible"

    };

    return classes[status]
        || "status-default";
}


// ========================================================
// FORMAT DATE
// ========================================================

function formatDate(value) {

    if (!value) {

        return "—";

    }

    try {

        return new Date(value)
            .toLocaleString(
                undefined,
                {
                    dateStyle: "medium",
                    timeStyle: "short"
                }
            );

    } catch (error) {

        return value;

    }
}


// ========================================================
// LOAD REFERRALS
// ========================================================

async function loadReferrals() {

    const content =
        document.getElementById(
            "content"
        );

    const refreshButton =
        document.getElementById(
            "refresh-button"
        );

    const lastUpdated =
        document.getElementById(
            "last-updated"
        );


    refreshButton.disabled = true;

    refreshButton.textContent =
        "Refreshing...";


    content.innerHTML = `
        <div class="loading">
            Loading referral queue...
        </div>
    `;


    try {

        const response =
            await fetch(
                REFERRALS_ENDPOINT,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    },
                    cache: "no-store"
                }
            );


        if (!response.ok) {

            throw new Error(
                `Referral API returned HTTP ${response.status}`
            );

        }


        const data =
            await response.json();


        // ------------------------------------------------
        // The current referral.py returns a LIST.
        //
        // We also support the older object format:
        //
        // {
        //     "count": 1,
        //     "referrals": [...]
        // }
        // ------------------------------------------------

        let referrals = [];


        if (Array.isArray(data)) {

            referrals = data;

        }

        else if (
            data &&
            Array.isArray(
                data.referrals
            )
        ) {

            referrals =
                data.referrals;

        }

        else {

            throw new Error(
                "Unexpected referral API response format."
            );

        }


        renderSummary(
            referrals
        );


        renderReferrals(
            referrals
        );


        lastUpdated.textContent =
            `Last updated: ${new Date().toLocaleString()}`;


    }

    catch (error) {

        console.error(
            "Unable to load referrals:",
            error
        );


        content.innerHTML = `

            <div class="error-state">

                <strong>
                    Unable to load referrals.
                </strong>

                <div style="margin-top:8px;">

                    ${escapeHtml(
                        error.message
                    )}

                </div>

            </div>

        `;


        lastUpdated.textContent =
            "Unable to load referral data.";

    }

    finally {

        refreshButton.disabled =
            false;

        refreshButton.textContent =
            "Refresh";

    }

}


// ========================================================
// SUMMARY
// ========================================================

function renderSummary(
    referrals
) {

    const summaryBar =
        document.getElementById(
            "summary-bar"
        );


    const total =
        referrals.length;


    const interested =
        referrals.filter(
            r =>
                r.status ===
                "INTERESTED"
        ).length;


    const underReview =
        referrals.filter(
            r =>
                r.status ===
                "UNDER_REVIEW"
        ).length;


    const screening =
        referrals.filter(
            r =>
                r.status ===
                "SCREENING"
        ).length;


    const enrolled =
        referrals.filter(
            r =>
                r.status ===
                "ENROLLED"
        ).length;


    summaryBar.style.display =
        "flex";


    summaryBar.innerHTML = `

        <div class="summary-box">

            <div class="summary-label">
                Total Referrals
            </div>

            <div class="summary-value">
                ${total}
            </div>

        </div>


        <div class="summary-box">

            <div class="summary-label">
                Interested
            </div>

            <div class="summary-value">
                ${interested}
            </div>

        </div>


        <div class="summary-box">

            <div class="summary-label">
                Under Review
            </div>

            <div class="summary-value">
                ${underReview}
            </div>

        </div>


        <div class="summary-box">

            <div class="summary-label">
                Screening
            </div>

            <div class="summary-value">
                ${screening}
            </div>

        </div>


        <div class="summary-box">

            <div class="summary-label">
                Enrolled
            </div>

            <div class="summary-value">
                ${enrolled}
            </div>

        </div>

    `;

}


// ========================================================
// RENDER REFERRALS
// ========================================================

function renderReferrals(
    referrals
) {

    const content =
        document.getElementById(
            "content"
        );


    if (
        !referrals ||
        referrals.length === 0
    ) {

        content.innerHTML = `

            <div class="empty-state">

                <h3>
                    No referrals
                </h3>

                <p>
                    There are currently no clinical
                    trial referrals in the queue.
                </p>

            </div>

        `;

        return;

    }


    // Newest first.

    referrals.sort(
        (
            a,
            b
        ) => {

            const dateA =
                new Date(
                    a.created_at || 0
                );

            const dateB =
                new Date(
                    b.created_at || 0
                );

            return dateB - dateA;

        }
    );


    content.innerHTML =
        referrals
            .map(
                referral =>
                    renderReferralCard(
                        referral
                    )
            )
            .join("");

}


// ========================================================
// RENDER ONE REFERRAL
// ========================================================

function renderReferralCard(
    referral
) {

    const status =
        String(
            referral.status ||
            "INTERESTED"
        ).toUpperCase();


    const duplicateCount =
        getDuplicateCount(
            referral
        );


    const history =
        Array.isArray(
            referral.referral_history
        )
            ? referral.referral_history
            : [];


    const historyHtml =
        renderHistory(
            history
        );


    return `

        <section
            class="referral-card"
            data-referral-id="${escapeHtml(
                referral.referral_id
            )}"
        >


            <!-- =========================================
                 CARD HEADER
                 ========================================= -->

            <div class="card-header">

                <div>

                    <h3
                        class="trial-title"
                    >
                        ${escapeHtml(
                            referral.trial_name
                            || "Clinical Trial"
                        )}
                    </h3>


                    <div
                        class="trial-id"
                    >
                        ${escapeHtml(
                            referral.trial_id
                            || "No trial ID"
                        )}
                    </div>

                </div>


                <div>

                    <span
                        class="status-badge ${statusClass(
                            status
                        )}"
                    >
                        ${escapeHtml(
                            statusLabel(
                                status
                            )
                        )}
                    </span>

                </div>

            </div>


            <!-- =========================================
                 INFORMATION
                 ========================================= -->

            <div class="info-grid">


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Patient
                    </div>

                    <div
                        class="info-value monospace"
                    >
                        ${escapeHtml(
                            referral.patient_id
                            || "Not provided"
                        )}
                    </div>

                </div>


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Referring Clinician
                    </div>

                    <div
                        class="info-value"
                    >
                        ${escapeHtml(
                            referral.clinician_id
                            || "Not provided"
                        )}
                    </div>

                </div>


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Encounter
                    </div>

                    <div
                        class="info-value monospace"
                    >
                        ${escapeHtml(
                            referral.encounter_id
                            || "Not provided"
                        )}
                    </div>

                </div>


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Research Team
                    </div>

                    <div
                        class="info-value"
                    >
                        ${escapeHtml(
                            referral.research_team
                            || "Not provided"
                        )}
                    </div>

                </div>


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Research Email
                    </div>

                    <div
                        class="info-value"
                    >
                        ${escapeHtml(
                            referral.research_email
                            || "Not provided"
                        )}
                    </div>

                </div>


                <div class="info-box">

                    <div
                        class="info-label"
                    >
                        Created
                    </div>

                    <div
                        class="info-value"
                    >
                        ${escapeHtml(
                            formatDate(
                                referral.created_at
                            )
                        )}
                    </div>

                </div>


            </div>


            <!-- =========================================
                 REFERRAL ID
                 ========================================= -->

            <div>

                <span
                    class="referral-id"
                >
                    Referral ID:
                    ${escapeHtml(
                        referral.referral_id
                        || "Unknown"
                    )}
                </span>

            </div>


            <!-- =========================================
                 DUPLICATE NOTICE
                 ========================================= -->

            ${
                duplicateCount > 0
                    ? `

                        <div
                            class="duplicate-notice"
                        >

                            <strong>
                                Duplicate protection:
                            </strong>

                            ${duplicateCount}
                            duplicate referral
                            ${
                                duplicateCount === 1
                                    ? "attempt"
                                    : "attempts"
                            }
                            detected for this
                            patient/trial combination.
                            No additional referral
                            was created.

                        </div>

                      `
                    : ""
            }


            <!-- =========================================
                 STATUS CONTROLS
                 ========================================= -->

            <div
                class="status-controls"
            >


                <button
                    class="status-button button-review"
                    onclick="updateStatus(
                        '${escapeJs(
                            referral.referral_id
                        )}',
                        'UNDER_REVIEW'
                    )"
                    ${status === "UNDER_REVIEW"
                        ? "disabled"
                        : ""}
                >
                    Under Review
                </button>


                <button
                    class="status-button button-contacted"
                    onclick="updateStatus(
                        '${escapeJs(
                            referral.referral_id
                        )}',
                        'CONTACTED'
                    )"
                    ${status === "CONTACTED"
                        ? "disabled"
                        : ""}
                >
                    Contacted
                </button>


                <button
                    class="status-button button-screening"
                    onclick="updateStatus(
                        '${escapeJs(
                            referral.referral_id
                        )}',
                        'SCREENING'
                    )"
                    ${status === "SCREENING"
                        ? "disabled"
                        : ""}
                >
                    Screening
                </button>


                <button
                    class="status-button button-enrolled"
                    onclick="updateStatus(
                        '${escapeJs(
                            referral.referral_id
                        )}',
                        'ENROLLED'
                    )"
                    ${status === "ENROLLED"
                        ? "disabled"
                        : ""}
                >
                    Enrolled
                </button>


                <button
                    class="status-button button-not-eligible"
                    onclick="updateStatus(
                        '${escapeJs(
                            referral.referral_id
                        )}',
                        'NOT_ELIGIBLE'
                    )"
                    ${status === "NOT_ELIGIBLE"
                        ? "disabled"
                        : ""}
                >
                    Not Eligible
                </button>


            </div>


            <!-- =========================================
                 HISTORY
                 ========================================= -->

            ${
                history.length > 0
                    ? `

                        <div
                            class="history-section"
                        >

                            <div
                                class="history-title"
                            >
                                Referral History
                            </div>

                            ${historyHtml}

                        </div>

                      `
                    : ""
            }


        </section>

    `;

}


// ========================================================
// JAVASCRIPT ESCAPE
// ========================================================

function escapeJs(
    value
) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";

    }


    return String(value)

        .replaceAll(
            "\\",
            "\\\\"
        )

        .replaceAll(
            "'",
            "\\'"
        )

        .replaceAll(
            "\n",
            "\\n"
        )

        .replaceAll(
            "\r",
            "\\r"
        );

}


// ========================================================
// DUPLICATE COUNT
// ========================================================

function getDuplicateCount(
    referral
) {

    const history =
        Array.isArray(
            referral.referral_history
        )
            ? referral.referral_history
            : [];


    return history.filter(
        event =>
            event &&
            event.event ===
                "DUPLICATE_REFERRAL_ATTEMPT"
    ).length;

}


// ========================================================
// HISTORY
// ========================================================

function renderHistory(
    history
) {

    return history
        .slice()
        .reverse()
        .map(
            event => {

                if (!event) {

                    return "";

                }


                const eventType =
                    event.event
                    || "EVENT";


                let description =
                    eventType;


                if (
                    eventType ===
                    "REFERRAL_CREATED"
                ) {

                    description =
                        "Referral created";

                }


                else if (
                    eventType ===
                    "DUPLICATE_REFERRAL_ATTEMPT"
                ) {

                    description =
                        "Duplicate referral attempt detected";

                }


                else if (
                    eventType ===
                    "STATUS_CHANGED"
                ) {

                    description =
                        `Status changed from ${
                            event.previous_status
                            || "unknown"
                        } to ${
                            event.new_status
                            || "unknown"
                        }`;

                }


                return `

                    <div
                        class="history-event"
                    >

                        <strong>
                            ${escapeHtml(
                                description
                            )}
                        </strong>

                        <br>

                        ${escapeHtml(
                            formatDate(
                                event.timestamp
                            )
                        )}

                        ${
                            event.clinician_id
                                ? `
                                    <br>
                                    Clinician:
                                    ${escapeHtml(
                                        event.clinician_id
                                    )}
                                  `
                                : ""
                        }

                        ${
                            event.encounter_id
                                ? `
                                    <br>
                                    Encounter:
                                    ${escapeHtml(
                                        event.encounter_id
                                    )}
                                  `
                                : ""
                        }

                    </div>

                `;

            }
        )
        .join("");

}


// ========================================================
// UPDATE STATUS
// ========================================================

async function updateStatus(
    referralId,
    newStatus
) {

    if (!referralId) {

        alert(
            "Referral ID is missing."
        );

        return;

    }


    if (
        ![
            "UNDER_REVIEW",
            "CONTACTED",
            "SCREENING",
            "ENROLLED",
            "NOT_ELIGIBLE"
        ].includes(
            newStatus
        )
    ) {

        alert(
            "Invalid referral status."
        );

        return;

    }


    try {

        const response =
            await fetch(
                `${STATUS_ENDPOINT}/${
                    encodeURIComponent(
                        referralId
                    )
                }/status`,
                {
                    method: "PATCH",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Accept":
                            "application/json"
                    },

                    body: JSON.stringify(
                        {
                            status:
                                newStatus
                        }
                    )
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.message
                || data.detail
                || "Unable to update referral status."
            );

        }


        await loadReferrals();


    }

    catch (error) {

        console.error(
            "Status update failed:",
            error
        );


        alert(
            `Unable to update referral status:\n\n${
                error.message
            }`
        );

    }

}


// ========================================================
// INITIAL LOAD
// ========================================================

document.addEventListener(
    "DOMContentLoaded",
    () => {

        loadReferrals();

    }
);


</script>


</body>

</html>
"""
    )


# ============================================================
# STATUS UPDATE API
# ============================================================

@router.patch(
    "/referrals/{referral_id}/status"
)
async def update_referral_status_endpoint(
    referral_id: str,
    payload: ReferralStatusUpdate,
):
    """
    Update a referral's status.

    Example:

    PATCH /referrals/HSR-12345678/status

    {
        "status": "SCREENING"
    }
    """

    normalized_status = str(
        payload.status or ""
    ).strip().upper()


    if normalized_status not in ALLOWED_STATUSES:

        raise HTTPException(
            status_code=400,

            detail=(
                f"Invalid status "
                f"'{normalized_status}'. "
                f"Allowed statuses: "
                f"{', '.join(
                    sorted(
                        ALLOWED_STATUSES
                    )
                )}"
            ),
        )


    existing_referral = get_referral(
        referral_id
    )


    if existing_referral is None:

        raise HTTPException(
            status_code=404,

            detail=(
                f"Referral "
                f"'{referral_id}' "
                f"was not found."
            ),
        )


    try:

        updated_referral = (
            update_referral_status(
                referral_id=
                    referral_id,

                status=
                    normalized_status,
            )
        )


        return {
            "status": "success",
            "message":
                "Referral status updated.",
            "referral":
                updated_referral,
        }


    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


# ============================================================
# SINGLE REFERRAL JSON ENDPOINT
# ============================================================

@router.get(
    "/research/referrals/{referral_id}"
)
async def research_referral_detail(
    referral_id: str,
):
    """
    Return one referral for research-team tooling.
    """

    referral = get_referral(
        referral_id
    )


    if referral is None:

        raise HTTPException(
            status_code=404,

            detail=(
                f"Referral "
                f"'{referral_id}' "
                f"was not found."
            ),
        )


    return referral
