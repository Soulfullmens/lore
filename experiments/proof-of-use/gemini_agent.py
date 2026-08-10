"""Gemini integration for the Lore proof-of-use runner.

Drop-in replacement for the call_agent() stub in run_pou.py. Uses the free-tier
Gemini API (Flash / Flash-Lite). Reads the key from the environment — NEVER
hardcode it, and never commit it.

Setup:
    pip install google-generativeai
    export GOOGLE_API_KEY="your-key-from-aistudio.google.com"   # (Windows: setx or $env:)

Experiment discipline baked in:
- temperature = 0 (determinism: the lesson is the only variable, not sampling noise)
- SAME model + config for control and treatment (the function doesn't know which
  condition it's in — it just answers a prompt; run_pou.py controls the variable)
- 429 rate-limit handling with exponential backoff (free tier is ~10-15 RPM;
  18 trials will brush the limit, so this matters)
"""

from __future__ import annotations

import os
import time

import google.generativeai as genai

# Free-tier model. Flash-Lite is smaller/faster and MORE likely to need the lesson,
# which makes the experiment sharper. Swap to "gemini-2.5-flash" for a stronger model.
MODEL_NAME = os.environ.get("LORE_POU_MODEL", "gemini-2.5-flash-lite")

_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set. Get a free key at aistudio.google.com and "
            "export it (never hardcode or commit it)."
        )
    genai.configure(api_key=key)
    _configured = True


def call_agent(prompt: str) -> str:
    """Send one prompt to Gemini at temperature 0; return raw text.

    Identical config for both experiment conditions — that's the controlled-variable
    guarantee. Retries on 429 (free-tier rate limit) with exponential backoff.
    """
    _ensure_configured()
    model = genai.GenerativeModel(MODEL_NAME)
    cfg = genai.types.GenerationConfig(
        temperature=0.0,      # deterministic
        max_output_tokens=2048,
    )

    delay = 2.0
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            resp = model.generate_content(prompt, generation_config=cfg)
            # Gemini can return multiple parts; concatenate text parts.
            if getattr(resp, "text", None):
                return resp.text
            parts = []
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
            if parts:
                return "".join(parts)
            return ""  # empty response — trial will be graded UNSOLVED, which is honest
        except Exception as e:  # noqa: BLE001 — includes ResourceExhausted (429)
            last_err = e
            msg = str(e).lower()
            if "429" in msg or "resource" in msg or "quota" in msg or "rate" in msg:
                time.sleep(delay)
                delay *= 2  # 2, 4, 8, 16s
                continue
            raise
    raise RuntimeError(f"Gemini call failed after retries: {last_err}")


# ---- self-test: confirms wiring WITHOUT spending quota on a fake experiment ----
if __name__ == "__main__":
    print(f"model: {MODEL_NAME}")
    print("key present:", bool(os.environ.get("GOOGLE_API_KEY")))
    print("Sending one trivial test prompt (uses 1 request of your daily quota)...")
    try:
        out = call_agent("Reply with exactly the word: OK")
        print("response:", repr(out.strip()[:80]))
        print("WIRED CORRECTLY" if "OK" in out.upper() else "responded, but check output")
    except Exception as e:
        print("FAILED:", e)
