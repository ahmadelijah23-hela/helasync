import json
import re
import traceback
import uuid
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
    version="1.6.3",
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
# ROUTERS
# ============================================================

app.include_router(research_router)

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
        "version": "1.6.3",
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

        print("\n" + "=" * 80)
        print("PRIVACY GATEWAY ERROR")
        print("=" * 80)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()
        print("=" * 80 + "\n")

        return {
            "status": "error",
            "privacy_processed": False,
            "error": str(e),
        }


# ============================================================
# FHIR PATIENT NORMALIZATION
# ============================================================

def _normalize_patient_resource(
    fhir_bundle: Dict[str, Any],
    patient_id: str,
) -> Dict[str, Any]:

    """
    Ensure the FHIR Patient resource has an id.

    CDS Hooks provides the patient identifier through:

        context.patientId

    Some Sandbox payloads may provide the Patient resource
    without its own FHIR id.

    The Privacy Gateway requires Patient.id.

    Therefore we use the already-provided CDS Hooks
    patientId to populate Patient.id when necessary.
    """

    if not isinstance(
        fhir_bundle,
        dict
    ):
        return fhir_bundle

    entries = fhir_bundle.get(
        "entry",
        []
    )

    if not isinstance(
        entries,
        list
    ):
        return fhir_bundle

    patient_found = False

    for entry in entries:

        if not isinstance(
            entry,
            dict
        ):
            continue

        resource = entry.get(
            "resource"
        )

        if not isinstance(
            resource,
            dict
        ):
            continue

        if resource.get(
            "resourceType"
        ) != "Patient":
            continue

        patient_found = True

        # ----------------------------------------------
        # Patient already has an ID.
        # Preserve it.
        # ----------------------------------------------

        if resource.get("id"):

            print(
                "FHIR Patient already contains id: "
                f"{resource.get('id')}"
            )

            continue

        # ----------------------------------------------
        # Patient is missing an ID.
        # Use CDS Hooks patientId.
        # ----------------------------------------------

        if patient_id:

            resource["id"] = str(
                patient_id
            )

            print(
                "FHIR Patient was missing an id. "
                "Assigned context.patientId: "
                f"{patient_id}"
            )

    if not patient_found:

        print(
            "WARNING: No FHIR Patient resource was "
            "found in the CDS Hooks prefetch bundle."
        )

    return fhir_bundle


# ============================================================
# TRIAL METADATA HELPERS
# ============================================================

def _as_text(
    value: Any
) -> str:

    if value is None:
        return ""

    if isinstance(
        value,
        str
    ):
        return value.strip()

    if isinstance(
        value,
        dict
    ):

        for key in [
            "text",
            "name",
            "title",
            "officialTitle",
            "briefTitle",
            "value",
            "label",
        ]:

            if value.get(key):

                return _as_text(
                    value.get(key)
                )

        given = value.get(
            "given"
        )

        family = value.get(
            "family"
        )

        if given or family:

            if isinstance(
                given,
                list
            ):

                given_text = " ".join(
                    str(x)
                    for x in given
                )

            else:

                given_text = str(
                    given or ""
                )

            return (
                f"{given_text} "
                f"{family or ''}"
            ).strip()

        return ""

    if isinstance(
        value,
        list
    ):

        values = [
            _as_text(item)
            for item in value
        ]

        values = [
            item
            for item in values
            if item
        ]

        return ", ".join(
            values
        )

    return str(
        value
    ).strip()


def _get_trial_metadata(
    trial_id: str | None
) -> Dict[str, str]:

    metadata = {
        "trial_id": trial_id or "",
        "title": "",
        "sponsor": "",
        "pi": "",
    }

    if not trial_id:
        return metadata

    try:

        for trial in trial_list:

            if not isinstance(
                trial,
                dict
            ):
                continue

            protocol = trial.get(
                "protocolSection",
                {}
            )

            identification = protocol.get(
                "identificationModule",
                {}
            )

            sponsor_module = protocol.get(
                "sponsorCollaboratorsModule",
                {}
            )

            contacts_module = protocol.get(
                "contactsLocationsModule",
                {}
            )

            possible_ids = [
                trial.get("id"),
                trial.get("trial_id"),
                trial.get("nct_id"),
                trial.get("study_id"),
                identification.get("nctId"),
            ]

            possible_ids = [
                str(x).strip()
                for x in possible_ids
                if x
            ]

            if trial_id not in possible_ids:
                continue

            # ------------------------------------------
            # Trial title
            # ------------------------------------------

            title = (
                identification.get(
                    "briefTitle"
                )
                or identification.get(
                    "officialTitle"
                )
                or trial.get(
                    "title"
                )
                or trial.get(
                    "name"
                )
                or ""
            )

            metadata["title"] = _as_text(
                title
            )

            # ------------------------------------------
            # Sponsor
            # ------------------------------------------

            sponsor = (
                sponsor_module.get(
                    "leadSponsor"
                )
                or trial.get(
                    "sponsor"
                )
                or trial.get(
                    "sponsor_name"
                )
                or ""
            )

            if isinstance(
                sponsor,
                dict
            ):

                sponsor = (
                    sponsor.get(
                        "name"
                    )
                    or sponsor.get(
                        "label"
                    )
                    or sponsor.get(
                        "text"
                    )
                    or ""
                )

            metadata["sponsor"] = _as_text(
                sponsor
            )

            # ------------------------------------------
            # Principal Investigator
            # ------------------------------------------

            pi = ""

            overall_official = (
                contacts_module.get(
                    "overallOfficials"
                )
            )

            if (
                isinstance(
                    overall_official,
                    list
                )
                and overall_official
            ):

                official = (
                    overall_official[0]
                )

                if isinstance(
                    official,
                    dict
                ):

                    pi = (
                        official.get(
                            "name"
                        )
                        or official.get(
                            "officialName"
                        )
                        or ""
                    )

            if not pi:

                pi = (
                    trial.get(
                        "principal_investigator"
                    )
                    or trial.get(
                        "principalInvestigator"
                    )
                    or trial.get(
                        "pi"
                    )
                    or ""
                )

            if not pi:

                contacts = (
                    contacts_module.get(
                        "centralContacts"
                    )
                )

                if isinstance(
                    contacts,
                    dict
                ):

                    pi = (
                        contacts.get(
                            "name"
                        )
                        or ""
                    )

            metadata["pi"] = _as_text(
                pi
            )

            return metadata

    except Exception as e:

        print(
            "Trial metadata lookup warning:",
            str(e)
        )

    return metadata


# ============================================================
# TRIAL ID EXTRACTION
# ============================================================

def _extract_trial_id(
    card: Dict[str, Any]
) -> str | None:

    extension = card.get(
        "extension",
        {}
    )

    if isinstance(
        extension,
        dict
    ):

        trial_id = extension.get(
            "helasync_trial_id"
        )

        if trial_id:

            return str(
                trial_id
            ).strip()

    detail = str(
        card.get(
            "detail",
            ""
        )
    )

    match = re.search(
        r"\bNCT[A-Z0-9]+\b",
        detail,
        flags=re.IGNORECASE,
    )

    if match:

        return match.group(
            0
        ).upper()

    return None


# ============================================================
# FALLBACK TITLE
# ============================================================

def _fallback_title(
    detail: str
) -> str:

    if not detail:

        return (
            "Clinical Trial Opportunity"
        )

    title = detail

    title = re.sub(
        r"Source:\s*HeLaSync",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"HeLaSync:\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"PI:\s*.*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\bNCT[A-Z0-9]+\b",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    return (
        title
        or "Clinical Trial Opportunity"
    )


# ============================================================
# FORMAT FINAL CDS CARD
# ============================================================

def _format_trial_card(
    card: Dict[str, Any],
    patient_id: str,
    user_id: str,
    hook_instance: str,
) -> Dict[str, Any]:

    formatted = dict(
        card
    )

    trial_id = _extract_trial_id(
        formatted
    )

    metadata = _get_trial_metadata(
        trial_id
    )

    summary = str(
        formatted.get(
            "summary",
            ""
        )
    ).strip()

    is_opportunity = (
        summary
        == "Potential Clinical Trial Opportunity"
    )

    if not is_opportunity:

        return formatted

    # ----------------------------------------------
    # Trial title
    # ----------------------------------------------

    title = (
        metadata.get(
            "title"
        )
        or _fallback_title(
            str(
                formatted.get(
                    "detail",
                    ""
                )
            )
        )
    )

    # ----------------------------------------------
    # Sponsor
    # ----------------------------------------------

    sponsor = (
        metadata.get(
            "sponsor"
        )
        or "Clinical Trial"
    )

    # ----------------------------------------------
    # Principal Investigator
    # ----------------------------------------------

    pi = (
        metadata.get(
            "pi"
        )
        or "Not listed"
    )

    # ----------------------------------------------
    # LOCKED CARD FORMAT
    # ----------------------------------------------

    formatted["summary"] = (
        "Potential Clinical Trial Opportunity"
    )

    formatted["detail"] = (
        f"{sponsor}: {title}\n\n"
        f"PI: {pi}"
    )

    formatted["indicator"] = "info"

    formatted["source"] = {
        "label": "HeLaSync"
    }

    # ----------------------------------------------
    # Remove internal extension
    # ----------------------------------------------

    formatted.pop(
        "extension",
        None
    )

    # ----------------------------------------------
    # Dismiss
    # ----------------------------------------------

    if trial_id:

        formatted[
            "selectionBehavior"
        ] = "at-most-one"

        formatted[
            "suggestions"
        ] = [
            {
                "label": "Dismiss",
                "uuid": (
                    f"helasync-dismiss-{trial_id}"
                ),
            }
        ]

    # ----------------------------------------------
    # View Trial Details
    # ----------------------------------------------

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

        formatted["links"] = [
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

        formatted.pop(
            "links",
            None
        )

    return formatted


# ============================================================
# CDS HOOKS SERVICE DISCOVERY
# ============================================================

@app.get("/cds-services")
async def cds_services():

    return {
        "services": [
            {
                "hook":
                    "patient-view",

                "title":
                    "HeLaSync Clinical Trial Matching",

                "description": (
                    "Identifies potentially relevant "
                    "clinical trials from the patient's "
                    "available clinical information."
                ),

                "id":
                    "helasync",

                "prefetch": {

                    "patient":
                        "Patient/{{context.patientId}}",

                    "conditions":
                        "Condition?"
                        "patient={{context.patientId}}",

                    "observations":
                        "Observation?"
                        "patient={{context.patientId}}",

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

@app.post(
    "/cds-services/helasync"
)
async def helasync_cds(
    request: Dict[str, Any]
):

    try:

        # ====================================================
        # 1. EXTRACT CDS HOOK REQUEST
        # ====================================================

        hook_instance = request.get(
            "hookInstance",
            f"helasync-hook-{uuid.uuid4()}",
        )

        context = request.get(
            "context",
            {},
        )

        if not isinstance(
            context,
            dict
        ):

            context = {}

        user_id = (
            context.get(
                "userId"
            )
            or request.get(
                "userId"
            )
            or "helasync-clinician"
        )

        patient_id = (
            context.get(
                "patientId"
            )
            or "unknown-patient"
        )

        prefetch = request.get(
            "prefetch",
            {},
        )

        if not isinstance(
            prefetch,
            dict
        ):

            prefetch = {}

        print(
            "\n" + "=" * 80
        )

        print(
            "HELASYNC CDS REQUEST"
        )

        print(
            "=" * 80
        )

        print(
            f"Patient ID: {patient_id}"
        )

        print(
            f"User ID: {user_id}"
        )

        print(
            f"Hook: {hook_instance}"
        )

        print(
            "Prefetch resources: "
            f"{list(prefetch.keys())}"
        )

        print(
            "=" * 80
        )

        # ====================================================
        # 2. CONVERT PREFETCH TO FHIR BUNDLE
        # ====================================================

        entries = []

        for resource_name, resource in (
            prefetch.items()
        ):

            if resource is None:

                continue

            # ----------------------------------------------
            # CDS Hooks may return a Bundle
            # ----------------------------------------------

            if (
                isinstance(
                    resource,
                    dict
                )
                and resource.get(
                    "resourceType"
                ) == "Bundle"
            ):

                for entry in resource.get(
                    "entry",
                    []
                ):

                    if (
                        isinstance(
                            entry,
                            dict
                        )
                        and entry.get(
                            "resource"
                        )
                    ):

                        entries.append(
                            {
                                "resource":
                                    entry[
                                        "resource"
                                    ]
                            }
                        )

            else:

                entries.append(
                    {
                        "resource":
                            resource
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

        print(
            "FHIR Bundle contains "
            f"{len(entries)} resources."
        )

        # ====================================================
        # 3. NORMALIZE FHIR PATIENT RESOURCE
        # ====================================================

        fhir_bundle = (
            _normalize_patient_resource(
                fhir_bundle=fhir_bundle,
                patient_id=str(
                    patient_id
                ),
            )
        )

        # ====================================================
        # 4. BUILD PATIENT DATA
        # ====================================================

        patient_data = {
            "patientId":
                patient_id,

            "fhirBundle":
                fhir_bundle,
        }

        # ====================================================
        # 5. PRIVACY GATEWAY
        # ====================================================

        try:

            sanitized_patient_data = (
                privacy_gateway.process_patient(
                    patient_data
                )
            )

            print(
                "Privacy Gateway: SUCCESS"
            )

        except Exception as privacy_error:

            print(
                "\n" + "-" * 80
            )

            print(
                "PRIVACY GATEWAY ERROR"
            )

            print(
                "-" * 80
            )

            print(
                f"Type: "
                f"{type(privacy_error).__name__}"
            )

            print(
                f"Message: "
                f"{str(privacy_error)}"
            )

            traceback.print_exc()

            print(
                "-" * 80 + "\n"
            )

            # Never send unprocessed FHIR data
            # to the AI pipeline if privacy processing fails.

            return {
                "cards": [
                    {
                        "summary":
                            "HeLaSync Service Error",

                        "indicator":
                            "warning",

                        "detail": (
                            "The HeLaSync Privacy "
                            "Gateway could not process "
                            "the patient data."
                        ),

                        "source": {
                            "label":
                                "HeLaSync"
                        },
                    }
                ]
            }

        # ====================================================
        # 6. BUILD ADK PROMPT
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

Use this information to perform the HeLaSync
5-agent clinical trial matching workflow.

The workflow consists of:

1. Patient_Data_Agent
2. Clinical_Profile_Agent
3. Trial_Matching_Agent
4. Eligibility_Verification_Agent
5. CDS_Card_Agent

Do not expose direct patient identifiers
in the CDS card.

The final CDS card must follow the exact
HeLaSync card design defined by CDS_Card_Agent.

Patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(
    context,
    indent=2,
    default=str
)}

Return ONLY the final JSON response generated
by the HeLaSync pipeline.

The response must have this structure:

{{
  "cards": [...]
}}
"""

        # ====================================================
        # 7. CREATE UNIQUE ADK SESSION
        # ====================================================

        adk_session_id = (
            f"cds-{uuid.uuid4().hex}"
        )

        print(
            "Creating ADK session: "
            f"{adk_session_id}"
        )

        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=str(user_id),
            session_id=adk_session_id,
        )

        # ====================================================
        # 8. CREATE ADK MESSAGE
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
        # 9. RUN 5-AGENT PIPELINE
        # ====================================================

        print(
            "Starting HeLaSync "
            "5-agent pipeline..."
        )

        final_output = None

        async for event in runner.run_async(
            user_id=str(user_id),
            session_id=session.id,
            new_message=content,
        ):

            if event.is_final_response():

                if (
                    event.content
                    and event.content.parts
                ):

                    parts = []

                    for part in (
                        event.content.parts
                    ):

                        text_value = getattr(
                            part,
                            "text",
                            None,
                        )

                        if text_value:

                            parts.append(
                                text_value
                            )

                    final_output = "".join(
                        parts
                    )

        print(
            "5-agent pipeline completed."
        )

        # ====================================================
        # 10. VALIDATE AGENT OUTPUT
        # ====================================================

        if not final_output:

            raise RuntimeError(
                "The HeLaSync ADK pipeline "
                "did not return a final response."
            )

        print(
            "\n" + "-" * 80
        )

        print(
            "RAW AGENT OUTPUT"
        )

        print(
            "-" * 80
        )

        print(
            final_output
        )

        print(
            "-" * 80 + "\n"
        )

        # ====================================================
        # 11. PARSE AGENT JSON
        # ====================================================

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

                raise ValueError(
                    "Agent returned invalid JSON. "
                    f"Raw output: {final_output}"
                )

        # ====================================================
        # 12. VALIDATE CARDS
        # ====================================================

        cards = result.get(
            "cards",
            []
        )

        if cards is None:

            cards = []

        if not isinstance(
            cards,
            list
        ):

            raise ValueError(
                "Agent response contains "
                "an invalid cards value."
            )

        # ====================================================
        # 13. FORMAT FINAL CDS CARDS
        # ====================================================

        formatted_cards = []

        for card in cards:

            if not isinstance(
                card,
                dict
            ):

                continue

            formatted_card = (
                _format_trial_card(
                    card=card,
                    patient_id=str(
                        patient_id
                    ),
                    user_id=str(
                        user_id
                    ),
                    hook_instance=str(
                        hook_instance
                    ),
                )
            )

            formatted_cards.append(
                formatted_card
            )

        # ====================================================
        # 14. LOG FINAL CDS RESPONSE
        # ====================================================

        print(
            "\n" + "=" * 80
        )

        print(
            "FINAL CDS RESPONSE"
        )

        print(
            "=" * 80
        )

        print(
            json.dumps(
                {
                    "cards":
                        formatted_cards
                },
                indent=2,
                default=str,
            )
        )

        print(
            "=" * 80 + "\n"
        )

        # ====================================================
        # 15. RETURN CDS RESPONSE
        # ====================================================

        return {
            "cards":
                formatted_cards
        }

    except Exception as e:

        # ====================================================
        # FULL ERROR DIAGNOSTICS
        # ====================================================

        print(
            "\n" + "=" * 80
        )

        print(
            "HELASYNC CDS SERVICE ERROR"
        )

        print(
            "=" * 80
        )

        print(
            f"Error type: "
            f"{type(e).__name__}"
        )

        print(
            f"Error message: "
            f"{str(e)}"
        )

        print(
            "\nFull traceback:"
        )

        traceback.print_exc()

        print(
            "=" * 80 + "\n"
        )

        return {
            "cards": [
                {
                    "summary":
                        "HeLaSync Service Error",

                    "indicator":
                        "warning",

                    "detail": (
                        "The HeLaSync clinical "
                        "trial matching service "
                        "encountered an error "
                        "while processing "
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
            "status":
                "error",

            "message":
                "trial_id is required",
        }

    if not patient_id:

        return {
            "status":
                "error",

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
            "status":
                "error",

            "message":
                str(e),
        }

    except Exception as e:

        print(
            "\n" + "=" * 80
        )

        print(
            "REFERRAL CREATION ERROR"
        )

        print(
            "=" * 80
        )

        print(
            f"Error type: "
            f"{type(e).__name__}"
        )

        print(
            f"Error message: "
            f"{str(e)}"
        )

        traceback.print_exc()

        print(
            "=" * 80 + "\n"
        )

        return {
            "status":
                "error",

            "message":
                "Unable to create referral.",
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
            "status":
                "error",

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
