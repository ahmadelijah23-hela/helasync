from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from referral import create_referral, get_trial_routing


router = APIRouter()


# ============================================================
# REFERRAL LAUNCH PAGE
# ============================================================

@router.get("/referral-launch", response_class=HTMLResponse)
async def referral_launch(
    trial_id: str,
    patient_id: str,
    clinician_id: str = "helasync-clinician",
    encounter_id: str = "helasync-encounter",
    hook_instance: str = "helasync-hook-instance",
):
    """
    Launch the HeLaSync referral workflow from a CDS Hooks card.

    The clinician reviews the trial information and explicitly
    confirms before a referral is created.
    """

    trial = get_trial_routing(trial_id)

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found",
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

    <title>HeLaSync Referral</title>

    <style>

        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
            background: #f5f7fa;
            color: #1f2937;
        }}

        .header {{
            background: #111827;
            color: white;
            padding: 24px 40px;
        }}

        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}

        .header p {{
            margin: 8px 0 0;
            color: #d1d5db;
        }}

        .container {{
            max-width: 760px;
            margin: 40px auto;
            padding: 0 20px;
        }}

        .card {{
            background: white;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 3px 12px rgba(0,0,0,0.08);
        }}

        .trial-name {{
            font-size: 26px;
            font-weight: bold;
            margin-bottom: 8px;
        }}

        .trial-id {{
            color: #6b7280;
            margin-bottom: 28px;
        }}

        .section {{
            margin-top: 24px;
        }}

        .section-title {{
            font-size: 14px;
            font-weight: bold;
            color: #6b7280;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}

        .info {{
            background: #f9fafb;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 10px;
        }}

        .label {{
            font-size: 12px;
            color: #6b7280;
            margin-bottom: 4px;
        }}

        .value {{
            font-size: 15px;
            font-weight: 500;
        }}

        .notice {{
            background: #eff6ff;
            border-left: 4px solid #2563eb;
            padding: 16px;
            margin-top: 24px;
            line-height: 1.5;
        }}

        .actions {{
            display: flex;
            gap: 12px;
            margin-top: 30px;
        }}

        button {{
            border: none;
            padding: 12px 20px;
            border-radius: 7px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
        }}

        .submit {{
            background: #2563eb;
            color: white;
        }}

        .submit:hover {{
            background: #1d4ed8;
        }}

        .cancel {{
            background: #e5e7eb;
            color: #374151;
        }}

        .success {{
            display: none;
            background: #ecfdf5;
            border-left: 4px solid #059669;
            padding: 20px;
            margin-top: 24px;
        }}

        .success h2 {{
            margin-top: 0;
            color: #065f46;
        }}

        .referral-id {{
            font-family: monospace;
            background: #f3f4f6;
            padding: 8px 10px;
            border-radius: 5px;
            display: inline-block;
            margin-top: 8px;
        }}

        .dashboard-link {{
            display: inline-block;
            margin-top: 16px;
            color: #2563eb;
            font-weight: 600;
            text-decoration: none;
        }}

    </style>

</head>

<body>

<div class="header">

    <h1>HeLaSync</h1>

    <p>
        Clinical Trial Referral
    </p>

</div>


<div class="container">

    <div class="card">

        <div class="trial-name">
            {trial["trial_name"]}
        </div>

        <div class="trial-id">
            Trial ID: {trial["trial_id"]}
        </div>


        <div class="section">

            <div class="section-title">
                Referral Information
            </div>

            <div class="info">

                <div class="label">
                    Patient
                </div>

                <div class="value">
                    {patient_id}
                </div>

            </div>


            <div class="info">

                <div class="label">
                    Referring Clinician
                </div>

                <div class="value">
                    {clinician_id}
                </div>

            </div>


            <div class="info">

                <div class="label">
                    Encounter
                </div>

                <div class="value">
                    {encounter_id}
                </div>

            </div>


            <div class="info">

                <div class="label">
                    Research Team
                </div>

                <div class="value">
                    {trial["research_team"]}
                </div>

            </div>

        </div>


        <div class="notice">

            <strong>Clinician confirmation</strong>

            <br><br>

            By selecting
            <strong>Submit Referral</strong>,
            you are indicating that the patient is interested
            in learning more about this clinical research
            opportunity and that the referral should be sent
            to the HeLaSync research team for follow-up.

            <br><br>

            This referral does not represent enrollment or
            final eligibility determination.

        </div>


        <div class="actions">

            <button
                class="submit"
                onclick="submitReferral()"
            >
                Submit Referral
            </button>

            <button
                class="cancel"
                onclick="window.history.back()"
            >
                Cancel
            </button>

        </div>


        <div
            id="success"
            class="success"
        >

            <h2>
                Referral Submitted
            </h2>

            <p>
                The HeLaSync research team has received
                the referral workflow request.
            </p>

            <div>
                Referral ID:
            </div>

            <div
                id="referral-id"
                class="referral-id"
            ></div>

            <br>

            <a
                class="dashboard-link"
                href="/research/referrals"
            >
                Open Research Referral Dashboard
            </a>

        </div>

    </div>

</div>


<script>

async function submitReferral() {{

    const button = document.querySelector(".submit");

    button.disabled = true;

    button.innerText = "Submitting...";


    const payload = {{

        trial_id: "{trial_id}",

        patient_id: "{patient_id}",

        clinician_id: "{clinician_id}",

        encounter_id: "{encounter_id}",

        source: "CDS Hooks",

        hook_instance: "{hook_instance}"

    }};


    try {{

        const response = await fetch(
            "/referrals/from-cds",
            {{

                method: "POST",

                headers: {{
                    "Content-Type": "application/json"
                }},

                body: JSON.stringify(payload)

            }}
        );


        const data = await response.json();


        if (!response.ok) {{

            alert(
                data.detail ||
                "Unable to create referral."
            );

            button.disabled = false;

            button.innerText = "Submit Referral";

            return;

        }}


        document.getElementById(
            "referral-id"
        ).innerText = data.referral.referral_id;


        document.getElementById(
            "success"
        ).style.display = "block";


        button.style.display = "none";

    }} catch (error) {{

        alert(
            "Unable to connect to HeLaSync."
        );

        button.disabled = false;

        button.innerText = "Submit Referral";

    }}

}}

</script>


</body>
</html>
"""


# ============================================================
# CREATE REFERRAL FROM CDS WORKFLOW
# ============================================================

@router.post("/referrals/from-cds")
async def create_referral_from_cds(payload: dict):

    trial_id = payload.get("trial_id")
    patient_id = payload.get("patient_id")

    clinician_id = payload.get(
        "clinician_id",
        "helasync-clinician",
    )

    encounter_id = payload.get(
        "encounter_id",
        "helasync-encounter",
    )

    hook_instance = payload.get(
        "hook_instance",
        "helasync-hook-instance",
    )


    if not trial_id:
        raise HTTPException(
            status_code=400,
            detail="trial_id is required",
        )


    if not patient_id:
        raise HTTPException(
            status_code=400,
            detail="patient_id is required",
        )


    referral = create_referral(

        trial_id=trial_id,

        patient_id=patient_id,

        clinician_id=clinician_id,

        encounter_id=encounter_id,

        source="CDS Hooks",

        patient_data={

            "hook_instance": hook_instance,

        },

    )


    return {

        "status": "success",

        "message": (
            "HeLaSync clinical trial referral created."
        ),

        "referral": referral,

    }
