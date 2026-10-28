#!/usr/bin/env python3
"""Generate a Reverse-MCP server skeleton.

The generated server is a thin, typed MCP adapter over a local JSON-RPC bridge.
It deliberately does not generate the target-specific hook/observer: that code
belongs in `bridge/` and is written from the surface map.

Examples:
    python scaffold_mcp.py --target "Acme Notes" --lang python --mode hook
    python scaffold_mcp.py --target "Acme Notes" --lang typescript --surface analysis/surface.json
    python scaffold_mcp.py --target "Acme Notes" --lang rust --out reverse-mcp/acme
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "target")[:48].strip("-")


def module_name(slug: str) -> str:
    name = "reverse_mcp_" + re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
    return name[:60].rstrip("_")


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    if executable:
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            pass


def render(template: str, **values: str) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"__{key.upper()}__", value)
    return text.lstrip("\n")


def load_surface(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError("surface map must be a JSON object")
    return data


def surface_summary(surface: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not surface:
        return [], []
    actions = [
        action.get("id", "?")
        for action in surface.get("actions", [])
        if isinstance(action, dict) and action.get("id")
    ]
    config = [
        entry.get("key", "?")
        for entry in surface.get("config", [])
        if isinstance(entry, dict) and entry.get("key")
    ]
    return actions, config


PY_BRIDGE = r'''
"""JSON-RPC client for the local Reverse-MCP bridge."""

from __future__ import annotations

import itertools
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class BridgeError(RuntimeError):
    """A structured error returned by the bridge or the transport."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class BridgeClient:
    """Small, dependency-free JSON-RPC 2.0 client over loopback HTTP."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        token_file: str | Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.url = (url or os.environ.get("REVERSE_MCP_BRIDGE", "__BRIDGE_URL__")).rstrip("/")
        self._token = token
        self.token_file = Path(
            token_file
            or os.environ.get("REVERSE_MCP_TOKEN_FILE", "~/.reverse-mcp/__SLUG__.token")
        ).expanduser()
        self.timeout = timeout
        self._ids = itertools.count(1)

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        env = os.environ.get("REVERSE_MCP_TOKEN")
        if env:
            return env
        try:
            return self.token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": method,
            "params": params or {},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = self.token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{self.url}/rpc",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            raise BridgeError(
                "BRIDGE_UNAVAILABLE",
                f"cannot reach {self.url}: {exc.reason}",
                retryable=True,
                details={"url": self.url},
            ) from exc

        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(
                "BRIDGE_PROTOCOL_ERROR",
                f"bridge returned non-JSON (HTTP {status})",
                retryable=False,
                details={"status": status},
            ) from exc

        if isinstance(data, dict) and data.get("error"):
            error = data["error"] or {}
            detail = error.get("data") if isinstance(error, dict) else None
            detail = detail if isinstance(detail, dict) else {}
            raise BridgeError(
                str(detail.get("code") or "BRIDGE_ERROR"),
                str(error.get("message") or "bridge error"),
                retryable=bool(detail.get("retryable", False)),
                details=detail,
            )
        if status >= 400:
            raise BridgeError(
                "BRIDGE_HTTP_ERROR",
                f"bridge returned HTTP {status}",
                retryable=status >= 500,
                details={"status": status},
            )
        if not isinstance(data, dict):
            raise BridgeError("BRIDGE_PROTOCOL_ERROR", "bridge response is not an object")
        return data.get("result")

    def health(self) -> dict[str, Any]:
        return self.call("bridge.health")

    def hello(self) -> dict[str, Any]:
        return self.call("bridge.hello")
'''

PY_MAIN = r'''
"""MCP server for __TARGET__.

Generated by Reverse-MCP-Anything. Replace the generic tools with typed tools for
the actions in analysis/surface.json once the bridge is implemented.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .bridge import BridgeClient, BridgeError

mcp = FastMCP("__NAME__")
bridge = BridgeClient()


def _call(method: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return bridge.call(method, params)
    except BridgeError as exc:
        # FastMCP turns exceptions into tool errors. Keep the structured fields
        # in the message until the bridge/client error type is wired through.
        raise RuntimeError(json_error(exc)) from exc


def json_error(exc: BridgeError) -> str:
    import json

    return json.dumps(exc.to_dict(), ensure_ascii=False)


@mcp.tool
def app_status() -> dict[str, Any]:
    """Return target identity and bridge health. Read-only."""
    return _call("bridge.hello")


@mcp.tool
def list_surfaces(kind: str | None = None) -> dict[str, Any]:
    """List known surfaces (ids, kinds, labels, risk). Read-only."""
    params: dict[str, Any] = {}
    if kind:
        params["kind"] = kind
    return _call("surface.list", params)


@mcp.tool
def get_snapshot(surface_ids: list[str] | None = None) -> dict[str, Any]:
    """Read current values for the requested surfaces. Read-only."""
    return _call("surface.snapshot", {"ids": surface_ids})


@mcp.tool
def get_config(keys: list[str] | None = None, reveal_secrets: bool = False) -> dict[str, Any]:
    """Read configuration values and sources. Secrets are redacted by default."""
    return _call("config.get", {"keys": keys, "reveal_secrets": reveal_secrets})


@mcp.tool
def set_config(key: str, value: str, confirm: bool = False) -> dict[str, Any]:
    """Change one setting. Without confirm=true, returns a preview only."""
    return _call("config.set", {"key": key, "value": value, "confirm": confirm})


@mcp.tool
def invoke_action(action_id: str, args: dict[str, Any] | None = None, confirm: bool = False) -> dict[str, Any]:
    """Invoke a mapped action. Without confirm=true, returns a preview only."""
    return _call("action.invoke", {"action_id": action_id, "args": args or {}, "confirm": confirm})


@mcp.tool
def wait_for_event(name: str, timeout_ms: int = 5000) -> dict[str, Any]:
    """Wait for a mapped event. Read-only; bounded by timeout_ms."""
    return _call("event.wait", {"name": name, "timeout_ms": timeout_ms})


def main() -> None:
    """Run over stdio (default). Use a loopback HTTP transport only if required."""
    mcp.run()


if __name__ == "__main__":
    main()
'''

PY_INIT = r'''
"""__TARGET__ MCP server package."""

__version__ = "0.1.0"
'''

PY_TEST = r'''
"""Contract-level tests that do not need a live target."""

from __future__ import annotations

from __MODULE__.bridge import BridgeClient, BridgeError


def test_error_shape() -> None:
    error = BridgeError("STALE_HANDLE", "dialog closed", retryable=True, details={"surface": "settings.theme"})
    payload = error.to_dict()
    assert payload["code"] == "STALE_HANDLE"
    assert payload["retryable"] is True
    assert payload["details"]["surface"] == "settings.theme"


def test_client_trims_trailing_slash() -> None:
    client = BridgeClient(url="http://127.0.0.1:8765/", token="test-token")
    assert client.url == "http://127.0.0.1:8765"
    assert client.token == "test-token"


def test_client_without_token_is_allowed_to_construct() -> None:
    client = BridgeClient(url="http://127.0.0.1:1", token_file="/nonexistent/token")
    assert client.token == ""
'''

PY_PYPROJECT = r'''
[project]
name = "__NAME__"
version = "0.1.0"
description = "Reverse-MCP server for __TARGET__"
requires-python = ">=3.10"
dependencies = ["fastmcp>=2"]

[project.scripts]
__NAME__ = "__MODULE__.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/__MODULE__"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
'''

PY_ENV = r'''
# Loopback bridge endpoint. Keep it on 127.0.0.1.
REVERSE_MCP_BRIDGE=__BRIDGE_URL__
# Prefer a token file with mode 0600; do not commit it.
REVERSE_MCP_TOKEN_FILE=~/.reverse-mcp/__SLUG__.token
'''

TS_BRIDGE = r'''
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface BridgeErrorShape {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export class BridgeError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;

  constructor(code: string, message: string, retryable = false, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }

  toJSON(): BridgeErrorShape {
    return { code: this.code, message: this.message, retryable: this.retryable, details: this.details };
  }
}

function readToken(path: string): string {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return "";
  }
}

export class BridgeClient {
  readonly url: string;
  private readonly token: string;
  private readonly timeoutMs: number;
  private nextId = 1;

  constructor(options: { url?: string; token?: string; tokenFile?: string; timeoutMs?: number } = {}) {
    this.url = (options.url ?? process.env.REVERSE_MCP_BRIDGE ?? "__BRIDGE_URL__").replace(/\/$/, "");
    this.token =
      options.token ??
      process.env.REVERSE_MCP_TOKEN ??
      readToken(options.tokenFile ?? process.env.REVERSE_MCP_TOKEN_FILE ?? join(homedir(), ".reverse-mcp", "__SLUG__.token"));
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  async call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    const headers: Record<string, string> = { "content-type": "application/json", accept: "application/json" };
    if (this.token) headers.authorization = `Bearer ${this.token}`;
    let response: Response;
    try {
      response = await fetch(`${this.url}/rpc`, {
        method: "POST",
        headers,
        body: JSON.stringify({ jsonrpc: "2.0", id: this.nextId++, method, params }),
        signal: controller.signal,
      });
    } catch (error) {
      throw new BridgeError("BRIDGE_UNAVAILABLE", `cannot reach ${this.url}: ${String(error)}`, true, { url: this.url });
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      throw new BridgeError("BRIDGE_PROTOCOL_ERROR", `bridge returned non-JSON (HTTP ${response.status})`, false, {
        status: response.status,
      });
    }
    if (data && typeof data === "object" && "error" in data) {
      const error = (data as { error?: { message?: string; data?: Record<string, unknown> } }).error ?? {};
      const detail = error.data ?? {};
      throw new BridgeError(
        String(detail.code ?? "BRIDGE_ERROR"),
        String(error.message ?? "bridge error"),
        Boolean(detail.retryable ?? false),
        detail,
      );
    }
    if (!response.ok) {
      throw new BridgeError("BRIDGE_HTTP_ERROR", `bridge returned HTTP ${response.status}`, response.status >= 500, {
        status: response.status,
      });
    }
    return (data as { result?: T }).result as T;
  }

  health(): Promise<unknown> {
    return this.call("bridge.health");
  }

  hello(): Promise<unknown> {
    return this.call("bridge.hello");
  }
}
'''

TS_MAIN = r'''
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { BridgeClient } from "./bridge.js";

const server = new McpServer({ name: "__NAME__", version: "0.1.0" });
const bridge = new BridgeClient();

function text(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value) }] };
}

server.registerTool(
  "app_status",
  { description: "Return target identity and bridge health. Read-only.", inputSchema: {} },
  async () => text(await bridge.call("bridge.hello")),
);

server.registerTool(
  "list_surfaces",
  {
    description: "List known surfaces (ids, kinds, labels, risk). Read-only.",
    inputSchema: { kind: z.string().optional() },
  },
  async ({ kind }) => text(await bridge.call("surface.list", kind ? { kind } : {})),
);

server.registerTool(
  "get_snapshot",
  {
    description: "Read current values for the requested surfaces. Read-only.",
    inputSchema: { surface_ids: z.array(z.string()).optional() },
  },
  async ({ surface_ids }) => text(await bridge.call("surface.snapshot", { ids: surface_ids })),
);

server.registerTool(
  "get_config",
  {
    description: "Read configuration values and sources. Secrets are redacted by default.",
    inputSchema: { keys: z.array(z.string()).optional(), reveal_secrets: z.boolean().default(false) },
  },
  async ({ keys, reveal_secrets }) => text(await bridge.call("config.get", { keys, reveal_secrets })),
);

server.registerTool(
  "set_config",
  {
    description: "Change one setting. Without confirm=true, returns a preview only.",
    inputSchema: { key: z.string(), value: z.string(), confirm: z.boolean().default(false) },
  },
  async ({ key, value, confirm }) => text(await bridge.call("config.set", { key, value, confirm })),
);

server.registerTool(
  "invoke_action",
  {
    description: "Invoke a mapped action. Without confirm=true, returns a preview only.",
    inputSchema: {
      action_id: z.string(),
      args: z.record(z.unknown()).optional(),
      confirm: z.boolean().default(false),
    },
  },
  async ({ action_id, args, confirm }) => text(await bridge.call("action.invoke", { action_id, args: args ?? {}, confirm })),
);

server.registerTool(
  "wait_for_event",
  {
    description: "Wait for a mapped event. Read-only; bounded by timeout_ms.",
    inputSchema: { name: z.string(), timeout_ms: z.number().int().positive().default(5000) },
  },
  async ({ name, timeout_ms }) => text(await bridge.call("event.wait", { name, timeout_ms })),
);

async function main() {
  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
'''

TS_TEST = r'''
import { describe, expect, it } from "vitest";
import { BridgeClient, BridgeError } from "../src/bridge.js";

describe("BridgeError", () => {
  it("serializes the structured fields", () => {
    const error = new BridgeError("STALE_HANDLE", "dialog closed", true, { surface: "settings.theme" });
    expect(error.toJSON()).toEqual({
      code: "STALE_HANDLE",
      message: "dialog closed",
      retryable: true,
      details: { surface: "settings.theme" },
    });
  });
});

describe("BridgeClient", () => {
  it("trims a trailing slash from the base URL", () => {
    const client = new BridgeClient({ url: "http://127.0.0.1:8765/", token: "test-token" });
    expect(client.url).toBe("http://127.0.0.1:8765");
  });
});
'''

TS_PACKAGE = r'''
{
  "name": "__NAME__",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "description": "Reverse-MCP server for __TARGET__",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "dev": "tsx src/main.ts",
    "start": "node dist/main.js",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "zod": "^3.23.8"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "tsx": "^4.0.0",
    "typescript": "^5.0.0",
    "vitest": "^2.0.0"
  }
}
'''

TS_TSCONFIG = r'''
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022"],
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "declaration": false,
    "sourceMap": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist", "tests"]
}
'''

TS_ENV = r'''
# Loopback bridge endpoint. Keep it on 127.0.0.1.
REVERSE_MCP_BRIDGE=__BRIDGE_URL__
# Prefer a token file with mode 0600; do not commit it.
REVERSE_MCP_TOKEN_FILE=~/.reverse-mcp/__SLUG__.token
'''

RUST_BRIDGE = r'''
use anyhow::{anyhow, Context, Result};
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;

#[derive(Clone)]
pub struct BridgeClient {
    base: String,
    token: String,
    http: Client,
}

impl BridgeClient {
    pub fn default_url() -> &'static str {
        "__BRIDGE_URL__"
    }

    pub fn from_env() -> Result<Self> {
        let base = std::env::var("REVERSE_MCP_BRIDGE").unwrap_or_else(|_| Self::default_url().to_string());
        let token = std::env::var("REVERSE_MCP_TOKEN")
            .ok()
            .or_else(|| {
                let path = std::env::var("REVERSE_MCP_TOKEN_FILE").ok()?;
                std::fs::read_to_string(path).ok().map(|value| value.trim().to_string())
            })
            .unwrap_or_default();
        let http = Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .context("build HTTP client")?;
        Ok(Self {
            base: base.trim_end_matches('/').to_string(),
            token,
            http,
        })
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let mut request = self.http.post(format!("{}/rpc", self.base)).json(&json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }));
        if !self.token.is_empty() {
            request = request.bearer_auth(&self.token);
        }
        let response = request.send().await.context("bridge request failed")?;
        let status = response.status();
        let body: Value = response.json().await.context("bridge returned non-JSON")?;
        if let Some(error) = body.get("error") {
            let detail = error.get("data").cloned().unwrap_or(Value::Null);
            let code = detail
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("BRIDGE_ERROR");
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("bridge error");
            return Err(anyhow!("{}: {}", code, message));
        }
        if !status.is_success() {
            return Err(anyhow!("bridge returned HTTP {}", status));
        }
        Ok(body.get("result").cloned().unwrap_or(Value::Null))
    }
}

#[cfg(test)]
mod tests {
    use super::BridgeClient;

    #[test]
    fn default_endpoint_is_loopback() {
        assert!(BridgeClient::default_url().starts_with("http://127.0.0.1:"));
    }
}
'''

RUST_MAIN = r'''
use rmcp::{
    handler::server::{
        router::tool::ToolRouter,
        wrapper::Parameters,
    },
    model::*,
    tool, tool_handler, tool_router,
    transport::stdio,
    ErrorData as McpError, ServerHandler, ServiceExt,
};
use serde_json::{json, Value};

mod bridge;

use bridge::BridgeClient;

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct ListSurfacesArgs {
    pub kind: Option<String>,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct SnapshotArgs {
    pub surface_ids: Option<Vec<String>>,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct GetConfigArgs {
    pub keys: Option<Vec<String>>,
    #[serde(default)]
    pub reveal_secrets: bool,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct SetConfigArgs {
    pub key: String,
    pub value: String,
    #[serde(default)]
    pub confirm: bool,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct InvokeActionArgs {
    pub action_id: String,
    pub args: Option<Value>,
    #[serde(default)]
    pub confirm: bool,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct WaitForEventArgs {
    pub name: String,
    #[serde(default = "default_timeout_ms")]
    pub timeout_ms: u64,
}

fn default_timeout_ms() -> u64 {
    5000
}

#[derive(Clone)]
pub struct AppServer {
    bridge: BridgeClient,
    #[allow(dead_code)]
    tool_router: ToolRouter<Self>,
}

#[tool_router]
impl AppServer {
    pub fn new(bridge: BridgeClient) -> Self {
        Self {
            bridge,
            tool_router: Self::tool_router(),
        }
    }

    #[tool(description = "Return target identity and bridge health. Read-only.")]
    async fn app_status(&self) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call("bridge.hello", json!({}))
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "List known surfaces (ids, kinds, labels, risk). Read-only.")]
    async fn list_surfaces(
        &self,
        Parameters(args): Parameters<ListSurfacesArgs>,
    ) -> Result<CallToolResult, McpError> {
        let mut params = json!({});
        if let Some(kind) = args.kind {
            params["kind"] = Value::String(kind);
        }
        let value = self
            .bridge
            .call("surface.list", params)
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "Read current values for the requested surfaces. Read-only.")]
    async fn get_snapshot(
        &self,
        Parameters(args): Parameters<SnapshotArgs>,
    ) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call("surface.snapshot", json!({ "ids": args.surface_ids }))
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "Read configuration values and sources. Secrets are redacted by default.")]
    async fn get_config(
        &self,
        Parameters(args): Parameters<GetConfigArgs>,
    ) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call(
                "config.get",
                json!({ "keys": args.keys, "reveal_secrets": args.reveal_secrets }),
            )
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "Change one setting. Without confirm=true, returns a preview only.")]
    async fn set_config(
        &self,
        Parameters(args): Parameters<SetConfigArgs>,
    ) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call(
                "config.set",
                json!({ "key": args.key, "value": args.value, "confirm": args.confirm }),
            )
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "Invoke a mapped action. Without confirm=true, returns a preview only.")]
    async fn invoke_action(
        &self,
        Parameters(args): Parameters<InvokeActionArgs>,
    ) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call(
                "action.invoke",
                json!({
                    "action_id": args.action_id,
                    "args": args.args.unwrap_or_else(|| json!({})),
                    "confirm": args.confirm,
                }),
            )
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }

    #[tool(description = "Wait for a mapped event. Read-only; bounded by timeout_ms.")]
    async fn wait_for_event(
        &self,
        Parameters(args): Parameters<WaitForEventArgs>,
    ) -> Result<CallToolResult, McpError> {
        let value = self
            .bridge
            .call(
                "event.wait",
                json!({ "name": args.name, "timeout_ms": args.timeout_ms }),
            )
            .await
            .map_err(to_mcp_error)?;
        Ok(text_result(value))
    }
}

#[tool_handler]
impl ServerHandler for AppServer {
    fn get_info(&self) -> ServerConfig {
        ServerConfig::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::from_build_env())
            .with_instructions(
                "Reverse-MCP server for __TARGET__. Start with app_status, then list_surfaces/get_snapshot. Mutations require confirm=true."
                    .to_string(),
            )
    }
}

fn to_mcp_error(error: anyhow::Error) -> McpError {
    McpError::internal_error("bridge_error", Some(json!({ "message": error.to_string() })))
}

fn text_result(value: Value) -> CallToolResult {
    CallToolResult::success(vec![ContentBlock::text(value.to_string())])
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .with_writer(std::io::stderr)
        .with_ansi(false)
        .init();

    let bridge = BridgeClient::from_env()?;
    let service = AppServer::new(bridge).serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}
'''

RUST_CARGO = r'''
[package]
name = "__NAME__"
version = "0.1.0"
edition = "2024"
rust-version = "1.88"
description = "Reverse-MCP server for __TARGET__"

[dependencies]
rmcp = { version = "3", features = ["server", "transport-io", "macros", "schemars"] }
tokio = { version = "1", features = ["macros", "rt-multi-thread", "io-std", "signal"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
schemars = "1"
anyhow = "1"
reqwest = { version = "0.13", default-features = false, features = ["json"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

[dev-dependencies]
tokio = { version = "1", features = ["macros", "rt"] }
'''

README = r'''
# Reverse-MCP: __TARGET__

Generated by Reverse-MCP-Anything.

- **Mode:** `__MODE__`
- **Stack:** `__LANG__`
- **MCP server name:** `__NAME__`
- **Bridge:** `__BRIDGE_URL__` (loopback only)

## What is here

- `analysis/surface.json` — the surface contract (if supplied).
- `server/` — MCP server skeleton with generic read/preview/action tools.
- `bridge/README.md` — the target-specific bridge contract and TODOs.
- tests live in `server/tests/` (Python/TS) or beside the Rust module.

## Run

__RUN__

The server expects the bridge to be running. Set `REVERSE_MCP_BRIDGE` if it is
not on the default port, and `REVERSE_MCP_TOKEN_FILE` to a mode-0600 token file.
Start with `app_status`, then `list_surfaces`, `get_snapshot`, and `get_config`.

## Register with an MCP client

Use the command above as the stdio server. Example:

```json
{
  "mcpServers": {
    "__NAME__": {
      "command": "__COMMAND__",
      "args": __ARGS__,
      "env": {
        "REVERSE_MCP_BRIDGE": "__BRIDGE_URL__",
        "REVERSE_MCP_TOKEN_FILE": "~/.reverse-mcp/__SLUG__.token"
      }
    }
  }
}
```

## Next steps

1. Implement the bridge in `bridge/` (observer, protocol proxy, or hook). Match
   the JSON-RPC methods in `bridge/README.md`.
2. Replace the generic tools with typed tools for the user-facing outcomes.
   Keep `app_status`, `list_surfaces`, `get_snapshot`, and `get_config` as primitives.
3. Add confirmation/elicitation for every mutation; keep `confirm=false` as a
   preview that changes nothing.
4. Run the verification matrix: read, preview, mutate, event, failure drills,
   binary hash check.
5. Update this README with the exact start command, client snippet, and limits.

## Safety

- Bind the bridge to `127.0.0.1`; never expose it on `0.0.0.0`.
- Do not commit tokens, captured secrets, or patched binaries.
- Original binary hash must remain unchanged unless this is an isolated copy.

## Mapped actions

__ACTIONS__

## Mapped config keys

__CONFIG__
'''

BRIDGE_README = r'''
# Bridge contract

Implement the target-specific bridge here. The generated MCP server speaks
JSON-RPC 2.0 over loopback HTTP:

- `POST __BRIDGE_URL__/rpc`
- `Authorization: Bearer <token>` (32 random bytes, token file mode 0600)
- Bind only to `127.0.0.1`.

Required methods:

| Method | Params | Result |
| --- | --- | --- |
| `bridge.hello` | `{}` | target name/version/pid/sha256, mode, capabilities |
| `bridge.health` | `{}` | ok, uptime_ms, queue_depth, target_alive |
| `surface.list` | `{kind?}` | surfaces with id/kind/label/risk |
| `surface.snapshot` | `{ids?, depth?}` | captured_at + values by surface id |
| `action.invoke` | `{action_id, args, confirm}` | preview when confirm=false |
| `config.get` | `{keys?, reveal_secrets?}` | values + sources, secrets redacted |
| `config.set` | `{key, value, confirm}` | preview when confirm=false |
| `event.wait` | `{name, timeout_ms}` | one event or timeout |

Error shape:

```json
{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"...","data":{"code":"STALE_HANDLE","retryable":true,"details":{}}}}
```

Implementation checklist:

- [ ] Start order: bridge (or launcher) before MCP server.
- [ ] Verify target hash in `bridge.hello`; reject a mismatched target.
- [ ] Allowlist methods/actions; no `eval`/`exec`.
- [ ] Redact secrets in `config.get` unless explicitly allowed.
- [ ] Re-check `confirm` in the bridge.
- [ ] Bounded payloads and timeouts; event buffer capped.
- [ ] Detach/unhook and close sockets on exit.
- [ ] Record the original binary hash before and after.
'''


GITIGNORE = r'''
# Local virtualenvs and caches
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node
node_modules/
dist/

# Rust
target/

# Local secrets and test artifacts
.env
*.token
work/
'''


def python_files(out: Path, *, name: str, slug: str, module: str, target: str, mode: str, bridge_url: str, surface: dict[str, Any] | None) -> None:
    server = out / "server"
    write(server / "pyproject.toml", render(PY_PYPROJECT, name=name, target=target, module=module))
    write(server / "src" / module / "__init__.py", render(PY_INIT, target=target))
    write(server / "src" / module / "bridge.py", render(PY_BRIDGE, bridge_url=bridge_url, slug=slug))
    write(server / "src" / module / "main.py", render(PY_MAIN, target=target, name=name))
    write(server / "tests" / "test_contract.py", render(PY_TEST, module=module))
    write(server / ".env.example", render(PY_ENV, bridge_url=bridge_url, slug=slug))
    write(
        out / "run.ps1",
        f'$here = Split-Path -Parent $MyInvocation.MyCommand.Path\n'
        f'$env:REVERSE_MCP_BRIDGE = "{bridge_url}"\n'
        f'uv --directory (Join-Path $here "server") run {name}\n',
    )
    write(
        out / "run.sh",
        f'#!/usr/bin/env bash\nset -euo pipefail\n'
        f'here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"\n'
        f'export REVERSE_MCP_BRIDGE="${{REVERSE_MCP_BRIDGE:-{bridge_url}}}"\n'
        f'uv --directory "$here/server" run {name}\n',
        executable=True,
    )


def typescript_files(out: Path, *, name: str, slug: str, target: str, mode: str, bridge_url: str) -> None:
    server = out / "server"
    write(server / "package.json", render(TS_PACKAGE, name=name, target=target))
    write(server / "tsconfig.json", TS_TSCONFIG)
    write(server / "src" / "bridge.ts", render(TS_BRIDGE, bridge_url=bridge_url, slug=slug))
    write(server / "src" / "main.ts", render(TS_MAIN, name=name))
    write(server / "tests" / "bridge.test.ts", TS_TEST)
    write(server / ".env.example", render(TS_ENV, bridge_url=bridge_url, slug=slug))
    write(
        out / "run.ps1",
        f'$here = Split-Path -Parent $MyInvocation.MyCommand.Path\n'
        f'$env:REVERSE_MCP_BRIDGE = "{bridge_url}"\n'
        f'pnpm --dir (Join-Path $here "server") dev\n',
    )
    write(
        out / "run.sh",
        f'#!/usr/bin/env bash\nset -euo pipefail\n'
        f'here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"\n'
        f'export REVERSE_MCP_BRIDGE="${{REVERSE_MCP_BRIDGE:-{bridge_url}}}"\n'
        f'pnpm --dir "$here/server" dev\n',
        executable=True,
    )


def rust_files(out: Path, *, name: str, slug: str, target: str, mode: str, bridge_url: str) -> None:
    server = out / "server"
    write(server / "Cargo.toml", render(RUST_CARGO, name=name, target=target))
    write(server / "src" / "bridge.rs", render(RUST_BRIDGE, bridge_url=bridge_url))
    write(server / "src" / "main.rs", render(RUST_MAIN, target=target))
    write(
        out / "run.ps1",
        f'$here = Split-Path -Parent $MyInvocation.MyCommand.Path\n'
        f'$env:REVERSE_MCP_BRIDGE = "{bridge_url}"\n'
        f'cargo run --manifest-path (Join-Path $here "server/Cargo.toml")\n',
    )
    write(
        out / "run.sh",
        f'#!/usr/bin/env bash\nset -euo pipefail\n'
        f'here="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"\n'
        f'export REVERSE_MCP_BRIDGE="${{REVERSE_MCP_BRIDGE:-{bridge_url}}}"\n'
        f'cargo run --manifest-path "$here/server/Cargo.toml"\n',
        executable=True,
    )


def build_readme(*, out: Path, name: str, slug: str, target: str, mode: str, lang: str, bridge_url: str, surface: dict[str, Any] | None) -> str:
    server_dir = out.resolve() / "server"
    if lang == "python":
        run = f"```bash\ncd server\nuv sync\nuv run {name}\n```"
        command = "uv"
        args = json.dumps(["--directory", str(server_dir), "run", name])
    elif lang == "typescript":
        run = "```bash\ncd server\npnpm install\npnpm build\npnpm start\n```"
        command = "node"
        args = json.dumps([str(server_dir / "dist" / "main.js")])
    else:
        run = "```bash\ncd server\ncargo run\n```"
        command = "cargo"
        args = json.dumps(["run", "--manifest-path", str(server_dir / "Cargo.toml")])

    actions, config = surface_summary(surface)
    actions_text = "\n".join(f"- `{item}`" for item in actions) if actions else "- None mapped yet. Add them to `analysis/surface.json` and regenerate typed tools."
    config_text = "\n".join(f"- `{item}`" for item in config) if config else "- None mapped yet. Add them to `analysis/surface.json`."

    return render(
        README,
        name=name,
        slug=slug,
        target=target,
        mode=mode,
        lang=lang,
        bridge_url=bridge_url,
        run=run,
        command=command,
        args=args,
        actions=actions_text,
        config=config_text,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Reverse-MCP server skeleton.")
    parser.add_argument("--target", required=True, help="Human-readable target name")
    parser.add_argument("--lang", choices=("python", "typescript", "rust"), required=True)
    parser.add_argument("--mode", choices=("observer", "protocol", "hook", "patch", "hybrid"), default="observer")
    parser.add_argument("--surface", type=Path, default=None, help="Path to analysis/surface.json")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: reverse-mcp/<slug>)")
    parser.add_argument("--name", default=None, help="MCP server name (default: reverse-mcp-<slug>)")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765", help="Loopback bridge URL")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing generated directory")
    args = parser.parse_args(argv)

    slug = slugify(args.target)
    out = args.out or Path("reverse-mcp") / slug
    name = args.name or f"reverse-mcp-{slug}"
    module = module_name(slug)

    if out.exists() and not out.is_dir():
        print(f"ERROR: {out} exists and is not a directory", file=sys.stderr)
        return 1
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"ERROR: {out} is not empty; pass --force to overwrite", file=sys.stderr)
        return 1

    resolved_out = out.resolve()
    cwd = Path.cwd().resolve()
    if args.force and (resolved_out == cwd or resolved_out == Path.home().resolve() or resolved_out.parent == resolved_out):
        print(f"ERROR: refusing to overwrite {resolved_out}; choose a project subdirectory", file=sys.stderr)
        return 1

    surface = None
    if args.surface:
        try:
            surface = load_surface(args.surface)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"ERROR: cannot read surface map: {exc}", file=sys.stderr)
            return 1

    if out.exists() and args.force:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    if surface is not None:
        write(out / "analysis" / "surface.json", json.dumps(surface, indent=2, ensure_ascii=False) + "\n")

    write(out / ".gitignore", GITIGNORE)
    write(out / "bridge" / "README.md", render(BRIDGE_README, bridge_url=args.bridge_url))
    write(
        out / "README.md",
        build_readme(
            out=out,
            name=name,
            slug=slug,
            target=args.target,
            mode=args.mode,
            lang=args.lang,
            bridge_url=args.bridge_url,
            surface=surface,
        ),
    )

    if args.lang == "python":
        python_files(
            out,
            name=name,
            slug=slug,
            module=module,
            target=args.target,
            mode=args.mode,
            bridge_url=args.bridge_url,
            surface=surface,
        )
    elif args.lang == "typescript":
        typescript_files(
            out,
            name=name,
            slug=slug,
            target=args.target,
            mode=args.mode,
            bridge_url=args.bridge_url,
        )
    else:
        rust_files(
            out,
            name=name,
            slug=slug,
            target=args.target,
            mode=args.mode,
            bridge_url=args.bridge_url,
        )

    print(f"Generated {out}")
    print(f"  name:   {name}")
    print(f"  module: {module}")
    print(f"  stack:  {args.lang} ({args.mode})")
    if surface is None:
        print("  surface map: not supplied; pass --surface analysis/surface.json next time")
    print("\nNext:")
    print(f"  cd {out / 'server'}")
    if args.lang == "python":
        print("  uv sync && uv run " + name)
    elif args.lang == "typescript":
        print("  pnpm install && pnpm build && pnpm start")
    else:
        print("  cargo run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
