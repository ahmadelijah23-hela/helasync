import json
from typing import Any, Dict
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent

from privacy.gateway import PrivacyGateway

from referral import (
    create_referral,
    get_referral,
    list_referrals,
)

from research_dashboard import (
    router as research_router,
)

from referral_launch import (
    router as referral_launch_router,
)


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="HeLaSync API",
    description=(
        "HeLaSync clinical trial matching, "
        "CDS Hooks, and clinical research referral API"
    ),
    version="1.4.0-STAGE2D",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PRIVACY GATEWAY
# ============================================================

privacy_gateway = PrivacyGateway()


# ============================================================
# GOOGLE ADK
# ============================================================

APP_NAME = "helasync"

session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


# ============================================================
# RESEARCH REFERRAL DASHBOARD
# ============================================================

app.include_router(research_router)


# ============================================================
# SMART APP / REFERRAL LAUNCH
# ============================================================

app.include_router(referral_launch_router)


# ============================================================
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": "5-agent clinical trial matching pipeline",
        "version": "1.4.0-STAGE2D",
    }


# ============================================================
# AGENT STATUS
# ============================================================

@app.get("/agent-status")
async def agent_status():

    return {
        "status": "healthy",
        "pipeline": [
            "Patient_Data_Agent",
            "Clinical_Profile_Agent",
            "Trial_Matching_Agent",
            "Eligibility_Verification_Agent",
            "CDS_Card_Agent",
        ],
    }


# ============================================================
# PRIVACY GATEWAY ENDPOINT
# ============================================================

@app.post("/privacy/process-patient")
async def process_patient(
    patient_data: Dict[str, Any]
):

    try:

        sanitized_data = (
            privacy_gateway.process_patient(
                patient_data
            )
        )

        return {
            "status": "success",
            "privacy_processed": True,
            "data": sanitized_data,
        }

    except Exception as e:

        return {
            "status": "error",
            "privacy_processed": False,
            "error": str(e),
        }


# ============================================================
# CDS HOOKS SERVICE DISCOVERY
# ============================================================

@app.get("/cds-services")
async def cds_services():

    return {

        "services": [

            {
                "hook": "patient-view",

                "title": (
                    "HeLaSync Clinical Trial Matching"
                ),

                "description": (
                    "Identifies potentially relevant "
                    "clinical trials from the patient's "
                    "available clinical information."
                ),

                "id": "helasync",

                "prefetch": {

                    "patient":
                        "Patient/{{context.patientId}}",

                    "conditions":
                        "Condition?patient={{context.patientId}}",

                    "observations":
                        "Observation?patient={{context.patientId}}",

                    "medications":
                        "MedicationRequest?"
                        "patient={{context.patientId}}",

                },

            }

        ]

    }


# ============================================================
# HELASYNC CDS HOOK
# ============================================================

@app.post("/cds-services/helasync")
async def helasync_cds(
    request: Dict[str, Any]
):

    try:

        # ====================================================
        # 1. EXTRACT REQUEST INFORMATION
        # ====================================================

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )

        context = request.get(
            "context",
            {},
        )

        user_id = context.get(
            "userId",
            request.get(
                "userId",
                "helasync-clinician",
            ),
        )

        patient_id = context.get(
            "patientId",
            "unknown-patient",
        )

        prefetch = request.get(
            "prefetch",
            {},
        )


        # ====================================================
        # 2. CONVERT PREFETCH DATA INTO FHIR BUNDLE
        # ====================================================

        entries = []

        for resource_name, resource in prefetch.items():

            if resource is None:
                continue

            if (
                isinstance(resource, dict)
                and resource.get("resourceType") == "Bundle"
            ):

                for entry in resource.get(
                    "entry",
                    []
                ):

                    if entry.get("resource"):

                        entries.append(
                            {
                                "resource":
                                    entry["resource"]
                            }
                        )

            else:

                entries.append(
                    {
                        "resource": resource
                    }
                )


        fhir_bundle = {

            "resourceType": "Bundle",

            "type": "collection",

            "entry": entries,

        }


        # ====================================================
        # 3. BUILD PATIENT DATA
        # ====================================================

        patient_data = {

            "patientId":
                patient_id,

            "fhirBundle":
                fhir_bundle,

        }


        # ====================================================
        # 4. PRIVACY GATEWAY
        # ====================================================

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient_data
                )
            )

        except Exception as privacy_error:

            sanitized_patient_data = {

                "patientId":
                    patient_id,

                "fhirBundle":
                    fhir_bundle,

                "privacy_gateway_warning":
                    str(privacy_error),

            }


        # ====================================================
        # 5. BUILD ADK PROMPT
        # ====================================================

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )

        prompt = f"""
You are processing a CDS Hooks patient-view
request for HeLaSync.

The following patient information has already
passed through the HeLaSync Privacy Gateway.

Use this information to perform the clinical
trial matching workflow.

Do not expose direct patient identifiers
in the CDS card.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(context, indent=2, default=str)}

Return the final CDS Hooks response generated
by the HeLaSync 5-agent pipeline.

The response must be valid JSON.
"""


        # ====================================================
        # 6. CREATE ADK SESSION
        # ====================================================

        session = await session_service.create_session(

            app_name=APP_NAME,

            user_id=user_id,

            session_id=hook_instance,

        )


        # ====================================================
        # 7. CREATE ADK MESSAGE
        # ====================================================

        content = types.Content(

            role="user",

            parts=[

                types.Part(
                    text=prompt
                )

            ],

        )


        # ====================================================
        # 8. RUN 5-AGENT PIPELINE
        # ====================================================

        final_output = None

        async for event in runner.run_async(

            user_id=user_id,

            session_id=session.id,

            new_message=content,

        ):

            if event.is_final_response():

                if (
                    event.content
                    and event.content.parts
                ):

                    final_output = "".join(

                        part.text

                        for part in event.content.parts

                        if getattr(
                            part,
                            "text",
                            None
                        )

                    )


        # ====================================================
        # 9. PARSE AGENT 5 OUTPUT
        # ====================================================

        if final_output:

            try:

                result = json.loads(
                    final_output
                )

            except json.JSONDecodeError:

                cleaned_output = (
                    final_output
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )

                try:

                    result = json.loads(
                        cleaned_output
                    )

                except json.JSONDecodeError:

                    result = {
                        "cards": []
                    }

        else:

            result = {
                "cards": []
            }


        # ====================================================
        # 10. GET CDS CARDS
        # ====================================================

        cards = result.get(
            "cards",
            []
        )


        # ====================================================
        # 11. ATTACH SMART APP LINK
        # ====================================================

        for card in cards:

            extension = card.get(
                "extension",
                {}
            )

            trial_id = extension.get(
                "helasync_trial_id"
            )


            # ------------------------------------------------
            # FALLBACK:
            # Try to extract an NCT-style trial ID from
            # the card detail if the extension is unavailable.
            # ------------------------------------------------

            if not trial_id:

                detail = card.get(
                    "detail",
                    ""
                )

                if (
                    "(" in detail
                    and ")" in detail
                ):

                    possible_trial_id = (
                        detail
                        .split("(")[-1]
                        .split(")")[0]
                        .strip()
                    )

                    if possible_trial_id.startswith(
                        "NCT"
                    ):

                        trial_id = (
                            possible_trial_id
                        )


            # ------------------------------------------------
            # BUILD SMART APP URL
            # ------------------------------------------------

            if trial_id:

                referral_url = (
                    "https://helasync.onrender.com"
                    "/referral-launch?"
                    + urlencode(
                        {
                            "trial_id":
                                trial_id,

                            "patient_id":
                                patient_id,

                            "clinician_id":
                                user_id,

                            "encounter_id":
                                hook_instance,

                            "hook_instance":
                                hook_instance,
                        }
                    )
                )


                # --------------------------------------------
                # VIEW TRIAL DETAILS
                # --------------------------------------------

                card["links"] = [

                    {
                        "label":
                            "View Trial Details",

                        "url":
                            referral_url,

                        "type":
                            "absolute",

                    }

                ]


            else:

                # No trial ID means the Smart App cannot
                # be safely constructed.

                card["links"] = []


            # ------------------------------------------------
            # REMOVE INTERNAL METADATA FROM THE FINAL CARD
            # ------------------------------------------------

            if "extension" in card:

                del card["extension"]


        # ====================================================
        # 12. RETURN CDS HOOKS RESPONSE
        # ====================================================

        return {

            "cards":
                cards

        }


    except Exception as e:

        print(
            f"HeLaSync CDS error: {str(e)}"
        )

        return {

            "cards": [

                {

                    "summary":
                        "HeLaSync Service Error",

                    "indicator":
                        "warning",

                    "detail": (
                        "The HeLaSync clinical trial "
                        "matching service encountered "
                        "an error while processing "
                        "this request."
                    ),

                    "source": {

                        "label":
                            "HeLaSync"

                    },

                }

            ]

        }


# ============================================================
# REFERRAL API
# ============================================================

@app.post("/referrals")
async def create_referral_endpoint(
    payload: Dict[str, Any]
):

    trial_id = payload.get(
        "trial_id"
    )

    patient_id = payload.get(
        "patient_id"
    )

    clinician_id = payload.get(
        "clinician_id"
    )

    encounter_id = payload.get(
        "encounter_id"
    )


    if not trial_id:

        return {

            "status": "error",

            "message":
                "trial_id is required",

        }


    if not patient_id:

        return {

            "status": "error",

            "message":
                "patient_id is required",

        }


    try:

        referral = create_referral(

            trial_id=trial_id,

            patient_id=patient_id,

            clinician_id=clinician_id,

            encounter_id=encounter_id,

            source=payload.get(
                "source",
                "CDS Hooks",
            ),

            patient_data=payload.get(
                "patient_data",
                {},
            ),

        )

        return referral


    except ValueError as e:

        return {

            "status": "error",

            "message":
                str(e),

        }


# ============================================================
# GET SINGLE REFERRAL
# ============================================================

@app.get(
    "/referrals/{referral_id}"
)
async def get_referral_endpoint(
    referral_id: str
):

    referral = get_referral(
        referral_id
    )


    if referral is None:

        return {

            "status": "error",

            "message":
                "Referral not found",

        }


    return referral


# ============================================================
# LIST REFERRALS
# ============================================================

@app.get("/referrals")
async def list_referrals_endpoint():

    return list_referrals()
