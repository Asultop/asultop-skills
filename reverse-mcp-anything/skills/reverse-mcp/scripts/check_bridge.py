#!/usr/bin/env python3
"""Check a live Reverse-MCP bridge before building the MCP server.

Calls `bridge.hello`, optionally verifies the target SHA-256, then calls
`surface.snapshot` and checks that the requested surface IDs came back. Read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class CheckError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


def read_token(token: str | None, token_file: str | None) -> str:
    if token:
        return token
    env = os.environ.get("REVERSE_MCP_TOKEN")
    if env:
        return env
    path = Path(
        token_file
        or os.environ.get("REVERSE_MCP_TOKEN_FILE", "~/.reverse-mcp/token")
    ).expanduser()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def rpc(url: str, method: str, params: dict[str, Any], token: str, timeout: float) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{url.rstrip('/')}/rpc",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    except urllib.error.URLError as exc:
        raise CheckError(
            "BRIDGE_UNAVAILABLE",
            f"cannot reach {url}: {exc.reason}",
            {"url": url},
        ) from exc

    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckError(
            "BRIDGE_PROTOCOL_ERROR",
            f"bridge returned non-JSON (HTTP {status})",
            {"status": status},
        ) from exc

    if isinstance(data, dict) and data.get("error"):
        error = data["error"] or {}
        detail = error.get("data") if isinstance(error, dict) else None
        detail = detail if isinstance(detail, dict) else {}
        raise CheckError(
            str(detail.get("code") or "BRIDGE_ERROR"),
            str(error.get("message") or "bridge error"),
            detail,
        )
    if status >= 400:
        raise CheckError(
            "BRIDGE_HTTP_ERROR",
            f"bridge returned HTTP {status}",
            {"status": status},
        )
    if not isinstance(data, dict):
        raise CheckError("BRIDGE_PROTOCOL_ERROR", "bridge response is not an object")
    return data.get("result")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a live Reverse-MCP bridge (read-only).")
    parser.add_argument(
        "--url",
        default=os.environ.get("REVERSE_MCP_BRIDGE", "http://127.0.0.1:8765"),
        help="Bridge base URL (default: REVERSE_MCP_BRIDGE or http://127.0.0.1:8765)",
    )
    parser.add_argument("--token", default=None, help="Bearer token (prefer --token-file)")
    parser.add_argument(
        "--token-file",
        default=None,
        help="Token file path (default: REVERSE_MCP_TOKEN_FILE or ~/.reverse-mcp/token)",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-call timeout in seconds")
    parser.add_argument("--expect-sha256", default=None, help="Expected target SHA-256")
    parser.add_argument(
        "--surface-id",
        action="append",
        default=[],
        help="Surface ID to require in the snapshot; repeat for several",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    args = parser.parse_args(argv)

    token = read_token(args.token, args.token_file)
    try:
        hello = rpc(args.url, "bridge.hello", {}, token, args.timeout)
        target = hello.get("target") if isinstance(hello, dict) else None
        target = target if isinstance(target, dict) else {}
        actual_hash = str(target.get("sha256") or "")
        if args.expect_sha256:
            if not actual_hash:
                raise CheckError(
                    "TARGET_HASH_MISSING",
                    "bridge.hello did not return target.sha256",
                    {"expected": args.expect_sha256},
                )
            if actual_hash.lower() != args.expect_sha256.lower():
                raise CheckError(
                    "TARGET_MISMATCH",
                    "bridge target hash does not match --expect-sha256",
                    {"expected": args.expect_sha256, "actual": actual_hash},
                )

        snapshot_params: dict[str, Any] = {}
        if args.surface_id:
            snapshot_params["ids"] = args.surface_id
        snapshot = rpc(args.url, "surface.snapshot", snapshot_params, token, args.timeout)
        values = snapshot.get("values") if isinstance(snapshot, dict) else None
        values = values if isinstance(values, dict) else {}
        missing = [surface_id for surface_id in args.surface_id if surface_id not in values]
        if missing:
            raise CheckError(
                "SURFACE_MISSING",
                "snapshot did not return every requested surface",
                {"missing": missing, "returned": sorted(values)},
            )

        report = {
            "ok": True,
            "url": args.url,
            "target": target,
            "hello": hello,
            "snapshot": {
                "requested": args.surface_id,
                "returned": sorted(values),
            },
        }
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            name = target.get("name") or target.get("id") or "unknown target"
            print(f"OK bridge={args.url} target={name} hash={actual_hash or 'not supplied'}")
            print(f"OK surfaces={', '.join(sorted(values)) or '(snapshot empty)'}")
            if args.surface_id:
                print(f"OK requested={', '.join(args.surface_id)}")
        return 0
    except CheckError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": exc.to_dict()}, indent=2, ensure_ascii=False))
        else:
            print(f"FAILED {exc.code}: {exc.message}", file=sys.stderr)
            if exc.details:
                print(json.dumps(exc.details, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
