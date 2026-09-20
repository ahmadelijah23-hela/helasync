from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

from privacy.gateway import PrivacyGateway


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
def helasync():

    return {
        "cards": [
            {
                "summary": "Potential Clinical Trial Match",

                "indicator": "info",

                "detail": (
                    "This patient may be eligible for a "
                    "clinical trial. Ask the patient if "
                    "they are interested in learning more."
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
