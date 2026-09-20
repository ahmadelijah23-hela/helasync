from datetime import date, datetime
from typing import Dict, Any, List

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


def extract_code_text(
    resource: Dict[str, Any]
) -> str:

    code = resource.get("code", {})

    # Try FHIR CodeableConcept text
    if code.get("text"):
        return code["text"]

    # Try coding display
    coding = code.get("coding", [])

    if coding:

        return (
            coding[0].get("display")
            or coding[0].get("code")
            or "Unknown"
        )

    return "Unknown"


def extract_conditions(
    conditions: Dict[str, Any]
) -> List[str]:

    results = []

    if conditions.get("resourceType") == "Bundle":

        for entry in conditions.get(
            "entry",
            []
        ):

            resource = entry.get(
                "resource",
                {}
            )

            if resource.get(
                "resourceType"
            ) == "Condition":

                condition = extract_code_text(
                    resource
                )

                if condition != "Unknown":
                    results.append(condition)

    elif conditions.get(
        "resourceType"
    ) == "Condition":

        condition = extract_code_text(
            conditions
        )

        if condition != "Unknown":
            results.append(condition)

    return results


def extract_observations(
    observations: Dict[str, Any]
) -> Dict[str, Any]:

    results = {}

    resources = []

    if observations.get(
        "resourceType"
    ) == "Bundle":

        for entry in observations.get(
            "entry",
            []
        ):

            resource = entry.get(
                "resource",
                {}
            )

            if resource.get(
                "resourceType"
            ) == "Observation":

                resources.append(resource)

    elif observations.get(
        "resourceType"
    ) == "Observation":

        resources.append(observations)

    for observation in resources:

        code = extract_code_text(
            observation
        )

        value_quantity = observation.get(
            "valueQuantity"
        )

        if value_quantity:

            value = value_quantity.get(
                "value"
            )

            unit = value_quantity.get(
                "unit"
            )

            if value is not None:

                results[code] = {
                    "value": value,
                    "unit": unit
                }

        elif observation.get(
            "valueString"
        ):

            results[code] = observation[
                "valueString"
            ]

    return results


def extract_medications(
    medications: Dict[str, Any]
) -> List[str]:

    results = []

    resources = []

    if medications.get(
        "resourceType"
    ) == "Bundle":

        for entry in medications.get(
            "entry",
            []
        ):

            resource = entry.get(
                "resource",
                {}
            )

            if resource.get(
                "resourceType"
            ) == "MedicationRequest":

                resources.append(resource)

    elif medications.get(
        "resourceType"
    ) == "MedicationRequest":

        resources.append(medications)

    for medication in resources:

        medication_concept = (
            medication.get(
                "medicationCodeableConcept",
                {}
            )
        )

        if medication_concept.get(
            "text"
        ):

            results.append(
                medication_concept["text"]
            )

            continue

        coding = medication_concept.get(
            "coding",
            []
        )

        if coding:

            display = (
                coding[0].get("display")
                or coding[0].get("code")
            )

            if display:
                results.append(display)

    return results


def deidentify_patient(
    patient: Dict[str, Any],
    conditions: Dict[str, Any] | None = None,
    medications: Dict[str, Any] | None = None,
    observations: Dict[str, Any] | None = None
) -> Dict[str, Any]:

    if not patient:

        raise ValueError(
            "FHIR Patient resource is required"
        )

    patient_id = patient.get("id")

    if not patient_id:

        raise ValueError(
            "FHIR Patient resource must contain an id"
        )

    patient_token = create_patient_token(
        patient_id
    )

    birth_date = patient.get(
        "birthDate"
    )

    age = None

    if birth_date:

        age = calculate_age(
            birth_date
        )

    return {
        "patient_token": patient_token,

        "age": age,

        "sex": patient.get(
            "gender"
        ),

        "conditions": extract_conditions(
            conditions or {}
        ),

        "medications": extract_medications(
            medications or {}
        ),

        "observations": extract_observations(
            observations or {}
        ),

        "procedures": [],

        "clinical_context": {}
    }
