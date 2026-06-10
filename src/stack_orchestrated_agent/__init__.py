"""Stack-Orchestrated Agent Architecture — domain-agnostic orchestration framework.

Core components
---------------
- ``WorkflowStackStore`` — LIFO stack state machine persisted to JSON.
- ``WorkflowTemplate`` — declarative workflow metadata (steps + cut-points).
- ``AgentWorkflowService`` — while-loop orchestration engine with pluggable handlers.
- ``agent_tasks`` — JSON-based program ↔ agent communication protocol.
- ``proposed_workflow`` — agent-authored workflow plan validation.

Quick start::

    from stack_orchestrated_agent import (
        AgentWorkflowService,
        WorkflowTemplate,
        register,
    )

    register(WorkflowTemplate(
        workflow_id="hello_v1",
        description="A minimal example workflow.",
        deterministic_steps=("greet", "decide"),
        agent_cut_points=("needs_decision",),
        supported_task_types=("agent_review",),
    ))

    @AgentWorkflowService.register_handler("hello_v1")
    def hello_handler(service, project_path, template, **kwargs):
        return service.emit_route_task(
            project_path,
            workflow_id="hello_v1",
            task_id="route:greeting",
            reason="needs_decision",
            summary="Decide: greet the world or greet the user?",
            recommended_workflow="hello_v1",
        )

    svc = AgentWorkflowService()
    result = svc.run("/tmp/demo")
    print(result["status"])  # → "waiting_for_agent"
"""

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
from .workflow_stack import (
    STACK_FILENAME,
    STACK_SCHEMA_VERSION,
    WorkflowStackStore,
    workflow_stack_path,
)
from .workflow_templates import (
    WorkflowTemplate,
    clear,
    get_template,
    list_templates,
    register,
    unregister,
)

__all__ = [
    # --- stack ---
    "WorkflowStackStore",
    "workflow_stack_path",
    "STACK_FILENAME",
    "STACK_SCHEMA_VERSION",
    # --- templates ---
    "WorkflowTemplate",
    "register",
    "unregister",
    "get_template",
    "list_templates",
    "clear",
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
