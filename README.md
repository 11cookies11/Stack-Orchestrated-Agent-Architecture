# Stack-Orchestrated Agent Architecture

A deterministic program ↔ AI agent collaboration framework built on a
**stack-based state machine**. Programs run known steps; at uncertainty
cut-points they emit structured JSON task files and pause. External agents
(or humans) read the tasks, make decisions, and hand control back — the
stack resumes exactly where it left off.

Language: English | [简体中文](README.zh-CN.md)

## Core idea

```
Program (deterministic steps)    Agent (uncertainty decisions)
        │                              │
        ├── step 1 ──────────────────► │
        ├── step 2                     │
        ├── step 3 → cut point         │
        │    │                         │
        │    ▼    agent-tasks.json     │
        │    ──────────────────────►   │  read / decide / write
        │    ◄──────────────────────   │
        │    │                         │
        ├── resume step 4              │
        ▼                              ▼
```

The protocol is **filesystem-based**: every interaction passes through
version-controlled JSON files (`agent-workflow-stack.json`,
`agent-tasks.json`). No long-running server, no in-memory session state —
everything is rebuildable after a restart.

## Architecture layers

| Layer | File(s) | Role |
|-------|---------|------|
| **WorkflowStackStore** | `workflow_stack.py` | LIFO stack with push/pop/placeholder; persisted to disk |
| **WorkflowTemplate** | `workflow_templates.py` | Declarative template registry: deterministic steps + agent cut-points |
| **AgentWorkflowService** | `agent_workflow.py` | Orchestration engine: `while` loop over the stack, dispatch, resume |
| **AgentTasks** | `agent_tasks.py` | JSON task file read/write — the program ↔ agent protocol |
| **ProposedWorkflow** | `proposed_workflow.py` | Agent-authored workflow plans with validation |

## Key design decisions

1. **Stack-based nesting** — workflows can push child workflows; on
   completion the child pops and the parent resumes. Exactly like a
   function call stack.

2. **Placeholder routing** — when a milestone fails and the next step is
   ambiguous, the engine pushes a `__route_pending__` placeholder and asks
   the agent to `choose_route()`.

3. **Idempotent & resumable** — all state lives on the filesystem. Kill
   the process, restart, call `run()` again — it picks up from the same
   stack and task files.

4. **Template-driven** — every workflow declares its deterministic steps
   and agent cut-points upfront. Adding a new workflow means registering a
   template + writing one handler function.

5. **Agent-authored workflows** — advanced agents can propose entirely new
   workflow plans (`agent-proposed-workflow.json`) that pass through a
   validation layer before execution.

## Getting started

```python
from orchestration import AgentWorkflowService

service = AgentWorkflowService()
result = service.run(
    project_path="/path/to/project",
    template="full_build_v1",
)
# → returns immediately if agent input is needed,
#   with task file path and "rerun_after_agent": True
```

## Repository conventions

- Changelog: `CHANGELOG.md` (Keep a Changelog style)
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`)
- Community docs: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`

## License

See `LICENSE`.
