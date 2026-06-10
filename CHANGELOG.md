# Changelog

Language: English | [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-10

### Added

- **WorkflowStackStore** — LIFO stack state machine with push/pop/placeholder
  routing, persisted to `agent-workflow-stack.json`.
- **WorkflowTemplate** — declarative template registry; templates specify
  deterministic steps and agent cut-points.
- **AgentWorkflowService** — `while`-loop orchestration engine with
  `register_handler()` plugin pattern.
- **AgentTasks** — JSON-based program ↔ agent communication protocol
  (`agent-tasks.json`).
- **ProposedWorkflow** — agent-authored workflow plan validation and
  persistence.
- **Atomic action layer** — `ActionContext` / `ActionResult` typed contract;
  action registry (`register_action` / `get_action` / `list_actions`).
- **StepRunner** — executes template `deterministic_steps` via registered
  actions; auto-handles cut-points via the orchestration service.
  `run_standalone()` mode for CLI / agent one-shot execution.
- **Context persistence** — `save_context()` / `load_context()` /
  `clear_context()` persist shared context to `action-context.json`.
  StepRunner auto-loads/saves; template_id mismatch → fresh context.
- **CLI (`__main__.py`)** — full agent-facing entry point:
  `action list/info/run`, `template list/info/run`,
  `workflow run/status/choose-route/propose/push/pop`.
- **65 unit tests** covering stack, templates, actions, StepRunner,
  orchestration engine, agent loop integration, and context persistence.
