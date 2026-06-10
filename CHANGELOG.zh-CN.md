# 更新日志

语言：简体中文 | [English](CHANGELOG.md)

本项目的所有重要变更都会记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，并遵循
[语义化版本](https://semver.org/spec/v2.0.0.html)。

## [0.1.0] — 2026-06-10

### 新增

- 从 KiCad Agent Suite 首次抽离
- `WorkflowStackStore` — LIFO 栈状态机，支持 push/pop/placeholder 路由
- `WorkflowTemplate` — 声明式模板注册表，含确定性步骤和 agent 切点
- `AgentWorkflowService` — 编排引擎，while 循环驱动栈分发与恢复
- `agent_tasks.py` — 基于 JSON 的程序 ↔ agent 通信协议
- `proposed_workflow.py` — agent 自编排工作流计划与校验
