import json
from typing import Any, Dict
from urllib.parse import urlencode

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
    version="1.6.4",
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
# RESEARCH REFERRAL DASHBOARD
# ============================================================

app.include_router(research_router)


# ============================================================
# REFERRAL LAUNCH WORKFLOW
# ============================================================

app.include_router(referral_launch_router)


# ============================================================
# FHIR / PRIVACY NORMALIZATION HELPERS
# ============================================================

def _resource_from_entry(
    entry: Any
) -> Dict[str, Any] | None:

    if not isinstance(entry, dict):
        return None

    resource = entry.get("resource")

    if isinstance(resource, dict):
        return resource

    if entry.get("resourceType"):
        return entry

    return None


def flatten_prefetch(
    prefetch: Dict[str, Any]
) -> list[Dict[str, Any]]:

    resources: list[Dict[str, Any]] = []

    for value in (prefetch or {}).values():

        if value is None:
            continue

        if (
            isinstance(value, dict)
            and value.get("resourceType") == "Bundle"
        ):

            for entry in value.get(
                "entry",
                []
            ):

                resource = _resource_from_entry(
                    entry
                )

                if resource:
                    resources.append(resource)

        elif isinstance(value, dict):

            resources.append(value)

    return resources


def find_patient_resource(
    fhir_bundle: Dict[str, Any],
    patient_id: str,
) -> Dict[str, Any]:

    resources = []

    for entry in fhir_bundle.get(
        "entry",
        []
    ):

        resource = _resource_from_entry(
            entry
        )

        if resource:
            resources.append(resource)


    # --------------------------------------------------------
    # First preference:
    # Patient with the exact CDS Hooks patient ID.
    # --------------------------------------------------------

    for resource in resources:

        if (
            resource.get("resourceType")
            == "Patient"
            and str(
                resource.get(
                    "id",
                    ""
                )
            )
            == str(patient_id)
        ):

            return dict(resource)


    # --------------------------------------------------------
    # Second preference:
    # Any Patient resource.
    # --------------------------------------------------------

    for resource in resources:

        if resource.get(
            "resourceType"
        ) == "Patient":

            patient = dict(resource)

            if (
                not patient.get("id")
                and patient_id
            ):

                patient["id"] = patient_id

            return patient


    # --------------------------------------------------------
    # Last-resort Patient shell.
    # --------------------------------------------------------

    return {
        "resourceType": "Patient",
        "id": patient_id,
    }


def normalize_patient(
    fhir_bundle: Dict[str, Any],
    patient_id: str,
    prefetch: Dict[str, Any] | None = None,
) -> Dict[str, Any]:

    patient = find_patient_resource(
        fhir_bundle,
        patient_id,
    )

    patient["resourceType"] = "Patient"

    # CDS Hooks context patientId is authoritative.
    if patient_id:
        patient["id"] = patient_id

    return patient


def build_privacy_input(
    patient_id: str,
    patient: Dict[str, Any],
    fhir_bundle: Dict[str, Any],
) -> Dict[str, Any]:

    """
    Build the input expected by the Privacy Gateway.

    CRITICAL:
    `patient` is the actual FHIR Patient resource.

    It contains:

        resourceType = Patient
        id = helasync-test-001

    This prevents the previous:

        FHIR Patient resource must contain an id

    error.
    """

    resources = [

        _resource_from_entry(entry)

        for entry in fhir_bundle.get(
            "entry",
            []
        )

    ]

    resources = [
        resource
        for resource in resources
        if resource
    ]


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
        ) in {
            "MedicationRequest",
            "MedicationStatement",
        }

    ]


    procedures = [

        resource

        for resource in resources

        if resource.get(
            "resourceType"
        ) == "Procedure"

    ]


    allergies = [

        resource

        for resource in resources

        if resource.get(
            "resourceType"
        ) == "AllergyIntolerance"

    ]


    return {

        "patientId":
            patient_id,

        "patient":
            patient,

        "conditions":
            conditions,

        "observations":
            observations,

        "medications":
            medications,

        "procedures":
            procedures,

        "allergies":
            allergies,

    }


# ============================================================
# BASIC HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {

        "message":
            "HeLaSync API is running",

        "status":
            "healthy",

        "pipeline":
            "5-agent clinical trial matching pipeline",

        "version":
            "1.6.4",

    }


# ============================================================
# AGENT STATUS
# ============================================================

@app.get("/agent-status")
async def agent_status():

    return {

        "status":
            "healthy",

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

    """
    Process patient information through the
    HeLaSync Privacy Gateway.
    """

    try:

        # ----------------------------------------------------
        # Accept either the new Privacy Gateway shape
        # or the older {patientId, fhirBundle} wrapper.
        # ----------------------------------------------------

        if (
            isinstance(
                patient_data,
                dict
            )
            and "fhirBundle"
            in patient_data
            and "patient"
            not in patient_data
        ):

            direct_patient_id = (
                patient_data.get(
                    "patientId",
                    "unknown-patient",
                )
            )

            direct_bundle = (
                patient_data.get(
                    "fhirBundle",
                    {
                        "resourceType":
                            "Bundle",

                        "type":
                            "collection",

                        "entry":
                            [],
                    },
                )
            )

            direct_patient = normalize_patient(
                direct_bundle,
                direct_patient_id,
            )

            patient_data = build_privacy_input(
                direct_patient_id,
                direct_patient,
                direct_bundle,
            )


        sanitized_data = (
            privacy_gateway.process_patient(
                patient_data
            )
        )


        return {

            "status":
                "success",

            "privacy_processed":
                True,

            "data":
                sanitized_data,

        }


    except Exception as e:

        return {

            "status":
                "error",

            "privacy_processed":
                False,

            "error":
                str(e),

        }


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

                "description":
                    (
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
                        "Condition?patient={{context.patientId}}",

                    "observations":
                        "Observation?patient={{context.patientId}}",

                    "medications":
                        (
                            "MedicationRequest?"
                            "patient={{context.patientId}}"
                        ),

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

    """
    Main HeLaSync CDS Hooks endpoint.

    CDS Hooks request
            ↓
    FHIR normalization
            ↓
    Privacy Gateway
            ↓
    5-agent pipeline
            ↓
    CDS Hooks card
            ↓
    HeLaSync Smart App
    """

    try:

        # ====================================================
        # 1. EXTRACT REQUEST INFORMATION
        # ====================================================

        hook_instance = request.get(
            "hookInstance",
            "helasync-hook-instance",
        )

        context = request.get(
            "context",
            {}
        ) or {}

        prefetch = request.get(
            "prefetch",
            {}
        ) or {}


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


        print("")
        print("=" * 80)
        print("HELASYNC CDS REQUEST")
        print("=" * 80)

        print(
            f"Patient ID: {patient_id}"
        )

        print(
            f"User ID: {user_id}"
        )

        print(
            f"Hook instance: {hook_instance}"
        )

        print(
            f"Prefetch keys: "
            f"{list(prefetch.keys())}"
        )


        # ====================================================
        # 2. BUILD FHIR BUNDLE
        # ====================================================

        entries = []


        for resource in prefetch.values():

            if resource is None:
                continue


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


            elif isinstance(
                resource,
                dict
            ):

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
            f"FHIR Bundle contains "
            f"{len(entries)} resources."
        )


        # ====================================================
        # 3. NORMALIZE PATIENT
        # ====================================================

        patient = normalize_patient(

            fhir_bundle,

            patient_id,

            prefetch=prefetch,

        )


        print("")
        print(
            "Normalized Patient resource:"
        )

        print(
            json.dumps(
                patient,
                indent=2,
                default=str,
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


        print("")
        print(
            "Privacy Gateway input prepared."
        )

        print(
            "Explicit Patient ID passed to gateway: "
            f"{patient_id}"
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


        except Exception as privacy_error:

            import traceback


            print("")
            print("=" * 80)
            print(
                "PRIVACY GATEWAY ERROR"
            )
            print("=" * 80)

            print(
                f"Type: "
                f"{type(privacy_error).__name__}"
            )

            print(
                f"Message: "
                f"{privacy_error}"
            )

            traceback.print_exc()

            print("=" * 80)


            # Fail closed.
            return {

                "cards": [

                    {

                        "summary":
                            "HeLaSync Service Error",

                        "indicator":
                            "warning",

                        "detail":
                            (
                                "The HeLaSync Privacy "
                                "Gateway could not "
                                "process the patient data."
                            ),

                        "source": {

                            "label":
                                "HeLaSync"

                        },

                    }

                ]

            }


        print(
            "Privacy Gateway processing succeeded."
        )


        if isinstance(
            sanitized_patient_data,
            dict
        ):

            print(
                "Sanitized patient data keys: "
                f"{list(sanitized_patient_data.keys())}"
            )


        # ====================================================
        # 6. SEND SANITIZED DATA TO AGENTS
        # ====================================================

        patient_context = json.dumps(

            sanitized_patient_data,

            indent=2,

            default=str,

        )


        prompt = f"""
You are processing a CDS Hooks patient-view request for HeLaSync.

The following patient information has already passed through the
HeLaSync Privacy Gateway.

Use ONLY this sanitized information for clinical trial matching.

Do not expose direct patient identifiers in the CDS card.

Do not invent missing clinical information.

Sanitized patient context:

{patient_context}

Original CDS Hooks context:

{json.dumps(context, indent=2, default=str)}

Run the HeLaSync 5-agent pipeline.

The final response must be valid JSON.
"""


        # ====================================================
        # 7. CREATE ADK SESSION
        # ====================================================

        session = (
            await session_service.create_session(

                app_name:
                    APP_NAME,

                user_id:
                    user_id,

                session_id:
                    hook_instance,

            )
        )


        content = types.Content(

            role:
                "user",

            parts: [

                types.Part(
                    text=prompt
                )

            ],

        )


        # ====================================================
        # 8. RUN FIVE-AGENT PIPELINE
        # ====================================================

        print("")
        print("=" * 80)
        print(
            "STARTING HELASYNC 5-AGENT PIPELINE"
        )
        print("=" * 80)


        final_output = None


        async for event in runner.run_async(

            user_id:
                user_id,

            session_id:
                session.id,

            new_message:
                content,

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
                            None,
                        )

                    )


        # ====================================================
        # 9. PARSE AGENT 5 OUTPUT
        # ====================================================

        if not final_output:

            result = {
                "cards": []
            }


        else:

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

                print(
                    "Agent 5 returned invalid JSON:"
                )

                print(
                    final_output
                )

                result = {
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

            cards = []


        print("")
        print("=" * 80)
        print(
            "FINAL CDS CARDS FROM AGENT 5"
        )
        print("=" * 80)

        print(
            json.dumps(
                cards,
                indent=2,
                default=str,
            )
        )


        # ====================================================
        # 10. NORMALIZE CDS CARD
        # ====================================================

        normalized_cards = []


        for card in cards:

            if not isinstance(
                card,
                dict
            ):

                continue


            summary = card.get(

                "summary",

                "Potential Clinical Trial Opportunity",

            )


            # Only present an actual trial opportunity.
            if (
                summary
                != "Potential Clinical Trial Opportunity"
            ):

                continue


            detail = str(
                card.get(
                    "detail",
                    ""
                )
            )


            extension = card.get(
                "extension",
                {}
            ) or {}


            trial_id = extension.get(
                "helasync_trial_id"
            )


            # Backward-compatible trial ID extraction.
            if not trial_id:

                if (
                    "(" in detail
                    and ")" in detail
                ):

                    possible = (

                        detail

                        .split("(")[-1]

                        .split(")")[0]

                        .strip()

                    )


                    if possible.upper().startswith(
                        "NCT"
                    ):

                        trial_id = possible


            # Never expose internal metadata.
            card.pop(
                "extension",
                None
            )


            # Locked CDS card wording.
            card["summary"] = (
                "Potential Clinical Trial Opportunity"
            )


            card["source"] = {
                "label":
                    "HeLaSync"
            }


            card["indicator"] = (
                "info"
            )


            # =================================================
            # SMART APP LINK
            # =================================================

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


                card["links"] = [

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

                card["links"] = []


            normalized_cards.append(
                card
            )


        # ====================================================
        # 11. FINAL CDS RESPONSE
        # ====================================================

        print("")
        print("=" * 80)
        print(
            "FINAL CDS RESPONSE"
        )
        print("=" * 80)

        print(

            json.dumps(

                {
                    "cards":
                        normalized_cards
                },

                indent=2,

                default=str,

            )

        )

        print("=" * 80)


        return {

            "cards":
                normalized_cards

        }


    except Exception as e:

        import traceback


        print("")
        print("=" * 80)
        print(
            "HELASYNC CDS PIPELINE ERROR"
        )
        print("=" * 80)

        print(
            f"Type: "
            f"{type(e).__name__}"
        )

        print(
            f"Message: "
            f"{e}"
        )

        traceback.print_exc()

        print("=" * 80)


        return {

            "cards": [

                {

                    "summary":
                        "HeLaSync Service Error",

                    "indicator":
                        "warning",

                    "detail":
                        (
                            "The HeLaSync clinical "
                            "trial matching service "
                            "encountered an error "
                            "while processing this "
                            "request."
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

    """
    Create a HeLaSync clinical trial referral.
    """

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

            trial_id=
                trial_id,

            patient_id=
                patient_id,

            clinician_id=
                clinician_id,

            encounter_id=
                encounter_id,

            source=
                payload.get(
                    "source",
                    "CDS Hooks",
                ),

            patient_data=
                payload.get(
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

@app.get(
    "/referrals"
)
async def list_referrals_endpoint():

    return list_referrals()
