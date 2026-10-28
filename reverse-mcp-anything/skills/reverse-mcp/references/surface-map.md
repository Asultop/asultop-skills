# Surface Map

`analysis/surface.json` is the contract between reverse engineering and the MCP server. If it is vague, the server becomes a pile of coordinate clicks; if it is precise, the server survives UI changes and can be tested.

Validate against [../assets/surface.schema.json](../assets/surface.schema.json) and run:

```bash
python scripts/validate_surface.py analysis/surface.json
```

## What "everything" means

Cover every element, config key, event, and action **inside the agreed scope**. Anything excluded goes into `out_of_scope` with a reason. Silent omissions are the failure mode: a later agent assumes a feature does not exist because it is absent from the map.

Inventory by user journey, not by widget tree. For each journey:

1. Starting screen and visible state.
2. Inputs the user can change.
3. Commands the user can invoke.
4. Feedback the app shows (status, toast, dialog, navigation).
5. Persistence (what changes on disk/registry/keychain).
6. Failure states (validation error, offline, permission denied).

## Surface fields

| Field | Meaning |
| --- | --- |
| `id` | Stable, dot-namespaced identifier, e.g. `main.status`, `settings.theme`. Never an array index. |
| `kind` | `window`, `menu`, `menu_item`, `toolbar`, `tab`, `list`, `tree`, `table`, `text`, `input`, `button`, `checkbox`, `radio`, `combo`, `slider`, `dialog`, `status`, `notification`, `canvas`, `terminal`, `webview`, `custom`. |
| `label` | Human-visible label, localized if that is what the user sees. Keep the stable ID separate. |
| `parent_id` | Containment, when it clarifies the tree. |
| `selector` | How to reach it; see priority below. |
| `reads` | Fields the surface exposes: `name`, `type`, `description`. These are the "current displayed information". |
| `actions` | IDs of top-level actions valid on this surface. |
| `visible_when` | Preconditions (dialog open, tab active, row selected). |
| `risk` | `read`, `write`, `destructive`, `external`. |
| `confidence` | `observed`, `inferred`, `unknown`. |
| `observed` | A sample of the current values captured during analysis; useful for tests, not authoritative. |
| `evidence` | Evidence Ledger IDs. |

## Selector priority

Use the most stable handle that reaches the element:

1. **`native_command`** — command ID, action name, `WM_COMMAND` ID, `QAction` object name, WPF `ICommand`.
2. **`ipc_method`** — HTTP/WS/JSON-RPC/named-pipe method and payload path.
3. **`accessibility_id`** — UIA `AutomationId`, AX identifier, AT-SPI accessible ID.
4. **`accessibility_name`** — accessible name/role, ideally with a stable parent path.
5. **`object_path`** — toolkit object path or DOM path (`window/dialog/...`).
6. **`dom_selector`** — CSS selector for Electron/web.
7. **`role_name`** — role + visible label; brittle under localization.
8. **`pty_pattern`** — expected text/escape sequence in a terminal.
9. **`coordinates`** — relative x/y; last resort, always marked `brittle: true`.

A selector may include a `fallback` chain. If the primary fails, the bridge should report `STALE_HANDLE` with the attempted chain, not silently click somewhere else.

## Configuration entries

Map both the **store** and the **UI path**:

- `key` — logical key (`ui.theme`), not just a file offset.
- `source` — exact path/registry key/DB table/env var; one entry per source.
- `precedence` — lower number wins or document the rule; test it.
- `type` / `default` / `current` — enough to build a typed schema.
- `writable` — whether the app supports changing it.
- `apply` — `live`, `restart`, `relogin`, `unknown`.
- `validation` — enum, range, regex, or free-form rule.
- `encryption` — `none`, `dpapi`, `keychain`, `libsecret`, `aes`, `custom`, `unknown`.
- `selector` — the settings control that edits it, when a UI path exists.
- `risk` — writing a config can be `write` or `destructive` (resetting state).

Prefer, in order: the app's own setter/command → its settings UI → direct store write with backup and validation. Direct file writes can corrupt schemas or race a live process; use them last.

## Events

Record:

- `name` — stable event name (`export.completed`), not a UI string.
- `source` — `ui`, `ipc`, `network`, `file`, `log`, `timer`, `hook`.
- `trigger` — what causes it, in one sentence.
- `payload` — fields and types.
- `rate` — `low`, `medium`, `high`; high-rate events need coalescing.
- `observed` — true only if a live event was captured; otherwise `false` with `confidence: inferred`.

## Actions

Record:

- `surface_id` — where the action is valid.
- `verb` — `click`, `invoke`, `set`, `open`, `save`, `export`, `delete`, `send`, etc.
- `args` — typed fields, required/optional.
- `side_effects` — files, network, external parties, state.
- `risk` — drives confirmation.
- `confirmation` — `none`, `always`, `destructive`.
- `idempotent` — whether repeating is safe.
- `timeout_ms` — sensible upper bound.

## Example

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-28T10:00:00+08:00",
  "target": {
    "name": "Acme Notes",
    "version": "4.2.1",
    "path": "C:/Program Files/Acme/Notes/acme.exe",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "platform": "windows",
    "arch": "x86_64",
    "ui_framework": "wpf",
    "runtime": "dotnet"
  },
  "mode": "observer",
  "surfaces": [
    {
      "id": "main.status",
      "kind": "status",
      "label": "Status bar",
      "selector": {"strategy": "accessibility_id", "value": "StatusBar"},
      "reads": [{"name": "text", "type": "string", "description": "Current status message"}],
      "actions": [],
      "visible_when": "main window is open",
      "risk": "read",
      "confidence": "observed",
      "evidence": ["E-001"]
    },
    {
      "id": "settings.theme",
      "kind": "combo",
      "label": "Theme",
      "selector": {"strategy": "accessibility_id", "value": "ThemeCombo"},
      "reads": [{"name": "value", "type": "enum", "description": "light, dark, system"}],
      "actions": ["action.set_theme"],
      "visible_when": "Settings dialog is open",
      "risk": "write",
      "confidence": "observed",
      "evidence": ["E-002"]
    }
  ],
  "config": [
    {
      "id": "config.theme",
      "key": "ui.theme",
      "type": "enum",
      "default": "system",
      "current": "dark",
      "source": "%APPDATA%/Acme/settings.json",
      "precedence": 2,
      "writable": true,
      "apply": "live",
      "validation": {"enum": ["light", "dark", "system"]},
      "encryption": "none",
      "risk": "write",
      "selector": "settings.theme",
      "evidence": ["E-002"],
      "confidence": "observed"
    }
  ],
  "events": [
    {
      "id": "event.export_done",
      "name": "export.completed",
      "source": "file",
      "trigger": "Export writes the target file and closes the progress dialog",
      "payload": [{"name": "path", "type": "string"}],
      "rate": "low",
      "observed": false,
      "evidence": ["E-003"],
      "confidence": "inferred"
    }
  ],
  "actions": [
    {
      "id": "action.set_theme",
      "surface_id": "settings.theme",
      "verb": "set",
      "args": [{"name": "value", "type": "enum", "required": true}],
      "side_effects": ["updates settings.json", "repaints UI"],
      "risk": "write",
      "confirmation": "none",
      "idempotent": true,
      "timeout_ms": 5000,
      "evidence": ["E-002"],
      "confidence": "observed"
    }
  ],
  "out_of_scope": [
    {"item": "cloud sync", "reason": "requires a remote account and is outside the local automation scope"}
  ],
  "evidence": [
    {"id": "E-001", "type": "runtime", "summary": "UIA tree exposes StatusBar with text", "source": "UIA inspection 2026-10-28"},
    {"id": "E-002", "type": "static", "summary": "settings.json contains ui.theme; combo writes it live", "source": "settings.json + UIA"},
    {"id": "E-003", "type": "inferred", "summary": "Export completion detected by file appearance; no event captured", "source": "code path only"}
  ]
}
```

## Common failures

- **Coordinates as the primary selector.** They break on DPI, theme, localization, and window size.
- **Localized labels as IDs.** Use the label for humans; use AutomationId/command for code.
- **One surface per screen.** A dialog's fields are separate surfaces; otherwise tools cannot target them.
- **Config key without source.** "Theme is in settings" is not actionable; record the exact file/key and precedence.
- **Event claimed but never observed.** Mark `confidence: inferred` and `observed: false`; do not build a `wait_for_event` tool on a guess without a fallback poll.
- **Missing `out_of_scope`.** An empty list is a claim of completeness; make it deliberate.
