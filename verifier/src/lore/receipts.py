"""Verification receipts generator for Lore.

Every verification run creates a signed receipt in receipts/<domain>/<slug>-<seq>/<UTC-timestamp>.json.
Committed to the repo as public, auditable proof of verification.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import VerifyReport


def generate_receipt(
    report: VerifyReport,
    lesson: dict[str, Any],
    verifier_id: str = "official-verifier-v0.2",
) -> dict[str, Any]:
    """Generate a receipt dict from a VerifyReport."""
    now = datetime.now(timezone.utc).isoformat()

    variants_data = []
    for v in report.variants:
        asserts_data = [
            {"assertion": r.assertion, "passed": r.passed, "detail": r.detail}
            for r in v.assert_results
        ]
        variants_data.append({
            "variant": v.variant,
            "command": v.command,
            "exit_code": v.output.exit_code,
            "duration_sec": round(v.output.duration_sec, 3),
            "timed_out": v.output.timed_out,
            "passed": v.passed,
            "assertions": asserts_data,
        })

    return {
        "receipt_version": "0.2",
        "lesson_id": report.lesson_id,
        "semver": report.semver,
        "timestamp": now,
        "verifier_id": verifier_id,
        "environment": {
            "image_tag": report.image_tag,
            "image_digest": report.image_id,
            "image_cached": report.image_cached,
            "setup_network": lesson.get("verification", {}).get("setup_network", "packages"),
            "eval_network": lesson.get("verification", {}).get("network", "none"),
        },
        "verdict": report.verdict,
        "variants": variants_data,
    }


def save_receipt(receipt: dict[str, Any], repo_root: Path) -> Path:
    """Save receipt file to receipts/<domain>/<slug>-<seq>/<timestamp>.json."""
    lesson_id = receipt["lesson_id"]  # lore:domain/slug/0001
    parts = lesson_id.replace("lore:", "").split("/")
    domain = parts[0]
    slug_seq = f"{parts[1]}-{parts[2]}"

    target_dir = repo_root / "receipts" / domain / slug_seq
    target_dir.mkdir(parents=True, exist_ok=True)

    ts_clean = receipt["timestamp"].replace(":", "-").replace(".", "-")
    receipt_file = target_dir / f"{ts_clean}.json"

    receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt_file
