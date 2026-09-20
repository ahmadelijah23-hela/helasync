from datetime import date, datetime
from typing import Dict, Any

from .tokenizer import create_patient_token


def calculate_age(birth_date: str) -> int:

    birth = datetime.strptime(
        birth_date,
        "%Y-%m-%d"
    ).date()

    today = date.today()

    age = today.year - birth.year

    if (today.month, today.day) < (
        birth.month,
        birth.day
    ):
        age -= 1

    return age


def deidentify_patient(
    patient: Dict[str, Any]
) -> Dict[str, Any]:

    patient_id = patient.get("id")

    if not patient_id:
        raise ValueError(
            "FHIR Patient resource must contain an id"
        )

    patient_token = create_patient_token(
        patient_id
    )

    birth_date = patient.get("birthDate")

    age = None

    if birth_date:
        age = calculate_age(
            birth_date
        )

    return {
        "patient_token": patient_token,
        "age": age,
        "sex": patient.get("gender"),

        "conditions": [],
        "medications": [],
        "procedures": [],
        "observations": {},

        "clinical_context": {}
    }
