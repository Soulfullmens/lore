"""Image builder for Lore verification.

Design decision (spec v0.2): setup and eval are separated STRUCTURALLY,
not by policy. Setup commands are baked into an ephemeral image via
`docker build` (builds have network per setup_network); evals then run
against that image with `--network none`. The phase separation cannot be
bypassed by a lesson because the eval container simply has no network.

Caching: the image tag is derived from a content hash of (base image,
setup commands, setup_network). Re-verification of an unchanged
environment is a cache hit; a changed dependency pin busts the cache
automatically.

HONEST LIMITATION (v0): setup_network="packages" grants full network
during build — Docker cannot scope build network to package indexes
without a filtering proxy. Until the proxy exists (v1), "packages" is a
declared intent, enforced as full-at-build / none-at-eval, and lessons
using it carry that note in their receipts.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

TAG_PREFIX = "lore-verify"
BUILD_TIMEOUT_SEC = 900


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuiltImage:
    tag: str
    image_id: str  # full content digest from docker inspect — this is the env_digest for receipts
    cached: bool


def context_hash(image: str, setup: list[str], setup_network: str) -> str:
    payload = json.dumps(
        {"image": image, "setup": setup, "setup_network": setup_network},
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def generate_dockerfile(image: str, setup: list[str]) -> str:
    """Ephemeral Dockerfile: base image + setup commands, nothing else.

    Lesson files are NOT baked in — they are bind-mounted at eval time so
    the same image serves both positive and negative variants, and so the
    image cache is keyed purely on environment, not lesson content.
    """
    lines = [f"FROM {image}"]
    lines += [f"RUN {cmd}" for cmd in setup]
    lines.append("WORKDIR /work")
    return "\n".join(lines) + "\n"


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, check=False
    )


def image_exists(tag: str) -> str | None:
    """Return the image ID if the tag exists locally, else None."""
    proc = _run(["docker", "image", "inspect", "--format", "{{.Id}}", tag], timeout=60)
    if proc.returncode == 0:
        return proc.stdout.strip()
    return None


def build_image(
    image: str,
    setup: list[str],
    setup_network: str = "packages",
    force_rebuild: bool = False,
) -> BuiltImage:
    """Build (or reuse) the verification image for a lesson environment."""
    tag = f"{TAG_PREFIX}:{context_hash(image, setup, setup_network)}"

    if not force_rebuild:
        existing = image_exists(tag)
        if existing:
            return BuiltImage(tag=tag, image_id=existing, cached=True)

    dockerfile = generate_dockerfile(image, setup)
    network_flag = "none" if setup_network == "none" else "default"

    with tempfile.TemporaryDirectory(prefix="lore-build-") as ctx:
        (Path(ctx) / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        cmd = [
            "docker", "build",
            "--network", network_flag,
            "--tag", tag,
            ctx,
        ]
        try:
            proc = _run(cmd, timeout=BUILD_TIMEOUT_SEC)
        except subprocess.TimeoutExpired as e:
            raise BuildError(f"docker build timed out after {BUILD_TIMEOUT_SEC}s") from e

    if proc.returncode != 0:
        raise BuildError(
            f"docker build failed (exit {proc.returncode}):\n{proc.stderr[-4000:]}"
        )

    image_id = image_exists(tag)
    if not image_id:
        raise BuildError("build reported success but image not found — docker state inconsistent")
    return BuiltImage(tag=tag, image_id=image_id, cached=False)
