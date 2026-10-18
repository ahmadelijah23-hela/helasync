import json
import re
import traceback
import uuid
from typing import Any, Dict, List, Optional
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

from research_dashboard import router as research_router
from referral_launch import router as referral_launch_router


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_VERSION = "1.6.4"
APP_NAME = "helasync"
BASE_URL = "https://helasync.onrender.com"

app = FastAPI(
    title="HeLaSync API",
    description=(
        "HeLaSync clinical trial matching, CDS Hooks, "
        "privacy gateway, and referral API"
    ),
    version=APP_VERSION,
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

session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


# ============================================================
# APPLICATION ROUTERS
# ============================================================

app.include_router(research_router)
app.include_router(referral_launch_router)


# ============================================================
# GENERAL HELPERS
# ============================================================

def as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    return {}


def as_text(
    value: Any,
    default: str = "",
) -> str:

    if value is None:
        return default

    if isinstance(value, str):
        value = value.strip()

        return value if value else default

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, dict):

        for key in (
            "text",
            "name",
            "label",
            "value",
        ):

            if value.get(key) is not None:

                result = as_text(
                    value.get(key)
                )

                if result:
                    return result

    if isinstance(value, list):

        values = []

        for item in value:

            item_text = as_text(item)

            if item_text:
                values.append(item_text)

        if values:
            return ", ".join(values)

    return default


# ============================================================
# FHIR HELPERS
# ============================================================

def find_patient_resource(
    resource: Any,
) -> Optional[Dict[str, Any]]:

    """
    Locate a FHIR Patient resource.

    Supports:
    - Patient resource
    - Bundle containing Patient
    """

    if not isinstance(resource, dict):
        return None

    if resource.get("resourceType") == "Patient":
        return resource

    if resource.get("resourceType") == "Bundle":

        for entry in resource.get(
            "entry",
            [],
        ) or []:

            entry = as_dict(entry)

            candidate = as_dict(
                entry.get("resource")
            )

            if candidate.get(
                "resourceType"
            ) == "Patient":

                return candidate

    return None


def flatten_prefetch(
    prefetch: Dict[str, Any],
) -> List[Dict[str, Any]]:

    """
    Convert CDS Hooks prefetch resources into
    a flat list of FHIR resources.
    """

    resources = []

    for resource in prefetch.values():

        if not isinstance(resource, dict):
            continue

        # Prefetch item is a Bundle
        if resource.get(
            "resourceType"
        ) == "Bundle":

            for entry in resource.get(
                "entry",
                [],
            ) or []:

                entry = as_dict(entry)

                item = as_dict(
                    entry.get("resource")
                )

                if item.get("resourceType"):
                    resources.append(item)

        # Prefetch item is a single FHIR resource
        elif resource.get("resourceType"):

            resources.append(resource)

    return resources


def normalize_patient(
    fhir_bundle: Dict[str, Any],
    patient_id: str,
    prefetch: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

    """
    Locate the Patient resource and guarantee that
    it contains the CDS Hooks context.patientId.

    The normalized Patient is also guaranteed to exist
    inside the FHIR Bundle.
    """

    patient = None

    # --------------------------------------------------------
    # Search the constructed Bundle
    # --------------------------------------------------------

    for entry in fhir_bundle.get(
        "entry",
        [],
    ) or []:

        entry = as_dict(entry)

        resource = as_dict(
            entry.get("resource")
        )

        if resource.get(
            "resourceType"
        ) == "Patient":

            patient = resource

            break

    # --------------------------------------------------------
    # Search original CDS Hooks patient prefetch
    # --------------------------------------------------------

    if patient is None and prefetch:

        patient = find_patient_resource(
            prefetch.get("patient")
        )

    # --------------------------------------------------------
    # If no Patient was returned, create a minimal
    # Patient resource using the CDS patient ID.
    # --------------------------------------------------------

    if patient is None:

        patient = {
            "resourceType": "Patient",
            "id": patient_id,
        }

        print(
            "WARNING: CDS Hooks did not provide a Patient "
            "resource. Created minimal Patient using "
            f"context.patientId: {patient_id}"
        )

    # --------------------------------------------------------
    # Guarantee Patient ID
    # --------------------------------------------------------

    if not patient.get("id"):

        patient["id"] = patient_id

        print(
            "FHIR Patient was missing an id. "
            f"Assigned context.patientId: {patient_id}"
        )

    else:

        print(
            "FHIR Patient already contains id: "
            f"{patient.get('id')}"
        )

    # --------------------------------------------------------
    # Guarantee Patient exists inside Bundle
    # --------------------------------------------------------

    patient_found_in_bundle = False

    for entry in fhir_bundle.get(
        "entry",
        [],
    ) or []:

        entry = as_dict(entry)

        resource = as_dict(
            entry.get("resource")
        )

        if resource.get(
            "resourceType"
        ) == "Patient":

            entry["resource"] = patient

            patient_found_in_bundle = True

            break

    if not patient_found_in_bundle:

        fhir_bundle.setdefault(
            "entry",
            [],
        ).insert(
            0,
            {
                "resource": patient,
            },
        )

    return patient


# ============================================================
# PRIVACY INPUT BUILDER
# ============================================================

def build_privacy_input(
    patient_id: str,
    patient: Dict[str, Any],
    fhir_bundle: Dict[str, Any],
) -> Dict[str, Any]:

    """
    Build the complete Privacy Gateway input.

    The Patient resource is supplied explicitly rather than
    requiring the Privacy Gateway to discover it only from
    the Bundle.
    """

    resources = []

    for entry in fhir_bundle.get(
        "entry",
        [],
    ) or []:

        entry = as_dict(entry)

        resource = as_dict(
            entry.get("resource")
        )

        if resource.get("resourceType"):
            resources.append(resource)

    conditions = [
        resource
        for resource in resources
        if resource.get(
            "resourceType"
        ) == "Condition"
    ]

    observations = [
        resource
        for resource in resources
        if resource.get(
            "resourceType"
        ) == "Observation"
    ]

    medications = [
        resource
        for resource in resources
        if resource.get(
            "resourceType"
        ) in (
            "MedicationRequest",
            "MedicationStatement",
        )
    ]

    return {
        "patientId": patient_id,
        "patient": patient,
        "fhirBundle": fhir_bundle,
        "conditions": conditions,
        "observations": observations,
        "medications": medications,
    }


# ============================================================
# TRIAL HELPERS
# ============================================================

def get_trial_metadata(
    trial_id: str,
) -> Dict[str, Any]:

    for trial in trial_list:

        if not isinstance(trial, dict):
            continue

        protocol = as_dict(
            trial.get("protocolSection")
        )

        identification = as_dict(
            protocol.get(
                "identificationModule"
            )
        )

        identifiers = {
            as_text(
                trial.get("id")
            ),
            as_text(
                trial.get("trial_id")
            ),
            as_text(
                identification.get("nctId")
            ),
        }

        if trial_id in identifiers:
            return trial

    return {}


def extract_trial_id(
    card: Dict[str, Any],
) -> str:

    extension = as_dict(
        card.get("extension")
    )

    trial_id = as_text(
        extension.get(
            "helasync_trial_id"
        )
    )

    if trial_id:
        return trial_id

    detail = as_text(
        card.get("detail")
    )

    for trial in trial_list:

        if not isinstance(trial, dict):
            continue

        protocol = as_dict(
            trial.get("protocolSection")
        )

        identification = as_dict(
            protocol.get(
                "identificationModule"
            )
        )

        identifiers = [
            as_text(
                trial.get("id")
            ),
            as_text(
                trial.get("trial_id")
            ),
            as_text(
                identification.get("nctId")
            ),
        ]

        for identifier in identifiers:

            if identifier and identifier in detail:
                return identifier

    return ""


def get_trial_title(
    trial: Dict[str, Any],
    trial_id: str,
) -> str:

    protocol = as_dict(
        trial.get("protocolSection")
    )

    identification = as_dict(
        protocol.get(
            "identificationModule"
        )
    )

    return (
        as_text(
            trial.get("title")
        )
        or as_text(
            trial.get("briefTitle")
        )
        or as_text(
            identification.get("briefTitle")
        )
        or as_text(
            identification.get("officialTitle")
        )
        or trial_id
        or "Clinical Trial"
    )


def get_trial_sponsor(
    trial: Dict[str, Any],
) -> str:

    protocol = as_dict(
        trial.get("protocolSection")
    )

    identification = as_dict(
        protocol.get(
            "identificationModule"
        )
    )

    sponsor_module = as_dict(
        protocol.get(
            "sponsorCollaboratorsModule"
        )
    )

    lead_sponsor = as_dict(
        sponsor_module.get(
            "leadSponsor"
        )
    )

    return (
        as_text(
            trial.get("sponsor")
        )
        or as_text(
            identification.get(
                "organization"
            )
        )
        or as_text(
            lead_sponsor.get("name")
        )
        or "Clinical Trial"
    )


def get_principal_investigator(
    trial: Dict[str, Any],
) -> str:

    pi = (
        as_text(
            trial.get(
                "principal_investigator"
            )
        )
        or as_text(
            trial.get("pi")
        )
    )

    if pi:
        return pi

    protocol = as_dict(
        trial.get("protocolSection")
    )

    contacts_module = as_dict(
        protocol.get(
            "contactsLocationsModule"
        )
    )

    for location in contacts_module.get(
        "locations",
        [],
    ) or []:

        location = as_dict(location)

        for contact in location.get(
            "contacts",
            [],
        ) or []:

            contact = as_dict(contact)

            role = as_text(
                contact.get("role")
            ).lower()

            name = as_text(
                contact.get("name")
            )

            if name and (
                "principal investigator"
                in role
                or role
                == "overall study official"
            ):
                return name

    return "Not listed"


# ============================================================
# CDS CARD FORMATTER
# ============================================================

def format_trial_card(
    card: Dict[str, Any],
    patient_id: str,
    user_id: str,
    hook_instance: str,
) -> Dict[str, Any]:

    """
    Convert the agent card into the locked HeLaSync
    CDS Hooks card design.
    """

    formatted = dict(card)

    if as_text(
        formatted.get("summary")
    ) != (
        "Potential Clinical Trial Opportunity"
    ):

        return formatted

    trial_id = extract_trial_id(
        formatted
    )

    trial = (
        get_trial_metadata(
            trial_id
        )
        if trial_id
        else {}
    )

    sponsor = get_trial_sponsor(
        trial
    )

    title = get_trial_title(
        trial,
        trial_id,
    )

    pi = get_principal_investigator(
        trial
    )

    # --------------------------------------------------------
    # Locked summary
    # --------------------------------------------------------

    formatted["summary"] = (
        "Potential Clinical Trial Opportunity"
    )

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    formatted["source"] = {
        "label": "HeLaSync",
    }

    # --------------------------------------------------------
    # Locked detail format
    # --------------------------------------------------------

    formatted["detail"] = (
        f"{sponsor}: {title}\n\n"
        f"PI: {pi}"
    )

    # --------------------------------------------------------
    # Internal metadata must never be shown to clinician
    # --------------------------------------------------------

    formatted.pop(
        "extension",
        None,
    )

    # --------------------------------------------------------
    # Smart App
    # --------------------------------------------------------

    if trial_id:

        query = urlencode({
            "trial_id": trial_id,
            "patient_id": patient_id,
            "clinician_id": user_id,
            "encounter_id": hook_instance,
            "hook_instance": hook_instance,
        })

        formatted["links"] = [
            {
                "label": "View Trial Details",
                "url": (
                    f"{BASE_URL}/referral-launch?"
                    f"{query}"
                ),
                "type": "absolute",
            }
        ]

    # --------------------------------------------------------
    # Dismiss
    # --------------------------------------------------------

    formatted["selectionBehavior"] = (
        "at-most-one"
    )

    formatted["suggestions"] = [
        {
            "label": "Dismiss",
            "uuid": str(
                uuid.uuid4()
            ),
        }
    ]

    return formatted


# ============================================================
# SERVICE ERROR
# ============================================================

def service_error_card(
    message: str,
) -> Dict[str, Any]:

    return {
        "cards": [
            {
                "summary": (
                    "HeLaSync Service Error"
                ),
                "indicator": "warning",
                "detail": message,
                "source": {
                    "label": "HeLaSync",
                },
            }
        ]
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy",
        "pipeline": (
            "5-agent clinical trial matching pipeline"
        ),
        "version": APP_VERSION,
    }


# ============================================================
# AGENT STATUS
# ============================================================

@app.get("/agent-status")
async def agent_status():

    return {
        "status": "healthy",
        "version": APP_VERSION,
        "pipeline": [
            "Patient_Data_Agent",
            "Clinical_Profile_Agent",
            "Trial_Matching_Agent",
            "Eligibility_Verification_Agent",
            "CDS_Card_Agent",
        ],
    }


# ============================================================
# PRIVACY GATEWAY TEST ENDPOINT
# ============================================================

@app.post(
    "/privacy/process-patient"
)
async def process_patient(
    patient_data: Dict[str, Any],
):

    try:

        patient_id = as_text(
            patient_data.get(
                "patientId"
            ),
            "unknown-patient",
        )

        fhir_bundle = as_dict(
            patient_data.get(
                "fhirBundle"
            )
        )

        if fhir_bundle.get(
            "resourceType"
        ) != "Bundle":

            return {
                "status": "error",
                "privacy_processed": False,
                "error": (
                    "Expected fhirBundle to contain "
                    "a FHIR Bundle."
                ),
            }

        patient = normalize_patient(
            fhir_bundle,
            patient_id,
        )

        gateway_input = (
            build_privacy_input(
                patient_id,
                patient,
                fhir_bundle,
            )
        )

        sanitized_data = (
            privacy_gateway.process_patient(
                gateway_input
            )
        )

        return {
            "status": "success",
            "privacy_processed": True,
            "data": sanitized_data,
        }

    except Exception as exc:

        print(
            "PRIVACY ENDPOINT ERROR:"
        )

        print(
            traceback.format_exc()
        )

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
                    "patient": (
                        "Patient/"
                        "{{context.patientId}}"
                    ),
                    "conditions": (
                        "Condition?"
                        "patient={{context.patientId}}"
                    ),
                    "observations": (
                        "Observation?"
                        "patient={{context.patientId}}"
                    ),
                    "medications": (
                        "MedicationRequest?"
                        "patient={{context.patientId}}"
                    ),
                },
            }
        ]
    }


# ============================================================
# MAIN HELASYNC CDS HOOK
# ============================================================

@app.post(
    "/cds-services/helasync"
)
async def helasync_cds(
    request: Dict[str, Any],
):

    try:

        # ====================================================
        # 1. EXTRACT CDS HOOK REQUEST
        # ====================================================

        hook_instance = as_text(
            request.get(
                "hookInstance"
            ),
            str(uuid.uuid4()),
        )

        context = as_dict(
            request.get("context")
        )

        user_id = as_text(
            context.get("userId")
            or request.get("userId"),
            "helasync-clinician",
        )

        patient_id = as_text(
            context.get(
                "patientId"
            ),
            "unknown-patient",
        )

        prefetch = as_dict(
            request.get(
                "prefetch"
            )
        )

        print()
        print("=" * 80)
        print("HELASYNC CDS REQUEST")
        print("=" * 80)

        print(
            "Patient ID:",
            patient_id,
        )

        print(
            "User ID:",
            user_id,
        )

        print(
            "Hook:",
            hook_instance,
        )

        print(
            "Prefetch resources:",
            list(prefetch.keys()),
        )

        print("=" * 80)

        # ====================================================
        # 2. FLATTEN PREFETCH INTO FHIR BUNDLE
        # ====================================================

        resources = flatten_prefetch(
            prefetch
        )

        fhir_bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": resource
                }
                for resource in resources
            ],
        }

        print(
            "FHIR Bundle contains",
            len(
                fhir_bundle.get(
                    "entry",
                    []
                )
            ),
            "resources.",
        )

        # ====================================================
        # 3. NORMALIZE PATIENT
        # ====================================================

        patient = normalize_patient(
            fhir_bundle,
            patient_id,
            prefetch=prefetch,
        )

        print(
            "Normalized Patient resource:"
        )

        print(
            json.dumps(
                {
                    "resourceType": patient.get(
                        "resourceType"
                    ),
                    "id": patient.get("id"),
                },
                indent=2,
            )
        )

        # ====================================================
        # 4. BUILD PRIVACY GATEWAY INPUT
        # ====================================================

        gateway_input = (
            build_privacy_input(
                patient_id,
                patient,
                fhir_bundle,
            )
        )

        print(
            "Privacy Gateway input prepared."
        )

        print(
            "Explicit Patient ID passed to gateway:",
            gateway_input.get(
                "patient",
                {},
            ).get(
                "id"
            ),
        )

        # ====================================================
        # 5. PRIVACY GATEWAY
        # ====================================================

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    gateway_input
                )
            )

            print()
            print(
                "++++++++++++++++++++++++++++++++++++++++"
            )
            print(
                "Privacy Gateway processing succeeded."
            )
            print(
                "++++++++++++++++++++++++++++++++++++++++"
            )
            print()

        except Exception as privacy_error:

            print()
            print("-" * 80)
            print(
                "PRIVACY GATEWAY ERROR"
            )
            print("-" * 80)

            print(
                "Type:",
                type(
                    privacy_error
                ).__name__,
            )

            print(
                "Message:",
                str(
                    privacy_error
                ),
            )

            print(
                "Full traceback:"
            )

            print(
                traceback.format_exc()
            )

            print(
                "-" * 80
            )

            # ------------------------------------------------
            # FAIL CLOSED
            #
            # Do NOT send raw patient data to AI.
            # ------------------------------------------------

            return service_error_card(
                "The HeLaSync Privacy Gateway "
                "could not process the patient data."
            )

        # ====================================================
        # 6. SANITIZED PATIENT CONTEXT
        # ====================================================

        patient_context = json.dumps(
            sanitized_patient_data,
            indent=2,
            default=str,
        )

        # ====================================================
        # 7. BUILD AGENT PROMPT
        # ====================================================

        prompt = f"""
You are processing a CDS Hooks patient-view request for HeLaSync.

The patient information below has already passed through the
HeLaSync Privacy Gateway.

Use only the sanitized patient information.

Do not expose direct patient identifiers in a CDS card.

SANITIZED PATIENT CONTEXT:

{patient_context}

AVAILABLE CLINICAL TRIALS:

{json.dumps(
    trial_list,
    indent=2,
    default=str,
)}

Run the HeLaSync five-agent clinical trial matching pipeline.

The pipeline is:

1. Patient_Data_Agent
2. Clinical_Profile_Agent
3. Trial_Matching_Agent
4. Eligibility_Verification_Agent
5. CDS_Card_Agent

Eligibility rules:

- Do not assume missing information is positive.
- UNKNOWN is different from NOT_MET.
- A missing core/gating criterion must block presentation.
- A confirmed exclusion must block presentation.
- Do not calculate match percentages.
- Do not diagnose a condition.
- Do not recommend tests simply to make a patient eligible.
- Only present a potential opportunity when the eligibility
  verification supports it.

The CDS card must be concise and clinician-facing.

For a qualifying trial, return:

{{
    "cards": [
        {{
            "summary": "Potential Clinical Trial Opportunity",
            "detail": "...",
            "source": {{
                "label": "HeLaSync"
            }},
            "extension": {{
                "helasync_trial_id": "TRIAL_ID"
            }}
        }}
    ]
}}

For a nonmatching trial or insufficient information:

{{
    "cards": []
}}

Do not include the following in the CDS card:

- eligibility criteria
- laboratory values
- match percentages
- missing information
- long descriptions
- Interested
- Not Interested
- Refer Patient
- Enroll
- Contact Site

The HeLaSync API will add the Smart App link and Dismiss
action after the agent response.

Return valid JSON only.
"""

        # ====================================================
        # 8. CREATE UNIQUE ADK SESSION
        # ====================================================

        adk_session_id = (
            f"cds-{uuid.uuid4().hex}"
        )

        session = (
            await session_service.create_session(
                app_name=APP_NAME,
                user_id=str(
                    user_id
                ),
                session_id=adk_session_id,
            )
        )

        # ====================================================
        # 9. CREATE ADK MESSAGE
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
        # 10. RUN FIVE-AGENT PIPELINE
        # ====================================================

        final_output = None

        async for event in runner.run_async(
            user_id=str(
                user_id
            ),
            session_id=session.id,
            new_message=content,
        ):

            if (
                event.is_final_response()
                and event.content
                and event.content.parts
            ):

                final_output = "".join(
                    part.text
                    for part in (
                        event.content.parts
                    )
                    if getattr(
                        part,
                        "text",
                        None,
                    )
                )

        if not final_output:

            print(
                "Agent pipeline returned no final output."
            )

            return {
                "cards": []
            }

        # ====================================================
        # 11. CLEAN AGENT JSON
        # ====================================================

        cleaned = (
            final_output.strip()
        )

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        # ====================================================
        # 12. PARSE JSON
        # ====================================================

        try:

            result = json.loads(
                cleaned
            )

        except json.JSONDecodeError:

            match = re.search(
                r"\{.*\}",
                cleaned,
                flags=re.DOTALL,
            )

            if not match:

                print(
                    "Agent returned invalid JSON:"
                )

                print(
                    cleaned[:2000]
                )

                return {
                    "cards": []
                }

            result = json.loads(
                match.group(0)
            )

        if not isinstance(
            result,
            dict,
        ):

            return {
                "cards": []
            }

        cards = result.get(
            "cards",
            [],
        )

        if not isinstance(
            cards,
            list,
        ):

            return {
                "cards": []
            }

        # ====================================================
        # 13. FORMAT CDS CARDS
        # ====================================================

        formatted_cards = []

        for card in cards:

            if not isinstance(
                card,
                dict,
            ):
                continue

            if as_text(
                card.get("summary")
            ) != (
                "Potential Clinical Trial Opportunity"
            ):
                continue

            formatted_card = (
                format_trial_card(
                    card=card,
                    patient_id=patient_id,
                    user_id=user_id,
                    hook_instance=hook_instance,
                )
            )

            formatted_cards.append(
                formatted_card
            )

        # ====================================================
        # 14. FINAL RESPONSE
        # ====================================================

        response = {
            "cards": formatted_cards
        }

        print()
        print(
            "FINAL CDS RESPONSE"
        )
        print(
            json.dumps(
                response,
                indent=2,
                default=str,
            )
        )

        return response

    except Exception:

        print()
        print(
            "=" * 80
        )
        print(
            "HELASYNC CDS HANDLER ERROR"
        )
        print(
            "=" * 80
        )

        print(
            traceback.format_exc()
        )

        print(
            "=" * 80
        )

        return service_error_card(
            "HeLaSync encountered an unexpected "
            "error while processing this request. "
            "No clinical trial recommendation "
            "was generated."
        )


# ============================================================
# REFERRAL ENDPOINTS
# ============================================================

@app.post("/referrals")
async def create_referral_endpoint(
    payload: Dict[str, Any],
):

    return create_referral(
        payload
    )


@app.get("/referrals")
async def list_referrals_endpoint():

    return list_referrals()


@app.get(
    "/referrals/{referral_id}"
)
async def get_referral_endpoint(
    referral_id: str,
):

    result = get_referral(
        referral_id
    )

    if result is None:

        return {
            "status": "not_found",
            "referral_id": referral_id,
        }

    return result
