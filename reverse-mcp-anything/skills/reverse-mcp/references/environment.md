# Runtime Probe and Stack Selection

The probe answers one question: **which server stack can be built and run on this machine without guesswork?** It does not install anything, does not modify the target, and does not decide the mode.

## Run it

```bash
python scripts/probe_environment.py --json analysis/environment.json
```

The script checks:

- OS, architecture, shell, Python/virtualenv, and whether WSL/container/display indicators are present.
- `PATH` for `uv`, Python, pip, Node/npm/pnpm/yarn/bun/deno, Rust/cargo/rustup, Go, .NET, Java, C/C++ compilers, CMake/Ninja/Make/Zig, Git, Frida, and common binary tools.
- Default install roots for version managers and SDK installers. It records both existing roots and executables found there.
- Version numbers with a short timeout. A tool that hangs is reported as `version: null`, not treated as absent.

It writes JSON with `system`, `tools`, `default_locations`, `warnings`, and `recommendations`. Treat `available: false` as "not found by this probe", not "impossible"; a tool outside `PATH` may still exist in a non-standard directory.

If Python is not available, reproduce the same check with the shell:

```powershell
Get-Command uv,python,node,npm,pnpm,cargo,rustc,dotnet,java,clang,gcc,cmake -ErrorAction SilentlyContinue |
  Select-Object Name,Source,Version
```

```bash
for tool in uv python3 node npm pnpm cargo rustc dotnet java clang gcc cmake; do
  command -v "$tool" && "$tool" --version 2>&1 | head -n 1
done
```

## How to read the result

- `source: "PATH"` — resolved from the process environment. This is what the MCP client will inherit when it launches the server.
- `source: "default-root"` — found in a known install location but not on `PATH`. Record the absolute path; the launch command may need it.
- `version: null` — the executable exists but did not answer a version probe. Try it manually before selecting it.
- `warnings` — version floors or missing companions (for example, `node` without a package manager, `cargo` without `rustc`).
- `recommendations.preferred` — a heuristic, not a decision. The user still chooses.

## Default roots the probe checks

| Platform | Common roots |
| --- | --- |
| Windows | `%USERPROFILE%\.cargo\bin`, `%USERPROFILE%\.rustup`, `%LOCALAPPDATA%\Programs\Python`, `%LOCALAPPDATA%\Microsoft\WindowsApps`, `%ProgramFiles%\nodejs`, `%APPDATA%\npm`, `%LOCALAPPDATA%\pnpm`, `%USERPROFILE%\.bun\bin`, `%ProgramFiles%\dotnet`, `%ProgramFiles%\Java`, `%ProgramFiles%\LLVM`, `%ProgramFiles%\Microsoft Visual Studio`, `C:\msys64\usr\bin`, Scoop/Chocolatey shims |
| macOS | `~/.cargo/bin`, `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`, `~/.nvm/versions/node/*/bin`, `~/.pyenv/shims`, `~/.volta/bin`, `~/.bun/bin`, `/Library/Java/JavaVirtualMachines/*/Contents/Home/bin`, `/usr/local/go/bin`, `~/.dotnet` |
| Linux | `~/.cargo/bin`, `~/.local/bin`, `~/.nvm/versions/node/*/bin`, `~/.pyenv/shims`, `~/.volta/bin`, `~/.bun/bin`, `/usr/local/bin`, `/usr/local/go/bin`, `/usr/lib/jvm/*/bin`, `~/.dotnet`, `/snap/bin` |

## Stack matrix

| Target / constraint | First choice | Why | Alternatives |
| --- | --- | --- | --- |
| Windows Win32/WPF/UWP/Qt GUI | Python + `uiautomation`/`comtypes`/`pywin32` | Mature UI Automation bindings; fast iteration | C# `UIAutomationClient`; Rust + `windows` crate |
| macOS native GUI | Python + PyObjC, or Swift | Direct Accessibility API access | AppleScript/JXA for simple cases |
| Linux GTK/Qt GUI | Python + AT-SPI (`pyatspi`, `python3-gi`) | Native accessibility bus | `dogtail`, D-Bus |
| Electron / Chromium app | TypeScript | CDP, DOM, IPC and async are natural | Python + Playwright/CDP |
| Web app in a browser | TypeScript | Playwright/CDP ecosystem | Python + Playwright |
| .NET desktop | C# + UI Automation, or Harmony hook | Same runtime, typed interop | Python UIA for read-only |
| Java desktop | Java/Kotlin + JVMTI/JMX/JNA | Same runtime, agent APIs | Python UIA for read-only |
| Native C/C++ with a C ABI | Rust or C++ bridge + Rust/Python MCP | Safe FFI and a single binary | Python `ctypes` |
| CLI / TUI | Python (`pexpect`, `pyte`) | PTY and screen-buffer handling | TypeScript `node-pty` |
| Hook-heavy, version-fragile target | Python + Frida | Fastest hook iteration and scripting | C++ + Detours/MinHook |
| Single-binary, no runtime dependency | Rust + `rmcp` | One executable, no Python/Node | Go + `mcp-go` |

Do not select a stack solely because it is installed. Match the **target's** UI/runtime and the bridge's language.

## Framework choices

As of late 2026, verify the installed version before writing code; APIs move.

### Python — FastMCP

- Package: `fastmcp` (PrefectHQ), currently 4.x; Python ≥ 3.10.
- Strengths: decorator tools, resources/prompts, typed schemas, in-memory test client, auth/proxy features.
- Install:

```bash
uv init --app reverse-mcp-server
cd reverse-mcp-server
uv add fastmcp
uv run python -c "import fastmcp; print(fastmcp.__version__)"
```

- Without `uv`: `python -m venv .venv`, activate, `python -m pip install fastmcp`.
- Official SDK fallback: `pip install "mcp[cli]"` and its `FastMCP`; use when the user wants the smallest dependency surface.

### TypeScript — FastMCP TS or official SDK

- Official FastMCP counterpart: `@prefecthq/fastmcp-ts` (see the PrefectHQ FastMCP README). It mirrors the Python framework's tools/resources/prompts model.
- Official MCP SDK: `@modelcontextprotocol/sdk` with `McpServer`, `StdioServerTransport`, and `registerTool`. This is the most conservative choice for a generated server.
- Node ≥ 20.

```bash
pnpm init
pnpm add @modelcontextprotocol/sdk zod
pnpm add -D typescript tsx vitest @types/node
```

If the user prefers FastMCP TS:

```bash
pnpm add @prefecthq/fastmcp-ts zod
```

### Rust — rmcp or fastmcp-rust

- `rmcp` is the official Rust SDK; 3.x. `cargo add rmcp --features server,transport-io,macros,schemars`.
- `fastmcp-rust` is a higher-level framework; 0.13.x currently advertises Rust 1.100. Do not choose it on an older toolchain; `rmcp` 3.8 requires Rust 1.88.
- Rust is the right choice when the bridge is native, when distribution as one binary matters, or when the user already has a Rust codebase. It is the wrong choice when the UI automation libraries only exist in Python.

```bash
cargo new --bin reverse-mcp-server
cd reverse-mcp-server
cargo add rmcp --features server,transport-io,macros,schemars
cargo add tokio --features macros,rt-multi-thread,io-std,signal
cargo add serde --features derive
cargo add serde_json anyhow tracing
cargo add schemars
cargo add tracing-subscriber --features env-filter
cargo add reqwest --no-default-features --features json
```

### Go / other

`mcp-go` is a reasonable fallback for a small server or an existing Go bridge. EasyMCP-style lightweight wrappers are acceptable for a handful of tools, but prefer a maintained SDK with schema validation and a test client.

## Platform libraries by job

| Job | Python | TypeScript | Rust |
| --- | --- | --- | --- |
| Windows UIA | `uiautomation`, `comtypes`, `pywin32` | `@nut-tree-fork/nut-js` (input only) | `windows` crate (UIA COM) |
| macOS AX | `pyobjc-framework-ApplicationServices` | `node-mac-permissions`? (limited) | `core-foundation` + AX FFI |
| Linux AT-SPI | `pyatspi`, `python3-gi` | limited | `atspi` crate / D-Bus |
| Browser/Electron | `playwright`, `websocket-client` | `playwright`, `chrome-remote-interface` | `chromiumoxide` |
| PTY/TUI | `pexpect`, `pyte` | `node-pty` | `portable-pty` |
| Hooking | `frida` | `frida` bindings | `frida-gum` / native |
| HTTP bridge | `urllib`, `http.server` | `fetch`, `node:http` | `reqwest`, `axum` |
| Named pipe | `pywin32` | `node:net` | `windows` / `interprocess` |

## Transport choice

- **stdio** — default. One MCP client owns the server process. Simplest auth model: the bridge token is the only secret.
- **Loopback HTTP** — use when several clients share one long-lived bridge, or when the bridge must survive an MCP client restart. Bind `127.0.0.1`, use a random bearer token, and never expose it on `0.0.0.0`.
- **Named pipe / Unix socket** — cheaper local IPC and better OS-level access control, at the cost of platform-specific code. Use it when the bridge is native or security-sensitive.

## Installing missing tools

Only after the user approves. Prefer the project's existing package manager and pin versions.

- `uv`: `winget install astral-sh.uv` (Windows), `brew install uv` (macOS), or the official installer (verify the URL before piping to a shell).
- Node: `fnm`/`volta` or the official installer; do not silently switch the global Node version.
- Rust: `rustup`; `rustup default stable`.
- Windows C++ build tools: Visual Studio Build Tools with the "Desktop development with C++" workload.
- Frida: `uv add frida` or `pip install frida-tools` in a dedicated venv.

If no viable toolchain exists and installation is not allowed, stop and report the blocker with the exact missing tool and the command that would fix it. A pure-Python server still needs Python; a Rust server still needs cargo.
