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

通信协议基于**文件系统**：每次交互通过可版本控制的 JSON 文件传递。
无需长驻服务、无内存中的会话状态 — 一切在重启后可重建。

## 架构分层

| 层 | 文件 | 职责 |
|---|------|------|
| **WorkflowStackStore** | `workflow_stack.py` | LIFO 栈，支持 push/pop/placeholder，持久化到磁盘 |
| **WorkflowTemplate** | `workflow_templates.py` | 声明式模板注册表：确定性步骤 + agent 切点 |
| **AgentWorkflowService** | `agent_workflow.py` | 编排引擎：`while` 循环遍历栈，分发，恢复 |
| **StepRunner** | `step_runner.py` | 按模板步骤依次执行注册的 action，自动处理切点 |
| **ActionContext / ActionResult** | `actions.py` | 步骤函数的类型化契约 + 注册表 + context 持久化 |
| **AgentTasks** | `agent_tasks.py` | JSON 任务文件读写 — 程序 ↔ agent 通信协议 |
| **ProposedWorkflow** | `proposed_workflow.py` | agent 自编排工作流计划，带校验 |

## 关键设计决策

1. **栈式嵌套** — workflow 可以 push 子 workflow；子完成后 pop，父恢复执行。
   类似函数调用栈。

2. **占位路由** — 当里程碑失败且下一步不确定时，引擎压入 `__route_pending__`
   占位帧，请求 agent 调用 `choose_route()` 做出路由决策。

3. **幂等 & 可恢复** — 所有状态落在文件系统中。杀掉进程、重启、再次调用
   `run()` — 从同一栈和任务文件继续执行。

4. **模板驱动 + action 化** — 每个 workflow 预先声明确定性步骤，每个步骤名
   映射到注册的 action 函数。新增流程只需注册 action + 声明顺序，无需编写
   handler 代码。

5. **Context 持久化** — 共享的 `ActionContext` 在每步 action 执行后自动
   持久化到 `build/action-context.json`。agent 通过 `action run` 的修改
   自动在后续 `workflow run` 中生效，无需手动文件管理。

6. **Agent 自编排** — 高级 agent 可以 propose 全新的 workflow 计划
   （`agent-proposed-workflow.json`），经过校验层后执行。

7. **CLI 优先的 agent 接口** — 所有能力通过 CLI（`python -m
   stack_orchestrated_agent`）暴露。agent 通过子进程调用 + JSON stdout
   交互，无需 SDK。

## 快速开始

```python
from stack_orchestrated_agent import (
    AgentWorkflowService,
    WorkflowTemplate,
    ActionContext,
    ActionResult,
    register_template,
    register_action,
)

# 1. 声明 workflow
register_template(WorkflowTemplate(
    workflow_id="hello_v1",
    description="带 agent 确认的问候流程。",
    deterministic_steps=("greet", "confirm"),
    agent_cut_points=("needs_confirmation",),
    supported_task_types=("agent_review",),
))

# 2. 将步骤实现为 action
def greet(ctx: ActionContext) -> ActionResult:
    ctx.data["message"] = "hello world"
    return ActionResult(status="ok")

def confirm(ctx: ActionContext) -> ActionResult:
    if ctx.data.get("confirmed"):
        return ActionResult(status="ok")
    return ActionResult(
        status="cut_point",
        reason="needs_confirmation",
        summary=f"请确认消息：{ctx.data.get('message')}",
    )

register_action("greet", greet)
register_action("confirm", confirm)

# 3. 运行 — 遇切点立即返回，context 已存盘
svc = AgentWorkflowService()
result = svc.run("/tmp/demo", template="hello_v1")
# → {"status": "waiting_for_agent", "rerun_after_agent": true, ...}
```

### Agent 视角（CLI）

```bash
# 发现可用能力
python -m stack_orchestrated_agent action list
python -m stack_orchestrated_agent template list

# 运行 workflow
python -m stack_orchestrated_agent workflow run --project /tmp/demo --template hello_v1

# 查看当前状态
python -m stack_orchestrated_agent workflow status --project /tmp/demo

# 执行单个 action（context 自动持久化）
python -m stack_orchestrated_agent action run confirm --project /tmp/demo

# 选择路由并重跑
python -m stack_orchestrated_agent workflow choose-route --project /tmp/demo --workflow hello_v1
python -m stack_orchestrated_agent workflow run --project /tmp/demo --template hello_v1
```

### Agent 循环

```
workflow run → "waiting_for_agent"，附带 tasks_file 路径
     │
     ▼
workflow status → 读取待处理任务
     │
     ▼
action run <approve> → context 已持久化
     │
     ▼
workflow choose-route → 解决占位路由
     │
     ▼
workflow run → "completed"
```

## 文件系统协议

```
project/
├── build/
│   ├── agent-workflow-stack.json   ← 栈状态
│   ├── agent-tasks.json            ← agent 待办任务
│   ├── action-context.json         ← 持久化的共享 context
│   └── agent-proposed-workflow.json ← agent 自编排计划
```

## 仓库约定

- 变更记录：`CHANGELOG.md`（Keep a Changelog 风格）
- 提交信息：Conventional Commits（`feat:`、`fix:`、`chore:`），正文中英双语
- 社区文档：`CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md`

## 许可证

见 `LICENSE`。
