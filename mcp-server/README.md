# Lore MCP Server (`mcp-server`)

Model Context Protocol (MCP) server for Lore. Exposes verified procedural gotchas, symptoms, anti-patterns, and container verification receipts directly to AI coding agents (Claude Desktop, Cursor, Windsurf, Aider).

---

## 🛠️ Configuration for Claude Desktop & Cursor

Add the following to your `claude_desktop_config.json` (or Cursor MCP settings):

### macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
### Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "lore": {
      "command": "python",
      "args": [
        "C:/Users/abdul rahaman/Downloads/Lore/mcp-server/server.py"
      ]
    }
  }
}
```

---

## ⚡ Exposed Tools

| Tool | Input Schema | Description |
| :--- | :--- | :--- |
| `lore_search` | `{"query": "asyncio gather"}` | Search verified procedural gotchas by symptom, error message, or technology tag. |
| `lore_get` | `{"slug": "0002"}` | Fetch full container-verified lesson, solution procedure, anti-patterns, and Docker eval receipt for a specific gotcha ID. |

---

## 🧪 Testing the MCP Server Locally

Test STDIO JSON-RPC initialization:

```bash
python mcp-server/server.py
```

Send test JSON-RPC request over STDIN:
```json
{"jsonrpc":"2.0","id":1,"method":"initialize"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lore_search","arguments":{"query":"gather"}}}
```
