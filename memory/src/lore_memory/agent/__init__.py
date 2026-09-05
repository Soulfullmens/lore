"""Agent package — the reference ReAct loop and LLM adapters."""

from .llm import (
    GeminiClient,
    LLMClient,
    LLMResponse,
    Message,
    OpenRouterClient,
    ScriptedClient,
    ToolCall,
    ToolSpec,
)
from .loop import ReActAgent
from .tools import Tool, ToolRegistry, default_tools

__all__ = [
    "GeminiClient",
    "LLMClient",
    "LLMResponse",
    "Message",
    "OpenRouterClient",
    "ReActAgent",
    "ScriptedClient",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolSpec",
    "default_tools",
]
