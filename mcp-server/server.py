#!/usr/bin/env python3
"""Lore MCP Server — Model Context Protocol endpoint for AI coding agents.

Exposes verified procedural gotchas to Claude Desktop, Cursor, Windsurf, and Aider
via standard MCP STDIO protocol.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LESSONS_DIR = REPO_ROOT / "lessons"
RECEIPTS_DIR = REPO_ROOT / "receipts"


def _find_latest_receipt(lesson_path: Path) -> Path | None:
    """Receipts live at receipts/<domain>/<lesson-stem>/<timestamp>.json.

    Return the most recent receipt for this lesson, or None if unverified.
    ISO-8601 timestamp filenames sort chronologically, so the last is newest.
    """
    stem = lesson_path.stem
    receipts = sorted(RECEIPTS_DIR.glob(f"**/{stem}/*.json"))
    return receipts[-1] if receipts else None


def _list_lessons() -> list[dict]:
    lessons = []
    for p in sorted(LESSONS_DIR.glob("**/*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_receipt_path"] = _find_latest_receipt(p)
        data["_file_path"] = p
        lessons.append(data)
    return lessons


def handle_lore_search(query: str) -> dict:
    """Search verified procedural gotchas by symptom, keyword, or error message."""
    lessons = _list_lessons()
    query_terms = [q.strip().lower() for q in query.split() if q.strip()]
    matches = []

    for l in lessons:
        searchable_text = " ".join([
            l.get("summary", ""),
            l.get("problem", ""),
            " ".join(l.get("symptoms", [])),
            " ".join(l.get("tags", [])),
            l.get("id", ""),
        ]).lower()

        score = sum(1 for term in query_terms if term in searchable_text)
        if score > 0 or not query_terms:
            matches.append({
                "id": l.get("id"),
                "slug": l["_file_path"].stem,
                "summary": l.get("summary"),
                "symptoms": l.get("symptoms", []),
                "status": l.get("lifecycle", {}).get("status", "unknown"),
                "verified": l.get("lifecycle", {}).get("status") == "verified",
                "receipt_stamped": l["_receipt_path"] is not None,
                "relevance_score": score,
            })

    matches.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {"results": matches[:5]}


def _matches_slug(stem: str, filename: str, slug: str) -> bool:
    """Match by filename stem, full filename, or trailing ID number only.

    Accepts '0002', 'asyncio-gather-detached-siblings-0002', or the full filename.
    Never matches on file *content* (which caused wrong-lesson resolution).
    """
    return slug == stem or slug == filename or stem.endswith(f"-{slug}")


def handle_lore_get(slug: str) -> dict:
    """Fetch complete verified lesson + receipt by lesson ID number or slug."""
    slug = (slug or "").strip().lower()
    if not slug:
        return {"error": "Empty slug. Pass an ID like '0002' or a full lesson slug."}

    for p in sorted(LESSONS_DIR.glob("**/*.json")):
        if _matches_slug(p.stem.lower(), p.name.lower(), slug):
            data = json.loads(p.read_text(encoding="utf-8"))
            receipt_path = _find_latest_receipt(p)
            receipt_data = None
            if receipt_path is not None:
                try:
                    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
                except Exception:
                    receipt_data = None
            return {
                "lesson": data,
                "receipt": receipt_data,
                "verified": data.get("lifecycle", {}).get("status") == "verified",
            }
    return {"error": f"Lesson not found for slug/ID: {slug}"}


TOOLS = [
    {
        "name": "lore_search",
        "description": "Search verified procedural coding gotchas by symptom, error message, or technology tag.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Error message, symptom, or topic (e.g. 'asyncio gather detached' or 'aclose')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "lore_get",
        "description": "Fetch the full container-verified lesson, solution procedure, anti-patterns, and Docker eval receipt for a specific gotcha ID or slug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Lesson ID number or filename slug (e.g. '0002' or 'asyncio-gather-detached-siblings-0002')"
                }
            },
            "required": ["slug"]
        }
    }
]


def process_mcp_request(request: dict) -> dict | None:
    method = request.get("method")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "lore-mcp", "version": "0.2.0"}
            }
        }
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "lore_search":
            res = handle_lore_search(args.get("query", ""))
        elif name == "lore_get":
            res = handle_lore_get(args.get("slug", ""))
        else:
            res = {"error": f"Unknown tool: {name}"}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}
        }
    elif method == "notifications/initialized":
        return None

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"}
    }


def main():
    """Run MCP STDIO loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = process_mcp_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
