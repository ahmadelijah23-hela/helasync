from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from privacy.gateway import PrivacyGateway


# --------------------------------------------------
# FastAPI Application
# --------------------------------------------------

app = FastAPI(
    title="HeLaSync API",
    description="HeLaSync Clinical Trial Matching and CDS API",
    version="1.0.0"
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Privacy Gateway
# --------------------------------------------------

privacy_gateway = PrivacyGateway()


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "HeLaSync API is running"
    }


# --------------------------------------------------
# Privacy Gateway Test Endpoint
# --------------------------------------------------

@app.post("/privacy/process-patient")
def process_patient(
    patient: Dict[str, Any]
):

    try:

        sanitized_patient = (
            privacy_gateway.process_patient(
                patient
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


# --------------------------------------------------
# CDS Hooks Service Discovery
# --------------------------------------------------

@app.get("/cds-services")
def cds_services():

    return {
        "services": [
            {
                "hook": "patient-view",
                "title": "HeLaSync",
                "description": "HeLaSync CDS service",
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


# --------------------------------------------------
# HeLaSync CDS Hook
# --------------------------------------------------

@app.post("/cds-services/helasync")
def helasync(request: Dict[str, Any]):

    try:

        # ------------------------------------------
        # Get CDS Hooks prefetch data
        # ------------------------------------------

        prefetch = request.get(
            "prefetch",
            {}
        )

        patient = prefetch.get(
            "patient"
        )

        # ------------------------------------------
        # No patient data
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
        # Send patient through Privacy Gateway
        # ------------------------------------------

        sanitized_patient = (
            privacy_gateway.process_patient(
                patient
            )
        )

        # ------------------------------------------
        # Temporary logging
        # ------------------------------------------
        #
        # This allows us to verify that the patient
        # has been processed by the Privacy Gateway.
        #
        # IMPORTANT:
        # Do not log real patient data in production.
        #

        print(
            "Sanitized patient:",
            sanitized_patient
        )

        # ------------------------------------------
        # Return CDS Hooks Card
        # ------------------------------------------

        return {
            "cards": [
                {
                    "summary": "Potential Clinical Trial Match",
                    "indicator": "info",
                    "detail": (
                        "HeLaSync processed the patient "
                        "through the Privacy Gateway. "
                        "This patient may be eligible "
                        "for a clinical trial."
                    ),
                    "source": {
                        "label": "HeLaSync",
                        "url": "https://www.helasync.org"
                    },
                    "links": [
                        {
                            "label": "View Clinical Trial",
                            "url": "https://www.helasync.org",
                            "type": "absolute"
                        }
                    ]
                }
            ]
        }

    except Exception as e:

        # ------------------------------------------
        # Error handling
        # ------------------------------------------

        print(
            "HeLaSync CDS error:",
            str(e)
        )

        return {
            "cards": [
                {
                    "summary": "HeLaSync",
                    "indicator": "warning",
                    "detail": (
                        "HeLaSync was unable to process "
                        "the patient data."
                    ),
                    "source": {
                        "label": "HeLaSync",
                        "url": "https://www.helasync.org"
                    }
                }
            ]
        }
