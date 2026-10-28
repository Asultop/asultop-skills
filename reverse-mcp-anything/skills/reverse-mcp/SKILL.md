---
name: reverse-mcp
description: Reverse-MCP-Anything: turn a local program's human-visible UI, live state, events, and configuration into a typed MCP server without modifying its installed binary. Use for /reverse-mcp, or when asked to expose a desktop, Electron, CLI/TUI, web, or native app to an agent through accessibility, IPC, hooks, or an explicitly approved patched copy. 适用于把程序界面、配置和事件接入 MCP。
compatibility: Local, user-authorized targets; REA (reverse-engineer-anything) and grilling (grill-me) are strongly recommended; Python 3.10+, Node 20+, or Rust 1.88+ for the generated server.
metadata:
  version: "0.2.0"
  author: "AsulTop"
  requires: "reverse-engineer-anything (morluto/rea); grilling (mattpocock/skills grill-me)"
---

# Reverse-MCP-Anything

Build a **Reverse-MCP**: a local MCP server that reads what the target currently shows, changes what a user can change, and waits for the events a user can trigger — by driving the running application, not by reimplementing it.

Default posture: **read-only-first, least-invasive-first, copy-only when patching.** The installed binary stays byte-identical unless the user explicitly chooses a patched copy.

## Non-negotiables

- **Authorization.** Work only on software the user owns or is authorized to test, on their own machine. Stop for remote/multi-tenant targets, anti-cheat, DRM/licence enforcement, or requests to weaken security controls.
- **Original bytes.** Hash the target before and after. Observer, protocol, and hook modes leave the on-disk binary unchanged; hook mode changes process memory. Patch only a copy under `work/`, never the installed original.
- **Least access.** Start read-only. Redact secrets by default. A mutating tool needs an explicit confirmation path.
- **Evidence.** Separate observation, inference, and unknown. Static analysis never proves runtime behavior; runtime observation never proves code structure.
- **No escape hatch.** Never expose `run_command`, `eval`, raw shell, or arbitrary memory writes as an MCP tool.

## Requires

- **REA** — load the `reverse-engineer-anything` skill ([morluto/rea](https://github.com/morluto/rea)) and follow its routing. If its tools are absent, read its connection-and-recovery reference and continue with native tools, marking evidence as non-REA.
- **grill-me** — load the `grilling` skill ([mattpocock/skills](https://github.com/mattpocock/skills)); `grill-me` is its user-invoked alias. If neither is available, use the question bank in [references/intake.md](references/intake.md) instead of skipping the interview.

If a dependency is missing, say which one and continue with the documented fallback. Do not silently replace the interview or the evidence standard.

## Route

`/reverse-mcp <target>` runs eight steps. Do not write the MCP server before the bridge is live.

| Step | Consumes | Produces | Gate to the next step |
| --- | --- | --- | --- |
| 1. **Mode Gate** | user intent, target facts | `analysis/DECISIONS.md` | No branch silently assumed |
| 2. **Runtime Probe** | OS/arch, client/host constraints | `analysis/environment.json`, chosen stack + transport | The chosen toolchain exists |
| 3. **REA Analysis** | target + agreed scope | `analysis/REPORT.md` + evidence ledger | The eight questions are answered or marked unknown |
| 4. **Surface Map** | report + scope | `analysis/surface.json` | Validator passes |
| 5. **Bridge** | surface map + mode | live bridge, hash record, `bridge.hello` + `surface.snapshot` proof | Bridge is live; original hash matches |
| 6. **MCP Server** | surface map + live bridge | `server/` with typed tools | Server lists tools; `app_status` returns live data |
| 7. **Verification** | server + bridge + surface map | test results, hashes, residual unknowns | Acceptance matrix passes |
| 8. **Delivery** | all of the above | README, report, handover | User can reproduce without the agent |

## Step 1 — Mode Gate with grill-me

Load `grilling` and run the interview in rounds. Ask the whole current frontier at once, number each question, and give a recommended answer. Probe facts yourself; put only decisions to the user.

The first frontier is in [references/intake.md](references/intake.md). Settle at least:

- **Target identity** — exact executable/process, version, path, OS/arch, and whether it is already running.
- **User outcomes** — the three concrete tasks the MCP must enable (read state, change a setting, trigger a command, wait for an event). Vague goals produce unusable tools.
- **Mode** — observer, protocol, hook, patch, or hybrid. Recommend observer → protocol → hook, and hook over patch. Recommend patch only when a read-only or hook route cannot reach the required surface, and only on a copy.
- **Write scope** — which actions may mutate; which need confirmation; what must never be exposed.
- **Environment constraints** — OS/arch, local-only, container/WSL, target vs client host, client. The final stack is chosen in Step 2 from the probe.
- **Acceptance** — one read, plus one mutation and/or one event when those are in scope.

Record the answers in `analysis/DECISIONS.md`. The interview is complete when no branch is silently assumed.

## Step 2 — Runtime Probe

Run the read-only probe and keep its JSON:

```bash
python scripts/probe_environment.py --json analysis/environment.json
```

It checks `PATH`, common version-manager locations, and default compiler/SDK install roots; it never installs anything. Read [references/environment.md](references/environment.md) to interpret the result and choose a stack. If `python` is unavailable, the agent can reproduce the same checks with `Get-Command`/`command -v`; the probe is a convenience, not a gate.

Pick the server stack from **observed** tools, not preference:

- `uv` + Python ≥ 3.10 → FastMCP Python (default for UIA, accessibility, Frida hosts).
- Node ≥ 20 + npm/pnpm → TypeScript (default for Electron/CDP and web targets).
- Rust ≥ 1.88 + cargo → `rmcp` (default when a native bridge or single-binary deployment matters).
- No viable toolchain → present exact install options and ask before installing.

## Step 3 — REA Analysis

Load `reverse-engineer-anything`. Route by target type, then answer the eight questions in [references/analysis.md](references/analysis.md):

1. How does the app launch, attach, and enforce single-instance?
2. Which UI toolkit renders it, and what does its accessibility tree expose?
3. Which human-readable elements and current values exist?
4. Which commands, IPC methods, and input events drive those elements?
5. Where does configuration come from, in what precedence, and which parts are encrypted?
6. Where are decrypt/encrypt routines, and can the app's own routine be called at runtime?
7. What state is observable, what mutates it, and what invariants must hold?
8. What blocks instrumentation — integrity checks, signing, anti-debug, elevation, sandboxing, updates?

Write `analysis/REPORT.md` with an **Evidence Ledger**: claim, Evidence ID, static/runtime, confidence, unknowns. Every later claim about the target cites a row.

Keep this step read-only: no hooks, no patches, no mutations. If an experiment would change state, defer it to Step 5 with the user's approval.

## Step 4 — Surface Map

Build `analysis/surface.json` against [assets/surface.schema.json](assets/surface.schema.json). This is the contract between analysis and server code.

Inventory, within the agreed scope:

- **Surfaces** — windows, menus, toolbars, tabs, lists, trees, tables, text, status areas, dialogs, notifications, canvases, terminals, webviews. For each: label, role, selector, readable fields, available actions, risk, evidence.
- **Configuration** — key, type, default, current value, source, precedence, writable, encryption, apply mode (live/restart), validation.
- **Events** — name, source, trigger, payload, rate, whether it is observed or only inferred.
- **Actions** — verb, target surface, argument schema, side effects, idempotency, confirmation rule.

Selector priority: native command/IPC method → accessibility AutomationId/name → object path → DOM selector → role+label → relative coordinates (last resort, marked brittle). A coordinate is not a contract; a stable ID is.

Use [references/surface-map.md](references/surface-map.md) for the checklist and examples. Discovery should not mutate persistent state; if a click is needed, use a disposable fixture and record it as evidence. Validate before coding:

```bash
python scripts/validate_surface.py analysis/surface.json
```

## Step 5 — Choose and implement the bridge

Pick the lowest-risk route that actually reaches the surface:

| Route | On-disk binary | What changes | Use when |
| --- | --- | --- | --- |
| **Observer** | unchanged | nothing in the process | Accessibility/UIA/AX/AT-SPI, logs, files, screenshots, PTY, CDP |
| **Protocol** | unchanged | traffic or a local IPC proxy | The app already speaks HTTP/WS/JSON-RPC/named pipe |
| **Hook** | unchanged | process memory and call flow | Internal state, decrypt routines, or commands are unreachable |
| **Patch** | **copy only** | a copied binary/ASAR/resource | Hook is blocked and the user explicitly authorizes a fork |

Try Observer → Protocol → Hook in that order. Patch is a separate, opt-in decision, not a shortcut.

Record the original hash before touching the process:

```powershell
Get-FileHash -Algorithm SHA256 "<target.exe>"    # Windows
```

```bash
sha256sum "<target>"                              # Linux/macOS
```

Then implement the chosen route behind the bridge contract in [references/instrumentation.md](references/instrumentation.md). Do not stop at "route chosen": a bridge that cannot answer `bridge.hello` and `surface.snapshot` is not a handoff, it is a hypothesis.

Start the bridge and prove it live:

```bash
python scripts/check_bridge.py \
  --url http://127.0.0.1:8765 \
  --token-file ~/.reverse-mcp/<slug>.token \
  --expect-sha256 <original-sha256> \
  --surface-id main.status
```

The gate is: `bridge.hello` returns the expected target identity/hash, `surface.snapshot` returns at least one current value matching the UI, and the original hash is unchanged (or the patched copy is isolated). For patch mode, record both the original and copy hashes. If the route cannot satisfy that gate, fall back to the next route or move the surface to `out_of_scope`; do not build the server over a mock.

## Step 6 — MCP Server

Scaffold only after the Step 5 bridge gate passes. Use the chosen stack and surface map:

```bash
python scripts/scaffold_mcp.py --target "<name>" --lang python --mode hook \
  --surface analysis/surface.json --out reverse-mcp/<slug>   # or --lang typescript / rust
```

Then replace the generated generic tools with **typed tools for the user's actual outcomes**. Keep `list_surfaces`, `get_snapshot`, and `get_config` as discovery/read primitives; add one tool per high-value action, not one tool per pixel.

Framework choice and the full tool contract are in [references/mcp-server.md](references/mcp-server.md). Minimum contract:

- Read tools declare read-only intent (annotations where the framework supports them) and return bounded JSON.
- Mutating tools support a dry run and require `confirm=true` (or an elicitation token) before acting.
- IDs are stable strings from `surface.json`; never expose array indices.
- Errors are structured: `TARGET_NOT_RUNNING`, `BRIDGE_UNAVAILABLE`, `SURFACE_NOT_FOUND`, `STALE_HANDLE`, `VALIDATION_FAILED`, `CONFIRMATION_REQUIRED`, `TIMEOUT`, `UNSUPPORTED`.
- Secrets are redacted by default; there is no shell/eval tool.

## Step 7 — Verification

Run the matrix in [references/verification.md](references/verification.md). At minimum:

- `app_status`, `list_surfaces`, and `get_snapshot` return live data matching the UI.
- `get_config` matches the app's settings UI for the agreed keys.
- If mutations are in scope: one safe mutation changes the UI/state, with confirmation.
- If events are in scope: the expected event is observed, or a polling fallback is documented.
- Target closed, bridge down, stale ID, invalid args, and timeout all fail cleanly.
- The original binary hash is unchanged (or the original is untouched and the copy is clearly identified).

Only then call the build complete.

## Step 8 — Delivery

Produce this layout:

```text
reverse-mcp/<target-slug>/
├── README.md                 # run, register, permissions, limitations
├── analysis/
│   ├── DECISIONS.md
│   ├── environment.json
│   ├── REPORT.md             # evidence ledger + coverage
│   └── surface.json
├── bridge/                   # hook/observer/proxy implementation
└── server/                   # MCP server + its tests
```

A runnable README names the exact start command, the client registration snippet, the read-only tool to try first, and the residual unknowns. Do not ship a patched binary, a token, or captured secrets.

## Done when

- `analysis/surface.json` validates and covers every in-scope element, config key, event, and action — or lists it under `out_of_scope` with a reason.
- Every nontrivial claim in `analysis/REPORT.md` cites evidence.
- The bridge answers `bridge.hello` and at least one `surface.snapshot` with live data.
- The MCP server starts, lists tools, and returns live data through the bridge.
- Read paths are tested; if mutations or events are in scope, they are tested and confirmation-gated too.
- The original binary hash is unchanged, or the patched copy is isolated and documented.
- The user can reproduce the run from the README without the agent.

## Failure routing

| Observed blocker | Move |
| --- | --- |
| REA tools absent or blocked | Use native analysis tools; mark evidence `non-REA`; resume REA after repair. |
| grill-me unavailable | Run the same rounds from `references/intake.md`; still wait for decisions. |
| No usable compiler | Present install options and exact commands; do not install without consent. |
| Accessibility tree empty | Try protocol/CDP/PTY; then hook. Record custom-rendered surfaces. |
| Hook blocked by integrity/anti-cheat | Stop. Prefer observer/protocol; only discuss patch on a copy with explicit authorization. |
| Crypto cannot be recovered | Hook the app's own decrypt/encrypt routine; otherwise mark those config keys read-only/out of scope. |
| Target updates and selectors break | Re-run Step 3 for the new version; version-pin the surface map. |
| Bridge crashes the target | Detach, restore, reduce hook scope, add a watchdog; never broaden injection to other processes. |
