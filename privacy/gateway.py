from typing import Dict, Any

from .deidentify import deidentify_patient


class PrivacyGateway:

    def process_patient(
        self,
        patient: Dict[str, Any]
    ) -> Dict[str, Any]:

        return deidentify_patient(patient)
