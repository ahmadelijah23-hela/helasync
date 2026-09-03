from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent

import json


# ============================================
# FASTAPI
# ============================================

app = FastAPI(title="HeLaSync CDS Hooks Service")


# ============================================
# CORS
# ============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# ADK SETUP
# ============================================

session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name="helasync",
    session_service=session_service,
)


# ============================================
# HOME
# ============================================

@app.get("/")
def home():
    return {
        "message": "HeLaSync CDS Hooks Service is running"
    }


# ============================================
# CDS HOOKS DISCOVERY
# ============================================

@app.get("/cds-services")
def cds_services():
    return {
        "services": [
            {
                "hook": "patient-view",
                "title": "HeLaSync",
                "description": "HeLaSync clinical trial matching service",
                "id": "helasync"
            }
        ]
    }


# ============================================
# HELASYNC CDS HOOK
# ============================================

@app.post("/cds-services/helasync")
async def helasync(request: Request):

    # ----------------------------------------
    # Receive CDS Hooks request
    # ----------------------------------------

    cds_request = await request.json()

    print("\n================================")
    print("CDS HOOK REQUEST RECEIVED")
    print("================================")

    print(json.dumps(cds_request, indent=2))


    # ----------------------------------------
    # Extract FHIR prefetch data
    # ----------------------------------------

    prefetch = cds_request.get("prefetch", {})

    fhir_bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": []
    }


    # ----------------------------------------
    # Convert prefetch data into FHIR Bundle
    # ----------------------------------------

    for key, resource in prefetch.items():

        if not resource:
            continue

        if not isinstance(resource, dict):
            continue

        # If the resource is already a Bundle
        if resource.get("resourceType") == "Bundle":

            for entry in resource.get("entry", []):
                fhir_bundle["entry"].append(entry)

        # If the resource is a single FHIR resource
        elif resource.get("resourceType"):

            fhir_bundle["entry"].append({
                "resource": resource
            })


    print("\n================================")
    print("FHIR BUNDLE SENT TO HELASYNC")
    print("================================")

    print(json.dumps(fhir_bundle, indent=2))


    # ----------------------------------------
    # Create ADK session
    # ----------------------------------------

    user_id = "helasync-user"

    session_id = cds_request.get(
        "hookInstance",
        "helasync-session"
    )

    try:

        await session_service.create_session(
            app_name="helasync",
            user_id=user_id,
            session_id=session_id
        )

    except Exception:

        # Session already exists
        pass


    # ----------------------------------------
    # Send FHIR Bundle to ADK
    # ----------------------------------------

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=f"""
Run the complete HeLaSync clinical trial matching pipeline.

Use the FHIR Bundle below as the patient information.

FHIR Bundle:

{json.dumps(fhir_bundle, indent=2)}

Process the patient through:

1. Patient Summary Agent
2. Trial Matching Agent
3. Eligibility Verification Agent
4. CDS Card Agent

Return ONLY the final JSON output from Agent 4.
"""
            )
        ]
    )


    # ----------------------------------------
    # Run the ADK pipeline
    # ----------------------------------------

    final_output = None

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message
    ):

        if event.is_final_response():

            if event.content and event.content.parts:

                final_output = event.content.parts[0].text


    # ----------------------------------------
    # Print Agent 4 result
    # ----------------------------------------

    print("\n================================")
    print("AGENT 4 OUTPUT")
    print("================================")

    print(final_output)


    # ----------------------------------------
    # Return CDS Hooks response
    # ----------------------------------------

    if not final_output:

        return {
            "cards": []
        }


    # ----------------------------------------
    # Convert Agent 4 JSON into response
    # ----------------------------------------

    try:

        agent_result = json.loads(final_output)

        return agent_result

    except json.JSONDecodeError:

        print("WARNING: Agent 4 did not return valid JSON.")

        return {
            "cards": [
                {
                    "summary": "Clinical Trial Opportunity",
                    "detail": final_output,
                    "indicator": "info",
                    "source": {
                        "label": "HeLaSync",
                        "url": "https://www.helasync.org"
                    }
                }
            ]
        }
