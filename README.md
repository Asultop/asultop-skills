# asultop-skills

**中文版：** [README.zh-CN.md](README.zh-CN.md)

AsulTop's Agent Skills marketplace.

- **Current plugin:** `reverse-mcp-anything`
- **Current skill:** `reverse-mcp`
- **Standalone command:** `/reverse-mcp`
- **Catalog coordinate:** `asultop-skills/reverse-mcp-anything:reverse-mcp`
- **Marketplace install id:** `reverse-mcp-anything@asultop-skills`
- **Plugin-qualified skill:** `/reverse-mcp-anything:reverse-mcp`

It turns a local program's human-visible UI, live state, events, and configuration into a typed MCP server — using accessibility, IPC, or hooks, and patching only an isolated copy when the user explicitly chooses that route.

## Install

### Standalone skill (gives `/reverse-mcp`)

Copy the skill folder into your skill directory, keeping the folder name `reverse-mcp` (from the repository root):

```bash
cp -r reverse-mcp-anything/skills/reverse-mcp ~/.claude/skills/reverse-mcp
```

```text
~/.claude/skills/reverse-mcp/          # Claude Code personal skill
<project>/.claude/skills/reverse-mcp/  # project skill
~/.agents/skills/reverse-mcp/          # agent-skills style discovery
```

Then type `/reverse-mcp`. The folder name must stay `reverse-mcp` because Agent Skills requires `name` to match the parent directory.

### Marketplace plugin

This directory follows the `anthropics/skills` marketplace layout: `.claude-plugin/marketplace.json` plus a plugin folder.

```text
/plugin marketplace add <absolute-path-to-this-Skills-directory>
/plugin install reverse-mcp-anything@asultop-skills
```

The plugin-qualified skill is `/reverse-mcp-anything:reverse-mcp`. The standalone install above is the one that gives the shorter `/reverse-mcp`.

## Requires

- **REA** — [`morluto/rea`](https://github.com/morluto/rea) / the `reverse-engineer-anything` skill.
- **grill-me** — [`mattpocock/skills`](https://github.com/mattpocock/skills) / the `grilling` skill (`grill-me` is its user-invoked alias).

The skill documents fallbacks, but the intended path uses both: grill-me settles the mode/environment/scope, REA supplies evidence.

## What it produces

```text
reverse-mcp/<target-slug>/
├── README.md
├── analysis/
│   ├── DECISIONS.md
│   ├── environment.json
│   ├── REPORT.md
│   └── surface.json
├── bridge/
└── server/        # MCP server + tests
```

The surface map is the contract: every in-scope element, config key, event, and action gets a stable ID, evidence, risk, and selector. The MCP server is a thin typed adapter over a loopback JSON-RPC bridge.

## Layout

```text
asultop-skills/
├── .claude-plugin/marketplace.json
├── README.md
├── README.zh-CN.md
└── reverse-mcp-anything/
    └── skills/
        └── reverse-mcp/
            ├── SKILL.md
            ├── README.md
            ├── README.zh-CN.md
            ├── references/
            │   ├── intake.md
            │   ├── environment.md
            │   ├── analysis.md
            │   ├── surface-map.md
            │   ├── instrumentation.md
            │   ├── mcp-server.md
            │   └── verification.md
            ├── scripts/
            │   ├── probe_environment.py
            │   ├── validate_surface.py
            │   ├── scaffold_mcp.py
            │   └── check_bridge.py
            └── assets/
                ├── surface.schema.json
                ├── surface.example.json
                ├── report-template.md
                └── mcp.json.example
```

## Quick smoke test

From the repository root:

```bash
python reverse-mcp-anything/skills/reverse-mcp/scripts/probe_environment.py \
  --json analysis/environment.json
python reverse-mcp-anything/skills/reverse-mcp/scripts/validate_surface.py \
  reverse-mcp-anything/skills/reverse-mcp/assets/surface.example.json
python reverse-mcp-anything/skills/reverse-mcp/scripts/scaffold_mcp.py \
  --target "Acme Notes" --lang python \
  --surface reverse-mcp-anything/skills/reverse-mcp/assets/surface.example.json \
  --out ./reverse-mcp-acme
```

## Safety

Use only on software you own or are authorized to test, on your own machine. The skill starts read-only, keeps the installed binary byte-identical, and treats anti-cheat, DRM, licence checks, and remote/multi-tenant targets as out of scope. It does not ship secrets, tokens, or patched binaries.
