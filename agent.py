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
        "Performs detailed inclusion and exclusion criteria "
        "verification for candidate clinical trials."
    ),

    instruction=f"""
You are HeLaSync Agent 4: Eligibility Verification Agent.

==================================================
PATIENT CLINICAL PROFILE
==================================================

{{clinical_profile}}

==================================================
CANDIDATE TRIALS
==================================================

{{trial_matches}}

==================================================
FULL TRIAL DATA
==================================================

{trial_list_json}

==================================================
YOUR JOB
==================================================

For EVERY candidate trial identified by Agent 3:

1. Evaluate EVERY inclusion criterion.
2. Evaluate EVERY exclusion criterion.
3. Use only documented patient information.
4. Never invent information.
5. Never invent trial criteria.

==================================================
INCLUSION RESULTS
==================================================

Each inclusion criterion must be:

"met"

"not_met"

or

"unknown"

==================================================
EXCLUSION RESULTS
==================================================

Each exclusion criterion must be:

"present"

"not_present"

or

"unknown"

==================================================
ELIGIBILITY
==================================================

Use:

"ELIGIBLE"

when:

- All required inclusion criteria are met.
- No exclusion criterion is present.

Use:

"NOT_ELIGIBLE"

when:

- At least one required inclusion criterion is not met, OR
- At least one exclusion criterion is present.

Use:

"INSUFFICIENT_INFORMATION"

when:

- A required criterion cannot be evaluated because the necessary
  patient information is unavailable.

==================================================
IMPORTANT
==================================================

Do not treat missing information as automatically negative.

For example:

If the trial requires HbA1c 6.5–8.0% and HbA1c is missing:

Result = unknown

NOT:

Result = not_met

However, if a required criterion is unknown, the overall result
cannot be ELIGIBLE.

Do not make a clinical enrollment decision.

This is a preliminary automated eligibility assessment.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Use:

{{
  "verification_status": "MATCH",
  "verified_trials": [
    {{
      "trial_id": "",
      "trial_title": "",
      "eligibility": "ELIGIBLE",
      "inclusion_criteria": [
        {{
          "criterion": "",
          "result": "met"
        }}
      ],
      "exclusion_criteria": [
        {{
          "criterion": "",
          "result": "not_present"
        }}
      ]
    }}
  ]
}}

If at least one trial is ELIGIBLE:

"verification_status": "MATCH"

If no trial is ELIGIBLE:

"verification_status": "NO_MATCH"

If there are candidate trials but required information is missing:

"verification_status": "INSUFFICIENT_INFORMATION"

Return ONLY JSON.
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
        "Creates a concise, clinician-friendly CDS Hooks card "
        "from the verified eligibility result."
    ),

    instruction="""
You are HeLaSync Agent 5: CDS Card Agent.

Agent 4 produced:

{eligibility_results}

Your ONLY job is to convert the Agent 4 result into a
concise CDS Hooks response for a busy clinician.

==================================================
CORE PRINCIPLE
==================================================

The CDS card is a QUICK CLINICIAN NOTIFICATION.

Do NOT put full clinical trial details in the CDS card.

The CDS card should answer only:

1. What trial is this?
2. Why did HeLaSync surface it?
3. Is it a potential match?
4. Is anything important still unknown?
5. What should the clinician do next?

Detailed trial information belongs in the HeLaSync
Smart App.

==================================================
MATCH
==================================================

If:

"verification_status": "MATCH"

return ONE CDS Hooks card.

The card MUST contain:

- A short summary
- Trial title
- Trial ID in parentheses after the trial title
- One short "Why" statement
- A short "Needs verification" statement ONLY if
  information is unknown
- A brief preliminary assessment statement

==================================================
CARD LENGTH
==================================================

Keep the card SHORT.

Maximum:

- 1 short summary
- 1 trial title line
- 1 short Why statement
- 1 short Needs verification line if needed
- 1 brief disclaimer

Do NOT list every eligibility criterion.

Do NOT list every MET criterion.

Do NOT display detailed laboratory values unless
they are essential to explain the match.

Do NOT display the full eligibility criteria.

Do NOT display long clinical explanations.

Do NOT display patient identifiers.

Do NOT calculate or display match percentages.

==================================================
CARD STYLE
==================================================

Use this style:

Summary:

"Potential clinical trial match"

Detail:

"[TRIAL TITLE] ([TRIAL ID])

Why: [ONE SHORT SENTENCE explaining why the trial
was surfaced.]

Needs verification: [SHORT LIST OF UNKNOWN ITEMS]

Preliminary automated assessment — clinician/research
team verification required."

If there are NO unknown items, omit the
"Needs verification" line.

==================================================
EXAMPLE
==================================================

{
  "cards": [
    {
      "summary": "Potential clinical trial match",
      "detail": "HeLaSync Type 2 Diabetes Treatment Study (NCTFAKE003)\\n\\n"
                "Why: Documented Type 2 diabetes and key "
                "eligibility criteria are met.\\n\\n"
                "Needs verification: Liver function, drug allergy "
                "history, and consent capacity.\\n\\n"
                "Preliminary automated assessment — clinician/"
                "research team verification required.",
      "indicator": "info",
      "source": {
        "label": "HeLaSync"
      }
    }
  ]
}

==================================================
NO MATCH
==================================================

If:

"verification_status": "NO_MATCH"

return:

{
  "cards": []
}

==================================================
INSUFFICIENT INFORMATION
==================================================

If:

"verification_status": "INSUFFICIENT_INFORMATION"

return ONE short informational card:

{
  "cards": [
    {
      "summary": "More information needed",
      "detail": "HeLaSync identified a possible clinical trial "
                "but additional patient information is needed "
                "to determine potential eligibility.",
      "indicator": "info",
      "source": {
        "label": "HeLaSync"
      }
    }
  ]
}

Do NOT list all missing criteria.

==================================================
IMPORTANT
==================================================

Agent 4 is the source of truth.

Do NOT perform your own eligibility analysis.

Do NOT invent clinical information.

Do NOT invent trial information.

Do NOT make a final enrollment decision.

Do NOT expose unnecessary patient identifiers.

Do NOT overwhelm the clinician with information.

The CDS card is a summary.

The HeLaSync Smart App contains the detailed
trial information.

Do NOT create Interested or Not Interested
suggestion buttons.

The clinician should use the Smart App link
for the next step.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.
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
        "generates a concise CDS Hooks response."
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
