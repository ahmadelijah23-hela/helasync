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


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync clinical trial matching and CDS Hooks API",
    version="1.2-STAGE2",
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
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": "5-agent clinical trial matching pipeline",
        "version": "1.2-STAGE2",
    }


# ============================================================
# AGENT STATUS
# ============================================================

@app.get("/agent-status")
async def agent_status():

    return {
        "status": "healthy",
        "version": "1.2-STAGE2",
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
                "title": "HeLaSync Clinical Trial Matching",
                "description": (
                    "Identifies potentially relevant clinical trials "
                    "from the patient's available clinical information."
                ),
                "id": "helasync",
                "prefetch": {
                    "patient": "Patient/{{context.patientId}}",
                    "conditions": (
                        "Condition?patient={{context.patientId}}"
                    ),
                    "observations": (
                        "Observation?patient={{context.patientId}}"
                    ),
                    "medications": (
                        "MedicationRequest?patient={{context.patientId}}"
                    ),
                },
            }
        ]
    }


# ============================================================
# STAGE 2
# CREATE HELASYNC REFERRAL
# ============================================================

@app.post("/referrals")
async def create_helasync_referral(
    referral_request: Dict[str, Any]
):

    try:

        # --------------------------------------------------------
        # Extract referral information
        # --------------------------------------------------------

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


        # --------------------------------------------------------
        # Validate trial ID
        # --------------------------------------------------------

        if not trial_id:

            return {
                "status": "error",
                "message": "trial_id is required",
            }


        # --------------------------------------------------------
        # Validate patient ID
        # --------------------------------------------------------

        if not patient_id:

            return {
                "status": "error",
                "message": "patient_id is required",
            }


        # --------------------------------------------------------
        # Create referral
        # --------------------------------------------------------

        referral = create_referral(
            trial_id=trial_id,
            patient_id=patient_id,
            clinician_id=clinician_id,
            encounter_id=encounter_id,
            source="CDS Hooks",
        )


        # --------------------------------------------------------
        # Return referral
        # --------------------------------------------------------

        return {
            "status": "success",
            "message": (
                "HeLaSync clinical trial referral created"
            ),
            "referral": referral,
        }


    except ValueError as e:

        return {
            "status": "error",
            "message": str(e),
        }


    except Exception as e:

        return {
            "status": "error",
            "message": (
                "Unable to create HeLaSync referral"
            ),
            "error": str(e),
        }


# ============================================================
# GET SINGLE REFERRAL
# ============================================================

@app.get("/referrals/{referral_id}")
async def get_helasync_referral(
    referral_id: str
):

    referral = get_referral(
        referral_id
    )

    if referral is None:

        return {
            "status": "not_found",
            "message": "Referral not found",
        }


    return {
        "status": "success",
        "referral": referral,
    }


# ============================================================
# LIST REFERRALS
# ============================================================

@app.get("/referrals")
async def get_helasync_referrals():

    referrals = list_referrals()

    return {
        "status": "success",
        "count": len(referrals),
        "referrals": referrals,
    }


# ============================================================
# HELASYNC CDS HOOK
# ============================================================

@app.post("/cds-services/helasync")
async def helasync_cds(
    request: Dict[str, Any]
):

    try:

        # ========================================================
        # 1. EXTRACT CDS HOOKS REQUEST INFORMATION
        # ========================================================

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )

        user_id = request.get(
            "userId",
            "helasync-clinician",
        )

        context = request.get(
            "context",
            {},
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


        # ========================================================
        # 2. BUILD FHIR BUNDLE
        # ========================================================

        entries = []

        for resource_name, resource in prefetch.items():

            if resource is None:
                continue


            if (
                isinstance(resource, dict)
                and resource.get(
                    "resourceType"
                ) == "Bundle"
            ):

                for entry in resource.get(
                    "entry",
                    []
                ):

                    if entry.get(
                        "resource"
                    ):

                        entries.append(
                            {
                                "resource": entry[
                                    "resource"
                                ]
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


        # ========================================================
        # 3. BUILD PATIENT DATA FOR PRIVACY GATEWAY
        # ========================================================

        patient_data = {
            "patientId": patient_id,
            "fhirBundle": fhir_bundle,
        }


        # ========================================================
        # 4. PRIVACY GATEWAY
        # ========================================================

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient_data
                )
            )

        except Exception as privacy_error:

            sanitized_patient_data = {
                "patientId": patient_id,
                "fhirBundle": fhir_bundle,
                "privacy_gateway_warning": str(
                    privacy_error
                ),
            }


        # ========================================================
        # 5. CREATE PATIENT CONTEXT FOR ADK
        # ========================================================

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )


        prompt = f"""
You are processing a CDS Hooks patient-view request for HeLaSync.

The following patient information has already passed through the
HeLaSync Privacy Gateway.

Use this information to perform the clinical trial matching workflow.

Do not expose direct patient identifiers in the CDS card.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(context, indent=2, default=str)}

Return the final CDS Hooks response generated by the HeLaSync
5-agent pipeline.

The response must be valid JSON.
"""


        # ========================================================
        # 6. CREATE ADK SESSION
        # ========================================================

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=hook_instance,
        )


        # ========================================================
        # 7. CREATE ADK MESSAGE
        # ========================================================

        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=prompt
                )
            ],
        )


        # ========================================================
        # 8. RUN 5-AGENT PIPELINE
        # ========================================================

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


        # ========================================================
        # 9. PARSE AGENT 5 OUTPUT
        # ========================================================

        if final_output:

            try:

                result = json.loads(
                    final_output
                )

            except json.JSONDecodeError:

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
                                "summary": (
                                    "HeLaSync Clinical Trial Matching"
                                ),
                                "indicator": "warning",
                                "detail": (
                                    "The HeLaSync clinical trial "
                                    "matching pipeline returned an "
                                    "unexpected response format."
                                ),
                                "source": {
                                    "label": (
                                        "HeLaSync v1.2-STAGE2"
                                    )
                                },
                            }
                        ]
                    }

        else:

            result = {
                "cards": [
                    {
                        "summary": (
                            "HeLaSync Clinical Trial Matching"
                        ),
                        "indicator": "warning",
                        "detail": (
                            "No final response was returned by "
                            "the HeLaSync clinical trial matching "
                            "pipeline."
                        ),
                        "source": {
                            "label": (
                                "HeLaSync v1.2-STAGE2"
                            )
                        },
                    }
                ]
            }


        # ========================================================
        # 10. GET CDS CARDS
        # ========================================================

        cards = result.get(
            "cards",
            [],
        )


        # ========================================================
        # 11. PRESERVE STAGE 1 LINK
        # ========================================================

        for card in cards:

            card["source"] = {
                "label": "HeLaSync v1.2-STAGE2"
            }

            card["links"] = [
                {
                    "label": "Additional Information",
                    "url": "https://helasync.app/launch",
                    "type": "absolute",
                }
            ]


        # ========================================================
        # 12. RETURN CDS HOOKS RESPONSE
        # ========================================================

        return {
            "cards": cards
        }


    except Exception as e:

        print(
            "HeLaSync CDS Hooks Error:",
            str(e),
        )

        return {
            "cards": [
                {
                    "summary": "HeLaSync Service Error",
                    "indicator": "warning",
                    "detail": (
                        "The HeLaSync clinical trial matching "
                        "service encountered an error while "
                        "processing this request."
                    ),
                    "source": {
                        "label": "HeLaSync v1.2-STAGE2"
                    },
                }
            ]
        }
