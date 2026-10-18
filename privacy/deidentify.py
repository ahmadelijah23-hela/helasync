from datetime import date, datetime
from typing import Dict, Any, List

from .tokenizer import create_patient_token


# ============================================================
# AGE CALCULATION
# ============================================================

def calculate_age(
    birth_date: str
) -> int:

    birth = datetime.strptime(
        birth_date,
        "%Y-%m-%d"
    ).date()

    today = date.today()

    age = (
        today.year
        - birth.year
    )

    if (
        today.month,
        today.day
    ) < (
        birth.month,
        birth.day
    ):

        age -= 1

    return age


# ============================================================
# FHIR CODE EXTRACTION
# ============================================================

def extract_code_text(
    resource: Dict[str, Any]
) -> str:

    code = resource.get(
        "code",
        {}
    )

    if not isinstance(
        code,
        dict
    ):

        return "Unknown"

    # --------------------------------------------------------
    # FHIR CodeableConcept text
    # --------------------------------------------------------

    if code.get("text"):

        return code["text"]


    # --------------------------------------------------------
    # FHIR coding display/code
    # --------------------------------------------------------

    coding = code.get(
        "coding",
        []
    )

    if coding:

        first_coding = coding[0]

        if isinstance(
            first_coding,
            dict
        ):

            return (
                first_coding.get(
                    "display"
                )
                or first_coding.get(
                    "code"
                )
                or "Unknown"
            )

    return "Unknown"


# ============================================================
# RESOURCE NORMALIZATION
# ============================================================

def normalize_resources(
    data: Any,
    resource_type: str,
) -> List[Dict[str, Any]]:

    """
    Normalize FHIR data into a list of resources.

    Supported input formats:

    1. Individual FHIR resource
       {
           "resourceType": "Condition",
           ...
       }

    2. FHIR Bundle
       {
           "resourceType": "Bundle",
           "entry": [...]
       }

    3. Python list of FHIR resources
       [
           {...},
           {...}
       ]

    This allows the Privacy Gateway to work with both
    raw FHIR Bundle data and the structured lists created
    by main.py.
    """

    resources = []

    if not data:
        return resources


    # --------------------------------------------------------
    # Python list
    # --------------------------------------------------------

    if isinstance(
        data,
        list
    ):

        for item in data:

            if not isinstance(
                item,
                dict
            ):

                continue

            if item.get(
                "resourceType"
            ) == resource_type:

                resources.append(
                    item
                )

        return resources


    # --------------------------------------------------------
    # Individual FHIR resource or Bundle
    # --------------------------------------------------------

    if isinstance(
        data,
        dict
    ):

        resource_type_value = data.get(
            "resourceType"
        )

        # Individual resource
        if resource_type_value == resource_type:

            resources.append(
                data
            )

            return resources


        # Bundle
        if resource_type_value == "Bundle":

            for entry in data.get(
                "entry",
                []
            ) or []:

                if not isinstance(
                    entry,
                    dict
                ):

                    continue

                resource = entry.get(
                    "resource"
                )

                if not isinstance(
                    resource,
                    dict
                ):

                    continue

                if resource.get(
                    "resourceType"
                ) == resource_type:

                    resources.append(
                        resource
                    )

    return resources


# ============================================================
# CONDITION EXTRACTION
# ============================================================

def extract_conditions(
    conditions: Any
) -> List[str]:

    results = []

    resources = normalize_resources(
        conditions,
        "Condition"
    )

    for resource in resources:

        condition = extract_code_text(
            resource
        )

        if condition != "Unknown":

            results.append(
                condition
            )

    return results


# ============================================================
# OBSERVATION EXTRACTION
# ============================================================

def extract_observations(
    observations: Any
) -> Dict[str, Any]:

    results = {}

    resources = normalize_resources(
        observations,
        "Observation"
    )

    for observation in resources:

        code = extract_code_text(
            observation
        )

        # ----------------------------------------------------
        # Quantity
        # ----------------------------------------------------

        value_quantity = observation.get(
            "valueQuantity"
        )

        if isinstance(
            value_quantity,
            dict
        ):

            value = value_quantity.get(
                "value"
            )

            unit = value_quantity.get(
                "unit"
            )

            if value is not None:

                results[code] = {
                    "value": value,
                    "unit": unit,
                }

                continue


        # ----------------------------------------------------
        # String
        # ----------------------------------------------------

        value_string = observation.get(
            "valueString"
        )

        if value_string:

            results[code] = (
                value_string
            )

            continue


        # ----------------------------------------------------
        # CodeableConcept
        # ----------------------------------------------------

        value_codeable = observation.get(
            "valueCodeableConcept"
        )

        if isinstance(
            value_codeable,
            dict
        ):

            text = (
                value_codeable.get(
                    "text"
                )
            )

            if text:

                results[code] = text

    return results


# ============================================================
# MEDICATION EXTRACTION
# ============================================================

def extract_medications(
    medications: Any
) -> List[str]:

    results = []

    # Support both MedicationRequest and
    # MedicationStatement resources.

    medication_requests = normalize_resources(
        medications,
        "MedicationRequest"
    )

    medication_statements = normalize_resources(
        medications,
        "MedicationStatement"
    )

    resources = (
        medication_requests
        + medication_statements
    )

    for medication in resources:

        # ----------------------------------------------------
        # MedicationCodeableConcept
        # ----------------------------------------------------

        medication_concept = medication.get(
            "medicationCodeableConcept",
            {}
        )

        if isinstance(
            medication_concept,
            dict
        ):

            if medication_concept.get(
                "text"
            ):

                results.append(
                    medication_concept[
                        "text"
                    ]
                )

                continue

            coding = medication_concept.get(
                "coding",
                []
            )

            if coding:

                first_coding = coding[0]

                if isinstance(
                    first_coding,
                    dict
                ):

                    display = (
                        first_coding.get(
                            "display"
                        )
                        or first_coding.get(
                            "code"
                        )
                    )

                    if display:

                        results.append(
                            display
                        )

                        continue


        # ----------------------------------------------------
        # MedicationReference
        # ----------------------------------------------------

        medication_reference = medication.get(
            "medicationReference"
        )

        if isinstance(
            medication_reference,
            dict
        ):

            display = (
                medication_reference.get(
                    "display"
                )
            )

            if display:

                results.append(
                    display
                )

    return results


# ============================================================
# DEIDENTIFY PATIENT
# ============================================================

def deidentify_patient(
    patient: Dict[str, Any],
    conditions: Any = None,
    medications: Any = None,
    observations: Any = None,
) -> Dict[str, Any]:

    """
    De-identify a FHIR Patient and extract only the
    clinical information required by the HeLaSync
    matching pipeline.

    Direct identifiers such as:

    - Patient name
    - DOB
    - Address
    - Phone
    - Email

    are not passed to the AI pipeline.

    The Patient ID is converted into a secure token.
    """

    # ========================================================
    # VALIDATE PATIENT
    # ========================================================

    if not patient:

        raise ValueError(
            "FHIR Patient resource is required"
        )

    if not isinstance(
        patient,
        dict
    ):

        raise ValueError(
            "FHIR Patient resource must be a dictionary"
        )

    patient_id = patient.get(
        "id"
    )

    if not patient_id:

        raise ValueError(
            "FHIR Patient resource must contain an id"
        )


    # ========================================================
    # CREATE PATIENT TOKEN
    # ========================================================

    patient_token = create_patient_token(
        patient_id
    )


    # ========================================================
    # AGE
    # ========================================================

    birth_date = patient.get(
        "birthDate"
    )

    age = None

    if birth_date:

        try:

            age = calculate_age(
                birth_date
            )

        except (
            ValueError,
            TypeError
        ):

            age = None


    # ========================================================
    # EXTRACT CLINICAL DATA
    # ========================================================

    extracted_conditions = (
        extract_conditions(
            conditions
        )
    )

    extracted_medications = (
        extract_medications(
            medications
        )
    )

    extracted_observations = (
        extract_observations(
            observations
        )
    )


    # ========================================================
    # RETURN SANITIZED PATIENT CONTEXT
    # ========================================================

    return {
        "patient_token": patient_token,

        "age": age,

        "sex": patient.get(
            "gender"
        ),

        "conditions": extracted_conditions,

        "medications": extracted_medications,

        "observations": extracted_observations,

        "procedures": [],

        "clinical_context": {},
    }
