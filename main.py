from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from privacy.gateway import PrivacyGateway


# ==================================================
# FASTAPI APPLICATION
# ==================================================

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync Clinical Trial Matching and CDS API",
    version="1.0.0"
)


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# PRIVACY GATEWAY
# ==================================================

privacy_gateway = PrivacyGateway()


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/")
def home():

    return {
        "message": "HeLaSync API is running",
        "status": "healthy"
    }


# ==================================================
# PRIVACY GATEWAY TEST ENDPOINT
# ==================================================

@app.post("/privacy/process-patient")
def process_patient(
    patient: Dict[str, Any]
):

    try:

        sanitized_patient = (
            privacy_gateway.process_patient(
                patient=patient
            )
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


# ==================================================
# CDS HOOKS SERVICE DISCOVERY
# ==================================================

@app.get("/cds-services")
def cds_services():

    return {
        "services": [
            {
                "hook": "patient-view",

                "title": "HeLaSync",

                "description": (
                    "HeLaSync identifies potential "
                    "clinical trial opportunities "
                    "during routine patient care."
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


# ==================================================
# HELASYNC CDS HOOK
# ==================================================

@app.post("/cds-services/helasync")
def helasync(
    request: Dict[str, Any]
):

    try:

        # ------------------------------------------
        # GET CDS HOOKS PREFETCH DATA
        # ------------------------------------------

        prefetch = request.get(
            "prefetch",
            {}
        )


        # ------------------------------------------
        # PATIENT
        # ------------------------------------------

        patient = prefetch.get(
            "patient"
        )


        # ------------------------------------------
        # CONDITIONS
        # ------------------------------------------

        conditions = prefetch.get(
            "conditions",
            {}
        )


        # ------------------------------------------
        # MEDICATIONS
        # ------------------------------------------

        medications = prefetch.get(
            "medications",
            {}
        )


        # ------------------------------------------
        # OBSERVATIONS
        # ------------------------------------------

        observations = prefetch.get(
            "observations",
            {}
        )


        # ------------------------------------------
        # CHECK FOR PATIENT
        # ------------------------------------------

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
                            "label": "HeLaSync",
                            "url": "https://www.helasync.org"
                        }
                    }
                ]
            }


        # ------------------------------------------
        # SEND DATA THROUGH PRIVACY GATEWAY
        # ------------------------------------------

        sanitized_patient = (
            privacy_gateway.process_patient(

                patient=patient,

                conditions=conditions,

                medications=medications,

                observations=observations
            )
        )


        # ------------------------------------------
        # TEMPORARY DEBUG LOG
        # ------------------------------------------
        #
        # IMPORTANT:
        # This is only for development/testing.
        # Do NOT log patient data in production.
        #

        print(
            "Sanitized patient profile:",
            sanitized_patient
        )


        # ------------------------------------------
        # CURRENT CDS CARD
        # ------------------------------------------

        return {

            "cards": [

                {

                    "summary":
                        "Potential Clinical Trial Match",

                    "indicator":
                        "info",

                    "detail": (
                        "HeLaSync processed the patient's "
                        "clinical information through the "
                        "Privacy Gateway. This patient may "
                        "be eligible for a clinical trial."
                    ),

                    "source": {

                        "label":
                            "HeLaSync",

                        "url":
                            "https://www.helasync.org"
                    },

                    "links": [

                        {

                            "label":
                                "View Clinical Trial",

                            "url":
                                "https://www.helasync.org",

                            "type":
                                "absolute"
                        }

                    ]
                }

            ]
        }


    # ==================================================
    # ERROR HANDLING
    # ==================================================

    except Exception as e:

        print(
            "HeLaSync CDS error:",
            str(e)
        )

        return {

            "cards": [

                {

                    "summary":
                        "HeLaSync",

                    "indicator":
                        "warning",

                    "detail": (
                        "HeLaSync was unable to process "
                        "the patient data."
                    ),

                    "source": {

                        "label":
                            "HeLaSync",

                        "url":
                            "https://www.helasync.org"
                    }

                }

            ]
        }
