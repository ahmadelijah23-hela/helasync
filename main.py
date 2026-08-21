from fastapi import FastAPI

app = FastAPI()

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
                "summary": "Hello from HeLaSync",
                "detail": "HeLaSync is successfully connected to CDS Hooks.",
                "indicator": "info"
            }
        ]
    }
