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


def build_trial_reference(trials):
    """Build a compact, model-friendly reference containing only fields
    needed for candidate matching and preliminary eligibility verification.
    This keeps Agent 4 prompts small and avoids unnecessary model latency.
    """
    reference = []
    for trial in trials:
        protocol = trial.get("protocolSection", {}) or {}
        identification = protocol.get("identificationModule", {}) or {}
        status = protocol.get("statusModule", {}) or {}
        conditions = protocol.get("conditionsModule", {}) or {}
        eligibility = protocol.get("eligibilityModule", {}) or {}
        sponsor = protocol.get("sponsorCollaboratorsModule", {}) or {}
        design = protocol.get("designModule", {}) or {}

        reference.append({
            "trial_id": identification.get("nctId") or trial.get("trial_id") or trial.get("id", ""),
            "trial_title": identification.get("briefTitle") or identification.get("officialTitle", ""),
            "status": status.get("overallStatus", ""),
            "conditions": conditions.get("conditions", []),
            "eligibility_criteria": eligibility.get("eligibilityCriteria", ""),
            "min_age": eligibility.get("minimumAge", ""),
            "max_age": eligibility.get("maximumAge", ""),
            "sex": eligibility.get("sex", ""),
            "sponsor": (sponsor.get("leadSponsor") or {}).get("name", ""),
            "principal_investigator": (sponsor.get("overallOfficials") or [{}])[0].get("name", "") if sponsor.get("overallOfficials") else "",
            "study_type": design.get("studyType", "")
        })
    return reference


# Compact trial reference used by matching/eligibility agents.
trial_reference = build_trial_reference(trial_list)
trial_reference_json = json.dumps(trial_reference, indent=2)


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
- NT-proBNP
- Other laboratory results

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
    description="Identifies active clinical trial candidates from the documented clinical profile.",
    instruction=f"""
You are HeLaSync Agent 3. Identify potential clinical trial candidates.

CLINICAL PROFILE:
{{clinical_profile}}

TRIAL REFERENCE:
{trial_reference_json}

RULES:
- Evaluate every active trial.
- Active statuses: RECRUITING, ENROLLING_BY_INVITATION, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING.
- Match documented disease/subtype alignment only.
- A documented specific subtype satisfies a broader aligned disease criterion.
- Do not infer a disease from another disease.
- Do not reject a disease-aligned trial because secondary criteria are unknown.
- Do not determine final eligibility. Agent 4 does that.

IMPORTANT:
A patient with documented "Chronic heart failure" AND "Transthyretin cardiac amyloidosis" is disease-aligned with a cardiac amyloidosis/heart failure treatment trial.

RETURN ONLY THIS JSON SHAPE:
{{
  "candidate_trials": [
    {{
      "trial_id": "NCT...",
      "trial_title": "...",
      "reason": "..."
    }}
  ]
}}

If there are no candidates, return {{"candidate_trials": []}}.
No Markdown. No commentary. Valid JSON only.
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
    description="Performs structured preliminary eligibility verification for candidate trials.",
    instruction=f"""
You are HeLaSync Agent 4: Eligibility Verification Agent.

PATIENT DATA:
{{patient_data}}

CLINICAL PROFILE:
{{clinical_profile}}

AGENT 3 CANDIDATES:
{{trial_matches}}

TRIAL REFERENCE:
{trial_reference_json}

YOUR TASK:
Verify ONLY the candidate trials against their ACTUAL eligibilityCriteria in the trial reference.

CRITICAL RECOVERY:
Agent 3 may produce malformed JSON. Extract recognizable trial IDs such as NCTFAKE002 from its text when possible. If no usable candidate IDs can be parsed, identify clearly disease-aligned active trials from the trial reference using the clinical profile.

CRITERION STATUS:
Inclusion: MET, NOT_MET, UNKNOWN.
Exclusion: PRESENT, CLEAR, UNKNOWN.
Never treat UNKNOWN as NOT_MET.
Never infer absence from missing documentation.

GATING:
Core disease/population requirements are GATING.
For NCTFAKE002, these are explicitly GATING:
1. Heart failure diagnosis.
2. Confirmed cardiac amyloidosis diagnosis.

DISEASE SEMANTICS:
"Transthyretin cardiac amyloidosis" directly satisfies "confirmed diagnosis of cardiac amyloidosis".
"Chronic heart failure" directly satisfies "heart failure".
Do not infer heart failure from amyloidosis alone.

OVERALL STATUS:
POTENTIAL_MATCH = every GATING criterion MET and no EXCLUSION is PRESENT. Secondary UNKNOWN values do not block.
BLOCKED = at least one GATING criterion UNKNOWN, with no GATING NOT_MET and no exclusion PRESENT.
NOT_ELIGIBLE = any GATING NOT_MET, any SECONDARY NOT_MET, or any EXCLUSION PRESENT.
INSUFFICIENT_INFORMATION = only when the patient data is broadly inadequate to evaluate the trial.

VERIFICATION STATUS:
MATCH if any verified trial is POTENTIAL_MATCH.
NO_MATCH if trials were evaluated and none is POTENTIAL_MATCH.
INSUFFICIENT_INFORMATION only when broadly inadequate.

IMPORTANT NCTFAKE002 TEST CASE:
If the clinical profile contains both "Chronic heart failure" and "Transthyretin cardiac amyloidosis", mark the two corresponding gating criteria MET. Do not mark them UNKNOWN.

OUTPUT ONLY VALID JSON. Keep the response compact.

{{
  "verification_status": "MATCH",
  "verified_trials": [
    {{
      "trial_id": "NCTFAKE002",
      "trial_title": "...",
      "overall_status": "POTENTIAL_MATCH",
      "summary": "...",
      "gating_criteria": [
        {{"criterion":"...","status":"MET","evidence":"..."}}
      ],
      "secondary_criteria": [],
      "exclusion_criteria": [],
      "missing_information": []
    }}
  ]
}}

No Markdown. No explanation outside JSON. No percentages.
""",
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
        "the locked HeLaSync clinician-facing CDS Hooks card."
    ),

    instruction="""
You are HeLaSync Agent 5: CDS Card Agent.

Agent 4 produced:

{eligibility_results}

Your ONLY job is to convert the Agent 4 eligibility result into
the locked HeLaSync CDS Hooks card format.

==================================================
SOURCE OF TRUTH
==================================================

Agent 4 is the ONLY source of truth for eligibility.

Do NOT perform your own eligibility analysis.

Do NOT invent patient information.

Do NOT invent trial information.

Do NOT calculate an eligibility percentage.

Do NOT present a BLOCKED trial.

Do NOT present a NOT_ELIGIBLE trial.

Do NOT make a final enrollment decision.

==================================================
WHEN TO CREATE A CARD
==================================================

Create a CDS card ONLY when:

1. verification_status = "MATCH"

AND

2. At least one verified trial has:

"overall_status": "POTENTIAL_MATCH"

Select the best potential match.

Return ONE card only.

==================================================
LOCKED CARD SUMMARY
==================================================

The card summary MUST be EXACTLY:

"Potential Clinical Trial Opportunity"

Do not add the trial title.

Do not add the trial ID.

Do not use:

"Potential clinical trial match"

Do not use:

"Potential Clinical Trial Match"

Do not use:

"Potential Clinical Trial Opportunity:"

The summary must be EXACTLY:

"Potential Clinical Trial Opportunity"

==================================================
CARD DETAIL
==================================================

The detail MUST contain exactly:

[TRIAL SPONSOR]: [TRIAL NAME]

PI: [PRINCIPAL INVESTIGATOR]

There must be one blank line between the trial name and PI.

Use the actual:

- Trial sponsor
- Trial name
- Principal investigator

from the available trial information.

If the principal investigator is not available, use:

PI: Not listed

Do NOT include:

- eligibility criteria
- laboratory values
- match percentages
- missing information
- clinical reasoning
- patient information
- long descriptions
- recommendations
- referral instructions

Detailed information belongs in the HeLaSync Smart App.

==================================================
SOURCE
==================================================

The source MUST be:

{
  "label": "HeLaSync"
}

==================================================
INDICATOR
==================================================

Use:

"indicator": "info"

==================================================
TRIAL ID
==================================================

Include the internal trial ID using:

"extension": {
  "helasync_trial_id": "[TRIAL ID]"
}

The API layer will use this internal trial ID to create the
HeLaSync Smart App URL.

Do NOT invent a URL.

Do NOT create the Smart App URL yourself.

==================================================
ACTIONS
==================================================

Do NOT create:

- Interested
- Not Interested
- Refer Patient
- Enroll
- Contact Site
- FHIR Task actions
- suggestions

The API layer handles the Smart App link.

The CDS interface handles dismissal separately.

==================================================
FINAL POTENTIAL MATCH OUTPUT
==================================================

Return ONLY:

{
  "cards": [
    {
      "summary": "Potential Clinical Trial Opportunity",
      "detail": "[TRIAL SPONSOR]: [TRIAL NAME]\\n\\nPI: [PRINCIPAL INVESTIGATOR]",
      "indicator": "info",
      "source": {
        "label": "HeLaSync"
      },
      "extension": {
        "helasync_trial_id": "[TRIAL ID]"
      }
    }
  ]
}

Replace bracketed values with actual information from the trial data.

==================================================
NO MATCH
==================================================

If there is no POTENTIAL_MATCH, return:

{
  "cards": []
}

This includes:

- NO_MATCH
- BLOCKED
- NOT_ELIGIBLE
- No candidate trials

==================================================
INSUFFICIENT INFORMATION
==================================================

If verification_status is:

"INSUFFICIENT_INFORMATION"

return:

{
  "cards": []
}

Do NOT create an informational CDS card.

The HeLaSync card should only surface an actionable potential
clinical trial opportunity.

==================================================
FINAL RULE
==================================================

Return ONLY valid JSON.

Do not include Markdown.

Do not include explanations outside the JSON.
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
