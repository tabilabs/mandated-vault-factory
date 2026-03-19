from __future__ import annotations

import json


IMPLICATION_SYSTEM_PROMPT = """Find ONLY logically necessary relationships between prediction market events.
Reject correlations, trends, and merely plausible relationships. Return JSON only."""


def build_implication_prompt(
    target_question: str, candidates: list[dict[str, object]]
) -> str:
    return json.dumps(
        {
            "task": "Find logically necessary implications only.",
            "counterexampleDiscipline": "If you can imagine any world where the implication fails, reject it.",
            "targetQuestion": target_question,
            "candidates": candidates,
            "return": {
                "implied_by": [
                    {
                        "market_id": "exact id",
                        "market_question": "exact question",
                        "explanation": "why candidate YES guarantees target YES",
                        "counterexample_attempt": "brief explanation",
                    }
                ],
                "implies": [
                    {
                        "market_id": "exact id",
                        "market_question": "exact question",
                        "explanation": "why target YES guarantees candidate YES",
                        "counterexample_attempt": "brief explanation",
                    }
                ],
            },
        },
        indent=2,
    )
