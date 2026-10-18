from typing import Dict, Any

from .deidentify import deidentify_patient


class PrivacyGateway:

    def process_patient(
        self,
        patient: Dict[str, Any],
        conditions: Dict[str, Any] | None = None,
        medications: Dict[str, Any] | None = None,
        observations: Dict[str, Any] | None = None,
        patient_id: str | None = None
    ) -> Dict[str, Any]:

        if not patient:
            raise ValueError(
                "Privacy Gateway received an empty Patient resource"
            )

        # Ensure the FHIR Patient resource has an ID.
        # If main.py explicitly provides the patient ID,
        # use it when the Patient object does not already contain one.
        if not patient.get("id"):

            if patient_id:
                patient = {
                    **patient,
                    "id": patient_id
                }

            else:
                raise ValueError(
                    "Privacy Gateway received a Patient resource "
                    "without an id"
                )

        return deidentify_patient(
            patient=patient,
            conditions=conditions,
            medications=medications,
            observations=observations
        )
