# Verification

A Reverse-MCP is done when a fresh client can prove live reads and clean failure — plus one safe mutation and/or one event when those are in scope — not when the code compiles.

## Test matrix

| Layer | Test | Pass condition |
| --- | --- | --- |
| Build | `uv run ruff check` / `pnpm typecheck` / `cargo clippy` | No errors; warnings triaged |
| Types | `uv run --with mypy mypy src` / `pnpm typecheck` / `cargo check` | Clean |
| Unit | Surface validator, bridge client, schema validation | All pass |
| Bridge live | `check_bridge.py`: `bridge.hello` + `surface.snapshot` | Target hash matches; requested values return |
| Protocol | MCP `initialize`, `tools/list`, `tools/call` | Tools list with descriptions; schemas valid |
| Read-only live | `app_status`, `list_surfaces`, `get_snapshot`, `get_config` | Values match the visible UI |
| Mutation live | One safe action/setting, when write scope includes mutations | UI/state changes; no collateral change |
| Event live | Expected event, when events are in scope | Event arrives or polling fallback is documented |
| Confirmation | Mutating call without `confirm` | Preview only; no side effect |
| Failure | Target closed, bridge down, bad token, stale ID, bad args, timeout | Structured error; no crash/hang |
| Security | Loopback bind, token required, secret redaction | Unauthorized call rejected; no secret in output/log |
| Immutability | SHA-256 before/after | Original unchanged; copy isolated (patch mode) |
| Repeatability | 10 consecutive read cycles | No leak, no growing queue, stable latency |
| Restart | Target restart + bridge reconnect | Recovers or reports `TARGET_NOT_RUNNING` cleanly |

## Commands

Use the generated project's own commands. Typical:

```bash
# Python
uv run ruff check .
uv run pytest -q
uv run python -m reverse_mcp_acme

# TypeScript
pnpm typecheck
pnpm test
pnpm build

# Rust
cargo fmt --check
cargo clippy -- -D warnings
cargo test
cargo run
```

MCP protocol smoke test (FastMCP Python; adjust the module/command to the generated project):

```python
import asyncio

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main() -> None:
    transport = StdioTransport(
        "uv",
        ["run", "python", "-m", "reverse_mcp_acme.main"],
        cwd="server",
    )
    async with Client(transport) as client:
        print(await client.list_tools())
        print(await client.call_tool("app_status", {}, raise_on_error=False))


asyncio.run(main())
```

For other frameworks, use the official inspector or the SDK's in-memory transport. Do not validate only by reading the source.

Bridge gate before server work:

```bash
python scripts/check_bridge.py \
  --url http://127.0.0.1:8765 \
  --token-file ~/.reverse-mcp/<slug>.token \
  --expect-sha256 <original-sha256> \
  --surface-id main.status
```

## Live verification procedure

1. **Freeze a baseline.** Screenshot the target, record the visible window title, status text, selected item, and the config file hash.
2. **Bridge gate.** Run `check_bridge.py`; `bridge.hello` must return the expected target hash and `surface.snapshot` must return live values.
3. **Read.** Call `list_surfaces`, then `get_snapshot` for 3–5 surfaces. Compare every field to the baseline. If a field is missing, fix the map, not the test.
4. **Config read.** Call `get_config` for the agreed keys. Compare to the settings UI and the backing store. Confirm the source precedence.
5. **Preview (if mutations are in scope).** Call a mutating tool with `confirm=false`. Verify it reports the correct target and side effects and changes nothing (hash/screenshot).
6. **Mutate (if mutations are in scope).** Call with `confirm=true`. Verify the UI updates. If events are in scope, verify the expected event arrives; otherwise document the polling fallback.
7. **Restore (if a mutation was made).** Revert the setting or reload the fixture. Verify the baseline hash/screenshot returns.
8. **Failure drills.** Close the target; call a read; kill the bridge; call again; send an invalid ID; wait past a timeout. Every path must return a structured error and leave the server responsive.
9. **Hash check.** `sha256sum`/`Get-FileHash` the original and the copy. For hook/observer: original identical. For patch: original identical, copy documented.

## Evidence to capture

- `analysis/environment.json` and the exact commands used.
- `analysis/surface.json` passing the validator.
- Baseline screenshot + post-mutation screenshot (redact personal data).
- Hash before/after for the original and copy.
- `check_bridge.py` output showing target hash and returned surfaces.
- Bridge log excerpt showing method, target, and result code (no token/secrets).
- MCP client transcript showing tool list and at least one successful call.
- Residual unknowns, with the search boundary that produced them.

## Acceptance criteria

- [ ] `analysis/surface.json` validates and covers every in-scope surface/config/event/action, or lists an `out_of_scope` reason.
- [ ] `analysis/REPORT.md` has an evidence row for each nontrivial claim.
- [ ] `check_bridge.py` proves the target hash and a live snapshot.
- [ ] The server starts with one documented command.
- [ ] The client lists the tools and calls `app_status` successfully.
- [ ] A read tool returns live data matching the UI.
- [ ] If mutations are in scope: a mutation is preview-gated and works with confirmation.
- [ ] If events are in scope: an event is observed, or its absence is documented with a polling fallback.
- [ ] Failure cases return structured errors; the server stays alive.
- [ ] The original binary hash is unchanged (or the copy is isolated and documented).
- [ ] The README lets the user reproduce the run without the agent.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| MCP client shows no tools | Server exited on startup; wrong command/cwd | Run the server manually; check stderr; use absolute paths in the client config |
| `BRIDGE_UNAVAILABLE` | Bridge not started; wrong port; firewall | Start the bridge; read the token/port file; verify `curl`/`Invoke-WebRequest` |
| `BRIDGE_AUTH_FAILED` | Token mismatch; token file permissions | Re-issue token; ensure the MCP process can read the file |
| `SURFACE_NOT_FOUND` | Wrong ID; stale `surface.json` | Re-run `list_surfaces`; re-validate the map |
| `STALE_HANDLE` | Dialog closed; app re-rendered; target restarted | Re-open the surface; re-snapshot; do not click blind |
| Read values differ from UI | Cached/derived state; wrong selector; virtualization | Read the authoritative object; scroll/virtualize; add evidence |
| Mutation appears to succeed but UI unchanged | Async apply; wrong source; restart required | Wait for event; check `apply` mode; re-read the store |
| App crashes on hook | Wrong signature/ABI; hooking a hot path; re-entrancy | Narrow the hook; check calling convention; add a detach/watchdog |
| Anti-cheat/integrity alert | Runtime instrumentation detected | Stop; this is a security control; use observer/protocol or decline |
| Selectors break after update | Version drift | Re-run REA for the new version; pin the map to the version |
| High CPU | Polling loop; unbounded event buffer | Use event/wakeup; backoff; cap and coalesce |
