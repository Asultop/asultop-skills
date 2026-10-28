# Intake and Mode Gate

Run this as the **grill-me** interview: load `grilling`, work the design tree in rounds, ask the whole current frontier, number the questions, and give a recommended answer. Ask in the user's language; the wording below is a scaffold, not a script to read verbatim.

Facts are the agent's job. Before asking a question, check the workspace, the process list, the binary metadata, and the environment. Only decisions belong to the user.

## Round 0 — Authorization and blast radius

Ask before touching the target:

1. **Ownership** — Is this software yours, or do you have written authorization to inspect and automate it on this machine?
2. **Environment** — Is this a disposable VM/test account, or your daily environment? What may be changed?
3. **Prohibited areas** — Are credentials, payments, messaging to third parties, anti-cheat, DRM, or licence checks in scope? (Recommend: exclude all of them.)
4. **Data handling** — May captured state be written to local files? May screenshots contain personal data? (Recommend: local-only, redact secrets, no uploads.)

Stop if the target is remote/multi-tenant, not owned by the user, or the request is to bypass a security/licence control. Record the answers at the top of `analysis/DECISIONS.md`.

## Round 1 — Target and outcomes

1. **Exact target** — executable path, process name, version, install directory, and whether it is running now. If the user says only "my app", resolve one installed artifact and ask if ambiguous.
2. **Three outcomes** — What are three concrete things the MCP should do? Prefer user-language verbs: "read the current order total", "switch the theme to dark", "wait for the export to finish".
3. **Current workaround** — How does the user do this today? Screenshots, clicks, copying text, editing a config file? This reveals the real surface.
4. **Acceptance** — What single read, plus whichever of a write or event is in scope, would prove the MCP works?
5. **Language/UI** — Is the UI localized? Which labels does the user actually see? Localized labels are weak selectors; prefer IDs.

Recommendation: start with 3–5 outcomes and a read-only first milestone. A giant "expose everything" scope hides which surface matters.

## Round 2 — Mode and write scope

Present the mode table and ask the user to choose. Recommend **hook** when observer/protocol cannot reach the needed surface; recommend **observer** first in all cases.

| Mode | Changes on disk | Changes in process | Strength | Cost/risk |
| --- | --- | --- | --- | --- |
| Observer | none | none | UIA/AX/AT-SPI, CDP, PTY, logs, files | May not see internal state |
| Protocol | none | none | Existing HTTP/WS/IPC is the cleanest API | Requires a reachable endpoint |
| Hook | none | injected code/hooks | Internal functions, decrypt, commands | Anti-tamper, crashes, version fragility |
| Patch | **copy only** | copied binary/ASAR | Full control | Signing/integrity/updates; highest maintenance |

Questions:

1. **Mode** — Observer, hook, patch, or hybrid? If the user says "invasive", confirm they mean a patched **copy**, not the installed original.
2. **Why** — Which outcome is unreachable without hook/patch? If none, stay observer.
3. **Write scope** — Read-only, settings-only, or full commands? Which actions are destructive or externally visible?
4. **Confirmation** — Which actions require a human confirmation each time? (Recommend: anything that deletes, purchases, sends, publishes, or changes another user's data.)
5. **Restart tolerance** — May the app be restarted to apply config? Is a restart observable to other users?
6. **Single instance** — Does the app refuse a second instance? Should the MCP attach to the running one or spawn its own?

Record: `mode`, `write_scope`, `confirmation_policy`, `restart_policy`, `attach_or_spawn`.

## Round 3 — Environment and stack

Run the probe first, then present only viable options.

1. **Stack** — Python/uv (FastMCP), TypeScript (FastMCP TS or official SDK), or Rust (rmcp/fastmcp-rust)? Recommend from the probe, not fashion:
   - Windows UIA/accessibility-heavy → Python.
   - Electron/web/CDP → TypeScript.
   - Native bridge/single binary → Rust.
2. **Transport** — stdio (default for one client) or loopback HTTP (multiple clients/long-lived bridge)? Recommend stdio unless the bridge must outlive the client.
3. **Client** — Claude Code, Claude Desktop, Codex, DSH, Cursor, or a custom client? Registration differs.
4. **Install permission** — May the agent add dependencies (`uv add`, `pnpm add`, `cargo add`)? Which package manager/registry?
5. **Deployment** — Local only? Any container/VM/WSL boundary? Does the MCP server run on the same OS as the target?

Record: `stack`, `framework`, `transport`, `client`, `dependency_policy`, `host_os`.

## Round 4 — Surface detail

Ask only what the evidence cannot answer:

1. **UI technology** — Does the user know the toolkit (Win32/WPF/Qt/Electron/Tauri/Flutter/Unity/custom)? If not, detect it from imports, resources, and windows.
2. **Accessibility** — Does the app expose an accessibility tree? If the user has ever used a screen reader or UI automation on it, that is useful evidence.
3. **Configuration** — Does the user know where settings live (file/registry/keychain/DB)? Is any value encrypted or machine-bound?
4. **Apply behavior** — Do settings apply live, on OK, or after restart? Is there a validation error surface?
5. **Events** — Which events matter (progress, toast, status change, file export, network response)? What latency is acceptable?
6. **Out of scope** — Which screens/features should be explicitly excluded? Write them into `out_of_scope` rather than leaving them ambiguous.

## Round 5 — Packaging

1. **Output directory** — Default `reverse-mcp/<target-slug>/` in the current workspace. Ask before writing outside it.
2. **Server name** — Stable, lowercase, hyphenated. This becomes the MCP server key.
3. **Docs language** — English, Chinese, or bilingual? Keep tool names/IDs in English.
4. **Tests** — Should tests run against the live app, a fixture, or both? Live tests need a disposable state.
5. **Handover** — One command to start, one snippet to register, one read-only tool to try first.

## Recommended defaults

Use these when the user has no preference, and say that you are applying them:

- Mode: observer → protocol → hook; patch only on an isolated copy with explicit consent.
- Write scope: read-only for the first milestone; settings-only next; destructive actions require per-call confirmation.
- Stack: `uv` + Python FastMCP if available; TypeScript for Electron/web; Rust only when it earns its build cost.
- Transport: stdio; loopback HTTP only for a shared bridge.
- Secrets: redact by default; never add a tool that returns credentials.
- Output: `reverse-mcp/<slug>/` with `analysis/`, `bridge/`, `server/` (tests inside the server project).
- Verification: one read, plus one safe write and/or one event if in scope, five failure cases.

## `analysis/DECISIONS.md` template

```markdown
# Reverse-MCP Decisions — <target>

## Authorization
- Owner/authorization:
- Environment:
- Excluded areas:
- Data handling:

## Target
- Name/version:
- Path:
- SHA-256:
- Process/attach model:
- OS/arch:
- UI toolkit:

## Outcomes
1.
2.
3.

## Mode
- Chosen: observer | protocol | hook | patch | hybrid
- Why:
- On-disk changes: none | copy only
- Write scope:
- Confirmation policy:
- Restart policy:

## Environment
- Probe file: analysis/environment.json
- Stack/framework:
- Transport:
- Client:
- Dependency policy:

## Scope
- In scope:
- Out of scope:

## Acceptance
- Read:
- Write:
- Event:
- Failure cases:

## Open questions
-
```
