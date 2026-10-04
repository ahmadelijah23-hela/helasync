import os
import json
import uuid
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from privacy.gateway import PrivacyGateway
from agent import root_agent


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync Clinical Trial Matching and CDS API",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ENVIRONMENT
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not configured.")


# ============================================================
# PRIVACY GATEWAY
# ============================================================

privacy_gateway = PrivacyGateway()


# ============================================================
# ADK SESSION SERVICE
# ============================================================

session_service = InMemorySessionService()


# ============================================================
# ADK RUNNER
# ============================================================

runner = Runner(
    agent=root_agent,
    app_name="helasync",
    session_service=session_service
)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": "5-agent clinical trial matching pipeline"
    }


# ============================================================
# AGENT STATUS
# ============================================================

@app.get("/agent-status")
def agent_status():

    return {
        "status": "ready",
        "pipeline": "HeLaSync_Pipeline",
        "agents": [
            "Patient_Data_Agent",
            "Clinical_Profile_Agent",
            "Trial_Matching_Agent",
            "Eligibility_Verification_Agent",
            "CDS_Card_Agent"
        ]
    }


# ============================================================
# PRIVACY GATEWAY TEST
# ============================================================

@app.post("/privacy/process-patient")
def process_patient(
    patient: Dict[str, Any]
):

    try:

        sanitized_patient = privacy_gateway.process_patient(
            patient=patient
        )

        return {
            "success": True,
            "patient": sanitized_patient
        }

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# ============================================================
# CDS HOOKS SERVICE DISCOVERY
# ============================================================

@app.get("/cds-services")
def cds_services():

    return {
        "services": [
            {
                "hook": "patient-view",

                "title": "HeLaSync",

                "description": (
                    "HeLaSync identifies potential clinical "
                    "trial opportunities during routine "
                    "patient care."
                ),

                "id": "helasync",

                "prefetch": {

                    "patient":
                        "Patient/{{context.patientId}}",

                    "conditions":
                        "Condition?patient={{context.patientId}}",

                    "medications":
                        "MedicationRequest?patient={{context.patientId}}",

                    "observations":
                        "Observation?patient={{context.patientId}}"
                }
            }
        ]
    }


# ============================================================
# RUN FIVE-AGENT PIPELINE
# ============================================================

async def run_helasync_agents(
    patient_data: Dict[str, Any]
):

    # --------------------------------------------------------
    # Create unique user/session IDs
    # --------------------------------------------------------

    user_id = "helasync-clinician"

    session_id = str(uuid.uuid4())


    # --------------------------------------------------------
    # Create ADK session
    # --------------------------------------------------------

    await session_service.create_session(
        app_name="helasync",
        user_id=user_id,
        session_id=session_id
    )


    # --------------------------------------------------------
    # Convert patient information to JSON
    # --------------------------------------------------------

    patient_json = json.dumps(
        patient_data,
        indent=2,
        default=str
    )


    # --------------------------------------------------------
    # Prompt Agent 1
    # --------------------------------------------------------

    prompt = f"""
You are running the HeLaSync five-agent clinical trial
matching pipeline.

The following is the available patient FHIR information.

IMPORTANT:

- Use only the information provided.
- Do not invent patient information.
- Do not make a final clinical decision.
- Follow the instructions of each HeLaSync agent.

PATIENT FHIR DATA:

{patient_json}

Begin the HeLaSync five-agent pipeline.
"""


    # --------------------------------------------------------
    # Create ADK message
    # --------------------------------------------------------

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=prompt
            )
        ]
    )


    # --------------------------------------------------------
    # Execute SequentialAgent
    # --------------------------------------------------------

    final_text = None

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message
    ):

        # ----------------------------------------------------
        # Look for the final agent response
        # ----------------------------------------------------

        if event.is_final_response():

            if event.content and event.content.parts:

                for part in event.content.parts:

                    if part.text:

                        final_text = part.text


    # --------------------------------------------------------
    # Make sure we received something
    # --------------------------------------------------------

    if not final_text:

        raise RuntimeError(
            "The HeLaSync agent pipeline did not return a response."
        )


    return final_text


# ============================================================
# PARSE CDS CARD
# ============================================================

def parse_agent_response(
    agent_response: str
):

    # --------------------------------------------------------
    # Remove markdown JSON fences if Gemini returns them
    # --------------------------------------------------------

    cleaned = agent_response.strip()

    if cleaned.startswith("```json"):

        cleaned = cleaned[7:]

    elif cleaned.startswith("```"):

        cleaned = cleaned[3:]


    if cleaned.endswith("```"):

        cleaned = cleaned[:-3]


    cleaned = cleaned.strip()


    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        result = json.loads(cleaned)

        return result

    except json.JSONDecodeError:

        # ----------------------------------------------------
        # If the final agent did not return valid JSON,
        # return a safe CDS card instead of crashing.
        # ----------------------------------------------------

        return {
            "cards": [
                {
                    "summary": "HeLaSync",
                    "indicator": "warning",
                    "detail": (
                        "HeLaSync completed the automated "
                        "assessment, but the CDS card could "
                        "not be formatted automatically."
                    ),
                    "source": {
                        "label": "HeLaSync"
                    }
                }
            ]
        }


# ============================================================
# HELASYNC CDS HOOK
# ============================================================

@app.post("/cds-services/helasync")
async def helasync(
    request: Dict[str, Any]
):

    try:

        # ----------------------------------------------------
        # Check Gemini API key
        # ----------------------------------------------------

        if not GEMINI_API_KEY:

            return {
                "cards": [
                    {
                        "summary": "HeLaSync Configuration Error",

                        "indicator": "warning",

                        "detail": (
                            "The Gemini API key has not been "
                            "configured on the HeLaSync server."
                        ),

                        "source": {
                            "label": "HeLaSync"
                        }
                    }
                ]
            }


        # ----------------------------------------------------
        # Get CDS Hooks prefetch
        # ----------------------------------------------------

        prefetch = request.get(
            "prefetch",
            {}
        )


        # ----------------------------------------------------
        # Extract FHIR resources
        # ----------------------------------------------------

        patient = prefetch.get(
            "patient"
        )

        conditions = prefetch.get(
            "conditions",
            {}
        )

        medications = prefetch.get(
            "medications",
            {}
        )

        observations = prefetch.get(
            "observations",
            {}
        )


        # ----------------------------------------------------
        # Check patient
        # ----------------------------------------------------

        if not patient:

            return {
                "cards": [
                    {
                        "summary": "HeLaSync",

                        "indicator": "info",

                        "detail": (
                            "No patient data was available "
                            "for this CDS Hooks request."
                        ),

                        "source": {
                            "label": "HeLaSync"
                        }
                    }
                ]
            }


        # ----------------------------------------------------
        # PRIVACY GATEWAY
        # ----------------------------------------------------

        sanitized_patient = (
            privacy_gateway.process_patient(

                patient=patient,

                conditions=conditions,

                medications=medications,

                observations=observations
            )
        )


        # ----------------------------------------------------
        # Create data package for the agents
        # ----------------------------------------------------

        agent_input = {

            "patient": sanitized_patient,

            "conditions": conditions,

            "medications": medications,

            "observations": observations
        }


        # ----------------------------------------------------
        # Run the five-agent pipeline
        # ----------------------------------------------------

        agent_response = await run_helasync_agents(
            patient_data=agent_input
        )


        # ----------------------------------------------------
        # Parse Agent 5 CDS response
        # ----------------------------------------------------

        cds_response = parse_agent_response(
            agent_response
        )


        # ----------------------------------------------------
        # Return CDS Hooks response
        # ----------------------------------------------------

        return cds_response


    except Exception as e:

        # ----------------------------------------------------
        # Server-side logging
        # ----------------------------------------------------

        print(
            "HeLaSync CDS error:",
            str(e)
        )


        # ----------------------------------------------------
        # Safe CDS response
        # ----------------------------------------------------

        return {

            "cards": [

                {

                    "summary":
                        "HeLaSync",

                    "indicator":
                        "warning",

                    "detail": (
                        "HeLaSync was unable to complete "
                        "the clinical trial assessment."
                    ),

                    "source": {

                        "label":
                            "HeLaSync"
                    }

                }

            ]
        }
