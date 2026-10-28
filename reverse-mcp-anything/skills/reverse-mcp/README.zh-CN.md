# Reverse-MCP-Anything（技能）

**English:** [README.md](README.md)

- **独立触发：** `/reverse-mcp <目标>`
- **插件限定触发：** `/reverse-mcp-anything:reverse-mcp <目标>`
- **Marketplace 安装 ID：** `reverse-mcp-anything@asultop-skills`

把一个本地程序变成带类型的 MCP server：读取界面当前显示的内容，修改用户能修改的状态，等待用户能触发的事件——全程不修改已安装的原程序。

本目录名为 `reverse-mcp`，因为 Agent Skills 规范要求 frontmatter 的 `name` 与父目录一致；承载它的插件名是 **Reverse-MCP-Anything**。

## 独立安装

```bash
cp -r reverse-mcp-anything/skills/reverse-mcp ~/.claude/skills/reverse-mcp
```

然后输入 `/reverse-mcp`。Marketplace 形式见[总 README](../../../README.zh-CN.md)。

## 依赖

- [`reverse-engineer-anything`](https://github.com/morluto/rea) — REA，用于目标分析。
- [`grilling`](https://github.com/mattpocock/skills) — `grill-me` 的底层技能，用于模式访谈。

依赖缺失时，技能会说明缺什么，并走文档中的降级路径，而不是跳过访谈或证据标准。

## 工作流

1. **Mode Gate** — grill-me 访谈：目标、期望结果、Observer/Hook/Patch、写权限、运行环境、验收标准。
2. **Runtime Probe** — `scripts/probe_environment.py` 读取 `PATH` 和编译器默认安装位置。
3. **REA Analysis** — 回答八个问题，建立证据台账。
4. **Surface Map** — 生成 `analysis/surface.json`，用 `scripts/validate_surface.py` 校验。
5. **Bridge** — 选择、实现并验证 Observer → Protocol → Hook → Patch（仅副本）；用 `check_bridge.py` 作为进入下一步的闸门。
6. **MCP Server** — 用 `scripts/scaffold_mcp.py` 生成 Python/TypeScript/Rust 骨架，再补充带类型的工具。
7. **Verification** — 读取、预览、变更、事件、失败路径、哈希校验。
8. **Delivery** — 可运行项目 + 报告 + 未解决项。

## 脚本

```bash
# 探测工具链；不会安装任何东西
python scripts/probe_environment.py --json analysis/environment.json

# 校验 surface 契约
python scripts/validate_surface.py analysis/surface.json

# 在生成 server 之前证明 bridge 已经可用
python scripts/check_bridge.py --url http://127.0.0.1:8765 \
  --token-file ~/.reverse-mcp/acme.token \
  --expect-sha256 <原始文件 SHA-256> \
  --surface-id main.status

# 生成 MCP server 骨架
python scripts/scaffold_mcp.py --target "Acme Notes" --lang python --mode hook \
  --surface analysis/surface.json --out reverse-mcp/acme
```

`scaffold_mcp.py` 支持 `--lang python|typescript|rust` 和 `--mode observer|protocol|hook|patch|hybrid`。

## 设计规则

- **只读优先，最小侵入优先，打补丁只碰副本。** Observer → Protocol → Hook；Patch 是单独、显式的决定。
- **已安装二进制保持字节不变。** Hook 改的是进程内存，不是文件；Patch 只改副本。
- **先有 Surface Map，再写服务端。** 每个可观察元素、配置键、事件和动作，都要有稳定 ID 和证据。
- **不留逃生通道。** 不暴露 `run_command`、`eval` 或任意内存写入工具。
- **确认做两次。** MCP 层先预览，bridge 再校验 `confirm`。
- **证据优先于推断。** 静态分析不能证明运行时行为，运行时观察也不能证明代码结构。

## 安全边界

仅用于你拥有或获得授权测试的软件，并且只在自己的机器上运行。遇到反作弊、DRM、许可证校验、远程/多租户目标时停止。不要提交 token、捕获的敏感数据或打过补丁的二进制。
