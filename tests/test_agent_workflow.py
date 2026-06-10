"""Tests for AgentWorkflowService — the orchestration engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stack_orchestrated_agent import (
    AgentWorkflowService,
    WorkflowTemplate,
    clear_actions,
    clear_templates,
    register_template,
)


class TestAgentWorkflowService(unittest.TestCase):
    def setUp(self) -> None:
        clear_templates()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        clear_templates()
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register_pass_through(self, workflow_id: str = "test_v1") -> None:
        """Register a template + handler that immediately completes."""
        register_template(
            WorkflowTemplate(
                workflow_id=workflow_id,
                description="Pass-through workflow for testing.",
                deterministic_steps=("done",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        @AgentWorkflowService.register_handler(workflow_id)
        def _handler(service, project_path, template, **kwargs):
            return {"status": "completed", "workflow_id": template.workflow_id}

    def _register_route_needed(self, workflow_id: str = "needs_route_v1") -> None:
        """Register a template + handler that emits a route task."""
        register_template(
            WorkflowTemplate(
                workflow_id=workflow_id,
                description="Workflow that needs routing.",
                deterministic_steps=("check",),
                agent_cut_points=("needs_selection",),
                supported_task_types=("agent_review",),
            )
        )

        @AgentWorkflowService.register_handler(workflow_id)
        def _handler(service, project_path, template, **kwargs):
            return service.emit_route_task(
                project_path,
                workflow_id=template.workflow_id,
                task_id="route:test",
                reason="needs_selection",
                summary="Agent must choose a route.",
                recommended_workflow="target_v1",
            )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_run_completes_immediately(self) -> None:
        self._register_pass_through()
        svc = AgentWorkflowService()
        result = svc.run(self.project, template="test_v1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["workflow"]["depth"], 0)

    def test_run_returns_waiting_for_agent_on_route(self) -> None:
        self._register_route_needed()
        svc = AgentWorkflowService()
        result = svc.run(self.project, template="needs_route_v1")
        self.assertEqual(result["status"], "waiting_for_agent")
        self.assertEqual(result["reason"], "route_decision_required")
        self.assertIn("tasks_file", result)
        self.assertTrue(result["rerun_after_agent"])

    def test_run_unknown_template_fails(self) -> None:
        svc = AgentWorkflowService()
        result = svc.run(self.project, template="does_not_exist")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "unknown_template")

    def test_run_no_handler_returns_no_handler_status(self) -> None:
        register_template(
            WorkflowTemplate(
                workflow_id="no_handler_v1",
                description="Template with no handler.",
                deterministic_steps=("step",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )
        svc = AgentWorkflowService()
        result = svc.run(self.project, template="no_handler_v1")
        self.assertEqual(result["status"], "no_handler")

    def test_choose_route_success(self) -> None:
        self._register_route_needed()
        register_template(
            WorkflowTemplate(
                workflow_id="target_v1",
                description="Target workflow.",
                deterministic_steps=("done",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )
        svc = AgentWorkflowService()
        svc.run(self.project, template="needs_route_v1")  # pauses
        result = svc.choose_route(self.project, workflow_id="target_v1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["workflow_id"], "target_v1")

    def test_choose_route_when_no_pending_fails(self) -> None:
        register_template(
            WorkflowTemplate(
                workflow_id="any",
                description="Any workflow.",
                deterministic_steps=(),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )
        svc = AgentWorkflowService()
        svc.run(self.project, template="any")  # ensure stack exists but isn't __route_pending__
        result = svc.choose_route(self.project, workflow_id="any")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "no_route_pending")

    def test_push_and_pop_workflow(self) -> None:
        self._register_pass_through("child_v1")
        self._register_pass_through("parent_v1")
        svc = AgentWorkflowService()
        svc.run(self.project, template="parent_v1")  # completes immediately
        push_result = svc.push_workflow(self.project, workflow_id="child_v1")
        self.assertTrue(push_result["ok"])
        self.assertEqual(push_result["workflow_id"], "child_v1")

        pop_result = svc.pop_workflow(self.project)
        self.assertTrue(pop_result["ok"])

    def test_push_unknown_template_fails(self) -> None:
        svc = AgentWorkflowService()
        result = svc.push_workflow(self.project, workflow_id="ghost")
        self.assertFalse(result["ok"])

    def test_status_idle(self) -> None:
        svc = AgentWorkflowService()
        result = svc.status(self.project)
        self.assertTrue(result["ok"])
        self.assertIn("workflow", result)
        self.assertIn("templates", result)

    def test_status_after_route(self) -> None:
        self._register_route_needed()
        svc = AgentWorkflowService()
        svc.run(self.project, template="needs_route_v1")
        result = svc.status(self.project)
        self.assertEqual(result["workflow"]["status"], "waiting_for_agent")

    def test_emit_agent_tasks(self) -> None:
        svc = AgentWorkflowService()
        result = svc.emit_agent_tasks(
            self.project,
            workflow_id="test_v1",
            tasks=[
                {
                    "task_id": "fix:1",
                    "type": "agent_repair",
                    "reason": "must_fix",
                    "summary": "Fix something.",
                }
            ],
            reason="needs_fix",
            next_action="Fix the issue and rerun.",
        )
        self.assertEqual(result["status"], "waiting_for_agent")
        self.assertEqual(result["task_count"], 1)
        self.assertTrue(result["rerun_after_agent"])

    def test_register_handler_decorator(self) -> None:
        @AgentWorkflowService.register_handler("decorated_v1")
        def _handler(service, project_path, template, **kwargs):
            return {"status": "completed"}

        self.assertIn("decorated_v1", AgentWorkflowService.list_handlers())

    def test_unregister_handler(self) -> None:
        @AgentWorkflowService.register_handler("temp_v1")
        def _handler(service, project_path, template, **kwargs):
            return {"status": "completed"}

        AgentWorkflowService.unregister_handler("temp_v1")
        self.assertNotIn("temp_v1", AgentWorkflowService.list_handlers())

    def test_handler_error_is_caught(self) -> None:
        register_template(
            WorkflowTemplate(
                workflow_id="crashy_v1",
                description="This handler crashes.",
                deterministic_steps=(),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        @AgentWorkflowService.register_handler("crashy_v1")
        def _handler(service, project_path, template, **kwargs):
            raise ValueError("deliberate crash")

        svc = AgentWorkflowService()
        result = svc.run(self.project, template="crashy_v1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "handler_error")
        self.assertIn("deliberate crash", result["reason"])

    def test_pushed_workflow_triggers_child_execution(self) -> None:
        """Parent pushes child; stack runs child next loop iteration."""
        register_template(
            WorkflowTemplate(
                workflow_id="parent_pusher_v1",
                description="Pushes a child.",
                deterministic_steps=("push",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        @AgentWorkflowService.register_handler("parent_pusher_v1")
        def _parent(service, project_path, template, **kwargs):
            # Idempotent guard: only push the child once per run.
            # Use a marker file so the handler doesn't re-push when
            # the parent becomes active again after the child pops.
            marker = Path(project_path) / "build" / ".child_pushed"
            if marker.exists():
                marker.unlink()
                return {"status": "completed"}
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            service.push_workflow(project_path, workflow_id="auto_child_v1", reason="delegate")
            return {"status": "pushed_workflow"}

        register_template(
            WorkflowTemplate(
                workflow_id="auto_child_v1",
                description="Auto child.",
                deterministic_steps=("done",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        @AgentWorkflowService.register_handler("auto_child_v1")
        def _child(service, project_path, template, **kwargs):
            return {"status": "completed"}

        svc = AgentWorkflowService()
        result = svc.run(self.project, template="parent_pusher_v1")
        self.assertEqual(result["status"], "completed")
        # Stack should be empty after both parent and child complete
        self.assertEqual(result["workflow"]["depth"], 0)


if __name__ == "__main__":
    unittest.main()
