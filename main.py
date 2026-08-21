from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "HeLaSync backend is running"}

@app.get("/cds-services")
def cds_services():
    return {
        "services": [
            {
                "hook": "patient-view",
                "title": "HeLaSync Clinical Trial Matching",
                "description": "Matches patients to potentially eligible clinical trials",
                "id": "helasync-trial-matching"
            }
        ]
    }
