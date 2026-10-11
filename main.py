import json
import re
from typing import Any, Dict
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent, trial_list

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
    version="1.6.0",
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
# RESEARCH DASHBOARD AND REFERRAL LAUNCH
# ============================================================

app.include_router(research_router)
app.include_router(referral_launch_router)


# ============================================================
# TRIAL METADATA HELPERS
# ============================================================

def _as_text(value: Any) -> str:
    """
    Convert common trial metadata values into readable text.

    Does not invent missing metadata.
    """

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in (
            "name",
            "fullName",
            "full_name",
            "display",
            "value",
            "text",
        ):
            item = value.get(key)

            if isinstance(item, str) and item.strip():
                return item.strip()

        first = value.get("firstName", "")
        middle = value.get("middleName", "")
        last = value.get("lastName", "")
        degree = value.get("degree", "")

        return " ".join(
            str(part).strip()
            for part in (first, middle, last, degree)
            if part and str(part).strip()
        ).strip()

    if isinstance(value, list) and value:
        return _as_text(value[0])

    return ""


def _get_trial_metadata(trial_id: str) -> Dict[str, str]:
    """
    Find a trial in the loaded Trial_List data.

    Supports common top-level trial fields and the
    ClinicalTrials.gov protocolSection structure.
    """

    for trial in trial_list:
        if not isinstance(trial, dict):
            continue

        protocol = trial.get("protocolSection", {})

        if not isinstance(protocol, dict):
            protocol = {}

        identification = (
            protocol.get("identificationModule")
            or trial.get("identificationModule")
            or {}
        )

        if not isinstance(identification, dict):
            identification = {}

        possible_ids = [
            trial.get("trial_id"),
            trial.get("trialId"),
            trial.get("nctId"),
            trial.get("NCTId"),
            trial.get("id"),
            identification.get("nctId"),
            identification.get("NCTId"),
        ]

        matching_ids = [
            str(value).strip()
            for value in possible_ids
            if value
        ]

        if trial_id not in matching_ids:
            continue

        title = (
            trial.get("trial_title")
            or trial.get("trialTitle")
            or trial.get("title")
            or trial.get("name")
            or identification.get("briefTitle")
            or identification.get("officialTitle")
            or ""
        )

        sponsor_module = (
            protocol.get("sponsorCollaboratorsModule", {})
        )

        if not isinstance(sponsor_module, dict):
            sponsor_module = {}

        sponsor_value = (
            trial.get("sponsor")
            or trial.get("leadSponsor")
            or sponsor_module.get("leadSponsor")
            or ""
        )

        sponsor = _as_text(sponsor_value)

        # Look for an explicitly identified principal investigator.
        pi = _as_text(
            trial.get("principal_investigator")
            or trial.get("principalInvestigator")
            or trial.get("principalInvestigatorName")
            or trial.get("pi")
            or ""
        )

        if not pi:
            contacts_module = (
                protocol.get("contactsLocationsModule", {})
            )

            if not isinstance(contacts_module, dict):
                contacts_module = {}

            officials = contacts_module.get(
                "overallOfficials",
                [],
            )

            if isinstance(officials, list):
                for official in officials:
                    if not isinstance(official, dict):
                        continue

                    role = str(
                        official.get("role", "")
                    ).lower()

                    if "principal investigator" in role:
                        pi = _as_text(official)

                        if pi:
                            break

        return {
            "title": _as_text(title),
            "sponsor": sponsor,
            "pi": pi or "Not listed",
        }

    return {
        "title": "",
        "sponsor": "",
        "pi": "Not listed",
    }


def _extract_trial_id(card: Dict[str, Any]) -> str:
    """
    Extract the trial ID from Agent 5's internal extension
    or the card detail.

    The extension is removed before the response is returned.
    """

    extension = card.get("extension", {})

    if isinstance(extension, dict):
        trial_id = extension.get("helasync_trial_id")

        if trial_id:
            return str(trial_id).strip()

    detail = str(card.get("detail", ""))

    match = re.search(
        r"\bNCT[A-Z0-9]+\b",
        detail,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(0)

    return ""


def _fallback_title(detail: str) -> str:
    """
    Extract a readable trial title from Agent 5's detail
    when the title is not found in Trial_List.
    """

    text = str(detail or "")

    # Remove duplicate source text.
    text = re.sub(
        r"(?im)^\s*Source:\s*HeLaSync\s*$",
        "",
        text,
    )

    # Remove an optional HeLaSync prefix.
    text = re.sub(
        r"(?im)^\s*HeLaSync:\s*",
        "",
        text,
    )

    # Remove PI information.
    text = re.sub(
        r"(?im)\s*PI:\s*.*$",
        "",
        text,
    )

    # Remove an NCT identifier from the title.
    text = re.sub(
        r"\s*\(NCT[A-Z0-9]+\)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove common trial labels if present.
    text = re.sub(
        r"(?im)^\s*Trial:\s*",
        "",
        text,
    )

    return text.strip(" \n\r\t:")


def _format_trial_card(
    card: Dict[str, Any],
    patient_id: str,
    user_id: str,
    hook_instance: str,
) -> Dict[str, Any]:
    """
    Format a HeLaSync opportunity card and attach the
    dynamic Smart App link.

    No referral is created by displaying the card.
    """

    trial_id = _extract_trial_id(card)

    detail = str(card.get("detail", ""))

    metadata = (
        _get_trial_metadata(trial_id)
        if trial_id
        else {
            "title": "",
            "sponsor": "",
            "pi": "Not listed",
        }
    )

    # Only apply the compact layout to opportunity cards.
    is_opportunity = (
        card.get("summary")
        == "Potential Clinical Trial Opportunity"
    )

    if is_opportunity:
        title = (
            metadata.get("title")
            or _fallback_title(detail)
            or "Trial title unavailable"
        )

        sponsor = (
            metadata.get("sponsor")
            or "Sponsor not listed"
        )

        pi = (
            metadata.get("pi")
            or "Not listed"
        )

        # Exact concise card layout.
        #
        # The Sandbox displays the source label separately,
        # so do not repeat "Source: HeLaSync" in detail.
        card["summary"] = (
            "Potential Clinical Trial Opportunity"
        )

        card["detail"] = (
            f"{sponsor}: {title}\n\n"
            f"PI: {pi}"
        )

        card["indicator"] = "info"

        card["source"] = {
            "label": "HeLaSync",
        }

        # Dismiss is a no-op suggestion.
        # It does not create a FHIR resource or referral.
        #
        # The CDS client controls how suggestions are rendered.
        card["selectionBehavior"] = "at-most-one"

        card["suggestions"] = [
            {
                "label": "Dismiss",
                "uuid": (
                    f"helasync-dismiss-{trial_id}"
                    if trial_id
                    else "helasync-dismiss"
                ),
            }
        ]

    # Remove internal pipeline metadata from the public response.
    card.pop("extension", None)

    # Attach the Smart App link without creating a referral.
    if trial_id:
        referral_url = (
            "https://helasync.onrender.com/referral-launch?"
            + urlencode(
                {
                    "trial_id": trial_id,
                    "patient_id": patient_id,
                    "clinician_id": user_id,
                    "encounter_id": hook_instance,
                    "hook_instance": hook_instance,
                }
            )
        )

        card["links"] = [
            {
                "label": "View Trial Details",
                "url": referral_url,
                "type": "absolute",
            }
        ]

    else:
        # Do not create a misleading link to an unknown trial.
        card.pop("links", None)

    return card


# ============================================================
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
async def root():
    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": "5-agent clinical trial matching pipeline",
        "version": "1.6.0",
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
    patient_data: Dict[str, Any],
):
    """
    Process patient information through the HeLaSync
    Privacy Gateway.
    """

    try:
        sanitized_data = privacy_gateway.process_patient(
            patient_data
        )

        return {
            "status": "success",
            "privacy_processed": True,
            "data": sanitized_data,
        }

    except Exception as exc:
        return {
            "status": "error",
            "privacy_processed": False,
            "error": str(exc),
        }


# ============================================================
# CDS HOOKS SERVICE DISCOVERY
# ============================================================

@app.get("/cds-services")
async def cds_services():
    """
    Register the HeLaSync patient-view CDS service.
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
                    "patient": (
                        "Patient/{{context.patientId}}"
                    ),
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
async def helasync_cds(
    request: Dict[str, Any],
):
    """
    Main HeLaSync CDS Hooks endpoint.

    Flow:
        CDS Hooks request
        -> FHIR prefetch
        -> Privacy Gateway
        -> Five-agent pipeline
        -> Compact CDS card
        -> Smart App link
    """

    try:
        # ----------------------------------------------------
        # 1. Extract request information
        # ----------------------------------------------------

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )

        context = request.get("context", {})

        if not isinstance(context, dict):
            context = {}

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

        prefetch = request.get("prefetch", {})

        if not isinstance(prefetch, dict):
            prefetch = {}

        # ----------------------------------------------------
        # 2. Convert prefetch resources into a FHIR Bundle
        # ----------------------------------------------------

        entries = []

        for resource in prefetch.values():
            if resource is None:
                continue

            if (
                isinstance(resource, dict)
                and resource.get("resourceType") == "Bundle"
            ):
                for entry in resource.get("entry", []):
                    if (
                        isinstance(entry, dict)
                        and entry.get("resource")
                    ):
                        entries.append(
                            {
                                "resource": entry["resource"]
                            }
                        )

            elif isinstance(resource, dict):
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

        # ----------------------------------------------------
        # 3. Build patient data for the Privacy Gateway
        # ----------------------------------------------------

        patient_data = {
            "patientId": patient_id,
            "fhirBundle": fhir_bundle,
        }

        # ----------------------------------------------------
        # 4. Process through the Privacy Gateway
        # ----------------------------------------------------

        sanitized_patient_data = (
            privacy_gateway.process_patient(patient_data)
        )

        # ----------------------------------------------------
        # 5. Build the agent prompt
        # ----------------------------------------------------

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )

        prompt = f"""
You are processing a CDS Hooks patient-view request
for HeLaSync.

The following patient information has passed through
the HeLaSync Privacy Gateway.

Use the information to perform the clinical-trial
matching workflow.

Do not expose direct patient identifiers in the CDS card.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(context, indent=2, default=str)}

Return the final CDS Hooks response generated by the
HeLaSync five-agent pipeline.

The response must be valid JSON.
"""

        # ----------------------------------------------------
        # 6. Create the ADK session
        # ----------------------------------------------------

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=hook_instance,
        )

        # ----------------------------------------------------
        # 7. Create the ADK message
        # ----------------------------------------------------

        content = types.Content(
            role="user",
            parts=[
                types.Part(text=prompt)
            ],
        )

        # ----------------------------------------------------
        # 8. Run the five-agent pipeline
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 9. Parse Agent 5 output
        # ----------------------------------------------------

        result = None

        if final_output:
            try:
                result = json.loads(final_output)

            except json.JSONDecodeError:
                cleaned_output = (
                    final_output
                    .replace("```json", "")
                    .replace("```", "")
                    .strip()
                )

                try:
                    result = json.loads(cleaned_output)

                except json.JSONDecodeError:
                    result = None

        if not isinstance(result, dict):
            result = {
                "cards": [
                    {
                        "summary": (
                            "HeLaSync Clinical Trial Matching"
                        ),
                        "indicator": "warning",
                        "detail": (
                            "The HeLaSync clinical trial matching "
                            "pipeline returned an unexpected response."
                        ),
                        "source": {
                            "label": "HeLaSync"
                        },
                    }
                ]
            }

        # ----------------------------------------------------
        # 10. Format cards and attach Smart App links
        # ----------------------------------------------------

        cards = result.get("cards", [])

        if not isinstance(cards, list):
            cards = []

        formatted_cards = []

        for card in cards:
            if not isinstance(card, dict):
                continue

            formatted_card = _format_trial_card(
                card=card,
                patient_id=patient_id,
                user_id=user_id,
                hook_instance=hook_instance,
            )

            formatted_cards.append(formatted_card)

        # ----------------------------------------------------
        # 11. Return CDS Hooks response
        # ----------------------------------------------------

        return {
            "cards": formatted_cards
        }

    except Exception:
        # Keep implementation details out of the clinician-facing
        # error card. Detailed diagnostics remain in Render logs.
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


# ============================================================
# CREATE REFERRAL
# ============================================================

@app.post("/referrals")
async def create_referral_endpoint(
    payload: Dict[str, Any],
):
    """
    Create a HeLaSync clinical-trial referral.

    Merely displaying a CDS card does not call this endpoint.
    """

    trial_id = payload.get("trial_id")
    patient_id = payload.get("patient_id")
    clinician_id = payload.get("clinician_id")
    encounter_id = payload.get("encounter_id")

    if not trial_id:
        return {
            "status": "error",
            "message": "trial_id is required",
        }

    if not patient_id:
        return {
            "status": "error",
            "message": "patient_id is required",
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

    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


# ============================================================
# GET SINGLE REFERRAL
# ============================================================

@app.get("/referrals/{referral_id}")
async def get_referral_endpoint(
    referral_id: str,
):
    referral = get_referral(referral_id)

    if referral is None:
        return {
            "status": "error",
            "message": "Referral not found",
        }

    return referral


# ============================================================
# LIST REFERRALS
# ============================================================

@app.get("/referrals")
async def list_referrals_endpoint():
    return list_referrals()
