"""Agent-assisted workflow orchestration — domain-agnostic engine.

This module provides the core orchestration loop: a **stack-based state
machine** that runs deterministic workflow steps and pauses at *cut-points*
for external agents (or humans) to make decisions.

Domain-specific workflow handlers are registered via ``register_handler()``
rather than being hard-coded. The orchestration engine itself has **zero**
domain knowledge — it only knows about stacks, templates, and task files.

Typical integration::

    from stack_orchestrated_agent import (
        AgentWorkflowService,
        WorkflowTemplate,
        register_handler,
    )

    # Register domain templates
    register(WorkflowTemplate(
        workflow_id="my_workflow",
        ...
    ))

    # Register domain handler
    @AgentWorkflowService.register_handler("my_workflow")
    def my_handler(service, project_path, template, **kwargs):
        ...
        return {"status": "completed"}

    service = AgentWorkflowService()
    result = service.run("/path/to/project", template="my_workflow")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .agent_tasks import (
    agent_tasks_path,
    clear_agent_tasks,
    current_task,
    read_agent_tasks,
    summarize_tasks,
    write_agent_tasks,
)
from .proposed_workflow import (
    load_proposed_workflow_file,
    proposed_workflow_summary,
    save_proposed_workflow,
    validate_proposed_workflow,
)
from .workflow_stack import WorkflowStackStore
from .workflow_templates import get_template, list_templates

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WORKFLOW_ID = "__no_template__"
ROUTE_PENDING_WORKFLOW_ID = "__route_pending__"

# ---------------------------------------------------------------------------
# Handler types
# ---------------------------------------------------------------------------

HandlerFunc = Callable[..., dict[str, Any]]
"""A workflow handler receives ``(service, project_path, template, **kwargs)``
and returns a result dict with at least a ``"status"`` key."""


# ---------------------------------------------------------------------------
# Orchestration engine
# ---------------------------------------------------------------------------


class AgentWorkflowService:
    """Run idempotent agent-assisted workflows.

    The ``run()`` method implements the core orchestration loop:

    1. Ensure the stack has an active workflow (initialise if empty).
    2. Look up the active template and its registered handler.
    3. Call the handler.  Based on the result status:

       - ``"pushed_workflow"`` — a child workflow was pushed onto the stack;
         loop and execute the child.
       - ``"completed"`` — pop the stack; if the stack is now empty, return.
         Otherwise loop and resume the parent.
       - anything else — update the active stack entry and return, allowing
         the caller (or an agent) to inspect the state and re-invoke ``run()``
         later.
    """

    # ------------------------------------------------------------------
    # Handler registry (class-level so it is shared across instances)
    # ------------------------------------------------------------------

    _handlers: dict[str, HandlerFunc] = {}

    @classmethod
    def register_handler(cls, workflow_id: str) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator that registers a domain-specific workflow handler.

        Usage::

            @AgentWorkflowService.register_handler("my_workflow_v1")
            def my_handler(service, project_path, template, **kwargs):
                ...
                return {"status": "completed"}
        """

        def _decorator(func: HandlerFunc) -> HandlerFunc:
            cls._handlers[workflow_id] = func
            return func

        return _decorator

    @classmethod
    def unregister_handler(cls, workflow_id: str) -> None:
        """Remove a registered handler (no-op if not found)."""
        cls._handlers.pop(workflow_id, None)

    @classmethod
    def list_handlers(cls) -> list[str]:
        """Return the workflow_ids of all registered handlers."""
        return list(cls._handlers.keys())

    # ------------------------------------------------------------------
    # Core orchestration loop
    # ------------------------------------------------------------------

    def run(
        self,
        project_path: str | Path,
        *,
        template: str = DEFAULT_WORKFLOW_ID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute workflows on the stack until completion or an agent cut-point.

        Args:
            project_path: Project directory (used for stack/task files).
            template: Initial workflow id when the stack is empty.
            **kwargs: Forwarded to every handler call.

        Returns:
            A result dict.  When ``"rerun_after_agent": True`` is present the
            caller is expected to let an agent resolve the pending tasks and
            then call ``run()`` again with the same ``project_path``.
        """
        project = Path(project_path)
        stack = WorkflowStackStore(project)
        stack.ensure(template)

        while True:
            active = stack.active()
            workflow_id = str(active.get("workflow_id", "")) if active else template
            workflow_template = get_template(workflow_id)

            # --- unknown template ------------------------------------------------
            if workflow_template is None:
                if workflow_id == ROUTE_PENDING_WORKFLOW_ID:
                    return self._with_stack(
                        {
                            "ok": False,
                            "stage": "workflow",
                            "status": "waiting_for_agent",
                            "reason": "route_decision_required",
                            "workflow_id": workflow_id,
                            "tasks_file": str(agent_tasks_path(project)),
                            "rerun_after_agent": True,
                        },
                        stack,
                    )
                stack.update_active(status="failed", reason="unknown_template")
                return self._with_stack(
                    {
                        "ok": False,
                        "stage": "workflow",
                        "status": "failed",
                        "reason": "unknown_template",
                        "workflow_id": workflow_id,
                        "available_templates": [
                            item["workflow_id"] for item in list_templates()
                        ],
                    },
                    stack,
                )

            # --- dispatch to registered handler -----------------------------------
            handler = self._handlers.get(workflow_id)

            if handler is None:
                # No explicit handler — try StepRunner fallback.
                # If the template's deterministic_steps name registered actions,
                # the runner can execute them automatically.
                result = self._try_step_runner(project, workflow_template)
                if result is None:
                    # Nothing registered at all — ask agent to route elsewhere.
                    result = self._no_handler_result(project, workflow_id)
            else:
                try:
                    result = handler(self, project, template=workflow_template, **kwargs)
                except Exception as exc:
                    result = {
                        "ok": False,
                        "stage": "workflow",
                        "status": "handler_error",
                        "reason": str(exc),
                        "workflow_id": workflow_id,
                    }

            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "stage": "workflow",
                    "status": "bad_handler",
                    "reason": f"handler for '{workflow_id}' returned non-dict: {type(result).__name__}",
                    "workflow_id": workflow_id,
                }

            status = str(result.get("status", ""))

            # --- pushed_workflow: child is on stack, loop to execute it ------------
            if status == "pushed_workflow":
                continue

            # --- completed: pop and resume parent (or exit) ------------------------
            if status == "completed":
                self.pop_workflow(project, reason="workflow_completed")
                if not stack.active():
                    return self._with_stack(result, stack)
                continue

            # --- agent cut-point: update stack and return --------------------------
            stack.update_active(
                status=status or "failed",
                reason=str(result.get("reason", "")),
                tasks_file=str(result.get("tasks_file", "")),
            )
            return self._with_stack(result, stack)

    # ------------------------------------------------------------------
    # Workflow status
    # ------------------------------------------------------------------

    def status(self, project_path: str | Path) -> dict[str, Any]:
        """Return the current orchestration state for an agent to consume."""
        project = Path(project_path)
        tasks = read_agent_tasks(project)
        task_list = tasks.get("tasks", [])
        if not isinstance(task_list, list):
            task_list = []
        stack_store = WorkflowStackStore(project)
        workflow = stack_store.to_agent_status(
            tasks_file=tasks.get("path", str(agent_tasks_path(project))),
            pending_task_count=int(tasks.get("task_count", 0) or 0),
            current_task=current_task(task_list),
            task_summary=summarize_tasks(task_list),
            reason=str(tasks.get("reason", "")),
        )
        if not workflow.get("active_workflow") and tasks.get("workflow_id"):
            workflow["active_workflow"] = tasks.get("workflow_id", "")
        workflow["proposed_workflow"] = proposed_workflow_summary(project)
        return {
            "ok": True,
            "stage": "workflow_status",
            "workflow": workflow,
            "templates": list_templates(),
            "registered_handlers": self.list_handlers(),
        }

    # ------------------------------------------------------------------
    # Stack manipulation helpers
    # ------------------------------------------------------------------

    def push_workflow(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Push a child workflow onto the stack (pauses the current active)."""
        template = get_template(workflow_id)
        if template is None:
            return {
                "ok": False,
                "stage": "workflow_push",
                "status": "failed",
                "reason": "unknown_template",
                "workflow_id": workflow_id,
            }
        stack = WorkflowStackStore(project_path)
        payload = stack.push(workflow_id, reason=reason)
        return {
            "ok": True,
            "stage": "workflow_action",
            "action": "push_workflow",
            "status": payload.get("status", "running"),
            "workflow_id": workflow_id,
            "workflow": stack.summary(),
        }

    def pop_workflow(
        self,
        project_path: str | Path,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        """Pop the active workflow from the stack (resumes the parent)."""
        stack = WorkflowStackStore(project_path)
        before = stack.summary()
        active = before.get("active_workflow", "")
        payload = stack.pop()
        after = stack.summary()
        return {
            "ok": True,
            "stage": "workflow_action",
            "action": "pop_workflow",
            "reason": reason,
            "workflow_id": active,
            "status": payload.get("status", "idle"),
            "workflow": after,
        }

    def push(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Backward-compatible alias for ``push_workflow``."""
        return self.push_workflow(project_path, workflow_id=workflow_id, reason=reason)

    def propose_workflow(
        self,
        project_path: str | Path,
        *,
        proposal_file: str | Path,
    ) -> dict[str, Any]:
        """Accept an agent-authored workflow plan, validate it, and activate it."""
        project = Path(project_path)
        plan = load_proposed_workflow_file(proposal_file)
        validation = validate_proposed_workflow(plan)
        path = save_proposed_workflow(project, plan, validation)
        if not validation.get("ok"):
            return {
                "ok": False,
                "stage": "workflow_propose",
                "status": "failed",
                "reason": "invalid_proposed_workflow",
                "proposal_file": str(path),
                "validation": validation,
            }
        workflow_id = f"agent_proposed:{validation.get('workflow_id')}"
        stack = WorkflowStackStore(project)
        payload = stack.replace_active(
            workflow_id,
            reason=str(plan.get("reason", "agent_proposed_workflow")),
            status="waiting_for_agent_execution",
            proposed_workflow_file=str(path),
        )
        return {
            "ok": True,
            "stage": "workflow_propose",
            "status": "waiting_for_agent_execution",
            "workflow_id": workflow_id,
            "proposal_file": str(path),
            "validation": validation,
            "workflow": WorkflowStackStore(project).summary(),
            "stack": payload,
        }

    def choose_route(
        self,
        project_path: str | Path,
        *,
        workflow_id: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Resolve a ``__route_pending__`` placeholder by selecting a concrete workflow.

        This is called by an agent after reviewing a route-decision task.
        """
        project = Path(project_path)
        template = get_template(workflow_id)
        if template is None:
            return {
                "ok": False,
                "stage": "workflow_choose_route",
                "status": "failed",
                "reason": "unknown_template",
                "workflow_id": workflow_id,
            }
        stack = WorkflowStackStore(project)
        active = stack.active()
        if not active or str(active.get("workflow_id", "")) != ROUTE_PENDING_WORKFLOW_ID:
            return {
                "ok": False,
                "stage": "workflow_choose_route",
                "status": "failed",
                "reason": "no_route_pending",
                "workflow_id": workflow_id,
                "workflow": stack.summary(),
            }
        clear_agent_tasks(project)
        payload = stack.replace_active(
            workflow_id,
            reason=reason or str(active.get("reason", "route_chosen")),
            status="running",
            chosen_from=ROUTE_PENDING_WORKFLOW_ID,
        )
        return {
            "ok": True,
            "stage": "workflow_choose_route",
            "status": "route_chosen",
            "workflow_id": workflow_id,
            "workflow": stack.summary(),
            "stack": payload,
        }

    # ------------------------------------------------------------------
    # Default handler helpers
    # ------------------------------------------------------------------

    def emit_route_task(
        self,
        project_path: Path,
        *,
        workflow_id: str,
        task_id: str,
        reason: str,
        summary: str,
        recommended_workflow: str,
        alternatives: list[str] | None = None,
        context: dict[str, Any] | None = None,
        allowed_actions: list[str] | None = None,
        blocked_by: str = "",
    ) -> dict[str, Any]:
        """Emit a routing-decision task and push a ``__route_pending__`` placeholder.

        Domain handlers call this when they hit a cut-point where the next
        workflow route must be chosen by an agent.

        Returns a result dict with ``status="waiting_for_agent"`` — handlers
        should return this directly.
        """
        if allowed_actions is None:
            allowed_actions = [
                "confirm_route",
                "choose_alternative",
                "propose_workflow",
                "needs_human_review",
                "mark_blocked",
            ]
        if alternatives is None:
            alternatives = [recommended_workflow]
        if context is None:
            context = {}
        context["blocked_by"] = blocked_by

        tasks_file = write_agent_tasks(
            project_path,
            workflow_id=workflow_id,
            tasks=[
                {
                    "task_id": task_id,
                    "type": "agent_review",
                    "decision_schema": "choose_workflow_route_v1",
                    "reason": reason,
                    "summary": summary,
                    "recommended_workflow": recommended_workflow,
                    "alternatives": alternatives,
                    "context": context,
                    "allowed_actions": allowed_actions,
                }
            ],
            reason="route_decision_required",
        )
        WorkflowStackStore(project_path).push_placeholder(
            reason=reason,
            task_id=task_id,
            tasks_file=str(tasks_file),
            recommended_workflow=recommended_workflow,
        )
        return {
            "ok": False,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "waiting_for_agent",
            "reason": "route_decision_required",
            "tasks_file": str(tasks_file),
            "task_count": 1,
            "route": {
                "reason": reason,
                "recommended_workflow": recommended_workflow,
                "alternatives": alternatives,
            },
            "rerun_after_agent": True,
            "next_action": "choose a workflow route, propose a workflow, or request human review",
        }

    def emit_agent_tasks(
        self,
        project_path: Path,
        *,
        workflow_id: str,
        tasks: list[dict[str, Any]],
        reason: str,
        next_action: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """Emit agent tasks and return a ``waiting_for_agent`` result.

        Convenience helper for domain handlers — writes the task file and
        returns a properly-shaped result dict.
        """
        tasks_file = write_agent_tasks(
            project_path,
            workflow_id=workflow_id,
            tasks=tasks,
            reason=reason,
        )
        result: dict[str, Any] = {
            "ok": False,
            "stage": "workflow",
            "workflow_id": workflow_id,
            "status": "waiting_for_agent",
            "reason": reason,
            "tasks_file": str(tasks_file),
            "task_count": len(tasks),
            "rerun_after_agent": True,
        }
        if next_action:
            result["next_action"] = next_action
        result.update(extra)
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _try_step_runner(
        self,
        project: Path,
        template: Any,  # WorkflowTemplate
    ) -> dict[str, Any] | None:
        """Attempt to execute *template* via the StepRunner.

        Returns a result dict if at least one step has a registered action,
        otherwise ``None`` (caller should fall back to ``_no_handler_result``).

        Uses ``runner.run()`` (not ``run_standalone``) so that cut_points
        trigger proper orchestration tasks and stack placeholders.
        """
        from .actions import get_action  # noqa: PLC0415
        from .step_runner import StepRunner  # noqa: PLC0415

        # Only use StepRunner if there is at least one actionable step
        steps = getattr(template, "deterministic_steps", ())
        has_action = any(get_action(step) is not None for step in steps)
        if not has_action:
            return None

        runner = StepRunner()
        return runner.run(project, template, self)

    @staticmethod
    def _with_stack(result: dict[str, Any], stack: WorkflowStackStore) -> dict[str, Any]:
        """Attach the current stack summary to a result dict."""
        return {**result, "workflow": stack.summary()}

    @staticmethod
    def _no_handler_result(project: Path, workflow_id: str) -> dict[str, Any]:
        """Return a result indicating no handler is registered for the workflow."""
        return {
            "ok": False,
            "stage": "workflow",
            "status": "no_handler",
            "reason": f"no handler registered for workflow '{workflow_id}'",
            "workflow_id": workflow_id,
            "registered_handlers": list(AgentWorkflowService._handlers.keys()),
        }
