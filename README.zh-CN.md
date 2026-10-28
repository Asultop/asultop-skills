# asultop-skills

**English:** [README.md](README.md)

AsulTop 的 Agent Skills marketplace。

- **当前插件：** `reverse-mcp-anything`
- **当前技能：** `reverse-mcp`
- **独立触发命令：** `/reverse-mcp`
- **目录坐标：** `asultop-skills/reverse-mcp-anything:reverse-mcp`
- **Marketplace 安装 ID：** `reverse-mcp-anything@asultop-skills`
- **插件限定技能：** `/reverse-mcp-anything:reverse-mcp`

它把一个本地程序的人类可见界面、实时状态、事件和配置，转换成带类型的 MCP server。优先使用 accessibility、IPC 或 Hook；只有在用户明确选择并同意时，才修改一个隔离副本，绝不修改已安装的原程序。

## 安装

### 独立安装（得到 `/reverse-mcp`）

把技能目录复制到你的技能目录，目录名必须保持 `reverse-mcp`（在仓库根目录执行）：

```bash
cp -r reverse-mcp-anything/skills/reverse-mcp ~/.claude/skills/reverse-mcp
```

```text
~/.claude/skills/reverse-mcp/          # Claude Code 个人技能
<project>/.claude/skills/reverse-mcp/  # 项目技能
~/.agents/skills/reverse-mcp/          # agent-skills 风格发现路径
```

然后直接输入 `/reverse-mcp`。目录名必须保持 `reverse-mcp`，因为 Agent Skills 规范要求 frontmatter 的 `name` 与父目录一致。

### Marketplace 插件

本目录采用 `anthropics/skills` 的 marketplace 结构：`.claude-plugin/marketplace.json` 加一个插件目录。

```text
/plugin marketplace add Asultop/asultop-skills
/plugin install reverse-mcp-anything@asultop-skills
```

插件方式下技能名是 `/reverse-mcp-anything:reverse-mcp`；上面的独立安装才会得到更短的 `/reverse-mcp`。

## 依赖

- **REA** — [`morluto/rea`](https://github.com/morluto/rea) / `reverse-engineer-anything` 技能。
- **grill-me** — [`mattpocock/skills`](https://github.com/mattpocock/skills) / `grilling` 技能（`grill-me` 是它的用户触发别名）。

技能内写了缺失依赖时的降级路径，但推荐流程会同时使用两者：grill-me 负责确认模式、环境和范围，REA 负责提供可引用的证据。

## 产物

```text
reverse-mcp/<target-slug>/
├── README.md
├── analysis/
│   ├── DECISIONS.md
│   ├── environment.json
│   ├── REPORT.md
│   └── surface.json
├── bridge/
└── server/        # MCP server 与测试
```

`surface.json` 是分析与服务端之间的契约：作用域内的每个元素、配置键、事件和动作，都有稳定 ID、证据、风险和选择器。MCP server 只是 loopback JSON-RPC bridge 之上的一层薄适配器。

## 目录结构

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

## 快速验证

在仓库根目录执行：

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

## 安全边界

仅用于你拥有或获得授权测试的软件，并且只在自己的机器上运行。技能默认只读，保持已安装二进制字节不变；反作弊、DRM、许可证校验、远程/多租户目标均视为超出范围。不要提交 token、捕获的敏感数据或打过补丁的二进制。
