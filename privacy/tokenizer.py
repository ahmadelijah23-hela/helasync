import hashlib
import os


TOKEN_SECRET = os.getenv("PATIENT_TOKEN_SECRET")


def create_patient_token(patient_id: str) -> str:

    if not TOKEN_SECRET:
        raise RuntimeError(
            "PATIENT_TOKEN_SECRET is not configured"
        )

    raw = f"{TOKEN_SECRET}:{patient_id}"

    token = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    return f"PT_{token[:16]}"
