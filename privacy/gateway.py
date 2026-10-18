from typing import Dict, Any

from .deidentify import deidentify_patient


class PrivacyGateway:

    def process_patient(
        self,
        patient: Dict[str, Any],
        conditions: Any = None,
        medications: Any = None,
        observations: Any = None,
        patient_id: str | None = None,
    ) -> Dict[str, Any]:

        """
        HeLaSync Privacy Gateway.

        Supports two input formats:

        1. New normalized format from main.py:

            {
                "patientId": "...",
                "patient": {...FHIR Patient...},
                "conditions": [...],
                "observations": [...],
                "medications": [...]
            }

        2. Legacy format:

            process_patient(
                patient={...FHIR Patient...},
                conditions=...,
                medications=...,
                observations=...,
                patient_id="..."
            )

        The gateway always extracts the actual FHIR Patient
        resource before sending data to the de-identification layer.
        """

        # ============================================================
        # 1. VALIDATE INPUT
        # ============================================================

        if not patient:
            raise ValueError(
                "Privacy Gateway received an empty Patient resource"
            )

        # ============================================================
        # 2. DETECT NEW NORMALIZED GATEWAY INPUT
        # ============================================================
        #
        # main.py now sends:
        #
        # {
        #     "patientId": "...",
        #     "patient": {...},
        #     "conditions": [...],
        #     "observations": [...],
        #     "medications": [...]
        # }
        #
        # In that case, extract the actual Patient resource.
        # ============================================================

        if (
            isinstance(patient, dict)
            and isinstance(patient.get("patient"), dict)
        ):
            gateway_input = patient

            patient_id = (
                gateway_input.get("patientId")
                or patient_id
            )

            patient = gateway_input.get("patient", {})

            conditions = (
                gateway_input.get("conditions")
                if gateway_input.get("conditions") is not None
                else conditions
            )

            medications = (
                gateway_input.get("medications")
                if gateway_input.get("medications") is not None
                else medications
            )

            observations = (
                gateway_input.get("observations")
                if gateway_input.get("observations") is not None
                else observations
            )

        # ============================================================
        # 3. VALIDATE THAT WE NOW HAVE A REAL FHIR PATIENT
        # ============================================================

        if not isinstance(patient, dict) or not patient:
            raise ValueError(
                "Privacy Gateway could not locate a valid "
                "FHIR Patient resource"
            )

        # Make sure this is explicitly a Patient resource.
        patient["resourceType"] = "Patient"

        # ============================================================
        # 4. ENSURE THE PATIENT HAS AN ID
        # ============================================================

        if not patient.get("id"):

            if patient_id:
                patient = {
                    **patient,
                    "resourceType": "Patient",
                    "id": patient_id,
                }

            else:
                raise ValueError(
                    "Privacy Gateway received a Patient resource "
                    "without an id"
                )

        # ============================================================
        # 5. LOG SAFE PROCESSING INFORMATION
        # ============================================================

        print(
            "Privacy Gateway received Patient resource."
        )

        print(
            f"Privacy Gateway Patient ID present: "
            f"{patient.get('id') is not None}"
        )

        print(
            "Privacy Gateway de-identifying patient data."
        )

        # ============================================================
        # 6. DE-IDENTIFY
        # ============================================================

        return deidentify_patient(
            patient=patient,
            conditions=conditions,
            medications=medications,
            observations=observations,
        )
