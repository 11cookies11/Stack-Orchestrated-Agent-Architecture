# Changelog

Language: English | [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-10

### Added

- Initial extraction from KiCad Agent Suite
- `WorkflowStackStore` — LIFO stack state machine with push/pop/placeholder routing
- `WorkflowTemplate` — declarative template registry with deterministic steps and agent cut-points
- `AgentWorkflowService` — orchestration engine with `while`-loop stack dispatch
- `agent_tasks.py` — JSON-based program ↔ agent communication protocol
- `proposed_workflow.py` — agent-authored workflow plans with validation
