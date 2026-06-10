"""Stack-Orchestrated Agent Architecture — domain-agnostic orchestration framework.

Core components
---------------
- ``WorkflowStackStore`` — LIFO stack state machine persisted to JSON.
- ``WorkflowTemplate`` — declarative workflow metadata (steps + cut-points).
- ``AgentWorkflowService`` — while-loop orchestration engine with pluggable handlers.
- ``agent_tasks`` — JSON-based program ↔ agent communication protocol.
- ``proposed_workflow`` — agent-authored workflow plan validation.

Atomic action layer (since 0.2.0)
----------------------------------
- ``ActionContext`` / ``ActionResult`` — typed contract for step functions.
- ``register_action`` / ``get_action`` / ``list_actions`` — action registry.
- ``StepRunner`` — execute template steps via registered actions, bridging
  the gap between declaration and implementation.

Quick start::

    from stack_orchestrated_agent import (
        AgentWorkflowService,
        WorkflowTemplate,
        ActionContext,
        ActionResult,
        register_action,
        register_template,
    )

    register_template(WorkflowTemplate(
        workflow_id="hello_v1",
        description="A minimal example workflow.",
        deterministic_steps=("greet",),
        agent_cut_points=(),
        supported_task_types=(),
    ))

    def greet(ctx: ActionContext) -> ActionResult:
        print("hello world")
        return ActionResult(status="ok")

    register_action("greet", greet)

    svc = AgentWorkflowService()
    result = svc.run("/tmp/demo", template="hello_v1")
    print(result["status"])  # → "completed"
"""

from .actions import (
    ActionContext,
    ActionResult,
    ActionFunc,
    clear_actions,
    clear_context,
    context_path,
    context_to_dict,
    get_action,
    list_actions,
    load_context,
    register_action,
    result_to_dict,
    save_context,
    unregister_action,
)
from .agent_tasks import (
    agent_tasks_path,
    clear_agent_tasks,
    current_task,
    read_agent_tasks,
    summarize_task,
    summarize_tasks,
    task_status,
    write_agent_tasks,
)
from .agent_workflow import (
    DEFAULT_WORKFLOW_ID,
    ROUTE_PENDING_WORKFLOW_ID,
    AgentWorkflowService,
    HandlerFunc,
)
from .proposed_workflow import (
    load_proposed_workflow_file,
    proposed_workflow_path,
    proposed_workflow_summary,
    save_proposed_workflow,
    validate_proposed_workflow,
)
from .step_runner import StepRunner
from .workflow_stack import (
    STACK_FILENAME,
    STACK_SCHEMA_VERSION,
    WorkflowStackStore,
    workflow_stack_path,
)
from .workflow_templates import (
    WorkflowTemplate,
    clear as clear_templates,
    get_template,
    list_templates,
    register as register_template,
    unregister as unregister_template,
)

__all__ = [
    # --- actions ---
    "ActionContext",
    "ActionResult",
    "ActionFunc",
    "register_action",
    "unregister_action",
    "get_action",
    "list_actions",
    "clear_actions",
    "result_to_dict",
    "context_to_dict",
    "context_path",
    "load_context",
    "save_context",
    "clear_context",
    # --- step runner ---
    "StepRunner",
    # --- stack ---
    "WorkflowStackStore",
    "workflow_stack_path",
    "STACK_FILENAME",
    "STACK_SCHEMA_VERSION",
    # --- templates ---
    "WorkflowTemplate",
    "register_template",
    "unregister_template",
    "get_template",
    "list_templates",
    "clear_templates",
    # --- tasks ---
    "agent_tasks_path",
    "clear_agent_tasks",
    "current_task",
    "read_agent_tasks",
    "summarize_task",
    "summarize_tasks",
    "task_status",
    "write_agent_tasks",
    # --- proposed workflow ---
    "load_proposed_workflow_file",
    "proposed_workflow_path",
    "proposed_workflow_summary",
    "save_proposed_workflow",
    "validate_proposed_workflow",
    # --- orchestration ---
    "AgentWorkflowService",
    "HandlerFunc",
    "DEFAULT_WORKFLOW_ID",
    "ROUTE_PENDING_WORKFLOW_ID",
]
