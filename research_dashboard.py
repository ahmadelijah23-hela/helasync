from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from referral import get_referral, list_referrals


router = APIRouter()


# ============================================================
# RESEARCH REFERRAL DASHBOARD
# ============================================================

@router.get("/research/referrals", response_class=HTMLResponse)
async def research_referral_dashboard():

    return """
<!DOCTYPE html>
<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>HeLaSync Research Referrals</title>

    <style>

        body {
            font-family: Arial, sans-serif;
            background: #f5f7fa;
            margin: 0;
            padding: 0;
            color: #1f2937;
        }

        .header {
            background: #111827;
            color: white;
            padding: 24px 40px;
        }

        .header h1 {
            margin: 0;
            font-size: 28px;
        }

        .header p {
            margin: 8px 0 0;
            color: #d1d5db;
        }

        .container {
            max-width: 1200px;
            margin: 30px auto;
            padding: 0 20px;
        }

        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .toolbar h2 {
            margin: 0;
        }

        .refresh-button {
            border: none;
            background: #2563eb;
            color: white;
            padding: 10px 16px;
            border-radius: 6px;
            cursor: pointer;
        }

        .refresh-button:hover {
            background: #1d4ed8;
        }

        .referral-card {
            background: white;
            border-radius: 10px;
            padding: 24px;
            margin-bottom: 18px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }

        .top-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 20px;
        }

        .trial-name {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 6px;
        }

        .trial-id {
            color: #6b7280;
            font-size: 14px;
        }

        .status {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            background: #dbeafe;
            color: #1e40af;
            font-size: 12px;
            font-weight: bold;
        }

        .details {
            margin-top: 20px;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }

        .detail-box {
            background: #f9fafb;
            padding: 14px;
            border-radius: 6px;
        }

        .label {
            font-size: 12px;
            color: #6b7280;
            margin-bottom: 5px;
        }

        .value {
            font-size: 15px;
            font-weight: 500;
        }

        .actions {
            margin-top: 22px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .action-button {
            border: none;
            padding: 10px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
        }

        .review {
            background: #2563eb;
            color: white;
        }

        .contact {
            background: #059669;
            color: white;
        }

        .screening {
            background: #7c3aed;
            color: white;
        }

        .enrolled {
            background: #16a34a;
            color: white;
        }

        .not-eligible {
            background: #dc2626;
            color: white;
        }

        .empty {
            background: white;
            padding: 40px;
            text-align: center;
            border-radius: 10px;
            color: #6b7280;
        }

        .referral-id {
            margin-top: 18px;
            font-family: monospace;
            background: #f3f4f6;
            padding: 8px;
            border-radius: 5px;
            display: inline-block;
        }

    </style>

</head>


<body>


<div class="header">

    <h1>HeLaSync Research Referrals</h1>

    <p>
        Clinical trial referral work queue
    </p>

</div>


<div class="container">


    <div class="toolbar">

        <h2>Referral Queue</h2>

        <button
            class="refresh-button"
            onclick="loadReferrals()">

            Refresh

        </button>

    </div>


    <div id="referrals">

        Loading referrals...

    </div>


</div>


<script>


async function loadReferrals() {

    const container =
        document.getElementById("referrals");

    try {

        const response =
            await fetch("/referrals");

        const referrals =
            await response.json();


        if (!referrals || referrals.length === 0) {

            container.innerHTML = `
                <div class="empty">
                    No referrals currently available.
                </div>
            `;

            return;
        }


        container.innerHTML =
            referrals.map(renderReferral).join("");


    } catch (error) {

        container.innerHTML = `
            <div class="empty">
                Unable to load referrals.
            </div>
        `;

    }

}


function renderReferral(referral) {

    const trial =
        referral.trial || {};

    const patient =
        referral.patient || {};

    const clinician =
        referral.clinician || {};

    const routing =
        referral.routing || {};


    return `

        <div class="referral-card">

            <div class="top-row">

                <div>

                    <div class="trial-name">

                        ${trial.trial_name || "Clinical Trial"}

                    </div>

                    <div class="trial-id">

                        ${trial.trial_id || ""}

                    </div>

                </div>


                <div>

                    <span class="status">

                        ${referral.status || "UNKNOWN"}

                    </span>

                </div>

            </div>


            <div class="details">


                <div class="detail-box">

                    <div class="label">
                        Patient
                    </div>

                    <div class="value">

                        ${patient.patient_id || "Unknown"}

                    </div>

                </div>


                <div class="detail-box">

                    <div class="label">
                        Referring Clinician
                    </div>

                    <div class="value">

                        ${clinician.clinician_id || "Unknown"}

                    </div>

                </div>


                <div class="detail-box">

                    <div class="label">
                        Encounter
                    </div>

                    <div class="value">

                        ${referral.encounter_id || "Unknown"}

                    </div>

                </div>


                <div class="detail-box">

                    <div class="label">
                        Research Team
                    </div>

                    <div class="value">

                        ${routing.research_team || "Unknown"}

                    </div>

                </div>


            </div>


            <div class="referral-id">

                Referral ID:
                ${referral.referral_id}

            </div>


            <div class="actions">


                <button
                    class="action-button review"
                    onclick="updateStatus(
                        '${referral.referral_id}',
                        'UNDER_REVIEW'
                    )">

                    Under Review

                </button>


                <button
                    class="action-button contact"
                    onclick="updateStatus(
                        '${referral.referral_id}',
                        'CONTACTED'
                    )">

                    Contacted

                </button>


                <button
                    class="action-button screening"
                    onclick="updateStatus(
                        '${referral.referral_id}',
                        'SCREENING'
                    )">

                    Screening

                </button>


                <button
                    class="action-button enrolled"
                    onclick="updateStatus(
                        '${referral.referral_id}',
                        'ENROLLED'
                    )">

                    Enrolled

                </button>


                <button
                    class="action-button not-eligible"
                    onclick="updateStatus(
                        '${referral.referral_id}',
                        'NOT_ELIGIBLE'
                    )">

                    Not Eligible

                </button>


            </div>

        </div>

    `;

}


async function updateStatus(
    referralId,
    status
) {

    try {

        const response =
            await fetch(
                `/referrals/${referralId}/status`,
                {
                    method: "PATCH",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        status: status
                    })
                }
            );


        if (!response.ok) {

            alert(
                "Unable to update referral status."
            );

            return;
        }


        await loadReferrals();


    } catch (error) {

        alert(
            "Error updating referral."
        );

    }

}


loadReferrals();


</script>


</body>

</html>
"""


# ============================================================
# REFERRAL STATUS UPDATE
# ============================================================

@router.patch("/referrals/{referral_id}/status")
async def update_referral_status(
    referral_id: str,
    payload: dict,
):

    referral = get_referral(referral_id)

    if referral is None:

        raise HTTPException(
            status_code=404,
            detail="Referral not found",
        )


    allowed_statuses = {
        "INTERESTED",
        "UNDER_REVIEW",
        "CONTACTED",
        "SCREENING",
        "ENROLLED",
        "NOT_ELIGIBLE",
    }


    new_status = payload.get("status")


    if new_status not in allowed_statuses:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. Allowed values: "
                + ", ".join(sorted(allowed_statuses))
            ),
        )


    referral["status"] = new_status

    return {
        "status": "success",
        "referral": referral,
    }
