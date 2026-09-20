from typing import Dict, Any

from .deidentify import deidentify_patient


class PrivacyGateway:

    def process_patient(
        self,
        patient: Dict[str, Any],
        conditions: Dict[str, Any] | None = None,
        medications: Dict[str, Any] | None = None,
        observations: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:

        return deidentify_patient(
            patient=patient,
            conditions=conditions,
            medications=medications,
            observations=observations
        )
