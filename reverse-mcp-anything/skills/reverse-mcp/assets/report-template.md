# Reverse-MCP Analysis — <Target>

> Status: draft | complete
> Version analyzed: <version> — SHA-256 `<hash>`
> Mode: observer | protocol | hook | patch | hybrid
> Owner/authorization: <who authorized this work; local-only scope>

## Verdict

One paragraph: what the MCP exposes, what it deliberately does not, and the biggest residual risk.

## Target identity

| Field | Value |
| --- | --- |
| Name | |
| Version | |
| Executable | |
| SHA-256 | |
| Platform / arch | |
| UI framework | |
| Runtime | |
| Install root | |
| User data root | |
| Launch model | attach / spawn / service |
| Process(es) | |

## Mode decision

- Chosen mode:
- Why this is the least invasive route that reaches the required surfaces:
- On-disk changes: none / copy only (`work/<copy>`)
- Process changes:
- Original hash after session:
- Copy hash (patch only):

## The eight answers

### 1. Launch, attach, single-instance

### 2. UI toolkit and accessibility

### 3. Human-visible elements and current values

### 4. Commands, IPC, and input events

### 5. Configuration sources and precedence

### 6. Encryption and decryption

### 7. State model and invariants

### 8. Instrumentation blockers

## Evidence ledger

| ID | Claim | Evidence | Type | Confidence | Unknowns |
| --- | --- | --- | --- | --- | --- |
| E-001 | | | static / runtime / inferred / non-REA | high / medium / low | |
| E-002 | | | | | |

## Coverage matrix

| Area | Covered | Evidence | Notes |
| --- | --- | --- | --- |
| Main window/status | | | |
| Menus/commands | | | |
| Settings dialog | | | |
| Config store | | | |
| Events | | | |
| Out of scope | | | |

## Bridge design

- Transport:
- Endpoint/token handling:
- Methods:
- Lifecycle:
- Watchdog/detach:
- Limits:

## MCP tool surface

| Tool | Kind | Side effects | Confirmation | Evidence |
| --- | --- | --- | --- | --- |
| app_status | read | none | n/a | |
| list_surfaces | read | none | n/a | |
| get_snapshot | read | none | n/a | |
| get_config | read | none | n/a | |
| set_config | write | | always | |
| invoke_action | write | | always | |
| wait_for_event | read | none | n/a | |

## Verification results

| Test | Result | Evidence |
| --- | --- | --- |
| Build/types | | |
| Surface validator | | |
| Read-only live | | |
| Mutation + confirmation | | |
| Event observation | | |
| Failure drills | | |
| Binary hash unchanged | | |
| Repeatability | | |

## Residual unknowns

- Unknown:
  - Search boundary:
  - Why it matters:
  - Suggested next probe:

## Handover

- Start command:
- Client registration:
- First read-only call:
- Known limitations:
- Files that must not be committed (tokens, patched binaries, captures):
