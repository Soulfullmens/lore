"""Lore CLI — verification, static checks, and receipt stamping."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from .builder import build_image, BuildError
from .runner import verify_lesson, RunnerError
from .static_checks import run_static_checks
from .receipts import generate_receipt, save_receipt


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """Lore — A verified experience commons for AI agents."""
    pass


@cli.command()
@click.argument("lesson_path", type=click.Path(exists=True, path_type=Path))
@click.option("--stamp/--no-stamp", default=False, help="Update lesson status to 'verified' and save receipt on success.")
@click.option("--json-out/--no-json", "json_out", default=False, help="Output machine-readable JSON verification report.")
@click.option("--schema-path", type=click.Path(exists=True, path_type=Path), default=None, help="Path to lesson.schema.json")
def verify(lesson_path: Path, stamp: bool, json_out: bool, schema_path: Path | None):
    """Verify a lesson file: static checks -> Docker build -> negative run -> positive run."""
    repo_root = _find_repo_root(lesson_path)
    if schema_path is None:
        schema_path = repo_root / "schemas" / "lesson.schema.json"

    if not json_out:
        click.echo(f"📋 Verifying {lesson_path}...")

    # Step 1: Read JSON
    raw_text = lesson_path.read_text(encoding="utf-8")
    try:
        lesson = json.loads(raw_text)
    except Exception as e:
        click.secho(f"❌ Failed to parse JSON: {e}", fg="red")
        sys.exit(1)

    # Step 2: Static Checks
    if not json_out:
        click.echo("🔍 Running static checks (schema, duplicate keys, token budgets, prompt injection)...")
    checks = run_static_checks(lesson, schema_path, raw_json=raw_text)
    all_static_ok = True
    for c in checks:
        if c.passed:
            click.echo(f"  ✅ [{c.check_name}] {c.detail}")
        else:
            click.secho(f"  ❌ [{c.check_name}] {c.detail}", fg="red")
            all_static_ok = False

    if not all_static_ok:
        click.secho("\n❌ Static checks failed. Aborting verification.", fg="red")
        sys.exit(1)

    # Step 3: Build Container Environment
    v = lesson.get("verification", {})
    image = v.get("image", "python:3.12-slim")
    setup = v.get("setup", [])
    setup_network = v.get("setup_network", "packages")

    click.echo(f"\n🐳 Building Docker environment ({image}, setup_network={setup_network})...")
    try:
        built = build_image(image=image, setup=setup, setup_network=setup_network)
        click.echo(f"  ✅ Tag: {built.tag} (cached={built.cached})")
        click.echo(f"  ✅ Digest: {built.image_id}")
    except BuildError as e:
        click.secho(f"❌ Docker build failed: {e}", fg="red")
        sys.exit(1)

    # Step 4: Run Verification Pipeline
    click.echo("\n🧪 Running verification pipeline (negative run first)...")
    try:
        report = verify_lesson(lesson, built)
    except RunnerError as e:
        click.secho(f"❌ Verification pipeline error: {e}", fg="red")
        sys.exit(1)

    for variant in report.variants:
        o = variant.output
        status_color = "green" if variant.passed else "red"
        click.echo(f"\n  [{variant.variant.upper()}] command: {variant.command}")
        click.echo(f"    exit_code={o.exit_code} | duration={o.duration_sec:.2f}s | timed_out={o.timed_out}")
        for r in variant.assert_results:
            mark = "✅" if r.passed else "❌"
            click.echo(f"    {mark} [{r.assertion['type']}] {r.detail}")
        if not variant.passed:
            if o.stdout:
                click.echo(f"    --- STDOUT ---\n    {o.stdout.strip()}")
            if o.stderr:
                click.echo(f"    --- STDERR ---\n    {o.stderr.strip()}")

    click.echo("")
    receipt = generate_receipt(report, lesson)
    if stamp and report.verdict == "pass":
        now = datetime.now(timezone.utc).isoformat()
        lesson["lifecycle"]["status"] = "verified"
        if not lesson["lifecycle"].get("first_verified"):
            lesson["lifecycle"]["first_verified"] = now
        lesson["lifecycle"]["last_verified"] = now

        lesson_path.write_text(json.dumps(lesson, indent=2) + "\n", encoding="utf-8")
        rpath = save_receipt(receipt, repo_root)
        if not json_out:
            click.echo(f"  Stamped {lesson_path} status to 'verified'")
            click.echo(f"  Saved receipt to {rpath}")

    if json_out:
        click.echo(json.dumps(receipt, indent=2))

    if report.verdict == "pass":
        if not json_out:
            click.secho(f"🎉 VERDICT: PASS ({report.lesson_id} @ {report.semver})", fg="green", bold=True)
        sys.exit(0)
    else:
        if not json_out:
            click.secho(f"💥 VERDICT: FAIL ({report.lesson_id} @ {report.semver})", fg="red", bold=True)
        sys.exit(1)


@cli.command("static-check")
@click.argument("lesson_path", type=click.Path(exists=True, path_type=Path))
@click.option("--schema-path", type=click.Path(exists=True, path_type=Path), default=None)
def static_check(lesson_path: Path, schema_path: Path | None):
    """Run static checks only (schema, token budgets, prompt injection) without Docker."""
    repo_root = _find_repo_root(lesson_path)
    if schema_path is None:
        schema_path = repo_root / "schemas" / "lesson.schema.json"

    raw_text = lesson_path.read_text(encoding="utf-8")
    try:
        lesson = json.loads(raw_text)
    except Exception as e:
        click.secho(f"❌ Failed to parse JSON: {e}", fg="red")
        sys.exit(1)

    checks = run_static_checks(lesson, schema_path, raw_json=raw_text)
    failed = False
    for c in checks:
        if c.passed:
            click.echo(f"✅ [{c.check_name}] {c.detail}")
        else:
            click.secho(f"❌ [{c.check_name}] {c.detail}", fg="red")
            failed = True

    sys.exit(1 if failed else 0)


def _find_repo_root(start_path: Path) -> Path:
    current = start_path.resolve()
    for parent in [current, *current.parents]:
        if (parent / "SPEC.md").exists() or (parent / "schemas").exists():
            return parent
    return Path.cwd()


if __name__ == "__main__":
    cli()
