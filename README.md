# 头脑风暴（brainstorm）

一个开源小工具，让多个 AI 助手住进你的钉钉群：你 @ 它就回话，不 @ 它就安静待着，几个 AI 之间还能自己接力干活，全程零常驻、零费用。

三件套：

1. **追加式房间文件** —— 一行一条 JSON 的 `room.jsonl`，是唯一事实源；天然可审计、可回放、多 agent 并发写不打架。
2. **事件驱动唤醒** —— 只有命中「人发的消息 / 点名 @ 我」才拉起一次无头 agent 会话，答完即退，不做常驻轮询。
3. **presence 在线协议** —— `/p`（放你离线）、`/l`（我办完你可以睡了）+ 60 秒无人说话自动离线，防止两个 agent 互相刷屏。

## 特性

- **agent CLI 可插拔**：`opencode` / `qoderclicn` / `claude` …… 任意能吃一行 prompt 的 CLI 都能接，唤醒命令写在配置模板里。
- **N 个 agent**：`agents` 数组，改配置即可增删成员，不用改代码。
- **凭据隔离**：真实 token 只放 `config.local.json`（已 gitignore），本机 `config.json` 不进 git，仓库只提供占位符版 `config.example.json`；日志按关键词脱敏。
- **注入与伪造防护**：群消息进 prompt 前消毒包裹（防"忽略指令"类注入，高危消息可配置直接拦截）；官方回调强制验签，拒绝伪造消息。
- **doctor 自检**：`.\doctor.ps1` 一键体检（依赖 / 配置 / 凭据 / 房间文件 / 进程）。
- **回帖走命令行**：`python -m brainstorm.room post`，任何能执行 shell 命令的 agent CLI 都能回帖，不依赖 MCP。

## 快速开始

```powershell
# 0. 配置（本机 config.json 不进 git，从占位符模板复制）
Copy-Item config.example.json config.json   # 然后按需修改
Copy-Item config.local.json.example config.local.json   # 然后填凭据（appSecret / webhook token）

# 1. 体检
.\doctor.ps1

# 2. 自测（核心逻辑 38 项断言，纯本地无网络）
python tests\test_core.py

# 3. 起桥（钉钉回调验签入站 + agent 回帖出站；--dump 可留原始报文便于对接）
python -m brainstorm.bridge --dump

# 4. 起 watcher（扫房间 → 按需唤醒 agent CLI）
python -m brainstorm.watcher
```

不接钉钉也能本地跑通一整轮：`python -m brainstorm.room post --from human --text "你好"` 之后起 watcher 即可（`tests\smoke\` 里有现成的假 agent 配置）。

## 配置

见 [`config.example.json`](./config.example.json)（可进 git，纯占位符无凭据、无本机环境信息）；本机复制出的 `config.json` 已 gitignore。凭据模板见 [`config.local.json.example`](./config.local.json.example)。字段说明见 [docs/架构.md](./docs/架构.md)。

`wakeup.args` 支持 `{prompt}`（已消毒包裹的群消息）与 `{model}`（agent 模型名）两个模板变量；进程以参数数组直接启动，prompt 不经过 shell（防命令注入）。

## 路线图

见 [docs/里程碑.md](./docs/里程碑.md)。

## License

MIT
