import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent


app = FastAPI(title="HeLaSync CDS Hooks Service")


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ADK session service
session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name="helasync",
    session_service=session_service,
)


# Home
@app.get("/")
def home():
    return {
        "message": "HeLaSync CDS Hooks Service is running"
    }


# CDS Hooks discovery
@app.get("/cds-services")
def cds_services():
    return {
        "services": [
            {
                "hook": "patient-view",
                "title": "HeLaSync",
                "description": "Clinical trial matching service",
                "id": "helasync"
            }
        ]
    }


# CDS Hooks service
@app.post("/cds-services/helasync")
async def helasync(request: Request):

    # Receive CDS Hooks request
    cds_request = await request.json()

    print("================================")
    print("CDS HOOK REQUEST RECEIVED")
    print("================================")
    print(json.dumps(cds_request, indent=2))


    # Get FHIR data from CDS Hooks prefetch
    prefetch = cds_request.get("prefetch", {})

    fhir_bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": []
    }


    # Convert prefetch resources into one FHIR Bundle
    for key, resource in prefetch.items():

        if not resource:
            continue

        if not isinstance(resource, dict):
            continue

        # Already a FHIR Bundle
        if resource.get("resourceType") == "Bundle":

            for entry in resource.get("entry", []):
                fhir_bundle["entry"].append(entry)

        # Single FHIR resource
        elif resource.get("resourceType"):

            fhir_bundle["entry"].append({
                "resource": resource
            })


    print("================================")
    print("FHIR BUNDLE SENT TO AGENTS")
    print("================================")
    print(json.dumps(fhir_bundle, indent=2))


    # Create ADK session
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
        # Session may already exist
        pass


    # Send FHIR patient data to the HeLaSync pipeline
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=f"""
Run the complete HeLaSync clinical trial matching pipeline.

Use the following FHIR Bundle as the patient's clinical information.

FHIR Bundle:

{json.dumps(fhir_bundle, indent=2)}

Process the patient through:

1. Patient Data Agent
2. Clinical Profile Agent
3. Trial Matching Agent
4. Eligibility Verification Agent
5. CDS Card Agent

Return ONLY the final JSON output from Agent 5.
"""
            )
        ]
    )


    # Run the ADK pipeline
    final_output = None

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message
    ):

        if event.is_final_response():

            if event.content and event.content.parts:

                final_output = event.content.parts[0].text


    print("================================")
    print("AGENT 5 OUTPUT")
    print("================================")
    print(final_output)


    # Return empty response if no output
    if not final_output:
        return {
            "cards": []
        }


    # Convert Agent 5 output to CDS Hooks JSON
    try:

        agent_result = json.loads(final_output)

        return agent_result

    except json.JSONDecodeError:

        print("WARNING: Agent 5 did not return valid JSON.")

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
