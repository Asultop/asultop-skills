# REA Analysis Playbook

Load `reverse-engineer-anything` and follow its routing. This file is the Reverse-MCP-specific question set, not a replacement for REA's target guides. Use REA Evidence IDs wherever the connected server provides them; if it does not, keep the complete inline evidence in `analysis/REPORT.md` and mark the source.

## Target identity first

Record before analysis:

- Display name, executable path, version, installer/product ID, SHA-256 of the main executable.
- Process name(s), child processes, architecture, signing status, install root, user-data root.
- Launch model: shortcut arguments, working directory, environment variables, single-instance mutex, service/daemon, updater.
- Whether the process is currently running; if so, PID and command line.

Do not let a version mismatch contaminate the map. If the installed version differs from the analyzed artifact, stop and re-identify.

## Route by artifact

| Target | First REA route | Focus |
| --- | --- | --- |
| Native PE/ELF/Mach-O | `open_binary` → `binary_overview` / imports / strings / xrefs / pseudocode | UI toolkit, config parsers, crypto imports, command dispatch, IPC names |
| ASAR or extracted Electron tree | `analyze_javascript_application` | `main`/`preload`/renderer split, IPC channel names, settings schema, feature flags |
| Packaged Electron app | archive/package inventory, then ASAR extraction | `app.asar`, `resources`, `package.json`, `electron-builder` config |
| .NET assembly | `inspect_managed_artifact` or managed decompiler | WPF/WinForms, settings providers, DPAPI, command bindings |
| Android APK | `inspect_android_package` + JADX | Activities, preferences, Room/SQLite, accessibility, intents |
| Java desktop | class/JAR analysis + JVMTI/JMX inspection | Swing/JavaFX, preferences, JMX beans, agent hooks |
| Browser/web app | `list_browser_targets` / CDP | DOM, accessibility tree, localStorage/IndexedDB, network APIs |
| TUI/CLI | strings/resources + PTY capture + `--help` | prompts, key bindings, config files, exit codes |
| Firmware/embedded | REA firmware route, then extraction | web UI, config partitions, crypto keys (only with authorization) |

For a first pass, start with the smallest overview. Then follow one user outcome end-to-end: entry point → state read → command → result. Do not inventory the whole binary before proving one path.

## The eight questions

### 1. Launch, attach, and single-instance

- Is there a mutex/named object/lock file? Does a second instance forward arguments to the first?
- Does the app accept CLI flags, deep links, `--remote-debugging-port`, `--inspect`, or a plugin directory?
- Can it be launched under a debugger/injector without tripping a check? Is it elevated?
- Does it spawn a broker/service that owns the real state?

This determines attach-vs-spawn and whether an observer can connect at all.

### 2. UI toolkit and accessibility

Fingerprint from imports, resources, and window classes:

- Win32 common controls, MFC, WPF (`PresentationFramework`), WinForms (`System.Windows.Forms`), UWP/XAML (`Windows.UI.Xaml`), Qt (`Qt5Core.dll`, `libQt5*`), GTK (`libgtk-*`), Electron/Chromium (`app.asar`, `chrome_elf.dll`, `resources.pak`), Tauri (`WebView2`, `tauri`), Flutter (`flutter_windows.dll`), Unity (`UnityPlayer.dll`), Unreal (`UE4Game`/`UE5`), Java (`jvm.dll`), .NET (`mscorlib`/`System.Private.CoreLib`).
- Does the process expose an accessibility tree? Check with UIA Inspect, Accessibility Inspector, or `AT-SPI` browser.
- Are controls custom-rendered (canvas/game/Chromium surface) with no child elements? Then the tree may only expose a single pane.

This decides whether Observer mode can carry the read path or whether a hook/protocol is required.

### 3. Human-visible elements and current values

Build the inventory from the **user's** point of view:

- Windows/dialogs: title, modal state, buttons, default button, close behavior.
- Menus/toolbars/ribbons: item labels, shortcuts, checked/disabled state, submenus.
- Tabs/panes: active tab, visibility, splitter state.
- Lists/trees/tables: columns, row identity, selected row, sort order, cell values, virtualization.
- Text/status: labels, status bar, progress, counters, timestamps, validation messages, tooltips.
- Notifications: toasts, banners, modal alerts, sound-only cues.
- Webviews: DOM text, input values, disabled state, ARIA roles.
- Canvas/custom: screenshot region + OCR only as a fallback, with a brittle marker.

For each element record what is currently displayed and what changes it. "The current value" is a read field, not a separate screenshot.

### 4. Commands, IPC, and input events

Find the semantic operation behind the UI:

- Command IDs, action names, menu resource IDs, `WM_COMMAND` handlers, `QAction` names, WPF `ICommand`, Electron `ipcMain.handle` channels.
- Local HTTP/WS/JSON-RPC/named-pipe endpoints; protocol framing; auth tokens; version negotiation.
- Keyboard shortcuts and accelerators; default button behavior; focus traversal.
- Drag/drop, context menus, double-click, inline edit commit, table selection.
- Timers, polling, background workers, file watchers that produce events.

Prefer the command/IPC method over synthesizing a click. A click at coordinates is a last-resort selector, not an API.

### 5. Configuration sources and precedence

Look for all of these, then determine which wins:

- CLI arguments, environment variables, portable `.ini`/`.toml`/`.yaml`/`.json` next to the executable.
- Per-user config: `%APPDATA%`, `%LOCALAPPDATA%`, `~/.config`, `~/Library/Application Support`, registry (`HKCU`/`HKLM`), plist, keychain.
- Per-machine config, installer defaults, group policy, MDM profiles.
- Embedded defaults in the binary/resources; remote/tenant config; feature flags.
- Databases: SQLite, LevelDB, IndexedDB, LiteDB, ESE; caches that look like config but are not authoritative.
- Secrets: DPAPI blobs, Keychain items, libsecret, credential manager, encrypted values in a JSON/DB column.

For each key record: type, default, current, source path/key, precedence, writable, validation, apply mode, encryption. Test precedence by changing a low-priority source and observing which value the app actually uses.

### 6. Encryption and decryption

Search imports, strings, and constants for:

- Windows: `CryptProtectData`, `CryptUnprotectData`, `BCrypt*`, `NCrypt*`, DPAPI-NG, `CryptStringToBinary`.
- macOS: `SecItemCopyMatching`, `SecKeyCreateDecryptedData`, Keychain access.
- Linux: `libsecret`, `gnome-keyring`, `kwallet`, OpenSSL `EVP_*`.
- Cross-platform: AES-GCM/CBC, ChaCha20-Poly1305, RSA, PBKDF2, scrypt, Argon2, bcrypt, Fernet, Rijndael, XOR, base64 wrappers, custom byte shuffles.
- Key material: embedded constants, machine GUID + user SID derivation, remote key service, OS keystore, licence file.

Preferred strategy: **call the app's own decrypt/encrypt routine at runtime** through the bridge. Reimplementing crypto is slower and easy to get wrong. If the routine is reachable, expose only the specific config values the user asked for — not a generic "decrypt any blob" tool.

If the key is remote or the routine is unreachable, mark those keys read-only/out of scope. Do not guess plaintext.

### 7. State model and invariants

- What is the authoritative in-memory state? Which object owns it?
- What is derived/cached, and when is it refreshed?
- What must be true before a command is valid (selection, login, modal closed, file loaded)?
- Which operations are idempotent? Which append/duplicate/send?
- What does the UI do after a mutation: refresh, toast, navigate, close dialog?
- How does the app behave when the target is busy, offline, or showing a modal?

Encode preconditions in the tool layer; do not let the model discover them by crashing the app.

### 8. Instrumentation blockers

- Code signing, hardened runtime, notarization, integrity hashes, self-check threads.
- Anti-debug/anti-attach, anti-cheat, packers, obfuscation, control-flow integrity.
- Elevation/UAC, AppContainer, sandbox, SELinux/AppArmor, SIP.
- Single-instance mutex, watchdog, crash reporter, updater that replaces binaries.
- Multi-user/session boundaries; RDP/console session differences.

If a blocker is a security control (anti-cheat, DRM, licence), stop and report. Do not treat "bypass the check" as an engineering task.

## Evidence Ledger

Every claim in `analysis/REPORT.md` gets a row:

| ID | Claim | Evidence | Type | Confidence | Unknowns |
| --- | --- | --- | --- | --- | --- |
| E-001 | App uses Qt 5.15 and exposes QAccessible | `Qt5Core.dll` import + accessibility tree | static + runtime | high | custom canvas children |
| E-002 | `settings.json` is DPAPI-encrypted | `CryptUnprotectData` xref + blob header | static | high | key scope (user/machine) |
| E-003 | Save button commits via `ipcMain` channel `doc:save` | ASAR source + CDP event | static + runtime | high | error path |

Rules:

- `static` means read from an artifact; `runtime` means observed in a live process; `inferred` is a hypothesis, not evidence.
- A negative search is bounded: record the search boundary ("no `CryptProtectData` import in the main PE; plugins not searched").
- Do not cite a filename as proof of behavior. Cite the code path or the observed event.
- Preserve raw evidence (hash, offset, Evidence ID, screenshot path, log excerpt) in the report or a sidecar.

## Report skeleton

Use [../assets/report-template.md](../assets/report-template.md). Keep it skim-friendly: verdict, target identity, mode decision, eight answers, surface/config/event coverage, risks, unknowns.
