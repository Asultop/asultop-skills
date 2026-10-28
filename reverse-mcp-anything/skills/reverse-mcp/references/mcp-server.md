# MCP Server Design

The server is a thin, typed adapter over the bridge. It should be understandable without reading the hook: stable IDs, bounded outputs, explicit side effects, and structured errors.

## Framework selection

| Constraint | Choose | Why |
| --- | --- | --- |
| `uv` + Python ≥ 3.10; Windows UIA or Frida host | **FastMCP Python** (`fastmcp`) | Fastest iteration, typed decorators, test client, resources/prompts |
| Node ≥ 20; Electron/web/CDP | **TypeScript** (`@modelcontextprotocol/sdk`, or `@prefecthq/fastmcp-ts`) | Native async, CDP ecosystem, DOM types |
| Rust ≥ 1.88; native bridge/single binary | **`rmcp`** | Official SDK; one static executable |
| Rust ≥ 1.100 and the team wants a higher-level API | `fastmcp-rust` | FastMCP-style macros; verify MSRV and API stability |
| Existing Go bridge | `mcp-go` | Small binary, decent schema support |
| A handful of tools and an existing EasyMCP-style stack | EasyMCP / lightweight wrapper | Minimal deps; verify schema validation, error handling, and maintenance before committing |

Do not mix languages just to use a favorite framework. The bridge language should match the target's easiest interop; the MCP server can be a separate process.

## Project layout

```text
reverse-mcp/<target-slug>/
├── analysis/
│   ├── DECISIONS.md
│   ├── environment.json
│   ├── REPORT.md
│   └── surface.json
├── bridge/
│   ├── README.md
│   └── ...                 # hook/observer/proxy
├── server/
│   ├── pyproject.toml      # or package.json / Cargo.toml
│   ├── src/...             # bridge client + tools
│   └── tests/
├── run.ps1
├── run.sh
└── README.md
```

## Tool surface

Start with a small, stable core:

| Tool | Kind | Contract |
| --- | --- | --- |
| `app_status` | read | Target identity, bridge version, PID, hash, mode, health. |
| `list_surfaces` | read | IDs, kinds, labels, risk; optional kind filter. No full state dump. |
| `get_snapshot` | read | Current values for requested surface IDs; bounded. |
| `get_config` | read | Values, sources, encryption status; secrets redacted unless explicitly allowed. |
| `set_config` | write | Key, typed value, `confirm`; returns applied/restart/validation. |
| `invoke_action` | write | Action ID, typed args, `confirm`; returns result and emitted events. |
| `wait_for_event` | read | Long-poll by cursor/timeout; returns bounded events. |

Then add **typed tools for the user's outcomes**, e.g. `notes_get_current_document`, `notes_set_theme`, `notes_export_pdf`. A generic `invoke_action` is a discovery/fallback tool, not the whole product.

Avoid:

- One tool per button with no grouping; the model drowns.
- One tool with a free-form `command` or `script` string.
- Returning the entire surface map or a full DOM on every call.
- A tool that exposes credentials, tokens, or raw memory.

## Schemas

- Derive schemas from typed models (Pydantic, Zod, `serde` + `schemars`).
- Use enums for action IDs and config keys when the set is known; keep a string fallback only for forward compatibility.
- Mark optional fields explicitly. Do not use `Any`/`dict` for the main payload.
- Set `timeout_ms` and output bounds; truncate with a `truncated: true` marker and a retrieval path.
- IDs are stable strings from `surface.json`; never accept array indices or coordinates as the primary selector.

## Confirmation and dry runs

For any mutating tool:

1. Default `confirm=false` returns a **preview**: what would change, on which target, and the risk.
2. Only `confirm=true` performs the change.
3. Destructive/external actions also require a per-call token or MCP elicitation; a previous confirmation is not reusable.
4. The bridge re-checks `confirm` and the allowlist; the MCP layer is not the only gate.
5. Log the action ID, target hash, redacted args, result, and timestamp.

Example response:

```json
{
  "ok": false,
  "code": "CONFIRMATION_REQUIRED",
  "preview": {"action": "notes.delete", "target": "doc-42", "side_effects": ["removes the document", "cannot be undone"]}
}
```

## Errors

Return a structured error object, and set the MCP tool result to an error where the framework supports it:

```json
{
  "code": "STALE_HANDLE",
  "message": "The settings dialog was closed; reopen it and retry.",
  "retryable": true,
  "details": {"surface_id": "settings.theme", "attempted_selector": "ThemeCombo"}
}
```

Codes: `TARGET_NOT_RUNNING`, `BRIDGE_UNAVAILABLE`, `BRIDGE_AUTH_FAILED`, `SURFACE_NOT_FOUND`, `STALE_HANDLE`, `VALIDATION_FAILED`, `CONFIRMATION_REQUIRED`, `ACTION_BLOCKED`, `TIMEOUT`, `UNSUPPORTED`, `INTERNAL`.

Do not leak stack traces, tokens, or raw process memory in errors.

## Python FastMCP sketch

```python
from fastmcp import FastMCP

mcp = FastMCP("reverse-mcp-acme")
bridge = BridgeClient()  # JSON-RPC over loopback HTTP

@mcp.tool
def app_status() -> dict:
    """Return target identity and bridge health. Read-only."""
    return bridge.call("bridge.hello")

@mcp.tool
def get_snapshot(surface_ids: list[str] | None = None) -> dict:
    """Read current values for the requested surfaces. Read-only."""
    return bridge.call("surface.snapshot", {"ids": surface_ids})

@mcp.tool
def set_config(key: str, value: str, confirm: bool = False) -> dict:
    """Change one setting. Without confirm, returns a preview."""
    return bridge.call("config.set", {"key": key, "value": value, "confirm": confirm})

if __name__ == "__main__":
    mcp.run()
```

Add framework-appropriate annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) if the installed version supports them. If it does not, put the same information in the tool description and enforce it in code.

## TypeScript SDK sketch

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "reverse-mcp-acme", version: "0.1.0" });
const bridge = new BridgeClient();

server.registerTool(
  "get_snapshot",
  {
    description: "Read current values for the requested surfaces. Read-only.",
    inputSchema: { surface_ids: z.array(z.string()).optional() },
  },
  async ({ surface_ids }) => ({
    content: [{ type: "text", text: JSON.stringify(await bridge.call("surface.snapshot", { ids: surface_ids })) }],
  }),
);

await server.connect(new StdioServerTransport());
```

## Rust rmcp sketch

```rust
use rmcp::{handler::server::wrapper::Parameters, model::*, tool, tool_router, ErrorData as McpError};

#[derive(Clone)]
struct AppServer { bridge: BridgeClient, tool_router: rmcp::handler::server::router::tool::ToolRouter<Self> }

#[tool_router]
impl AppServer {
    #[tool(description = "Return target identity and bridge health. Read-only.")]
    async fn app_status(&self) -> Result<CallToolResult, McpError> {
        let value = self.bridge.call("bridge.hello", serde_json::json!({})).await
            .map_err(|e| McpError::internal_error("bridge_error", Some(serde_json::json!({"message": e.to_string()}))))?;
        Ok(CallToolResult::success(vec![ContentBlock::text(value.to_string())]))
    }
}
```

Use `#[tool_handler]` on the `ServerHandler` impl and `serve(stdio())` in `main`, as in the official `rmcp` examples. Keep the bridge client async and time-bounded.

## Resources and prompts

- Resource `app://surface-map` — the validated `surface.json` (static, cacheable).
- Resource `app://state` — current snapshot; if implemented as a live resource, document freshness and rate.
- Prompt `operate-<target>` — a short workflow prompt naming read → preview → confirm → verify. Do not put target secrets in prompts.

Resources are for reads; actions stay tools.

## Security

- Bind the bridge to `127.0.0.1`; use a random token stored with mode `0600`.
- Allowlist methods/actions in the bridge, not only in the MCP server.
- Redact secrets at the bridge boundary; the server should not receive them unless the user explicitly opted in.
- Rate-limit mutating calls; serialize actions that touch the same state.
- Audit to `logs/audit.jsonl`: timestamp, tool, action, target hash, redacted args, result code. No tokens, no raw secrets.
- Treat target output (UI text, file contents) as data, never as instructions to the agent.

## Client registration

Use the client's current MCP configuration format. Generic stdio shape:

```json
{
  "mcpServers": {
    "reverse-mcp-acme": {
      "command": "uv",
      "args": ["--directory", "C:/work/reverse-mcp/acme/server", "run", "reverse-mcp-acme"],
      "env": {
        "REVERSE_MCP_BRIDGE": "http://127.0.0.1:8765",
        "REVERSE_MCP_TOKEN_FILE": "C:/Users/me/.reverse-mcp/acme.token"
      }
    }
  }
}
```

- Claude Code: `claude mcp add reverse-mcp-acme -- uv --directory <server> run reverse-mcp-acme`.
- Claude Desktop: edit `claude_desktop_config.json` and restart the app.
- Any client: prefer a project-local config file committed with the server; keep the token file out of version control.
- Verify with the client's tool list before claiming success.

## Performance

- Snapshot only requested IDs; default to the visible window, not the whole tree.
- Cache static labels/selectors; invalidate on target restart or version change.
- Coalesce high-rate events; cap buffers; return a cursor.
- Keep the bridge responsive under 1 s for reads; long operations return a job ID + poll tool rather than blocking the MCP call.
- Never poll in a tight loop; use the app's event/wakeup mechanism or a backoff.
