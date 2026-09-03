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
                "id": "helasync"
            }
        ]
    }


@app.post("/cds-services/helasync")
def helasync():
    return {
        "cards": [
            {
                "summary": "Clinical Trial Opportunity",
                "detail": "This patient may qualify for a clinical trial.",
                "indicator": "info",
                "source": {
                    "label": "HeLaSync",
                    "url": "https://www.helasync.org"
                },
                "suggestions": [
                    {
                        "label": "Refer Patient",
                        "uuid": "123",
                        "actions": []
                    }
                ]
            }
        ]
    }
 
