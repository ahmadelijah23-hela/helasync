import json
from pathlib import Path

from google.adk.agents import Agent, SequentialAgent


# ============================================================
# LOAD CLINICAL TRIALS
# ============================================================

def load_trials():
    """
    Load all clinical trial JSON files from the Trial_List directory.
    """

    trial_folder = Path(__file__).parent / "Trial_List"

    if not trial_folder.exists():
        raise FileNotFoundError(
            f"Trial_List folder was not found: {trial_folder}"
        )

    trials = []

    for trial_file in sorted(trial_folder.iterdir()):

        # Ignore hidden files
        if trial_file.name.startswith("."):
            continue

        # Ignore folders
        if not trial_file.is_file():
            continue

        # Only process JSON files
        if trial_file.suffix.lower() != ".json":
            continue

        try:
            with open(trial_file, "r", encoding="utf-8") as file:
                trial_data = json.load(file)

            trials.append(trial_data)

        except json.JSONDecodeError as e:
            print(
                f"WARNING: Could not parse {trial_file.name}: {e}"
            )

        except Exception as e:
            print(
                f"WARNING: Could not read {trial_file.name}: {e}"
            )

    if not trials:
        raise ValueError(
            "No valid clinical trial JSON files were found in Trial_List."
        )

    print(f"Loaded {len(trials)} clinical trial files.")

    return trials


# Load trials when application starts
trial_list = load_trials()

# Convert trials to readable JSON for agents
trial_list_json = json.dumps(
    trial_list,
    indent=2
)


# ============================================================
# AGENT 1
# PATIENT DATA AGENT
# ============================================================

patient_data_agent = Agent(

    model="gemini-3.6-flash",

    name="Patient_Data_Agent",

    description=(
        "Extracts and structures patient demographics, conditions, "
        "medications, procedures, laboratory results, imaging, "
        "and medical history from FHIR data."
    ),

    instruction="""
You are HeLaSync Agent 1: Patient Data Agent.

Your ONLY job is to extract and structure information from the
provided FHIR Bundle.

Do NOT determine clinical trial eligibility.

Do NOT recommend clinical trials.

Do NOT invent missing information.

Do NOT make clinical decisions.

==================================================
EXTRACT
==================================================

Extract:

1. Patient ID
2. Date of birth
3. Age
4. Sex
5. Gender
6. Active conditions
7. Historical conditions
8. Medications
9. Procedures
10. Laboratory results
11. Imaging
12. Allergies
13. Relevant medical history

Calculate age from birthDate when possible.

Preserve actual documented values and units.

If information is missing, mark it as unknown.

Never assume missing information means the patient does not
have a condition.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Use this structure:

{
  "patient": {
    "id": "",
    "birthDate": "",
    "age": null,
    "sex": "",
    "gender": ""
  },
  "conditions": [],
  "medications": [],
  "procedures": [],
  "labs": [],
  "imaging": [],
  "relevant_history": {
    "allergies": [],
    "family_history": [],
    "surgical_history": [],
    "other": []
  },
  "data_gaps": []
}
""",

    output_key="patient_data"
)


# ============================================================
# AGENT 2
# CLINICAL PROFILE AGENT
# ============================================================

clinical_profile_agent = Agent(

    model="gemini-3.6-flash",

    name="Clinical_Profile_Agent",

    description=(
        "Creates a concise clinical profile from the structured "
        "patient data for clinical trial matching."
    ),

    instruction="""
You are HeLaSync Agent 2: Clinical Profile Agent.

Agent 1 has extracted the patient's FHIR information.

Agent 1 output:

{patient_data}

Your job is to create a concise clinical profile that highlights
information relevant to clinical trial matching.

==================================================
IMPORTANT
==================================================

Use ONLY information provided by Agent 1.

Do NOT invent information.

Do NOT determine clinical trial eligibility.

Do NOT recommend a trial.

Do NOT assume missing information.

==================================================
PROFILE
==================================================

Summarize:

- Patient demographics
- Age
- Sex
- Active conditions
- Relevant historical conditions
- Important medications
- Important laboratory values
- Relevant procedures
- Relevant medical history
- Important data gaps

Highlight objective values such as:

- HbA1c
- eGFR
- Blood pressure
- BMI
- Laboratory results
- Disease severity

ONLY when actually documented.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Use:

{
  "clinical_profile": {
    "patient_id": "",
    "age": null,
    "sex": "",
    "conditions": [],
    "medications": [],
    "labs": [],
    "procedures": [],
    "relevant_history": [],
    "data_gaps": []
  }
}
""",

    output_key="clinical_profile"
)


# ============================================================
# AGENT 3
# TRIAL MATCHING AGENT
# ============================================================

trial_matching_agent = Agent(

    model="gemini-3.6-flash",

    name="Trial_Matching_Agent",

    description=(
        "Compares the patient's clinical profile against active "
        "clinical trials and identifies potential trial candidates."
    ),

    instruction=f"""
You are HeLaSync Agent 3: Clinical Trial Matching Agent.

The Clinical Profile Agent produced:

{{clinical_profile}}

The available clinical trials are:

{trial_list_json}

==================================================
YOUR JOB
==================================================

Evaluate EVERY active clinical trial.

Identify trials where the patient's documented clinical profile
appears clinically aligned with the trial's disease area and
basic requirements.

This is a CANDIDATE MATCHING step.

Agent 4 will perform detailed eligibility verification.

==================================================
ACTIVE TRIALS
==================================================

Consider trials with statuses such as:

RECRUITING
ENROLLING_BY_INVITATION
NOT_YET_RECRUITING
ACTIVE_NOT_RECRUITING

Do NOT select:

COMPLETED
TERMINATED
SUSPENDED
WITHDRAWN

==================================================
RULES
==================================================

Consider:

1. Disease/condition alignment
2. Age requirements when obvious
3. Sex requirements when obvious
4. Obvious clinical conflicts
5. Clearly documented exclusion criteria

Do NOT reject a potentially relevant trial solely because
information is missing.

Missing information should be passed to Agent 4.

Do NOT perform final eligibility verification.

Do NOT invent patient information.

Do NOT invent trial requirements.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Use:

{{
  "candidate_trials": [
    {{
      "trial_id": "",
      "trial_title": "",
      "reason": ""
    }}
  ]
}}

If no potential candidates exist:

{{
  "candidate_trials": []
}}
""",

    output_key="trial_matches"
)


# ============================================================
# AGENT 4
# ELIGIBILITY VERIFICATION AGENT
# ============================================================

eligibility_verification_agent = Agent(

    model="gemini-3.6-flash",

    name="Eligibility_Verification_Agent",

    description=(
        "Performs structured verification of trial inclusion and exclusion "
        "criteria using gating, secondary, and exclusion categories."
    ),

    # IMPORTANT:
    # This instruction is intentionally NOT an f-string.  The trial JSON is
    # appended separately so literal JSON braces are never interpreted by
    # Python as format specifiers.
    instruction=(
        """
You are HeLaSync Agent 4: Eligibility Verification Agent.

Your job is to perform a structured, preliminary eligibility verification
for every candidate trial identified by Agent 3.

==================================================
INPUTS
==================================================

Patient clinical profile:

{clinical_profile}

Candidate trials identified by Agent 3:

{trial_matches}

The complete trial JSON files are provided below.

==================================================
FULL TRIAL DATA
==================================================

"""
        + trial_list_json
        + """

==================================================
STEP 1 — READ THE ACTUAL TRIAL CRITERIA
==================================================

For each candidate trial, use the actual value at:

protocolSection.eligibilityModule.eligibilityCriteria

The eligibilityCriteria field contains free text such as:

Inclusion Criteria:
1. Age 18 or older.
2. Diagnosis of Heart Failure.
3. NT-proBNP above 300 pg/mL.

Exclusion Criteria:
1. Pregnancy.
2. eGFR below 30 mL/min/1.73 m2.

You MUST parse the actual numbered inclusion and exclusion criteria from
the trial JSON before evaluating them.

Do not invent criteria that are not present in the trial JSON.

Do not replace the trial's actual criterion with a generic assumption.

Preserve the meaning of the original criterion in your output.

==================================================
STEP 2 — CLASSIFY EACH CRITERION
==================================================

Every inclusion criterion must be classified as either:

1. GATING
2. SECONDARY

Every exclusion criterion is classified as:

3. EXCLUSION

GATING criteria are criteria that define whether the patient belongs to
the trial's required study population or otherwise represent a core,
required eligibility condition.

Examples include:

- Age requirement
- Required disease diagnosis
- Required disease subtype
- Required confirmed diagnosis that defines the study population

For example, in NCTFAKE002:

"Diagnosis of heart failure" = GATING
"Confirmed diagnosis of cardiac amyloidosis" = GATING

A patient without confirmed cardiac amyloidosis must NOT be presented as
a potential match for that trial merely because other values match.

SECONDARY criteria are explicit inclusion requirements that can be
verified from patient data but do not define the core disease population.
For the current synthetic trial set:

NCTFAKE001:
- HbA1c between 6.5% and 8.0% = SECONDARY

NCTFAKE002:
- NT-proBNP above 300 pg/mL = SECONDARY

NCTFAKE003:
- NT-proBNP above 300 pg/mL = SECONDARY

Do not assume every laboratory criterion is secondary in future trials.
Classify based on the actual trial context.

==================================================
STEP 3 — EVALUATE GATING CRITERIA
==================================================

For every GATING criterion use exactly one status:

MET
NOT_MET
UNKNOWN

MET means the available patient data directly supports the criterion.

NOT_MET means the available patient data directly contradicts the
criterion.

UNKNOWN means the required information is not available or cannot be
reliably determined from the provided patient data.

NEVER convert UNKNOWN into NOT_MET.

Examples:

If age is 65 and the trial requires age >=18:
MET

If age is 16 and the trial requires age >=18:
NOT_MET

If age is unavailable:
UNKNOWN

If heart failure is documented:
MET

If the trial requires cardiac amyloidosis and the patient has no
confirmed cardiac amyloidosis documented:
UNKNOWN unless the patient data explicitly establishes that the
condition is absent.

If the patient data explicitly documents that the required disease is
not present, use NOT_MET.

==================================================
STEP 4 — EVALUATE SECONDARY CRITERIA
==================================================

For every SECONDARY criterion use exactly one status:

MET
NOT_MET
UNKNOWN

Use the same evidence rules as above.

A secondary criterion that is UNKNOWN does NOT automatically block a
potential match if all GATING criteria are MET and no exclusion is
present.

Example:

Trial requires HbA1c 6.5–8.0%.

HbA1c = 7.1% -> MET
HbA1c = 9.2% -> NOT_MET
HbA1c unavailable -> UNKNOWN

==================================================
STEP 5 — EVALUATE EXCLUSION CRITERIA
==================================================

For every EXCLUSION criterion use exactly one status:

PRESENT
CLEAR
UNKNOWN

PRESENT means the patient clearly meets the exclusion criterion.

CLEAR means available patient information supports that the exclusion
criterion is not present.

UNKNOWN means the available information cannot reliably determine whether
the exclusion criterion is present.

Examples:

Trial excludes eGFR below 30.

eGFR = 65 -> CLEAR
eGFR = 20 -> PRESENT
eGFR unavailable -> UNKNOWN

Do not assume an undocumented exclusion is absent.

==================================================
STEP 6 — OVERALL STATUS
==================================================

Use exactly one of these statuses for every verified trial:

POTENTIAL_MATCH
BLOCKED
NOT_ELIGIBLE
INSUFFICIENT_INFORMATION

POTENTIAL_MATCH means:

- ALL GATING criteria are MET.
- NO exclusion criterion is PRESENT.
- Secondary criteria may be MET, NOT_MET, or UNKNOWN.

If a SECONDARY criterion is NOT_MET, use NOT_ELIGIBLE because an explicit
required inclusion criterion is not satisfied.

BLOCKED means:

- At least one GATING criterion is UNKNOWN.
- There is not enough information to establish that the patient belongs
to the trial's core target population.

NOT_ELIGIBLE means:

- At least one GATING criterion is NOT_MET, OR
- At least one SECONDARY criterion is NOT_MET, OR
- At least one EXCLUSION criterion is PRESENT.

INSUFFICIENT_INFORMATION is used when the trial cannot be responsibly
classified because the available information is broadly inadequate.
Prefer BLOCKED when a specific core/gating criterion is unknown.

IMPORTANT:

Do NOT calculate an eligibility percentage.

Do NOT say 8/10 criteria = 80% eligible.

Do NOT present a patient as a potential match when a core/gating disease
criterion is missing or unknown.

==================================================
STEP 7 — MISSING INFORMATION
==================================================

For every UNKNOWN criterion, add an entry to missing_information.

Each entry must identify:

- criterion
- category
- why_information_is_needed

Do NOT recommend a test, diagnosis, medication, or clinical intervention
solely to make a patient eligible for a trial.

Simply identify what information is missing and why it matters to trial
eligibility verification.

==================================================
EVIDENCE RULE
==================================================

Every evaluated criterion MUST include concise evidence based on the
provided patient data.

Evidence must distinguish between:

- documented facts
- explicitly documented absence
- unavailable information

Never invent evidence.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY valid JSON.

Use this exact structure:

{
  "verification_status": "MATCH",
  "verified_trials": [
    {
      "trial_id": "NCTFAKE003",
      "trial_title": "HeLaSync Heart Failure Treatment Study",
      "overall_status": "POTENTIAL_MATCH",
      "summary": "All gating criteria are met and no exclusion criterion is present.",
      "gating_criteria": [
        {
          "criterion": "Age 18 or older",
          "status": "MET",
          "evidence": "Patient age is 65 years."
        }
      ],
      "secondary_criteria": [
        {
          "criterion": "NT-proBNP above 300 pg/mL",
          "status": "UNKNOWN",
          "evidence": "No NT-proBNP value is documented."
        }
      ],
      "exclusion_criteria": [
        {
          "criterion": "Pregnancy",
          "status": "CLEAR",
          "evidence": "Pregnancy is documented as not present."
        }
      ],
      "missing_information": [
        {
          "criterion": "NT-proBNP above 300 pg/mL",
          "category": "secondary",
          "why_information_is_needed": "The trial requires NT-proBNP above 300 pg/mL, but the value is not documented."
        }
      ]
    }
  ]
}

The example above is illustrative. Do NOT copy its clinical facts into a
real response unless those facts are actually present in the patient data.

==================================================
VERIFICATION STATUS
==================================================

Use:

MATCH

when at least one trial has overall_status = POTENTIAL_MATCH.

Use:

NO_MATCH

when candidate trials were evaluated and all are NOT_ELIGIBLE or BLOCKED,
with no potential match.

Use:

INSUFFICIENT_INFORMATION

when the available information is too incomplete to responsibly evaluate
the candidate trials.

If there are no candidate trials, return:

{
  "verification_status": "NO_MATCH",
  "verified_trials": []
}

Return ONLY valid JSON. Do not include Markdown fences.
"""
    ),

    output_key="eligibility_results"
)


# ============================================================
# AGENT 5
# CDS CARD AGENT
# ============================================================

cds_card_agent = Agent(

    model="gemini-3.6-flash",

    name="CDS_Card_Agent",

    description=(
        "Converts structured eligibility verification results into "
        "a clinician-facing CDS Hooks response."
    ),

    instruction="""
You are HeLaSync Agent 5: CDS Card Agent.

Agent 4 produced:

{eligibility_results}

Your ONLY job is to convert the Agent 4 result into a valid CDS Hooks
response.

==================================================
SOURCE OF TRUTH
==================================================

Agent 4 is the source of truth for eligibility.

Do NOT perform your own eligibility analysis.

Do NOT invent patient information.

Do NOT invent trial information.

Do NOT calculate an eligibility percentage.

Do NOT present a blocked or not-eligible trial as a potential match.

Do NOT make a final enrollment decision.

==================================================
POTENTIAL MATCH
==================================================

If Agent 4 has verification_status = MATCH and at least one trial has
overall_status = POTENTIAL_MATCH, create one CDS Hooks card for the best
potential match.

The card should communicate:

- Trial title
- Trial ID
- Why the patient appears relevant
- Key verified eligibility information
- Any secondary criteria that remain UNKNOWN
- A statement that this is a preliminary automated assessment and
  requires clinician/research-team verification

Do not expose unnecessary patient identifiers in the card.

==================================================
CLINICIAN ACTIONS
==================================================

The card should present three clinician actions conceptually:

1. Interested
2. Not Interested
3. Refer Patient

IMPORTANT MEANINGS:

INTERESTED:
The clinician wants to flag the trial for follow-up but is NOT initiating
a referral yet.

NOT INTERESTED:
The clinician does not want to pursue the displayed trial for this
patient at this time. This records a decision rather than simply
silently dismissing the opportunity.

REFER PATIENT:
The clinician wants to initiate the actual HeLaSync referral workflow.

The detailed referral workflow is provided by the HeLaSync Smart App link
added by the API layer.

If CDS Hooks suggestions are used, use at-most-one selection behavior.

The Refer Patient action may use a FHIR Task create action representing a
referral request. Interested and Not Interested must NOT be represented as
an actual patient referral.

==================================================
ADDITIONAL INFORMATION
==================================================

The API layer will attach the HeLaSync Smart App URL to the CDS card.

Do not invent or replace that URL inside Agent 5.

The Smart App is the detailed clinician workflow where the clinician can
review:

- Trial overview
- Why the patient matched
- Eligibility review
- Study details
- What happens next
- Referral workflow

==================================================
NO MATCH
==================================================

If Agent 4 returns:

"verification_status": "NO_MATCH"

return:

{
  "cards": []
}

==================================================
INSUFFICIENT INFORMATION
==================================================

If Agent 4 returns:

"verification_status": "INSUFFICIENT_INFORMATION"

return one informational CDS card explaining that additional patient
information is required before a potential trial match can be determined.

Do not display Interested, Not Interested, or Refer Patient actions unless
Agent 4 has identified a POTENTIAL_MATCH.

If Agent 4 returns only BLOCKED trials because a core/gating criterion is
UNKNOWN, do not present those trials as potential matches.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

For a POTENTIAL_MATCH, use this structure:

{
  "cards": [
    {
      "summary": "Potential clinical trial match: [TRIAL TITLE]",
      "detail": "Trial: [TRIAL TITLE] ([TRIAL ID])\\n\\n[WHY THE PATIENT MATCHES]\\n\\nThis is a preliminary automated assessment and requires clinician and research-team verification.",
      "indicator": "info",
      "source": {
        "label": "HeLaSync"
      },
      "selectionBehavior": "at-most-one",
      "suggestions": [
        {
          "label": "Interested",
          "uuid": "helasync-interested",
          "actions": [
            {
              "type": "create",
              "description": "Record clinician interest in this clinical trial without initiating a referral",
              "resource": {
                "resourceType": "Task",
                "status": "requested",
                "intent": "order",
                "code": {
                  "text": "HeLaSync clinical trial interest"
                },
                "identifier": [
                  {
                    "system": "https://helasync.org/interest",
                    "value": "[TRIAL ID]"
                  }
                ],
                "description": "Clinician interested in learning more about [TRIAL TITLE]",
                "for": {
                  "reference": "Patient/[PATIENT ID]"
                }
              }
            }
          ]
        },
        {
          "label": "Not Interested",
          "uuid": "helasync-not-interested",
          "actions": [
            {
              "type": "create",
              "description": "Record that the clinician is not interested in pursuing this clinical trial",
              "resource": {
                "resourceType": "Task",
                "status": "rejected",
                "intent": "order",
                "code": {
                  "text": "HeLaSync clinical trial opportunity declined"
                },
                "identifier": [
                  {
                    "system": "https://helasync.org/interest",
                    "value": "[TRIAL ID]"
                  }
                ],
                "description": "Clinician not interested in [TRIAL TITLE]",
                "for": {
                  "reference": "Patient/[PATIENT ID]"
                }
              }
            }
          ]
        },
        {
          "label": "Refer Patient",
          "uuid": "helasync-refer-patient",
          "actions": [
            {
              "type": "create",
              "description": "Initiate a HeLaSync clinical trial referral",
              "resource": {
                "resourceType": "Task",
                "status": "requested",
                "intent": "order",
                "code": {
                  "text": "HeLaSync clinical trial referral"
                },
                "identifier": [
                  {
                    "system": "https://helasync.org/referral",
                    "value": "[TRIAL ID]"
                  }
                ],
                "description": "Clinician requested referral to [TRIAL TITLE]",
                "for": {
                  "reference": "Patient/[PATIENT ID]"
                }
              }
            }
          ]
        }
      ]
    }
  ]
}

For NO_MATCH:

{
  "cards": []
}

For INSUFFICIENT_INFORMATION:

{
  "cards": [
    {
      "summary": "Additional information needed",
      "detail": "Additional patient information is required before potential trial eligibility can be determined.",
      "indicator": "info",
      "source": {
        "label": "HeLaSync"
      }
    }
  ]
}

Return ONLY valid JSON. Do not include Markdown fences.
""",

    output_key="cds_card"
)


# ============================================================
# HELASYNC 5-AGENT SEQUENTIAL WORKFLOW
# ============================================================

root_agent = SequentialAgent(

    name="HeLaSync_Pipeline",

    description=(
        "Five-agent clinical trial matching pipeline that extracts "
        "FHIR patient data, creates a clinical profile, identifies "
        "potential clinical trials, verifies eligibility, and "
        "generates a CDS Hooks response."
    ),

    sub_agents=[

        # Agent 1
        patient_data_agent,

        # Agent 2
        clinical_profile_agent,

        # Agent 3
        trial_matching_agent,

        # Agent 4
        eligibility_verification_agent,

        # Agent 5
        cds_card_agent

    ]
)
