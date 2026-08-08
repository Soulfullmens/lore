"""Static checks for Lore lessons: schema validation, token budgets, and prompt injection linting."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except ImportError:
    _ENC = None

SUSPICIOUS_PATTERNS = [
    r"ignore\s+(your|all|previous)\s+(instructions|rules|constraints)",
    r"you\s+are\s+now\s+",
    r"forget\s+(everything|your|all)",
    r"system\s*prompt",
    r"<\s*/?\s*system\s*>",
    r"IMPORTANT:\s*(?:override|ignore|disregard)",
    r"(?:execute|run|eval)\s+(?:this|the\s+following)\s+(?:command|code|script)",
    r"base64\s*decode",
    r"\\x[0-9a-f]{2}",
]


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    passed: bool
    detail: str


def count_tokens(text: str) -> int:
    if _ENC:
        return len(_ENC.encode(text))
    return int(len(text.split()) * 1.3)  # rough estimate if tiktoken missing


def validate_schema(lesson: dict[str, Any], schema_path: Path) -> CheckResult:
    """Validate lesson against lesson.schema.json."""
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=lesson, schema=schema)
        return CheckResult("schema_validation", True, "schema valid")
    except jsonschema.ValidationError as e:
        return CheckResult("schema_validation", False, f"schema error at {e.json_path}: {e.message}")
    except Exception as e:
        return CheckResult("schema_validation", False, f"schema loading failed: {e}")


def check_token_budgets(lesson: dict[str, Any]) -> list[CheckResult]:
    """Check summary <= 60 tokens and body <= 900 tokens."""
    results = []

    summary = lesson.get("summary", "")
    st = count_tokens(summary)
    if st > 60:
        results.append(CheckResult("token_budget_summary", False, f"summary is {st} tokens (max 60)"))
    else:
        results.append(CheckResult("token_budget_summary", True, f"summary is {st} tokens (max 60)"))

    body_parts = [
        lesson.get("problem", ""),
        " ".join(lesson.get("procedure", [])),
        " ".join(lesson.get("anti_patterns", [])),
    ]
    for fa in lesson.get("failed_attempts", []):
        body_parts.append(fa.get("approach", ""))
        body_parts.append(fa.get("why_it_fails", ""))

    bt = count_tokens(" ".join(body_parts))
    if bt > 900:
        results.append(CheckResult("token_budget_body", False, f"body is {bt} tokens (max 900)"))
    else:
        results.append(CheckResult("token_budget_body", True, f"body is {bt} tokens (max 900)"))

    return results


def check_prompt_injection(lesson: dict[str, Any]) -> CheckResult:
    """Scan lesson text fields for prompt injection patterns."""
    text_fields = [
        lesson.get("summary", ""),
        lesson.get("problem", ""),
        *lesson.get("procedure", []),
        *lesson.get("anti_patterns", []),
        *lesson.get("symptoms", []),
    ]
    for fa in lesson.get("failed_attempts", []):
        text_fields.extend([fa.get("approach", ""), fa.get("why_it_fails", "")])

    all_text = " ".join(text_fields).lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            return CheckResult("prompt_injection", False, f"suspicious pattern detected: {pattern}")

    return CheckResult("prompt_injection", True, "no prompt injection patterns detected")


def run_static_checks(lesson: dict[str, Any], schema_path: Path) -> list[CheckResult]:
    """Run all static checks (schema, budgets, injection)."""
    results = [validate_schema(lesson, schema_path)]
    results.extend(check_token_budgets(lesson))
    results.append(check_prompt_injection(lesson))
    return results
