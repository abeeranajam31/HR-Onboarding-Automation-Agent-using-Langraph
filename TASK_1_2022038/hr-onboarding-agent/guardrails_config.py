from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

FORBIDDEN_TOPICS = {
    "delete the database",
    "drop database",
    "exfiltrate",
    "leak secrets",
    "reveal system prompt",
    "show internal instructions",
}

INJECTION_PATTERNS = {
    "persona_bypass": [
        r"\bpretend\b.*\b(system|assistant|developer)\b",
        r"\bdo anything now\b",
        r"\bdan\b",
    ],
    "instruction_hijacking": [
        r"\bignore (all )?(previous|prior) instructions\b",
        r"\boverride (your )?(rules|policies|safety)\b",
        r"\bdisregard\b.*\binstructions\b",
    ],
    "payload_smuggling": [
        r"\bsecretly\b.*\b(delete|drop|exfiltrate|leak)\b",
        r"\bhidden\b.*\b(command|payload)\b",
        r"\bpoem\b.*\b(delete|drop|database)\b",
    ],
}

RAW_METADATA_KEYS = {
    "chunk_id",
    "chunk_index",
    "ingestion_date",
    "embedding",
    "metadata",
    "score",
}

FILE_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:)?(?:/[\w.\- ]+)+")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class GuardrailInput(BaseModel):
    query: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def validate_guardrails(self) -> "GuardrailInput":
        lowered = self.query.lower()
        for keyword in FORBIDDEN_TOPICS:
            if keyword in lowered:
                raise ValueError(f"Forbidden topic detected: {keyword}")

        for patterns in INJECTION_PATTERNS.values():
            for pattern in patterns:
                if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
                    raise ValueError("Prompt injection attempt detected")
        return self


@dataclass
class GuardrailDecision:
    status: Literal["SAFE", "UNSAFE"]
    reason: str
    category: str = "safe"


def classify_prompt(query: str) -> GuardrailDecision:
    try:
        GuardrailInput(query=query)
        return GuardrailDecision(status="SAFE", reason="Prompt passed deterministic validation.")
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        lowered = query.lower()
        for category, patterns in INJECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
                    return GuardrailDecision(status="UNSAFE", reason=message, category=category)
        return GuardrailDecision(status="UNSAFE", reason=message, category="forbidden_topic")


def sanitize_output_text(text: str) -> tuple[str, list[str]]:
    sanitized = text
    redactions: list[str] = []

    file_matches = set(FILE_PATH_PATTERN.findall(sanitized))
    for match in file_matches:
        if match.count("/") >= 2 and ("Users" in match or "output" in match or "data" in match):
            sanitized = sanitized.replace(match, "[REDACTED_PATH]")
            redactions.append("internal_path")

    email_matches = set(EMAIL_PATTERN.findall(sanitized))
    for match in email_matches:
        sanitized = sanitized.replace(match, "[REDACTED_EMAIL]")
        redactions.append("email")

    for key in RAW_METADATA_KEYS:
        if key in sanitized:
            sanitized = re.sub(rf"\b{re.escape(key)}\b\s*[:=]\s*[^,\n]+", f"{key}: [REDACTED]", sanitized)
            redactions.append(key)

    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    return sanitized, sorted(set(redactions))
