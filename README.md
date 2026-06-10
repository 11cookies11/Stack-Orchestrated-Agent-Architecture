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
version-controlled JSON files. No long-running server, no in-memory
session state — everything is rebuildable after a restart.

## Architecture layers

| Layer | File(s) | Role |
|-------|---------|------|
| **WorkflowStackStore** | `workflow_stack.py` | LIFO stack with push/pop/placeholder; persisted to disk |
| **WorkflowTemplate** | `workflow_templates.py` | Declarative template registry: deterministic steps + agent cut-points |
| **AgentWorkflowService** | `agent_workflow.py` | Orchestration engine: `while` loop over the stack, dispatch, resume |
| **StepRunner** | `step_runner.py` | Executes template steps via registered actions; auto-handles cut-points |
| **ActionContext / ActionResult** | `actions.py` | Typed contract for step functions + registry + context persistence |
| **AgentTasks** | `agent_tasks.py` | JSON task file read/write — the program ↔ agent protocol |
| **ProposedWorkflow** | `proposed_workflow.py` | Agent-authored workflow plans with validation |

## Key design decisions

1. **Stack-based nesting** — workflows can push child workflows; on
   completion the child pops and the parent resumes. Exactly like a
   function call stack.

2. **Placeholder routing** — when a milestone fails and the next step is
   ambiguous, the engine pushes a `__route_pending__` placeholder and asks
   the agent to call `choose_route()`.

3. **Idempotent & resumable** — all state lives on the filesystem. Kill
   the process, restart, call `run()` again — it picks up from the same
   stack and task files.

4. **Template-driven + action-based** — every workflow declares its
   deterministic steps. Each step name maps to a registered action
   function. Adding a workflow can be as simple as registering actions
   and declaring their order — no handler code needed.

5. **Context persistence** — the shared `ActionContext` is automatically
   persisted to `build/action-context.json` after every action execution.
   Agent modifications via `action run` survive across `workflow run`
   calls without manual file management.

6. **Agent-authored workflows** — advanced agents can propose entirely new
   workflow plans (`agent-proposed-workflow.json`) that pass through a
   validation layer before execution.

7. **CLI-first agent interface** — every capability is exposed through
   the CLI (`python -m stack_orchestrated_agent`). Agents interact via
   subprocess calls + JSON stdout — no SDK required.

## Getting started

```python
from stack_orchestrated_agent import (
    AgentWorkflowService,
    WorkflowTemplate,
    ActionContext,
    ActionResult,
    register_template,
    register_action,
)

# 1. Declare the workflow
register_template(WorkflowTemplate(
    workflow_id="hello_v1",
    description="Greet the world, with agent confirmation.",
    deterministic_steps=("greet", "confirm"),
    agent_cut_points=("needs_confirmation",),
    supported_task_types=("agent_review",),
))

# 2. Implement steps as actions
def greet(ctx: ActionContext) -> ActionResult:
    ctx.data["message"] = "hello world"
    return ActionResult(status="ok")

def confirm(ctx: ActionContext) -> ActionResult:
    if ctx.data.get("confirmed"):
        return ActionResult(status="ok")
    return ActionResult(
        status="cut_point",
        reason="needs_confirmation",
        summary=f"Approve message: {ctx.data.get('message')}",
    )

register_action("greet", greet)
register_action("confirm", confirm)

# 3. Run — returns immediately at cut-point, context saved to disk
svc = AgentWorkflowService()
result = svc.run("/tmp/demo", template="hello_v1")
# → {"status": "waiting_for_agent", "rerun_after_agent": true, ...}
```

### Agent perspective (CLI)

```bash
# Discover what's available
python -m stack_orchestrated_agent action list
python -m stack_orchestrated_agent template list

# Run a workflow
python -m stack_orchestrated_agent workflow run --project /tmp/demo --template hello_v1

# Check current state
python -m stack_orchestrated_agent workflow status --project /tmp/demo

# Execute a single action (context auto-persisted)
python -m stack_orchestrated_agent action run confirm --project /tmp/demo

# Resolve a route and rerun
python -m stack_orchestrated_agent workflow choose-route --project /tmp/demo --workflow hello_v1
python -m stack_orchestrated_agent workflow run --project /tmp/demo --template hello_v1
```

### Agent loop

```
workflow run → "waiting_for_agent" with tasks_file
     │
     ▼
workflow status → read pending task
     │
     ▼
action run <approve> → context persisted
     │
     ▼
workflow choose-route → resolve placeholder
     │
     ▼
workflow run → "completed"
```

## Filesystem protocol

```
project/
├── build/
│   ├── agent-workflow-stack.json   ← stack state
│   ├── agent-tasks.json            ← pending agent tasks
│   ├── action-context.json         ← persisted shared context
│   └── agent-proposed-workflow.json ← agent-authored plans
```

## Repository conventions

- Changelog: `CHANGELOG.md` (Keep a Changelog style)
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`), bilingual
  body (EN + 中文)
- Community docs: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`

## License

See `LICENSE`.
