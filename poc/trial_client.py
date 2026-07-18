"""
STEP: Trial side.

Fetches a trial's eligibility criteria from the ClinicalTrials.gov public API v2
(no auth) and caches it to trials/trial_v1.json. If the fixture already exists we
load it, so the demo runs offline and against a stable version.

POC scope: one trial, cached to disk. A subagent can later build the v2
'protocol amendment' fixture, version metadata, and multi-trial support.
"""

import json
import urllib.request
from pathlib import Path

TRIALS_DIR = Path(__file__).resolve().parent / "trials"
CT_GOV = "https://clinicaltrials.gov/api/v2/studies/{nct}?fields={fields}"
FIELDS = "NCTId,BriefTitle,EligibilityCriteria,MinimumAge,MaximumAge,Sex,HealthyVolunteers"


def load_trial(version: str = "v1") -> dict:
    """Load a cached trial fixture from disk."""
    path = TRIALS_DIR / f"trial_{version}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run fetch_trial(nct_id) to create it."
        )
    with open(path) as f:
        return json.load(f)


def fetch_trial(nct_id: str, version: str = "v1", save: bool = True) -> dict:
    """Fetch eligibility criteria live from ClinicalTrials.gov and cache it."""
    url = CT_GOV.format(nct=nct_id, fields=FIELDS)
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.load(resp)
    p = data["protocolSection"]
    el = p["eligibilityModule"]
    trial = {
        "trial_id": nct_id,
        "version": version,
        "source": "ClinicalTrials.gov API v2",
        "brief_title": p["identificationModule"].get("briefTitle"),
        "minimum_age": el.get("minimumAge"),
        "maximum_age": el.get("maximumAge"),
        "sex": el.get("sex"),
        "healthy_volunteers": el.get("healthyVolunteers"),
        "eligibility_criteria": el.get("eligibilityCriteria", ""),
    }
    if save:
        TRIALS_DIR.mkdir(exist_ok=True)
        with open(TRIALS_DIR / f"trial_{version}.json", "w") as f:
            json.dump(trial, f, indent=2)
    return trial


def trial_to_text(trial: dict) -> str:
    """Render trial eligibility as a text block for the LLM prompt."""
    return (
        f"TRIAL {trial['trial_id']} (protocol version: {trial['version']})\n"
        f"Title: {trial.get('brief_title')}\n"
        f"Age: {trial.get('minimum_age')} to {trial.get('maximum_age')}\n"
        f"Sex: {trial.get('sex')}  Healthy volunteers: {trial.get('healthy_volunteers')}\n\n"
        f"{trial['eligibility_criteria']}"
    )


if __name__ == "__main__":
    print(trial_to_text(load_trial("v1")))
