import json
from typing import Any, Dict

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

from research_dashboard import router as research_router


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync clinical trial matching and CDS Hooks API",
    version="1.3.0-STAGE2C",
)


# ============================================================
# RESEARCH REFERRAL DASHBOARD
# ============================================================

app.include_router(research_router)


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
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": "5-agent clinical trial matching pipeline",
        "version": "1.3.0-STAGE2C",
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

        "stage": "2C",
    }


# ============================================================
# PRIVACY GATEWAY ENDPOINT
# ============================================================

@app.post("/privacy/process-patient")
async def process_patient(
    patient_data: Dict[str, Any]
):

    """
    Process patient information through the
    HeLaSync Privacy Gateway.

    The Privacy Gateway is responsible for removing
    or transforming identifying patient information
    before data is passed to the HeLaSync AI pipeline.
    """

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

    """
    CDS Hooks service discovery endpoint.
    """

    return {

        "services": [

            {
                "hook": "patient-view",

                "title":
                    "HeLaSync Clinical Trial Matching",

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
                        "MedicationRequest?patient={{context.patientId}}",
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

    """
    Main HeLaSync CDS Hooks endpoint.

    Flow:

    CDS Hooks Request
            ↓
    Extract FHIR prefetch data
            ↓
    Privacy Gateway
            ↓
    HeLaSync 5-Agent Pipeline
            ↓
    CDS Hooks Card
    """

    try:

        # ----------------------------------------------------
        # 1. Extract request information
        # ----------------------------------------------------

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )


        context = request.get(
            "context",
            {}
        )


        # CDS Hooks userId normally lives inside context.
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


        encounter_id = context.get(
            "encounterId",
            None,
        )


        prefetch = request.get(
            "prefetch",
            {},
        )


        # ----------------------------------------------------
        # 2. Convert prefetch resources into FHIR Bundle
        # ----------------------------------------------------

        entries = []


        for resource_name, resource in prefetch.items():

            if resource is None:
                continue


            # Some CDS Hooks environments return
            # a FHIR Bundle.

            if (
                isinstance(resource, dict)
                and resource.get("resourceType")
                == "Bundle"
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

            "resourceType":
                "Bundle",

            "type":
                "collection",

            "entry":
                entries,
        }


        # ----------------------------------------------------
        # 3. Build patient data for Privacy Gateway
        # ----------------------------------------------------

        patient_data = {

            "patientId":
                patient_id,

            "fhirBundle":
                fhir_bundle,
        }


        # ----------------------------------------------------
        # 4. Process through Privacy Gateway
        # ----------------------------------------------------

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient_data
                )
            )

        except Exception as privacy_error:

            # Keep CDS service operational if Privacy
            # Gateway returns an unexpected format.

            sanitized_patient_data = {

                "patientId":
                    patient_id,

                "fhirBundle":
                    fhir_bundle,

                "privacy_gateway_warning":
                    str(privacy_error),
            }


        # ----------------------------------------------------
        # 5. Convert sanitized data into ADK message
        # ----------------------------------------------------

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )


        prompt = f"""
You are processing a CDS Hooks patient-view request
for HeLaSync.

The following patient information has already passed
through the HeLaSync Privacy Gateway.

Use this information to perform the clinical trial
matching workflow.

Do not expose direct patient identifiers in the CDS card.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(
    context,
    indent=2,
    default=str
)}

Return the final CDS Hooks response generated by
the HeLaSync 5-agent pipeline.

The response must be valid JSON.
"""


        # ----------------------------------------------------
        # 6. Create ADK session
        # ----------------------------------------------------

        session = await session_service.create_session(

            app_name=APP_NAME,

            user_id=user_id,

            session_id=hook_instance,
        )


        # ----------------------------------------------------
        # 7. Create ADK message
        # ----------------------------------------------------

        content = types.Content(

            role="user",

            parts=[
                types.Part(
                    text=prompt
                )
            ],
        )


        # ----------------------------------------------------
        # 8. Run 5-agent pipeline
        # ----------------------------------------------------

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

                        for part
                        in event.content.parts

                        if getattr(
                            part,
                            "text",
                            None
                        )
                    )


        # ----------------------------------------------------
        # 9. Parse Agent 5 output
        # ----------------------------------------------------

        if final_output:

            try:

                result = json.loads(
                    final_output
                )


            except json.JSONDecodeError:

                # Handle accidental Markdown
                # code fences.

                cleaned_output = (
                    final_output
                    .replace(
                        "```json",
                        ""
                    )
                    .replace(
                        "```",
                        ""
                    )
                    .strip()
                )


                try:

                    result = json.loads(
                        cleaned_output
                    )


                except json.JSONDecodeError:

                    result = {

                        "cards": [

                            {

                                "summary":
                                    "HeLaSync Clinical "
                                    "Trial Matching",

                                "indicator":
                                    "warning",

                                "detail": (
                                    "The HeLaSync clinical "
                                    "trial matching pipeline "
                                    "returned an unexpected "
                                    "response format."
                                ),

                                "source": {

                                    "label":
                                        "HeLaSync"
                                },
                            }
                        ]
                    }


        else:

            result = {

                "cards": [

                    {

                        "summary":
                            "HeLaSync Clinical "
                            "Trial Matching",

                        "indicator":
                            "warning",

                        "detail": (
                            "No final response was returned "
                            "by the HeLaSync clinical trial "
                            "matching pipeline."
                        ),

                        "source": {

                            "label":
                                "HeLaSync"
                        },
                    }
                ]
            }


        # ----------------------------------------------------
        # 10. Get CDS cards
        # ----------------------------------------------------

        cards = result.get(
            "cards",
            []
        )


        # ----------------------------------------------------
        # 11. Force Additional Information link
        # ----------------------------------------------------

        for card in cards:

            card["links"] = [

                {

                    "label":
                        "Additional Information",

                    "url":
                        "https://helasync.app/launch",

                    "type":
                        "absolute",
                }
            ]


        # ----------------------------------------------------
        # 12. Return CDS Hooks response
        # ----------------------------------------------------

        return {
            "cards": cards
        }


    except Exception as e:

        # ----------------------------------------------------
        # ERROR RESPONSE
        # ----------------------------------------------------

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
# STAGE 2C — CREATE REFERRAL
# ============================================================

@app.post("/referrals")
async def create_referral_endpoint(
    referral_request: Dict[str, Any]
):

    """
    Create a HeLaSync clinical trial referral.

    This endpoint is used by the referral workflow
    after a clinician expresses interest in a trial.
    """

    trial_id = referral_request.get(
        "trial_id"
    )

    patient_id = referral_request.get(
        "patient_id"
    )

    clinician_id = referral_request.get(
        "clinician_id"
    )

    encounter_id = referral_request.get(
        "encounter_id"
    )

    source = referral_request.get(
        "source",
        "CDS Hooks",
    )

    patient_data = referral_request.get(
        "patient_data",
        {},
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

            source=source,

            patient_data=patient_data,
        )


        return referral


    except ValueError as e:

        return {

            "status": "error",

            "message":
                str(e),
        }


    except Exception as e:

        return {

            "status": "error",

            "message":
                "Unable to create referral",

            "detail":
                str(e),
        }


# ============================================================
# STAGE 2C — GET SINGLE REFERRAL
# ============================================================

@app.get("/referrals/{referral_id}")
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
# STAGE 2C — LIST REFERRALS
# ============================================================

@app.get("/referrals")
async def list_referrals_endpoint():

    return list_referrals()
