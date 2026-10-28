#!/usr/bin/env python3
"""Read-only toolchain probe for Reverse-MCP-Anything.

Checks PATH, common version-manager bins, and default compiler/SDK install
roots. It never installs, upgrades, or modifies anything. Output is JSON so the
skill can choose a server stack from observed facts.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "uv": {"commands": ["uv"], "args": ["--version"]},
    "python": {"commands": ["python", "python3", "py"], "args": ["--version"]},
    "pip": {"commands": ["pip", "pip3"], "args": ["--version"]},
    "node": {"commands": ["node"], "args": ["--version"]},
    "npm": {"commands": ["npm"], "args": ["--version"]},
    "pnpm": {"commands": ["pnpm"], "args": ["--version"]},
    "yarn": {"commands": ["yarn"], "args": ["--version"]},
    "bun": {"commands": ["bun"], "args": ["--version"]},
    "deno": {"commands": ["deno"], "args": ["--version"]},
    "rustc": {"commands": ["rustc"], "args": ["--version"]},
    "cargo": {"commands": ["cargo"], "args": ["--version"]},
    "rustup": {"commands": ["rustup"], "args": ["--version"]},
    "go": {"commands": ["go"], "args": ["version"]},
    "dotnet": {"commands": ["dotnet"], "args": ["--version"]},
    "java": {"commands": ["java"], "args": ["-version"]},
    "javac": {"commands": ["javac"], "args": ["-version"]},
    "clang": {"commands": ["clang"], "args": ["--version"]},
    "gcc": {"commands": ["gcc"], "args": ["--version"]},
    "g++": {"commands": ["g++"], "args": ["--version"]},
    "cl": {"commands": ["cl"], "args": []},
    "cmake": {"commands": ["cmake"], "args": ["--version"]},
    "ninja": {"commands": ["ninja"], "args": ["--version"]},
    "make": {"commands": ["make"], "args": ["--version"]},
    "zig": {"commands": ["zig"], "args": ["version"]},
    "git": {"commands": ["git"], "args": ["--version"]},
    "frida": {"commands": ["frida"], "args": ["--version"]},
    "frida-ps": {"commands": ["frida-ps"], "args": ["--version"]},
    "objdump": {"commands": ["objdump"], "args": ["--version"]},
    "dumpbin": {"commands": ["dumpbin"], "args": []},
    "7z": {"commands": ["7z", "7za"], "args": []},
    "adb": {"commands": ["adb"], "args": ["version"]},
}


def expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def existing_dirs(paths: list[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(expand(raw))
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            result.append(path)
    return result


def default_roots() -> list[Path]:
    """Known install roots. Only existing directories are returned."""
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get(
            "ProgramFiles(x86)", r"C:\Program Files (x86)"
        )
        local = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        roaming = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        candidates = [
            str(home / ".cargo" / "bin"),
            str(home / ".rustup" / "toolchains"),
            str(home / ".local" / "bin"),
            str(home / ".dotnet"),
            str(home / ".bun" / "bin"),
            str(home / "scoop" / "shims"),
            str(Path(local) / "Programs" / "Python"),
            str(Path(local) / "Microsoft" / "WindowsApps"),
            str(Path(local) / "pnpm"),
            str(Path(roaming) / "npm"),
            str(Path(program_files) / "nodejs"),
            str(Path(program_files) / "dotnet"),
            str(Path(program_files) / "Java"),
            str(Path(program_files) / "LLVM"),
            str(Path(program_files) / "LLVM" / "bin"),
            str(Path(program_files) / "Microsoft Visual Studio" / "Installer"),
            str(Path(program_files_x86) / "Microsoft Visual Studio" / "Installer"),
            str(Path(program_files) / "Microsoft Visual Studio"),
            str(Path(program_data) / "chocolatey" / "bin"),
            r"C:\msys64\usr\bin",
            r"C:\msys64\mingw64\bin",
            str(Path(program_files) / "Git" / "cmd"),
        ]
    elif system == "Darwin":
        candidates = [
            str(home / ".cargo" / "bin"),
            str(home / ".local" / "bin"),
            str(home / ".pyenv" / "shims"),
            str(home / ".volta" / "bin"),
            str(home / ".bun" / "bin"),
            str(home / ".dotnet"),
            "/opt/homebrew/bin",
            "/opt/homebrew/opt/node/bin",
            "/usr/local/bin",
            "/usr/local/go/bin",
            "/Library/Java/JavaVirtualMachines",
            "/usr/local/opt/llvm/bin",
        ]
    else:
        candidates = [
            str(home / ".cargo" / "bin"),
            str(home / ".local" / "bin"),
            str(home / ".pyenv" / "shims"),
            str(home / ".volta" / "bin"),
            str(home / ".bun" / "bin"),
            str(home / ".dotnet"),
            "/usr/local/bin",
            "/usr/local/go/bin",
            "/usr/lib/jvm",
            "/usr/lib/llvm",
            "/snap/bin",
            "/opt/rust/bin",
        ]
    return existing_dirs(candidates)


def version_tool_globs(tool: str) -> list[str]:
    """Globs for tools hidden inside version-managed directories."""
    home = str(Path.home())
    if tool in {"python", "python3"}:
        return [
            f"{home}/.pyenv/versions/*/bin/python3",
            f"{home}/.pyenv/versions/*/bin/python",
            f"{home}/.local/share/uv/python/*/bin/python3",
            f"{home}/AppData/Local/Programs/Python/Python*/python.exe",
        ]
    if tool == "node":
        return [
            f"{home}/.nvm/versions/node/*/bin/node",
            f"{home}/.volta/bin/node",
            f"{home}/.fnm/node-versions/*/installation/bin/node",
            f"{home}/AppData/Roaming/nvm/*/node.exe",
        ]
    if tool in {"cargo", "rustc"}:
        return [
            f"{home}/.cargo/bin/{tool}",
            f"{home}/.cargo/bin/{tool}.exe",
            f"{home}/.rustup/toolchains/*/bin/{tool}",
            f"{home}/.rustup/toolchains/*/bin/{tool}.exe",
        ]
    if tool == "java":
        return [
            "/usr/lib/jvm/*/bin/java",
            f"{home}/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java",
        ]
    if tool == "clang":
        return [
            "/usr/lib/llvm-*/bin/clang",
            f"{home}/AppData/Local/Programs/LLVM/bin/clang.exe",
        ]
    return []


def run_version(
    path: Path, args: list[str], timeout: float = 5.0
) -> tuple[str | None, int | None]:
    """Run a version command. Returns (short output, exit code)."""
    cmd: list[str] = [str(path), *args]
    try:
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            creationflags=creationflags,
        )
        text = (
            completed.stdout.decode("utf-8", errors="replace")
            if completed.stdout
            else ""
        )
        line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        line = line.replace("\x00", "")[:240]
        if any(
            marker in line.lower()
            for marker in (
                "is not recognized",
                "could not be loaded",
                "command not found",
                "no such file",
            )
        ):
            return None, completed.returncode
        return (line or None), completed.returncode
    except (OSError, subprocess.SubprocessError):
        return None, None


def first_version_tuple(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(part) if part is not None else 0 for part in match.groups())


def dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def find_tool(
    name: str, spec: dict[str, Any], roots: list[Path], timeout: float = 5.0
) -> dict[str, Any]:
    candidates: list[Path] = []
    for command in spec["commands"]:
        which = shutil.which(command)
        if which:
            candidates.append(Path(which))
    for pattern in version_tool_globs(name):
        for match in glob.glob(expand(pattern)):
            path = Path(match)
            if path.is_file():
                candidates.append(path)
    for root in roots:
        for command in spec["commands"]:
            for suffix in ("", ".exe", ".cmd", ".bat"):
                path = root / f"{command}{suffix}"
                if path.is_file():
                    candidates.append(path)
    candidates = dedupe_paths(candidates)

    best: dict[str, Any] | None = None
    for path in candidates:
        output, code = run_version(path, spec["args"], timeout)
        item = {
            "available": True,
            "path": str(path),
            "version": output,
            "version_tuple": list(first_version_tuple(output) or []),
            "exit_code": code,
            "source": "default-root",
        }
        which = shutil.which(path.name)
        if which:
            try:
                if Path(which).resolve() == path.resolve():
                    item["source"] = "PATH"
            except OSError:
                pass
        if best is None or (item["version_tuple"] and not best["version_tuple"]):
            best = item
    if best is not None:
        return best
    return {
        "available": False,
        "path": None,
        "version": None,
        "version_tuple": [],
        "exit_code": None,
        "source": None,
    }


def at_least(tool: dict[str, Any], minimum: tuple[int, ...]) -> bool:
    version = tuple(tool.get("version_tuple") or [])
    if not version:
        return False
    padded = version + (0,) * (len(minimum) - len(version))
    return padded[: len(minimum)] >= minimum


def build_recommendations(tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    python_ok = tools["python"]["available"] and at_least(tools["python"], (3, 10))
    uv_ok = tools["uv"]["available"]
    node_ok = tools["node"]["available"] and at_least(tools["node"], (20,))
    rust_ok = (
        tools["cargo"]["available"]
        and tools["rustc"]["available"]
        and at_least(tools["rustc"], (1, 88))
    )
    pkg_manager = next(
        (name for name in ("pnpm", "npm", "yarn", "bun") if tools[name]["available"]),
        None,
    )

    options = {
        "python": {
            "available": python_ok and (uv_ok or tools["pip"]["available"]),
            "framework": "fastmcp",
            "reason": "uv + Python >= 3.10"
            if uv_ok and python_ok
            else "Python >= 3.10 with a package manager"
            if python_ok
            else "Python < 3.10 or missing",
        },
        "typescript": {
            "available": node_ok and pkg_manager is not None,
            "framework": "@modelcontextprotocol/sdk",
            "reason": f"Node >= 20 with {pkg_manager}"
            if node_ok and pkg_manager
            else "Node >= 20 with npm/pnpm is required",
        },
        "rust": {
            "available": rust_ok,
            "framework": "rmcp",
            "reason": "cargo + rustc >= 1.88"
            if rust_ok
            else "cargo + rustc >= 1.88 is required for rmcp",
        },
    }

    warnings: list[str] = []
    if tools["python"]["available"] and not at_least(tools["python"], (3, 10)):
        warnings.append(
            f"Python {tools['python']['version']} is below 3.10; FastMCP requires >= 3.10."
        )
    if tools["node"]["available"] and not at_least(tools["node"], (20,)):
        warnings.append(
            f"Node {tools['node']['version']} is below 20; the TypeScript SDK requires >= 20."
        )
    if tools["cargo"]["available"] and not tools["rustc"]["available"]:
        warnings.append(
            "cargo is present but rustc is missing; the Rust toolchain is incomplete."
        )
    if tools["rustc"]["available"] and not at_least(tools["rustc"], (1, 88)):
        warnings.append(
            "rustc is below 1.88; rmcp 3.x requires >= 1.88. fastmcp-rust 0.13 may require 1.100."
        )
    if tools["node"]["available"] and pkg_manager is None:
        warnings.append(
            "Node is present but no package manager (npm/pnpm/yarn/bun) was found on PATH."
        )
    for name, tool in tools.items():
        if tool.get("available") and not tool.get("version"):
            warnings.append(
                f"{name} exists at {tool.get('path')} but did not report a version; verify it manually."
            )

    preferred = None
    framework = None
    reason = "No viable stack found; install a toolchain or use an existing interpreter on the target."
    if options["python"]["available"]:
        preferred, framework, reason = "python", "fastmcp", options["python"]["reason"]
    elif options["typescript"]["available"]:
        preferred, framework, reason = (
            "typescript",
            "@modelcontextprotocol/sdk",
            options["typescript"]["reason"],
        )
    elif options["rust"]["available"]:
        preferred, framework, reason = "rust", "rmcp", options["rust"]["reason"]
    elif python_ok:
        preferred, framework, reason = (
            "python",
            "fastmcp",
            "Python >= 3.10; add uv or pip to install FastMCP.",
        )
    elif node_ok:
        preferred, framework, reason = (
            "typescript",
            "@modelcontextprotocol/sdk",
            "Node >= 20; add a package manager.",
        )
    elif tools["rustc"]["available"]:
        preferred, framework, reason = (
            "rust",
            "rmcp",
            "Rust present but cargo/version floor is not satisfied.",
        )

    if preferred is None:
        warnings.append(reason)

    return {
        "preferred": preferred,
        "framework": framework,
        "reason": reason,
        "options": options,
        "warnings": warnings,
    }


def collect_locations(roots: list[Path]) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    for root in roots:
        names: list[str] = []
        try:
            for entry in root.iterdir():
                if entry.name.startswith("."):
                    continue
                names.append(entry.name)
                if len(names) >= 40:
                    break
        except OSError:
            pass
        locations.append({"path": str(root), "exists": True, "entries": sorted(names)})
    return locations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe local toolchains without installing anything."
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Write JSON to this path (default: stdout)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON to stdout"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-version-command timeout in seconds",
    )
    args = parser.parse_args(argv)

    roots = default_roots()
    tools: dict[str, dict[str, Any]] = {}
    for name, spec in TOOL_SPECS.items():
        tools[name] = find_tool(name, spec, roots, args.timeout)

    recommendations = build_recommendations(tools)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "system": {
            "os": platform.system(),
            "platform": platform.platform(),
            "release": platform.release(),
            "arch": platform.machine(),
            "processor": platform.processor(),
            "python_runtime": sys.version.split()[0],
            "python_executable": sys.executable,
            "shell": os.environ.get("SHELL") or os.environ.get("COMSPEC") or "",
            "cwd": os.getcwd(),
            "is_wsl": "microsoft" in platform.release().lower(),
            "display": os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")
            or "",
        },
        "path": os.environ.get("PATH", "").split(os.pathsep),
        "tools": tools,
        "default_locations": collect_locations(roots),
        "warnings": recommendations.pop("warnings"),
        "recommendations": recommendations,
    }

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.json}")
        if not args.pretty:
            summary = ", ".join(
                f"{name}={tool['version'] or 'found'}"
                for name, tool in tools.items()
                if tool["available"]
            )
            print(f"Available: {summary or 'none'}")
            print(
                f"Preferred: {recommendations['preferred'] or 'none'} ({recommendations['reason']})"
            )
            for warning in result["warnings"]:
                print(f"WARN: {warning}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
