# 更新日志

语言：简体中文 | [English](CHANGELOG.md)

本项目的所有重要变更都会记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，并遵循
[语义化版本](https://semver.org/spec/v2.0.0.html)。

## [0.1.0] — 2026-06-10

### 新增

- **WorkflowStackStore** — LIFO 栈状态机，支持 push/pop/placeholder 路由，
  持久化到 `agent-workflow-stack.json`。
- **WorkflowTemplate** — 声明式模板注册表；模板指定确定性步骤与 agent 切点。
- **AgentWorkflowService** — `while` 循环编排引擎，含 `register_handler()`
  插件机制。
- **AgentTasks** — 基于 JSON 的程序 ↔ agent 通信协议（`agent-tasks.json`）。
- **ProposedWorkflow** — agent 自编排工作流计划的校验与持久化。
- **原子 action 层** — `ActionContext` / `ActionResult` 类型化契约；
  action 注册表（`register_action` / `get_action` / `list_actions`）。
- **StepRunner** — 按模板 `deterministic_steps` 顺序执行注册的 action；
  自动通过编排服务处理切点。`run_standalone()` 模式支持 CLI / agent 单步执行。
- **Context 持久化** — `save_context()` / `load_context()` /
  `clear_context()` 将共享 context 持久化到 `action-context.json`。
  StepRunner 自动加载/保存；template_id 不匹配时返回全新 context。
- **CLI（`__main__.py`）** — 完整的 agent 入口：
  `action list/info/run`、`template list/info/run`、
  `workflow run/status/choose-route/propose/push/pop`。
- **65 个单元测试**，覆盖栈、模板、action、StepRunner、编排引擎、agent 循环
  集成和 context 持久化。
