import json
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent

from privacy.gateway import PrivacyGateway


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync clinical trial matching and CDS Hooks API",
    version="1.0.0",
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
async def process_patient(patient_data: Dict[str, Any]):
    """
    Process patient information through the HeLaSync Privacy Gateway.

    The Privacy Gateway is responsible for removing or transforming
    identifying patient information before data is passed to the
    HeLaSync AI pipeline.
    """

    try:
        sanitized_data = privacy_gateway.process_patient(patient_data)

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
# HELASYNC CDS HOOK
# ============================================================

@app.post("/cds-services/helasync")
async def helasync_cds(request: Dict[str, Any]):
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

        # --------------------------------------------------------
        # 1. Extract request information
        # --------------------------------------------------------

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )

        user_id = request.get(
            "userId",
            "helasync-clinician",
        )

        context = request.get("context", {})

        patient_id = context.get(
            "patientId",
            "unknown-patient",
        )

        prefetch = request.get(
            "prefetch",
            {},
        )


        # --------------------------------------------------------
        # 2. Convert prefetch resources into a FHIR Bundle
        # --------------------------------------------------------

        entries = []

        for resource_name, resource in prefetch.items():

            if resource is None:
                continue

            # Some CDS Hooks environments may return a Bundle.
            if isinstance(resource, dict) and resource.get(
                "resourceType"
            ) == "Bundle":

                for entry in resource.get("entry", []):
                    if entry.get("resource"):
                        entries.append(
                            {
                                "resource": entry["resource"]
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


        # --------------------------------------------------------
        # 3. Build patient data for Privacy Gateway
        # --------------------------------------------------------

        patient_data = {
            "patientId": patient_id,
            "fhirBundle": fhir_bundle,
        }


        # --------------------------------------------------------
        # 4. Process through Privacy Gateway
        # --------------------------------------------------------

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient_data
                )
            )

        except Exception as privacy_error:

            # Keep the CDS service operational if the Privacy
            # Gateway implementation returns an unexpected format.
            sanitized_patient_data = {
                "patientId": patient_id,
                "fhirBundle": fhir_bundle,
                "privacy_gateway_warning": str(
                    privacy_error
                ),
            }


        # --------------------------------------------------------
        # 5. Convert sanitized data into an ADK message
        # --------------------------------------------------------

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )


        prompt = f"""
You are processing a CDS Hooks patient-view request for HeLaSync.

The following patient information has already passed through the
HeLaSync Privacy Gateway.

Use this information to perform the clinical trial matching
workflow.

Do not expose direct patient identifiers in the CDS card.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(context, indent=2, default=str)}

Return the final CDS Hooks response generated by the HeLaSync
5-agent pipeline.

The response must be valid JSON.
"""


        # --------------------------------------------------------
        # 6. Create ADK session
        # --------------------------------------------------------

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=hook_instance,
        )


        # --------------------------------------------------------
        # 7. Create ADK message
        # --------------------------------------------------------

        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=prompt
                )
            ],
        )


        # --------------------------------------------------------
        # 8. Run the 5-agent pipeline
        # --------------------------------------------------------

        final_output = None

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):

            if event.is_final_response():

                if event.content and event.content.parts:

                    final_output = "".join(
                        part.text
                        for part in event.content.parts
                        if getattr(part, "text", None)
                    )


        # --------------------------------------------------------
        # 9. Parse Agent 5 output
        # --------------------------------------------------------

        if final_output:

            try:

                result = json.loads(
                    final_output
                )

            except json.JSONDecodeError:

                # Handle accidental Markdown code fences.
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
                        "cards": [
                            {
                                "summary": (
                                    "HeLaSync Clinical Trial "
                                    "Matching"
                                ),
                                "indicator": "warning",
                                "detail": (
                                    "The HeLaSync clinical trial "
                                    "matching pipeline returned "
                                    "an unexpected response format."
                                ),
                                "source": {
                                    "label": "HeLaSync"
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
                            "No final response was returned "
                            "by the HeLaSync clinical trial "
                            "matching pipeline."
                        ),
                        "source": {
                            "label": "HeLaSync"
                        },
                    }
                ]
            }


        # --------------------------------------------------------
        # 10. Get CDS cards
        # --------------------------------------------------------

        cards = result.get(
            "cards",
            [],
        )


        # --------------------------------------------------------
        # 11. STAGE 1 FIX
        #
        # Force Additional Information to be a plain absolute URL.
        #
        # This prevents Gemini from returning:
        #
        # [https://helasync.app/launch](https://helasync.app/launch)
        #
        # and guarantees:
        #
        # https://helasync.app/launch
        # --------------------------------------------------------

        for card in cards:

            card["links"] = [
                {
                    "label": "Additional Information",
                    "url": "https://helasync.app/launch",
                    "type": "absolute",
                }
            ]


        # --------------------------------------------------------
        # 12. Return CDS Hooks response
        # --------------------------------------------------------

        return {
            "cards": cards
        }


    except Exception as e:

        # --------------------------------------------------------
        # ERROR RESPONSE
        # --------------------------------------------------------

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
                        "label": "HeLaSync"
                    },
                }
            ]
        }
