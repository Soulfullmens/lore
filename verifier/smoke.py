#!/usr/bin/env python3
"""End-to-end smoke test: verify one real lesson against real Docker.

Usage (from repo root, Docker running):
    python verifier/smoke.py lessons/python-async/aiohttp-session-close-event-loop-0001.json

Expected on the three v0.2 seed lessons: verdict=pass, negative run first,
with per-assert detail printed. This script is deliberately tiny — it is
the CLI's skeleton before the CLI exists.

SANDBOX HONESTY NOTE: asserts/builder/runner pure logic is unit-tested
(15 tests, test_core.py). The docker build/run paths below have NOT been
executed against a live daemon by the author environment — this smoke run
on your machine is their first real verification. If something breaks
here, it's expected to break here.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lore.builder import build_image
from lore.runner import verify_lesson


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    lesson_path = Path(sys.argv[1])
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    v = lesson["verification"]

    print(f"lesson : {lesson['id']} (semver {lesson['semver']})")
    print(f"image  : {v['image']}  setup_network={v.get('setup_network', 'packages')}")

    built = build_image(
        image=v["image"],
        setup=v.get("setup", []),
        setup_network=v.get("setup_network", "packages"),
    )
    print(f"built  : {built.tag}  cached={built.cached}")
    print(f"digest : {built.image_id}")

    report = verify_lesson(lesson, built)

    for variant in report.variants:
        o = variant.output
        print(f"\n[{variant.variant}] {variant.command}")
        print(f"  exit={o.exit_code}  {o.duration_sec:.2f}s  timed_out={o.timed_out}")
        for r in variant.assert_results:
            mark = "PASS" if r.passed else "FAIL"
            print(f"  [{mark}] {r.assertion['type']}: {r.detail}")

    print(f"\nVERDICT: {report.verdict.upper()}")
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
