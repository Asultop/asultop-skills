#!/usr/bin/env python3
"""Validate a Reverse-MCP surface map.

Read-only, standard library only. Exit 0 when the map is structurally valid;
exit 1 when there are errors. Warnings do not fail unless --strict is given.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
EVIDENCE_RE = re.compile(r"^E-[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[a-fA-F0-9]{64}$")

SURFACE_KINDS = {
    "window", "menu", "menu_item", "toolbar", "tab", "list", "tree", "table",
    "text", "input", "button", "checkbox", "radio", "combo", "slider", "dialog",
    "status", "notification", "canvas", "terminal", "webview", "custom",
}
RISKS = {"read", "write", "destructive", "external"}
CONFIDENCE = {"observed", "inferred", "unknown"}
SELECTORS = {
    "native_command", "ipc_method", "accessibility_id", "accessibility_name",
    "object_path", "dom_selector", "role_name", "pty_pattern", "coordinates",
}
FIELD_TYPES = {
    "string", "integer", "number", "boolean", "enum", "array", "object",
    "secret", "unknown",
}
APPLY = {"live", "restart", "relogin", "unknown"}
ENCRYPTION = {"none", "dpapi", "keychain", "libsecret", "aes", "custom", "unknown"}
EVENT_SOURCES = {"ui", "ipc", "network", "file", "log", "timer", "hook", "unknown"}
EVENT_RATES = {"low", "medium", "high", "unknown"}
CONFIRMATION = {"none", "always", "destructive"}
EVIDENCE_TYPES = {"static", "runtime", "inferred", "non-REA"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def is_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def check_keys(obj: Any, where: str, required: tuple[str, ...], report: Report) -> bool:
    if not isinstance(obj, dict):
        report.error(f"{where}: expected an object")
        return False
    missing = [key for key in required if key not in obj]
    if missing:
        report.error(f"{where}: missing required field(s): {', '.join(missing)}")
        return False
    return True


def check_id(value: Any, where: str, report: Report, seen: set[str]) -> None:
    if not is_str(value):
        report.error(f"{where}: id must be a non-empty string")
        return
    if not ID_RE.match(value):
        report.error(f"{where}: id {value!r} must match {ID_RE.pattern}")
    if value in seen:
        report.error(f"{where}: duplicate id {value!r}")
    seen.add(value)


def check_selector(value: Any, where: str, report: Report) -> None:
    if not isinstance(value, dict):
        report.error(f"{where}: selector must be an object")
        return
    strategy = value.get("strategy")
    if strategy not in SELECTORS:
        report.error(f"{where}: selector.strategy must be one of {sorted(SELECTORS)}")
    if "value" not in value:
        report.error(f"{where}: selector.value is required")
    elif not isinstance(value["value"], (str, dict, list)):
        report.error(f"{where}: selector.value must be a string, object, or array")
    if "brittle" in value and not isinstance(value["brittle"], bool):
        report.error(f"{where}: selector.brittle must be a boolean")
    if "fallback" in value:
        check_selector(value["fallback"], f"{where}.fallback", report)


def check_fields(value: Any, where: str, report: Report) -> None:
    if not isinstance(value, list):
        report.error(f"{where}: must be an array")
        return
    for index, field in enumerate(value):
        at = f"{where}[{index}]"
        if not check_keys(field, at, ("name", "type"), report):
            continue
        if not is_str(field["name"]):
            report.error(f"{at}.name: must be a non-empty string")
        if field["type"] not in FIELD_TYPES:
            report.error(f"{at}.type: must be one of {sorted(FIELD_TYPES)}")


def check_evidence_refs(value: Any, where: str, known: set[str], report: Report) -> None:
    if not isinstance(value, list):
        report.error(f"{where}: evidence must be an array")
        return
    for item in value:
        if not is_str(item):
            report.error(f"{where}: evidence entries must be strings")
            continue
        if not EVIDENCE_RE.match(item):
            report.error(f"{where}: evidence id {item!r} must match {EVIDENCE_RE.pattern}")
        elif known and item not in known:
            report.error(f"{where}: evidence id {item!r} is not defined in top-level evidence")


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(data: Any) -> Report:
    report = Report()
    if not check_keys(
        data,
        "root",
        ("schema_version", "target", "mode", "surfaces", "config", "events", "actions", "out_of_scope"),
        report,
    ):
        return report

    if data["schema_version"] != 1:
        report.error("root.schema_version: must be 1")
    if data["mode"] not in {"observer", "protocol", "hook", "patch", "hybrid"}:
        report.error("root.mode: must be observer, protocol, hook, patch, or hybrid")

    # Evidence first, so references can be checked.
    known_evidence: set[str] = set()
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        report.error("root.evidence: must be an array when present")
        evidence = []
    for index, item in enumerate(evidence):
        at = f"evidence[{index}]"
        if not check_keys(item, at, ("id", "type", "summary"), report):
            continue
        if not is_str(item["id"]) or not EVIDENCE_RE.match(item["id"]):
            report.error(f"{at}: id {item['id']!r} must match {EVIDENCE_RE.pattern}")
        elif item["id"] in known_evidence:
            report.error(f"{at}: duplicate evidence id {item['id']!r}")
        else:
            known_evidence.add(item["id"])
        if item["type"] not in EVIDENCE_TYPES:
            report.error(f"{at}.type: must be one of {sorted(EVIDENCE_TYPES)}")
        if not is_str(item["summary"]):
            report.error(f"{at}.summary: must be a non-empty string")

    target = data["target"]
    if check_keys(
        target,
        "target",
        ("name", "version", "path", "sha256", "platform", "arch", "ui_framework", "runtime"),
        report,
    ):
        for key in ("name", "version", "path", "platform", "arch", "ui_framework", "runtime"):
            if not is_str(target[key]):
                report.error(f"target.{key}: must be a non-empty string")
        if not is_str(target["sha256"]) or not SHA_RE.match(target["sha256"]):
            report.error("target.sha256: must be a 64-character hex digest")

    surfaces = data["surfaces"]
    if not isinstance(surfaces, list):
        report.error("root.surfaces: must be an array")
        surfaces = []
    surface_ids: set[str] = set()
    surface_action_refs: list[tuple[str, str]] = []
    for index, surface in enumerate(surfaces):
        at = f"surfaces[{index}]"
        if not check_keys(
            surface,
            at,
            ("id", "kind", "label", "selector", "reads", "actions", "risk", "confidence", "evidence"),
            report,
        ):
            continue
        check_id(surface["id"], at, report, surface_ids)
        if surface["kind"] not in SURFACE_KINDS:
            report.error(f"{at}.kind: must be one of {sorted(SURFACE_KINDS)}")
        if not is_str(surface["label"]):
            report.error(f"{at}.label: must be a non-empty string")
        check_selector(surface["selector"], f"{at}.selector", report)
        check_fields(surface["reads"], f"{at}.reads", report)
        if not isinstance(surface["actions"], list) or not all(isinstance(a, str) for a in surface["actions"]):
            report.error(f"{at}.actions: must be an array of action ids")
        else:
            surface_action_refs.extend((surface["id"], action_id) for action_id in surface["actions"])
        if surface["risk"] not in RISKS:
            report.error(f"{at}.risk: must be one of {sorted(RISKS)}")
        if surface["confidence"] not in CONFIDENCE:
            report.error(f"{at}.confidence: must be one of {sorted(CONFIDENCE)}")
        check_evidence_refs(surface["evidence"], f"{at}.evidence", known_evidence, report)
        if "brittle" in surface and not isinstance(surface["brittle"], bool):
            report.error(f"{at}.brittle: must be a boolean")
        if "parent_id" in surface and surface["parent_id"] is not None and not is_str(surface["parent_id"]):
            report.error(f"{at}.parent_id: must be a string or null")

    # Parent references are checked after all surface ids are known.
    for index, surface in enumerate(surfaces):
        parent = surface.get("parent_id") if isinstance(surface, dict) else None
        if parent and parent not in surface_ids:
            report.error(f"surfaces[{index}].parent_id: {parent!r} is not a defined surface")

    config = data["config"]
    if not isinstance(config, list):
        report.error("root.config: must be an array")
        config = []
    config_ids: set[str] = set()
    for index, entry in enumerate(config):
        at = f"config[{index}]"
        if not check_keys(
            entry,
            at,
            ("id", "key", "type", "source", "precedence", "writable", "apply", "encryption", "risk", "evidence", "confidence"),
            report,
        ):
            continue
        check_id(entry["id"], at, report, config_ids)
        if not is_str(entry["key"]):
            report.error(f"{at}.key: must be a non-empty string")
        if entry["type"] not in FIELD_TYPES:
            report.error(f"{at}.type: must be one of {sorted(FIELD_TYPES)}")
        if not is_str(entry["source"]):
            report.error(f"{at}.source: must be a non-empty string")
        if not isinstance(entry["precedence"], int) or isinstance(entry["precedence"], bool):
            report.error(f"{at}.precedence: must be an integer")
        if not isinstance(entry["writable"], bool):
            report.error(f"{at}.writable: must be a boolean")
        if entry["apply"] not in APPLY:
            report.error(f"{at}.apply: must be one of {sorted(APPLY)}")
        if entry["encryption"] not in ENCRYPTION:
            report.error(f"{at}.encryption: must be one of {sorted(ENCRYPTION)}")
        if entry["risk"] not in RISKS:
            report.error(f"{at}.risk: must be one of {sorted(RISKS)}")
        if entry["confidence"] not in CONFIDENCE:
            report.error(f"{at}.confidence: must be one of {sorted(CONFIDENCE)}")
        if "selector" in entry and entry["selector"] is not None:
            if not is_str(entry["selector"]):
                report.error(f"{at}.selector: must be a non-empty string when present")
            elif entry["selector"] not in surface_ids:
                report.warn(f"{at}.selector: {entry['selector']!r} is not a defined surface")
        check_evidence_refs(entry["evidence"], f"{at}.evidence", known_evidence, report)

    events = data["events"]
    if not isinstance(events, list):
        report.error("root.events: must be an array")
        events = []
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        at = f"events[{index}]"
        if not check_keys(
            event,
            at,
            ("id", "name", "source", "trigger", "payload", "rate", "observed", "evidence", "confidence"),
            report,
        ):
            continue
        check_id(event["id"], at, report, event_ids)
        if not is_str(event["name"]):
            report.error(f"{at}.name: must be a non-empty string")
        if event["source"] not in EVENT_SOURCES:
            report.error(f"{at}.source: must be one of {sorted(EVENT_SOURCES)}")
        if not is_str(event["trigger"]):
            report.error(f"{at}.trigger: must be a non-empty string")
        check_fields(event["payload"], f"{at}.payload", report)
        if event["rate"] not in EVENT_RATES:
            report.error(f"{at}.rate: must be one of {sorted(EVENT_RATES)}")
        if not isinstance(event["observed"], bool):
            report.error(f"{at}.observed: must be a boolean")
        if event["confidence"] not in CONFIDENCE:
            report.error(f"{at}.confidence: must be one of {sorted(CONFIDENCE)}")
        if event["observed"] and event["confidence"] != "observed":
            report.warn(f"{at}: observed=true but confidence={event['confidence']!r}")
        if not event["observed"] and event["confidence"] == "observed":
            report.warn(f"{at}: observed=false but confidence='observed'")
        check_evidence_refs(event["evidence"], f"{at}.evidence", known_evidence, report)

    actions = data["actions"]
    if not isinstance(actions, list):
        report.error("root.actions: must be an array")
        actions = []
    action_ids: set[str] = set()
    action_surface_refs: list[tuple[str, Any]] = []
    for index, action in enumerate(actions):
        at = f"actions[{index}]"
        if not check_keys(
            action,
            at,
            ("id", "surface_id", "verb", "args", "side_effects", "risk", "confirmation", "idempotent", "timeout_ms", "evidence", "confidence"),
            report,
        ):
            continue
        check_id(action["id"], at, report, action_ids)
        if action["surface_id"] is not None and not is_str(action["surface_id"]):
            report.error(f"{at}.surface_id: must be a string or null")
        action_surface_refs.append((action["id"], action["surface_id"]))
        if not is_str(action["verb"]):
            report.error(f"{at}.verb: must be a non-empty string")
        check_fields(action["args"], f"{at}.args", report)
        if not is_str_list(action["side_effects"]):
            report.error(f"{at}.side_effects: must be an array of non-empty strings")
        if action["risk"] not in RISKS:
            report.error(f"{at}.risk: must be one of {sorted(RISKS)}")
        if action["confirmation"] not in CONFIRMATION:
            report.error(f"{at}.confirmation: must be one of {sorted(CONFIRMATION)}")
        if not isinstance(action["idempotent"], bool):
            report.error(f"{at}.idempotent: must be a boolean")
        if not isinstance(action["timeout_ms"], int) or isinstance(action["timeout_ms"], bool) or action["timeout_ms"] < 1:
            report.error(f"{at}.timeout_ms: must be a positive integer")
        if action["risk"] in {"destructive", "external"} and action["confirmation"] == "none":
            report.warn(f"{at}: {action['risk']} action has confirmation='none'")
        if not action["idempotent"] and action["risk"] == "read":
            report.warn(f"{at}: read action marked non-idempotent")
        if action["confidence"] not in CONFIDENCE:
            report.error(f"{at}.confidence: must be one of {sorted(CONFIDENCE)}")
        check_evidence_refs(action["evidence"], f"{at}.evidence", known_evidence, report)

    for surface_id, action_id in surface_action_refs:
        if action_id not in action_ids:
            report.error(f"surfaces[{surface_id}].actions: {action_id!r} is not a defined action")
    for action_id, surface_id in action_surface_refs:
        if surface_id and surface_id not in surface_ids:
            report.error(f"actions[{action_id}].surface_id: {surface_id!r} is not a defined surface")
        if surface_id and surface_id in surface_ids:
            linked = [s for s in surfaces if isinstance(s, dict) and s.get("id") == surface_id]
            if linked and action_id not in linked[0].get("actions", []):
                report.warn(f"actions[{action_id}]: surface {surface_id!r} does not list this action")

    out_of_scope = data["out_of_scope"]
    if not isinstance(out_of_scope, list):
        report.error("root.out_of_scope: must be an array")
    else:
        for index, item in enumerate(out_of_scope):
            at = f"out_of_scope[{index}]"
            if not check_keys(item, at, ("item", "reason"), report):
                continue
            if not is_str(item["item"]) or not is_str(item["reason"]):
                report.error(f"{at}: item and reason must be non-empty strings")

    if not surfaces:
        report.warn("no surfaces defined; the MCP would have nothing to read")
    if not actions:
        report.warn("no actions defined; the MCP would be read-only")
    if not events:
        report.warn("no events defined; document why, or add a polling fallback")
    if not known_evidence:
        report.warn("no evidence entries; every substantive claim needs evidence")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Reverse-MCP surface map.")
    parser.add_argument("path", type=Path, help="Path to analysis/surface.json")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    parser.add_argument("--quiet", action="store_true", help="Only print errors and warnings")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1
    try:
        data = load(args.path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read JSON: {exc}", file=sys.stderr)
        return 1

    report = validate(data)
    exit_code = 1 if report.errors or (args.strict and report.warnings) else 0

    if args.json:
        print(
            json.dumps(
                {
                    "ok": exit_code == 0,
                    "errors": report.errors,
                    "warnings": report.warnings,
                    "counts": {
                        "surfaces": len(data.get("surfaces", [])) if isinstance(data, dict) else 0,
                        "config": len(data.get("config", [])) if isinstance(data, dict) else 0,
                        "events": len(data.get("events", [])) if isinstance(data, dict) else 0,
                        "actions": len(data.get("actions", [])) if isinstance(data, dict) else 0,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        if not args.quiet:
            counts = (
                len(data.get("surfaces", [])) if isinstance(data, dict) else 0,
                len(data.get("config", [])) if isinstance(data, dict) else 0,
                len(data.get("events", [])) if isinstance(data, dict) else 0,
                len(data.get("actions", [])) if isinstance(data, dict) else 0,
            )
            print(f"Checked {args.path}: {counts[0]} surfaces, {counts[1]} config, {counts[2]} events, {counts[3]} actions")
        for warning in report.warnings:
            print(f"WARN: {warning}")
        for error in report.errors:
            print(f"ERROR: {error}")
        if exit_code == 0:
            print("OK: surface map is valid")
        else:
            print(f"FAILED: {len(report.errors)} error(s), {len(report.warnings)} warning(s)")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
