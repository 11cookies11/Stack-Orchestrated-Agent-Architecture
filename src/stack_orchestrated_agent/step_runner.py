"""StepRunner — execute ``WorkflowTemplate.deterministic_steps`` via registered actions.

Bridges the gap between template declarations and action implementations.
A handler can delegate to ``StepRunner`` instead of hand-writing step-by-step
logic.  The runner:

1. Iterates through ``template.deterministic_steps``.
2. Looks up each step name in the action registry.
3. Calls the action, threading an ``ActionContext`` across steps.
4. On ``"cut_point"`` or ``"error"`` it emits the appropriate agent task
   (via the ``AgentWorkflowService``) and stops.
5. If all steps return ``"ok"`` the workflow is ``"completed"``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .actions import (
    ActionContext,
    ActionResult,
    get_action,
    result_to_dict,
)
from .workflow_templates import WorkflowTemplate

# Forward reference — resolved at runtime to avoid circular imports.
_AgentWorkflowService: type | None = None


def _service():
    global _AgentWorkflowService
    if _AgentWorkflowService is None:
        from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

        _AgentWorkflowService = AgentWorkflowService
    return _AgentWorkflowService


# ---------------------------------------------------------------------------
# StepRunner
# ---------------------------------------------------------------------------


class StepRunner:
    """Execute a template's steps as registered actions.

    Usage inside a workflow handler::

        @AgentWorkflowService.register_handler("my_workflow_v1")
        def my_handler(service, project_path, template, **kwargs):
            runner = StepRunner()
            return runner.run(project_path, template, service)
    """

    def run(
        self,
        project_path: str | Path,
        template: WorkflowTemplate,
        service: Any | None = None,  # AgentWorkflowService instance
        *,
        initial_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute each step in *template.deterministic_steps*.

        Args:
            project_path: Project directory.
            template: The workflow template whose steps to run.
            service: ``AgentWorkflowService`` instance (for emitting tasks).
                If ``None`` a bare-bones fallback result is returned — useful
                for standalone testing but not for full orchestration.
            initial_data: Pre-populated context data (e.g. a preloaded model).

        Returns:
            A result dict compatible with the orchestration engine:
            ``status="completed"``, ``"waiting_for_agent"``, or ``"failed"``.
        """
        project = Path(project_path)
        ctx = ActionContext(
            project_path=project,
            data=dict(initial_data or {}),
            template_id=template.workflow_id,
        )

        for step_index, step_name in enumerate(template.deterministic_steps):
            ctx.step_index = step_index

            # --- resolve action -------------------------------------------------
            action = get_action(step_name)
            if action is None:
                # Step with no registered action — skip gracefully.
                # This lets templates declare informational steps that a
                # domain may choose not to implement yet.
                continue

            # --- execute --------------------------------------------------------
            try:
                result = action(ctx)
            except Exception as exc:
                if service is not None:
                    return service.emit_route_task(
                        project,
                        workflow_id=template.workflow_id,
                        task_id=f"route:action_error:{step_name}",
                        reason="action_error",
                        summary=f"Action '{step_name}' raised {type(exc).__name__}: {exc}",
                        recommended_workflow="unknown_task_v1",
                        alternatives=["unknown_task_v1"],
                        context={
                            "step_name": step_name,
                            "step_index": step_index,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "source": f"{template.workflow_id}.step.{step_name}",
                        },
                    )
                return {
                    "ok": False,
                    "stage": "step_runner",
                    "workflow_id": template.workflow_id,
                    "status": "action_error",
                    "reason": str(exc),
                    "step_name": step_name,
                    "step_index": step_index,
                }

            # --- handle result --------------------------------------------------
            if result.is_ok:
                # Merge action output data into shared context
                if result.data:
                    ctx.data.update(result.data)
                continue

            if result.is_cut_point:
                if service is not None:
                    return service.emit_route_task(
                        project,
                        workflow_id=template.workflow_id,
                        task_id=f"route:{result.reason or 'cut_point'}:{step_name}",
                        reason=result.reason or "cut_point",
                        summary=result.summary
                        or f"Step '{step_name}' requires agent input.",
                        recommended_workflow=template.workflow_id,
                        alternatives=[template.workflow_id, "unknown_task_v1"],
                        context={
                            "step_name": step_name,
                            "step_index": step_index,
                            "source": f"{template.workflow_id}.step.{step_name}",
                            **(result.data or {}),
                        },
                    )
                return {
                    "ok": False,
                    "stage": "step_runner",
                    "workflow_id": template.workflow_id,
                    "status": "cut_point",
                    "reason": result.reason,
                    "summary": result.summary,
                    "step_name": step_name,
                    "step_index": step_index,
                    "data": result.data,
                }

            if result.is_error:
                if service is not None:
                    return service.emit_route_task(
                        project,
                        workflow_id=template.workflow_id,
                        task_id=f"route:step_error:{step_name}",
                        reason=result.reason or "step_error",
                        summary=result.summary
                        or f"Step '{step_name}' failed: {result.reason}",
                        recommended_workflow="unknown_task_v1",
                        alternatives=["unknown_task_v1"],
                        context={
                            "step_name": step_name,
                            "step_index": step_index,
                            "source": f"{template.workflow_id}.step.{step_name}",
                            **(result.data or {}),
                        },
                    )
                return {
                    "ok": False,
                    "stage": "step_runner",
                    "workflow_id": template.workflow_id,
                    "status": "step_error",
                    "reason": result.reason,
                    "summary": result.summary,
                    "step_name": step_name,
                    "step_index": step_index,
                    "data": result.data,
                }

            # Unknown status — treat as error
            if service is not None:
                return service.emit_route_task(
                    project,
                    workflow_id=template.workflow_id,
                    task_id=f"route:unknown_status:{step_name}",
                    reason="unknown_action_status",
                    summary=f"Step '{step_name}' returned unknown status '{result.status}'.",
                    recommended_workflow="unknown_task_v1",
                    alternatives=["unknown_task_v1"],
                    context={
                        "step_name": step_name,
                        "step_index": step_index,
                        "action_status": result.status,
                        "source": f"{template.workflow_id}.step.{step_name}",
                    },
                )
            return {
                "ok": False,
                "stage": "step_runner",
                "workflow_id": template.workflow_id,
                "status": "unknown_action_status",
                "reason": f"Unknown action status: {result.status}",
                "step_name": step_name,
            }

        # All steps completed successfully
        return {
            "ok": True,
            "stage": "workflow",
            "workflow_id": template.workflow_id,
            "status": "completed",
            "reason": "",
            "steps_executed": len(template.deterministic_steps),
        }

    def run_standalone(
        self,
        project_path: str | Path,
        template: WorkflowTemplate,
        *,
        initial_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute steps WITHOUT emitting orchestration tasks.

        Returns a flat summary dict suitable for CLI / agent inspection.
        Each step result is recorded in ``"steps"``.
        """
        project = Path(project_path)
        ctx = ActionContext(
            project_path=project,
            data=dict(initial_data or {}),
            template_id=template.workflow_id,
        )
        steps: list[dict[str, Any]] = []

        for step_index, step_name in enumerate(template.deterministic_steps):
            ctx.step_index = step_index
            action = get_action(step_name)
            if action is None:
                steps.append(
                    {
                        "step_name": step_name,
                        "step_index": step_index,
                        "status": "no_action",
                        "reason": "no registered action",
                    }
                )
                continue

            try:
                result = action(ctx)
                steps.append(result_to_dict(result) | {"step_name": step_name, "step_index": step_index})
            except Exception as exc:
                steps.append(
                    {
                        "step_name": step_name,
                        "step_index": step_index,
                        "status": "action_error",
                        "reason": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
                return {
                    "ok": False,
                    "status": "action_error",
                    "workflow_id": template.workflow_id,
                    "steps": steps,
                }

            if result.is_ok:
                if result.data:
                    ctx.data.update(result.data)
                continue
            # Stop on first non-ok result
            return {
                "ok": False if not result.is_ok else True,
                "status": result.status,
                "workflow_id": template.workflow_id,
                "steps": steps,
            }

        return {
            "ok": True,
            "status": "completed",
            "workflow_id": template.workflow_id,
            "steps": steps,
        }
