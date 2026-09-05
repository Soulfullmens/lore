"""LLM client abstraction.

The agent loop talks to an ``LLMClient`` protocol, never to a vendor SDK
directly. That keeps the loop testable offline (via ``ScriptedClient``)
and swappable (OpenRouter, Gemini, local, etc.) — the same decoupling
discipline the memory engine uses for storage.

Tool use is modelled as structured ``ToolCall``s rather than parsed out of
free text. Function-calling is far more robust than regex-scraping a
"Thought/Action:" transcript, especially when the argument is a blob of
multi-line code — the SDK / API handles JSON encoding so newlines never corrupt
the parse.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass(slots=True)
class Message:
    """One turn in the conversation. ``role`` is 'system' | 'user' |
    'assistant' | 'tool'. For tool results, ``tool_name`` and ``tool_call_id``
    identify which call this answers."""

    role: str
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


@dataclass(slots=True)
class ToolSpec:
    """Declaration of a tool the model may call (JSON-schema parameters)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(slots=True)
class LLMResponse:
    """A single model turn: optional prose plus zero or more tool calls."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        seed: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...


# --------------------------------------------------------------------------- #
# OpenRouter implementation (OpenAI-compatible HTTP, zero external deps)
# --------------------------------------------------------------------------- #
class OpenRouterClient:
    """Adapter for OpenRouter (OpenAI-compatible) chat completions API.

    Uses standard library ``urllib.request`` — no extra packages required.
    Reads the API key from ``OPENROUTER_API_KEY``.

    Supports any model hosted on OpenRouter, for example:
      - "anthropic/claude-3.5-haiku"
      - "anthropic/claude-3.5-sonnet"
      - "openai/gpt-4o-mini"
      - "google/gemini-2.0-flash-001"
      - "meta-llama/llama-3.3-70b-instruct"
      - "qwen/qwen-2.5-coder-32b-instruct"
      - "deepseek/deepseek-chat"
    """

    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        *,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_api_key(self) -> str:
        key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Set the environment variable or pass api_key."
            )
        return key

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        seed: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        api_key = self._get_api_key()
        url = f"{self.base_url}/chat/completions"

        # Format messages for OpenAI / OpenRouter API
        formatted_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                formatted_messages.append({"role": "system", "content": m.content})
            elif m.role == "user":
                formatted_messages.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                msg_dict: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id or f"call_{tc.name}_{i}",
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.args),
                            },
                        }
                        for i, tc in enumerate(m.tool_calls)
                    ]
                formatted_messages.append(msg_dict)
            elif m.role == "tool":
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or f"call_{m.tool_name or 'tool'}",
                    "name": m.tool_name,
                    "content": m.content,
                })

        # Format tools for OpenAI API
        formatted_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "seed": seed,
        }
        if formatted_tools:
            payload["tools"] = formatted_tools

        req_body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Soulfullmens/lore",
                "X-Title": "Lore Memory Engine",
                "User-Agent": "Lore-Memory/0.1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {err.code}: {err_body}") from err
        except Exception as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc}") from exc

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        text = message.get("content") or ""

        tool_calls: list[ToolCall] = []
        for raw_tc in message.get("tool_calls", []):
            fn = raw_tc.get("function", {})
            fn_name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {"raw": raw_args}
            else:
                args = raw_args
            tool_calls.append(ToolCall(name=fn_name, args=args, id=raw_tc.get("id")))

        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )


# --------------------------------------------------------------------------- #
# Gemini implementation
# --------------------------------------------------------------------------- #
class GeminiClient:
    """Adapter over Google's Gemini function-calling.

    Uses the current ``google-genai`` SDK (``from google import genai``).
    Reads the key from ``GEMINI_API_KEY``.

        pip install google-genai
        export GEMINI_API_KEY=...
    """

    def __init__(self, model: str = "gemini-2.0-flash-lite") -> None:
        self.model = model
        self._client = None  # lazy — importing the SDK is deferred

    def _ensure(self) -> None:
        if self._client is not None:
            return
        from google import genai  # type: ignore

        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=key)

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        seed: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self._ensure()
        from google.genai import types  # type: ignore

        # Map our neutral Message list into Gemini "contents".
        system_text = "\n\n".join(m.content for m in messages if m.role == "system")
        contents: list[Any] = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))

        fn_decls = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters=t.parameters
            )
            for t in tools
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_text or None,
            temperature=temperature,
            seed=seed,
            tools=[types.Tool(function_declarations=fn_decls)] if fn_decls else None,
        )
        resp = self._client.models.generate_content(  # type: ignore[union-attr]
            model=self.model, contents=contents, config=config
        )

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for cand in getattr(resp, "candidates", []) or []:
            for part in getattr(cand.content, "parts", []) or []:
                if getattr(part, "text", None):
                    text_parts.append(part.text)
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    calls.append(ToolCall(name=fc.name, args=dict(fc.args or {})))

        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=calls,
            tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
        )


# --------------------------------------------------------------------------- #
# Scripted client — deterministic, offline, for tests and the loop demo
# --------------------------------------------------------------------------- #
class ScriptedClient:
    """Replays a fixed list of ``LLMResponse``s, ignoring the prompt.

    This is how we verify the loop, tools, and evaluation are real without
    an API key: feed the exact tool-call sequence a competent agent would
    make, and confirm the task genuinely passes its checks.
    """

    def __init__(self, script: Sequence[LLMResponse]) -> None:
        self._script = list(script)
        self._i = 0
        self.calls_made = 0

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        *,
        seed: int,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls_made += 1
        if self._i >= len(self._script):
            # Ran out of script — emit a finish so the loop terminates cleanly.
            return LLMResponse(text="(script exhausted)", tool_calls=[ToolCall("finish", {})])
        resp = self._script[self._i]
        self._i += 1
        return resp
