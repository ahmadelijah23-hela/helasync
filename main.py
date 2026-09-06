from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
 
app = FastAPI()
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
 
@app.get("/")
def home():
    return {"message": "Hello World"}
 
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
                    "patient": "Patient/{{context.patientId}}",
                    "conditions": "Condition?patient={{context.patientId}}",
                    "medications": "MedicationRequest?patient={{context.patientId}}",
                    "observations": "Observation?patient={{context.patientId}}"
                }
            }
        ]
    }
 
@app.post("/cds-services/helasync")
def helasync():
    return {
  "cards": [
    {
      "summary": "Potential Clinical Trial Match",
      "indicator": "info",
      "detail": "This patient may be eligible for a clinical trial. Ask the patient if they are interested in learning more.",
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
