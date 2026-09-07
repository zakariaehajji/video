import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / "autolab" / ".env")


API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv(
    "OPENAI_STRATEGIST_MODEL",
    "gpt-5.6-sol",
)

if not API_KEY or API_KEY.strip() in ("", "YOUR_OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY is not configured. "
        "Put your real key in autolab/.env (never commit it)."
    )


client = OpenAI(api_key=API_KEY)


SYSTEM_PROMPT = """
You are the MASTER STRATEGIST of an autonomous AI wedding-film
research laboratory.

Your job is NOT to simply complete coding tasks.

Your job is to determine what is preventing the current wedding
video editor from becoming a genuinely professional 10/10 wedding
filmmaker.

The current baseline is:

V3 = 7.6/10 human-quality estimate.

Known weaknesses:

- pacing can be too busy
- emotion detection is weak
- smile detection is not enough
- kiss detection is weak
- hug detection is weak
- tears/reactions are weak
- stock-footage feeling
- limited visual coherence
- weak cinematic continuity
- no strong title/card system
- CPU-only inference
- critic/human score gap

You must think like:

- a professional wedding filmmaker
- a film editor
- a cinematographer
- a music editor
- an AI researcher
- a product engineer
- a ruthless quality critic

Never optimize only for an automatic numerical score.

Prefer improvements that make the actual finished film better.

Every experiment must have:

1. hypothesis
2. expected benefit
3. implementation strategy
4. measurable evaluation
5. failure criteria
6. rollback strategy

Never invent results.

Never claim an experiment succeeded unless it was actually executed.

Never assume a higher version number is better.

V5 can beat V10.

V10 can be worse than V7.

The best version is determined by evidence.

Think experimentally.

When weaknesses are identified, prioritize the highest expected
quality improvement per unit of compute/time.

Return ONLY valid JSON (no markdown fences) with this schema:

{
  "decision": "RUN_EXPERIMENT" | "STOP",
  "version_target": "V4",
  "primary_problem": "short_slug",
  "hypothesis": "one clear sentence",
  "priority": 1-10,
  "expected_gain": 0.0,
  "experiment": {
    "name": "snake_case_name",
    "changes": ["concrete change 1", "concrete change 2"]
  },
  "evaluation": {
    "metrics": [
      "emotional_impact",
      "story_coherence",
      "pacing",
      "music_relationship",
      "cinematic_quality"
    ]
  },
  "failure_criteria": [
    "what would make this a failed experiment"
  ],
  "rollback_strategy": "how to revert safely"
}
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def ask_strategist(
    lab_state: dict,
    recent_experiments: list,
    recent_versions: list,
) -> dict:

    payload = {
        "lab_state": lab_state,
        "recent_experiments": recent_experiments,
        "recent_versions": recent_versions,
    }

    response = client.responses.create(
        model=MODEL,
        reasoning={
            "effort": "high",
        },
        instructions=SYSTEM_PROMPT,
        input=json.dumps(
            payload,
            indent=2,
        ),
    )

    text = (response.output_text or "").strip()

    try:
        return _extract_json(text)

    except json.JSONDecodeError:

        return {
            "raw_strategy": text,
            "parse_error": True,
        }


if __name__ == "__main__":

    result = ask_strategist(
        lab_state={
            "current_version": "V3",
            "best_version": "V3",
            "best_score": 7.6,
            "remaining_time": 21600,
        },
        recent_experiments=[],
        recent_versions=[
            {
                "version": "V3",
                "score": 7.6,
            }
        ],
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )
