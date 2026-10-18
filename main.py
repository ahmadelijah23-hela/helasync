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
# ROUTERS
# ============================================================

app.include_router(research_router)
app.include_router(referral_launch_router)


# ============================================================
# GENERAL HELPERS
# ============================================================

def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_text(
    value: Any,
    default: str = "",
) -> str:

    if value is None:
        return default

    if isinstance(value, str):
        return value.strip() or default

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
                    value[key]
                )

                if result:
                    return result

    if isinstance(value, list):

        values = [
            as_text(item)
            for item in value
        ]

        return ", ".join(
            item
            for item in values
            if item
        ) or default

    return default


# ============================================================
# FHIR RESOURCE HELPERS
# ============================================================

def find_patient_resource(
    resource: Any,
) -> Optional[Dict[str, Any]]:

    """
    Find a Patient resource inside either a standalone
    FHIR Patient resource or a FHIR Bundle.
    """

    if not isinstance(resource, dict):
        return None

    if resource.get("resourceType") == "Patient":
        return resource

    if resource.get("resourceType") == "Bundle":

        for entry in resource.get(
            "entry",
            []
        ) or []:

            item = as_dict(
                as_dict(entry).get(
                    "resource"
                )
            )

            if item.get(
                "resourceType"
            ) == "Patient":

                return item

    return None


def flatten_prefetch(
    prefetch: Dict[str, Any],
) -> List[Dict[str, Any]]:

    """
    Convert CDS Hooks prefetch resources into a flat list
    of FHIR resources.

    Handles both individual FHIR resources and Bundles.
    """

    resources = []

    for value in prefetch.values():

        if not isinstance(value, dict):
            continue

        if value.get(
            "resourceType"
        ) == "Bundle":

            for entry in value.get(
                "entry",
                []
            ) or []:

                resource = as_dict(
                    as_dict(entry).get(
                        "resource"
                    )
                )

                if resource.get(
                    "resourceType"
                ):

                    resources.append(
                        resource
                    )

        elif value.get(
            "resourceType"
        ):

            resources.append(value)

    return resources


def normalize_patient(
    fhir_bundle: Dict[str, Any],
    patient_id: str,
    prefetch: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:

    """
    Find the Patient resource, ensure it has an ID,
    and ensure the normalized Patient remains inside
    the FHIR Bundle.
    """

    patient = None

    # --------------------------------------------------------
    # First search the generated FHIR Bundle
    # --------------------------------------------------------

    for entry in fhir_bundle.get(
        "entry",
        []
    ) or []:

        resource = as_dict(
            as_dict(entry).get(
                "resource"
            )
        )

        if resource.get(
            "resourceType"
        ) == "Patient":

            patient = resource
            break

    # --------------------------------------------------------
    # If necessary, search the original CDS prefetch
    # --------------------------------------------------------

    if patient is None and prefetch:

        patient = find_patient_resource(
            prefetch.get("patient")
        )

    # --------------------------------------------------------
    # If no Patient exists, create a minimal resource
    # --------------------------------------------------------

    if patient is None:

        patient = {
            "resourceType": "Patient"
        }

    # --------------------------------------------------------
    # Ensure Patient has an ID
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
    # Ensure normalized Patient exists in Bundle
    # --------------------------------------------------------

    patient_entry_found = False

    for entry in fhir_bundle.get(
        "entry",
        []
    ) or []:

        resource = as_dict(
            as_dict(entry).get(
                "resource"
            )
        )

        if resource.get(
            "resourceType"
        ) == "Patient":

            entry["resource"] = patient

            patient_entry_found = True

            break

    if not patient_entry_found:

        fhir_bundle.setdefault(
            "entry",
            []
        ).insert(
            0,
            {
                "resource": patient
            },
        )

    return patient


def build_privacy_input(
    patient_id: str,
    patient: Dict[str, Any],
    fhir_bundle: Dict[str, Any],
) -> Dict[str, Any]:

    """
    Build the structured input used by the Privacy Gateway.

    The gateway receives:
      - Patient
      - Conditions
      - Observations
      - Medications
      - Patient ID
      - Complete FHIR Bundle
    """

    resources = []

    for entry in fhir_bundle.get(
        "entry",
        []
    ) or []:

        resource = as_dict(
            as_dict(entry).get(
                "resource"
            )
        )

        if resource.get(
            "resourceType"
        ):

            resources.append(
                resource
            )

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
# TRIAL METADATA HELPERS
# ============================================================

def get_trial_metadata(
    trial_id: str,
) -> Dict[str, Any]:

    for trial in trial_list:

        if not isinstance(
            trial,
            dict
        ):
            continue

        protocol = as_dict(
            trial.get(
                "protocolSection"
            )
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

        if not isinstance(
            trial,
            dict
        ):
            continue

        protocol = as_dict(
            trial.get(
                "protocolSection"
            )
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

            if (
                identifier
                and identifier in detail
            ):

                return identifier

    return ""


def get_trial_title(
    trial: Dict[str, Any],
    trial_id: str,
) -> str:

    protocol = as_dict(
        trial.get(
            "protocolSection"
        )
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
            identification.get(
                "briefTitle"
            )
        )
        or as_text(
            identification.get(
                "officialTitle"
            )
        )
        or trial_id
        or "Clinical Trial"
    )


def get_trial_sponsor(
    trial: Dict[str, Any],
) -> str:

    protocol = as_dict(
        trial.get(
            "protocolSection"
        )
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
            lead_sponsor.get(
                "name"
            )
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
        trial.get(
            "protocolSection"
        )
    )

    contacts_module = as_dict(
        protocol.get(
            "contactsLocationsModule"
        )
    )

    for location in contacts_module.get(
        "locations",
        []
    ) or []:

        for contact in as_dict(
            location
        ).get(
            "contacts",
            []
        ) or []:

            contact = as_dict(
                contact
            )

            role = as_text(
                contact.get(
                    "role"
                )
            ).lower()

            name = as_text(
                contact.get(
                    "name"
                )
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
# CDS CARD FORMATTING
# ============================================================

def format_trial_card(
    card: Dict[str, Any],
    patient_id: str,
    user_id: str,
    hook_instance: str,
) -> Dict[str, Any]:

    """
    Apply the required HeLaSync CDS card design:

    Potential Clinical Trial Opportunity

    Sponsor: Trial Name

    PI: Principal Investigator

    View Trial Details
    Dismiss
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
        trial_id
    )

    pi = get_principal_investigator(
        trial
    )

    # --------------------------------------------------------
    # Required card summary
    # --------------------------------------------------------

    formatted["summary"] = (
        "Potential Clinical Trial Opportunity"
    )

    # --------------------------------------------------------
    # Required source
    # --------------------------------------------------------

    formatted["source"] = {
        "label": "HeLaSync"
    }

    # --------------------------------------------------------
    # Required card detail
    # --------------------------------------------------------

    formatted["detail"] = (
        f"{sponsor}: {title}\n\n"
        f"PI: {pi}"
    )

    # --------------------------------------------------------
    # Remove internal metadata
    # --------------------------------------------------------

    formatted.pop(
        "extension",
        None
    )

    # --------------------------------------------------------
    # View Trial Details
    # --------------------------------------------------------

    if trial_id:

        query = urlencode(
            {
                "trial_id": trial_id,
                "patient_id": patient_id,
                "clinician_id": user_id,
                "encounter_id": hook_instance,
                "hook_instance": hook_instance,
            }
        )

        formatted["links"] = [
            {
                "label": "View Trial Details",
                "url": (
                    f"{BASE_URL}"
                    f"/referral-launch?"
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


def service_error_card(
    message: str,
) -> Dict[str, Any]:

    return {
        "cards": [
            {
                "summary": "HeLaSync Service Error",
                "indicator": "warning",
                "detail": message,
                "source": {
                    "label": "HeLaSync"
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

@app.post("/privacy/process-patient")
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

        gateway_input = build_privacy_input(
            patient_id,
            patient,
            fhir_bundle,
        )

        # IMPORTANT:
        # Pass the actual Patient resource to the gateway,
        # NOT the entire gateway_input wrapper.
        sanitized_data = (
            privacy_gateway.process_patient(
                patient=gateway_input[
                    "patient"
                ],
                conditions=gateway_input.get(
                    "conditions"
                ),
                medications=gateway_input.get(
                    "medications"
                ),
                observations=gateway_input.get(
                    "observations"
                ),
                patient_id=patient_id,
            )
        )

        return {
            "status": "success",
            "privacy_processed": True,
            "data": sanitized_data,
        }

    except Exception as exc:

        print(
            "PRIVACY ENDPOINT ERROR:\n",
            traceback.format_exc(),
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
                        "Patient/{{context.patientId}}"
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
# MAIN CDS HOOK
# ============================================================

@app.post("/cds-services/helasync")
async def helasync_cds(
    request: Dict[str, Any],
):

    try:

        # ====================================================
        # 1. EXTRACT CDS HOOK REQUEST INFORMATION
        # ====================================================

        hook_instance = as_text(
            request.get(
                "hookInstance"
            ),
            str(
                uuid.uuid4()
            ),
        )

        context = as_dict(
            request.get(
                "context"
            )
        )

        user_id = as_text(
            context.get(
                "userId"
            )
            or request.get(
                "userId"
            ),
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

        print(
            "\n"
            + "=" * 80
        )

        print(
            "HELASYNC CDS REQUEST"
        )

        print(
            "=" * 80
        )

        print(
            "Patient ID:",
            patient_id
        )

        print(
            "User ID:",
            user_id
        )

        print(
            "Hook:",
            hook_instance
        )

        print(
            "Prefetch resources:",
            list(
                prefetch.keys()
            )
        )

        print(
            "=" * 80
        )

        # ====================================================
        # 2. CONVERT PREFETCH INTO FHIR BUNDLE
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

        # ====================================================
        # 3. NORMALIZE PATIENT
        # ====================================================

        patient = normalize_patient(
            fhir_bundle,
            patient_id,
            prefetch=prefetch,
        )

        print(
            "FHIR Bundle contains",
            len(
                fhir_bundle.get(
                    "entry",
                    []
                )
            ),
            "resources."
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
                    "id": patient.get(
                        "id"
                    ),
                },
                indent=2,
            )
        )

        # ====================================================
        # 4. BUILD PRIVACY GATEWAY INPUT
        # ====================================================

        gateway_input = build_privacy_input(
            patient_id,
            patient,
            fhir_bundle,
        )

        print(
            "Privacy Gateway input prepared."
        )

        print(
            "Explicit Patient ID passed to gateway:",
            patient_id,
        )

        # ====================================================
        # 5. PRIVACY GATEWAY
        # ====================================================

        try:

            # IMPORTANT FIX:
            #
            # Do NOT pass gateway_input as the `patient`
            # argument.
            #
            # The gateway expects:
            #
            # patient={
            #     "resourceType": "Patient",
            #     "id": "helasync-test-001"
            # }
            #
            # and not:
            #
            # patient={
            #     "patient": {...},
            #     "conditions": [...],
            #     ...
            # }

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient=gateway_input[
                        "patient"
                    ],

                    conditions=gateway_input.get(
                        "conditions"
                    ),

                    medications=gateway_input.get(
                        "medications"
                    ),

                    observations=gateway_input.get(
                        "observations"
                    ),

                    patient_id=patient_id,
                )
            )

            print(
                "Privacy Gateway processing succeeded."
            )

            print(
                "Sanitized patient data keys:",
                list(
                    sanitized_patient_data.keys()
                )
                if isinstance(
                    sanitized_patient_data,
                    dict
                )
                else "non-dict",
            )

        except Exception as privacy_error:

            print(
                "\n"
                + "-" * 80
            )

            print(
                "PRIVACY GATEWAY ERROR"
            )

            print(
                "-" * 80
            )

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
                traceback.format_exc()
            )

            print(
                "-" * 80
            )

            # IMPORTANT:
            #
            # Fail closed.
            #
            # Never send raw FHIR data to the AI agents
            # when the Privacy Gateway fails.

            return service_error_card(
                "The HeLaSync Privacy Gateway could not "
                "safely process the patient data. No patient "
                "data was sent to the matching agents. "
                "Please retry after the privacy service "
                "has been corrected."
            )

        # ====================================================
        # 6. BUILD SANITIZED AI CONTEXT
        # ====================================================

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

Use ONLY the sanitized patient context below.

Do not reproduce direct patient identifiers in any
CDS card.

SANITIZED PATIENT CONTEXT:

{patient_context}


AVAILABLE TRIAL CATALOG:

{json.dumps(
    trial_list,
    indent=2,
    default=str
)}


Run the HeLaSync five-agent clinical trial matching
pipeline using the instructions defined for the agents.

The five agents are:

1. Patient_Data_Agent
2. Clinical_Profile_Agent
3. Trial_Matching_Agent
4. Eligibility_Verification_Agent
5. CDS_Card_Agent


ELIGIBILITY RULES:

- Do not treat a missing value as proof that a criterion
  is met.

- Distinguish NOT_MET from UNKNOWN.

- If a core disease-defining criterion is NOT_MET or
  UNKNOWN, do not present the trial as a potential
  opportunity.

- Do not present a trial when a disqualifying exclusion
  is present.

- Do not calculate a match percentage by counting
  criteria.

- Do not diagnose the patient.

- Do not recommend testing solely to make the patient
  eligible for a trial.

- Secondary actionable information may remain UNKNOWN
  when the core gating criteria are satisfied.


CDS CARD REQUIREMENTS:

Return valid JSON with this structure:

{{
  "cards": []
}}


For an appropriate clinical trial opportunity, the card
summary must be exactly:

"Potential Clinical Trial Opportunity"


The internal trial identifier must be included in:

"extension": {{
    "helasync_trial_id": "<trial identifier>"
}}


The API will remove the internal extension before
returning the CDS card.


The CDS card must NOT contain:

- Eligibility criteria
- Laboratory values
- Match percentages
- Missing information
- Long descriptions
- Interested
- Not Interested
- Refer Patient
- Enroll
- Contact Site


The clinician-facing card should only communicate that
there is a potential clinical trial opportunity.

Detailed trial information belongs in the HeLaSync
Smart App.
"""

        # ====================================================
        # 7. CREATE ADK SESSION
        # ====================================================

        adk_session_id = (
            f"cds-{uuid.uuid4().hex}"
        )

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=str(
                user_id
            ),
            session_id=adk_session_id,
        )

        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=prompt
                )
            ],
        )

        # ====================================================
        # 8. RUN FIVE-AGENT PIPELINE
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
                    for part in event.content.parts
                    if getattr(
                        part,
                        "text",
                        None
                    )
                )

        # ====================================================
        # 9. HANDLE EMPTY AGENT RESPONSE
        # ====================================================

        if not final_output:

            print(
                "The agent pipeline returned "
                "no final output."
            )

            return {
                "cards": []
            }

        # ====================================================
        # 10. CLEAN AGENT RESPONSE
        # ====================================================

        cleaned = (
            final_output
            .strip()
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
        # 11. PARSE JSON
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
                    "Agent returned non-JSON output:"
                )

                print(
                    cleaned[:2000]
                )

                return {
                    "cards": []
                }

            try:

                result = json.loads(
                    match.group(0)
                )

            except json.JSONDecodeError:

                print(
                    "Unable to parse agent JSON:"
                )

                print(
                    cleaned[:2000]
                )

                return {
                    "cards": []
                }

        # ====================================================
        # 12. VALIDATE AGENT RESULT
        # ====================================================

        if not isinstance(
            result,
            dict
        ):

            return {
                "cards": []
            }

        cards = result.get(
            "cards",
            []
        )

        if not isinstance(
            cards,
            list
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
                dict
            ):

                continue

            # Only allow the approved opportunity card.
            if as_text(
                card.get(
                    "summary"
                )
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
        # 14. FINAL CDS RESPONSE
        # ====================================================

        response = {
            "cards": formatted_cards
        }

        print(
            "\n"
            + "=" * 80
        )

        print(
            "CDS RESPONSE"
        )

        print(
            "=" * 80
        )

        print(
            json.dumps(
                response,
                indent=2,
                default=str,
            )
        )

        print(
            "=" * 80
        )

        return response

    except Exception:

        print(
            "HELASYNC CDS HANDLER ERROR:\n",
            traceback.format_exc(),
        )

        return service_error_card(
            "HeLaSync encountered an unexpected error "
            "while processing this request. No clinical "
            "trial recommendation was generated."
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


@app.get("/referrals/{referral_id}")
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
