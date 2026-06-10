# Stack-Orchestrated Agent Architecture

确定性程序 ↔ AI agent 协作框架，基于**栈式状态机**。程序执行已知步骤；
遇到不确定的切点（cut-point）时，将问题写成结构化 JSON 任务文件并暂停。
外部 agent（或人）读取任务、做出决策、交还控制权 — 栈从断点处精确恢复。

语言：简体中文 | [English](README.md)

## 核心思路

```
程序（确定性步骤）              Agent（不确定性决策）
        │                              │
        ├── 第1步 ──────────────────► │
        ├── 第2步                     │
        ├── 第3步 → 切点              │
        │    │                         │
        │    ▼    agent-tasks.json     │
        │    ──────────────────────►   │  读取 / 决策 / 写入
        │    ◄──────────────────────   │
        │    │                         │
        ├── 恢复第4步                  │
        ▼                              ▼
```

通信协议基于**文件系统**：每次交互通过可版本控制的 JSON 文件
（`agent-workflow-stack.json`、`agent-tasks.json`）传递。无需长驻服务、
无内存中的会话状态 — 一切在重启后可重建。

## 架构分层

| 层 | 文件 | 职责 |
|---|------|------|
| **WorkflowStackStore** | `workflow_stack.py` | LIFO 栈，支持 push/pop/placeholder，持久化到磁盘 |
| **WorkflowTemplate** | `workflow_templates.py` | 声明式模板注册表：确定性步骤 + agent 切点 |
| **AgentWorkflowService** | `agent_workflow.py` | 编排引擎：`while` 循环遍历栈，分发，恢复 |
| **AgentTasks** | `agent_tasks.py` | JSON 任务文件读写 — 程序 ↔ agent 通信协议 |
| **ProposedWorkflow** | `proposed_workflow.py` | agent 自编排出流程计划，带校验 |

## 关键设计决策

1. **栈式嵌套** — workflow 可以 push 子 workflow；子完成后 pop，父恢复执行。类似函数调用栈。

2. **占位路由** — 当里程碑失败且下一步不确定时，引擎压入 `__route_pending__` 占位帧，请求 agent 调用 `choose_route()` 做出路由决策。

3. **幂等 & 可恢复** — 所有状态落在文件系统中。杀掉进程、重启、再次调用 `run()` — 从同一栈和任务文件继续执行。

4. **模板驱动** — 每个 workflow 预先声明确定性步骤和 agent 切点。新增流程只需注册模板 + 编写一个 handler 函数。

5. **agent 自编排** — 高级 agent 可以 propose 全新的 workflow 计划（`agent-proposed-workflow.json`），经过校验层后执行。

## 快速开始

```python
from orchestration import AgentWorkflowService

service = AgentWorkflowService()
result = service.run(
    project_path="/path/to/project",
    template="full_build_v1",
)
# → 如果需要 agent 介入则立即返回，
#   附带任务文件路径和 "rerun_after_agent": True
```

## 仓库约定

- 变更记录：`CHANGELOG.md`（Keep a Changelog 风格）
- 提交信息：Conventional Commits（`feat:`、`fix:`、`chore:`）
- 社区文档：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`

## 许可证

见 `LICENSE`。
