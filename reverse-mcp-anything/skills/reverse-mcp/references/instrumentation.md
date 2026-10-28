# Instrumentation and Bridge

Choose the least invasive route that reaches the surface. Every route below ends at the same place: a **local bridge** that the MCP server can call with stable IDs.

## Route matrix

| Route | Binary on disk | Process changes | Best for | Main failure |
| --- | --- | --- | --- | --- |
| Observer | unchanged | none | Accessibility trees, CDP, PTY, logs, files, screenshots | Custom-rendered UI exposes nothing |
| Protocol | unchanged | none (or a proxy) | Existing HTTP/WS/JSON-RPC/named-pipe API | No endpoint, auth, TLS pinning |
| Hook | unchanged | injected code / function hooks | Internal state, decrypt routines, command dispatch | Anti-tamper, crashes, version drift |
| Patch | **copy only** | copied binary/resources | Hook blocked; deep behavior change required | Signing, integrity checks, updates |

Try Observer → Protocol → Hook. Patch requires a fresh, explicit decision from the user.

## Observer techniques

### Windows UI Automation

- Tool: `uiautomation` (Python), Inspect.exe, Accessibility Insights, or `System.Windows.Automation` (C#).
- Walk the tree from the top-level window; record `ControlType`, `AutomationId`, `Name`, `ClassName`, `BoundingRectangle`, `IsEnabled`, `IsOffscreen`, and supported patterns.
- Read: `ValuePattern`, `TextPattern`, `SelectionPattern`, `TablePattern`, `TogglePattern`, `RangeValuePattern`.
- Act: `InvokePattern`, `SelectionItemPattern`, `ValuePattern.SetValue`, `TogglePattern.Toggle`, `ExpandCollapsePattern`.
- Prefer `AutomationId` + control type. Names are localized; class names are toolkit-specific.

```python
import uiautomation as auto

win = auto.WindowControl(searchDepth=1, Name="Acme Notes")
status = win.StatusBarControl(AutomationId="StatusBar")
print(status.Name, status.BoundingRectangle)
```

UIA is COM/STA-sensitive. Run it on a dedicated thread with `pythoncom.CoInitialize()` if the bridge is async.

### macOS Accessibility

- Use `AXUIElementCreateApplication(pid)`, then `AXUIElementCopyAttributeValue` for `kAXChildrenAttribute`, `kAXTitleAttribute`, `kAXValueAttribute`, `kAXRoleAttribute`, `kAXIdentifierAttribute`.
- Act with `AXUIElementPerformAction` (`kAXPressAction`) or set `kAXValueAttribute`.
- Requires Accessibility permission for the bridge/MCP host. Check with `AXIsProcessTrustedWithOptions`.
- AppleScript/JXA is fine for simple menu/keyboard actions but is not a stable element API.

### Linux AT-SPI

- Ensure `QT_ACCESSIBILITY=1` for Qt and `GTK_MODULES=gail:atk-bridge`/`NO_AT_BRIDGE=0` where applicable.
- Use `pyatspi.Registry` or `dogtail`; inspect with Accerciser.
- X11 input tools (`xdotool`) work only on X11; Wayland needs `ydotool`/portal APIs and is often restricted.

### Electron and browsers (CDP)

- Launch the app with `--remote-debugging-port=9222` (or a random port). This does not modify the binary; it changes the launch arguments.
- Enumerate `http://127.0.0.1:9222/json`; connect with Playwright `connect_over_cdp`, `chrome-remote-interface`, or raw WebSocket.
- Read DOM text/values, `Accessibility.getFullAXTree`, `Runtime.evaluate` for app-exposed globals, `Network` for requests.
- Act with `DOM`/`Input.dispatchMouseEvent`/`Input.dispatchKeyEvent`, or call the page's own functions.
- For the Electron **main** process, use `--inspect` and the Node inspector; do not assume `require` is available in the renderer.
- If the app is already running without a debug port, relaunching under the observer is usually required. That is a process change, not a binary patch.

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]
    print(page.title(), page.locator("body").inner_text()[:500])
```

### CLI / TUI

- Spawn under a PTY (`pexpect`, `node-pty`, `portable-pty`), not a plain pipe; many TUIs change behavior without a TTY.
- Parse with a screen buffer (`pyte`) rather than regexing raw ANSI.
- Prefer app commands/flags/config over keystroke synthesis. If keystrokes are required, send them only when the expected prompt is visible.
- Record the exact terminal size; TUI layout changes with rows/columns.

### Screenshots and OCR

Use only when the tree/DOM/PTY has no semantic handles. Capture a bounded region, hash it, and mark the surface `brittle: true`. OCR text is an observation, not a stable ID; never make it the only way to invoke a destructive action.

## Protocol techniques

- **HTTP/WS** — inspect the app's own endpoints first. A local API is better than UI automation. If a proxy is needed, use mitmproxy/Charles with the user's consent; certificate pinning may block it.
- **JSON-RPC / gRPC** — reuse the schema; add a version check and a typed error mapping.
- **Named pipes (Windows)** — `CreateFile`/`ReadFile`/`WriteFile`, or `pywin32` `win32pipe`/`win32file`. Enumerate with `pip list`/PipeList tools; do not connect to pipes owned by other users.
- **Unix sockets** — `AF_UNIX` with `SOCK_STREAM`; set mode `0600`; use `$XDG_RUNTIME_DIR` or a private temp dir.
- **Electron IPC** — channel names are visible in the ASAR. Reaching `ipcMain` from outside usually needs the main-process inspector or a hook; a renderer CDP session can call preload-exposed APIs but not arbitrary main-process modules.

A protocol route is still a bridge. Normalize it to the JSON-RPC contract below so the MCP server does not depend on the app's wire format.

## Hook techniques

Hook only the target process, only the functions needed for the agreed outcomes. Keep a detach path and a watchdog.

### Frida (cross-platform, fastest iteration)

- Host: `frida` Python package or `frida-tools`.
- Attach: `frida.attach(pid)`; spawn: `frida.spawn(path, argv=...)`, then `resume(pid)`.
- Agent: `Interceptor.attach(Module.getExportByName(null, "CryptUnprotectData"), {...})`, `Module.findBaseAddress`, `Memory.scan`, `NativeFunction`.
- Expose a narrow RPC surface: `rpc.exports.snapshot()`, `rpc.exports.invoke(action, args)`. Do not expose `eval`.
- Frida is blocked by some hardened/anti-cheat targets. If injection is detected as a security violation, stop; do not escalate.

```javascript
// agent.js — observe a decrypt call without changing its behavior
const p = Module.getExportByName(null, "CryptUnprotectData");
Interceptor.attach(p, {
  onEnter(args) { this.blob = args[1]; },
  onLeave(ret) {
    if (ret.toInt32() !== 0) send({ type: "decrypt", ok: true });
  }
});
```

### Windows native

- **Detours** (Microsoft Research) or **MinHook** for inline/IAT hooks; build a DLL with a bridge thread and a C ABI.
- Inject with a launcher: `CreateProcess` suspended → `VirtualAllocEx`/`WriteProcessMemory`/`CreateRemoteThread` (or `QueueUserAPC`) → resume. This is sensitive to AV/EDR; use only on an authorized test machine.
- Prefer DLL proxying/sideloading for a patched **copy** over runtime injection when the app already loads a suitable DLL.
- Hook candidates: `CryptUnprotectData`/`CryptProtectData`, `RegQueryValueExW`, `CreateFileW`, `ReadFile`, `send`/`WSASend`, `DispatchMessageW`, window procedures, config parser functions.
- Do not use global `SetWindowsHookEx` or `AppInit_DLLs`; they affect other processes.

### Linux native

- `LD_PRELOAD` shim: resolve the real symbol with `dlsym(RTLD_NEXT, ...)`, log/forward, start a Unix-socket bridge from a constructor.
- Hook `open/openat/fopen`, `read`, `write`, crypto (`EVP_Decrypt*`), and app-specific symbols found via `nm`/`objdump`/Ghidra.
- `ptrace` may be restricted by `kernel.yama.ptrace_scope`; do not change host security settings without explicit approval.
- Frida works well for userspace apps; Flatpak/Snap sandboxes may block it.

```c
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>

static FILE *(*real_fopen)(const char *, const char *);
FILE *fopen(const char *path, const char *mode) {
    if (!real_fopen) real_fopen = dlsym(RTLD_NEXT, "fopen");
    fprintf(stderr, "[bridge] fopen %s\n", path);
    return real_fopen(path, mode);
}
```

### macOS

- Accessibility first. `DYLD_INSERT_LIBRARIES` is blocked by SIP/hardened runtime in many cases; do not disable SIP.
- Frida may work on non-hardened local apps. If the app is hardened/notarized, treat injection as unavailable and use Accessibility or a protocol.
- `osascript`/JXA can drive menus and simple controls; use AX for state reads.

### .NET

- **Harmony** patches managed methods in-process; inject a managed assembly via a startup hook or a small launcher. `DOTNET_STARTUP_HOOKS` only works when the app honors it at launch.
- **CLR profiling API / `ICorProfilerInfo`** can rewrite IL and inspect types; heavier, but robust for a dedicated build.
- **EventPipe** is observation-only and does not require injection; useful for logs/metrics.
- **UIA** is often enough for WPF/WinForms read paths; prefer it before managed hooking.

### JVM

- `-javaagent` via a launcher (`JAVA_TOOL_OPTIONS` is global; prefer an app-specific launcher) with a ByteBuddy agent.
- **JMX** for exposed MBeans; **JDI** for debugger-style attach; **JVMTI** for native agents.
- Java Access Bridge/AT-SPI for UI reads.

### Electron

- Renderer: CDP (`--remote-debugging-port`), DOM/AX tree, `Runtime.evaluate` for app globals.
- Main: Node inspector (`--inspect`), then evaluate in the main context. Treat this as a privileged surface; allowlist methods.
- Preload/ASAR injection is a patch, not an observer. If the app has `contextIsolation`, do not assume renderer code can reach Node.

### Qt / custom-rendered UI

- Set `QT_ACCESSIBILITY=1`; inspect with Accerciser/AT-SPI. Qt's accessibility can be incomplete for custom widgets.
- D-Bus may expose app actions; check `qdbus`.
- Frida can call `QMetaObject::invokeMethod` or hook signal/slot dispatch, but signatures are version-specific.
- Unity/Unreal/game engines often expose only a canvas. Use screenshots + input for observation, mark it brittle, and never automate competitive/anti-cheat contexts.

## Patch mode (copy only)

Use only after the user explicitly chooses it and confirms a disposable copy.

1. Copy the install tree to `work/<target>-patched/`; record hashes of the original and the copy.
2. Choose the smallest patch:
   - **DLL proxy/sideload** — replace a DLL the app already loads with a forwarder that also hosts the bridge.
   - **Import table patch** — LIEF (`lief`) to add/replace an import; keep the PE structurally valid.
   - **Resource/ASAR patch** — extract, edit, repack; preserve the original copy.
   - **Branch patch** — only for a local check that blocks the agreed automation; never for licence/DRM/anti-cheat.
3. Re-sign only the copy if the platform requires it; document that the signature is no longer the vendor's.
4. Launch the copy, run the verification matrix, and keep the original untouched.
5. Do not distribute the patched binary or commit it. It is a local test artifact.

Linux: `patchelf --add-needed ./libbridge.so ./copy` is an alternative to `LD_PRELOAD`.
macOS: `install_name_tool` changes the load path; hardened runtime may still reject the copy.
Electron: `npx asar extract app.asar app/`, edit, `npx asar pack app/ app.asar`; keep the original `app.asar` hash.

## Bridge protocol

Default: JSON-RPC 2.0 over loopback HTTP.

- Endpoint: `POST http://127.0.0.1:<port>/rpc`
- Auth: `Authorization: Bearer <token>`; token is 32 random bytes, stored in a file with mode `0600`.
- Bind: `127.0.0.1` only. Never `0.0.0.0`.
- Body: `{"jsonrpc":"2.0","id":1,"method":"surface.snapshot","params":{...}}`
- Response: `{"jsonrpc":"2.0","id":1,"result":{...}}` or `{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"...","data":{"code":"STALE_HANDLE"}}}`
- Limits: request ≤ 256 KiB; response ≤ 1 MiB; default timeout 10 s; event buffer 1,000; no unbounded arrays.
- Methods:

| Method | Params | Result | Side effect |
| --- | --- | --- | --- |
| `bridge.hello` | `{}` | `{protocol_version, target:{name,version,pid,sha256}, mode, capabilities}` | none |
| `bridge.health` | `{}` | `{ok, uptime_ms, queue_depth, target_alive}` | none |
| `surface.list` | `{kind?}` | `{surfaces:[...]}` | none |
| `surface.snapshot` | `{ids?, depth?}` | `{captured_at, values:{id:{...}}}` | none |
| `action.invoke` | `{action_id, args, confirm}` | `{ok, result, events?}` | yes |
| `config.get` | `{keys?, reveal_secrets?}` | `{values, sources}` | none |
| `config.set` | `{key, value, confirm}` | `{ok, applied, requires_restart}` | yes |
| `event.poll` | `{cursor?, timeout_ms?, limit?}` | `{events, next_cursor}` | none |
| `event.wait` | `{name, timeout_ms}` | `{event}` or timeout | none |

`confirm` must be checked in the bridge as well as the MCP layer. A client can call the bridge directly; do not rely on the model to be polite.

## Lifecycle

1. Start the bridge (or the launcher that starts the target + bridge).
2. Wait for `bridge.hello` with the expected target hash.
3. Run `scripts/check_bridge.py` and require a live `surface.snapshot`; this is the gate before server code.
4. Start the MCP server; it verifies `protocol_version` and target identity.
5. On target exit, the bridge marks `target_alive: false`; the MCP server returns `TARGET_NOT_RUNNING`.
6. On MCP shutdown, close the bridge only if this server owns it; otherwise leave it for the next client.
7. On hook detach, remove hooks in reverse order and join threads.

Use a watchdog: if the target is unresponsive for N seconds, stop issuing calls, detach, and report. Never let a stuck hook block the target's UI thread.

## Integrity and anti-tamper

- Hash the main executable and note child binaries/resources. Re-hash after the session.
- Hook mode changes memory; document that anti-tamper systems may flag it even though the file is unchanged.
- Patch mode changes the copy's bytes; the original hash must remain identical. Do not claim "undetectable".
- If the app uses anti-cheat, DRM, licence enforcement, or a protected kernel driver: stop. These are security controls, not obstacles to route around.
- Keep a rollback path: kill the bridge, restart the app, restore the config backup.
