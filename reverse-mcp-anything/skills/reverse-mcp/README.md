# Reverse-MCP-Anything (skill)

**中文版：** [README.zh-CN.md](README.zh-CN.md)

- **Standalone trigger:** `/reverse-mcp <target>`
- **Plugin-qualified trigger:** `/reverse-mcp-anything:reverse-mcp <target>`
- **Marketplace install id:** `reverse-mcp-anything@asultop-skills`

Turn one local program into a typed MCP server that can read what the UI shows, change what a user can change, and wait for events — without modifying the installed binary.

This folder is named `reverse-mcp` because the Agent Skills specification requires the frontmatter `name` to match the parent directory. The plugin that ships it is **Reverse-MCP-Anything**.

## Install as a standalone skill

```bash
cp -r reverse-mcp-anything/skills/reverse-mcp ~/.claude/skills/reverse-mcp
```

Then type `/reverse-mcp`. For the marketplace form, see [the marketplace README](../../../README.md).

## Dependencies

- [`reverse-engineer-anything`](https://github.com/morluto/rea) — REA; load it for target analysis.
- [`grilling`](https://github.com/mattpocock/skills) — the engine behind `grill-me`; load it for the mode gate.

If a dependency is missing, the skill says so and uses the documented fallback rather than skipping the step.

## Workflow

1. **Mode Gate** — grill-me interview: target, outcomes, observer/hook/patch, write scope, environment, acceptance.
2. **Runtime Probe** — `scripts/probe_environment.py` reads `PATH` and default install roots.
3. **REA Analysis** — eight questions, evidence ledger.
4. **Surface Map** — `analysis/surface.json`, validated by `scripts/validate_surface.py`.
5. **Bridge** — choose, implement, and prove observer → protocol → hook → patch (copy only); `check_bridge.py` gates the handoff.
6. **MCP Server** — `scripts/scaffold_mcp.py` for Python/TypeScript/Rust, then typed tools.
7. **Verification** — reads, previews, mutations, events, failure drills, hash check.
8. **Delivery** — runnable project + report + residual unknowns.

## Scripts

```bash
# Detect toolchains; never installs anything
python scripts/probe_environment.py --json analysis/environment.json

# Validate the surface contract
python scripts/validate_surface.py analysis/surface.json

# Prove the bridge is live before generating the server
python scripts/check_bridge.py --url http://127.0.0.1:8765 \
  --token-file ~/.reverse-mcp/acme.token \
  --expect-sha256 <original-sha256> \
  --surface-id main.status

# Generate a server skeleton
python scripts/scaffold_mcp.py --target "Acme Notes" --lang python --mode hook \
  --surface analysis/surface.json --out reverse-mcp/acme
```

`scaffold_mcp.py` supports `--lang python|typescript|rust` and `--mode observer|protocol|hook|patch|hybrid`.

## Design rules

- **Read-only-first, least-invasive-first, copy-only when patching.** Observer → protocol → hook; patch is an explicit, separate decision.
- **The installed binary stays byte-identical.** Hook mode changes memory, not the file. Patch only a copy.
- **Surface map before server code.** Every observable element, config key, event, and action gets a stable ID and evidence.
- **No escape hatch.** No `run_command`, `eval`, or arbitrary memory write tools.
- **Confirmation is enforced twice.** The MCP layer previews; the bridge re-checks `confirm`.
- **Evidence beats inference.** Static analysis does not prove runtime behavior; runtime observation does not prove code structure.

## Safety

Use only on software you own or are authorized to test, on your own machine. Stop for anti-cheat, DRM, licence enforcement, or remote/multi-tenant targets. Do not commit tokens, captured secrets, or patched binaries.
