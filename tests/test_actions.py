"""Tests for actions, ActionContext, ActionResult, and StepRunner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stack_orchestrated_agent import (
    ActionContext,
    ActionResult,
    StepRunner,
    WorkflowTemplate,
    clear_actions,
    clear_templates,
    get_action,
    list_actions,
    register_action,
    register_template,
    result_to_dict,
    context_to_dict,
    unregister_action,
)


class TestActionResult(unittest.TestCase):
    def test_ok_status(self) -> None:
        r = ActionResult(status="ok")
        self.assertTrue(r.is_ok)
        self.assertFalse(r.is_cut_point)
        self.assertFalse(r.is_error)

    def test_cut_point_status(self) -> None:
        r = ActionResult(status="cut_point", reason="needs_selection")
        self.assertTrue(r.is_cut_point)
        self.assertFalse(r.is_ok)
        self.assertFalse(r.is_error)

    def test_error_status(self) -> None:
        r = ActionResult(status="error", reason="download_failed")
        self.assertTrue(r.is_error)
        self.assertFalse(r.is_ok)
        self.assertFalse(r.is_cut_point)

    def test_carry_data(self) -> None:
        r = ActionResult(status="ok", data={"model": {"refs": ["U1"]}})
        self.assertEqual(r.data["model"]["refs"], ["U1"])

    def test_result_to_dict(self) -> None:
        r = ActionResult(status="ok", reason="done", summary="All good.", data={"k": "v"})
        d = result_to_dict(r)
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["reason"], "done")
        self.assertEqual(d["summary"], "All good.")
        self.assertEqual(d["data"], {"k": "v"})

    def test_context_to_dict(self) -> None:
        ctx = ActionContext(
            project_path=Path("/tmp/test"),
            data={"model": {}},
            step_index=2,
            template_id="test_v1",
        )
        d = context_to_dict(ctx)
        self.assertEqual(d["project_path"], str(Path("/tmp/test")))
        self.assertEqual(d["step_index"], 2)
        self.assertEqual(d["template_id"], "test_v1")
        self.assertIn("model", d["data_keys"])


class TestActionRegistry(unittest.TestCase):
    def setUp(self) -> None:
        clear_actions()

    def tearDown(self) -> None:
        clear_actions()

    def test_register_and_retrieve(self) -> None:
        def _dummy(ctx: ActionContext) -> ActionResult:
            return ActionResult(status="ok")

        register_action("dummy", _dummy)
        self.assertIsNotNone(get_action("dummy"))

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(get_action("ghost"))

    def test_unregister(self) -> None:
        def _dummy(ctx: ActionContext) -> ActionResult:
            return ActionResult(status="ok")

        register_action("dummy", _dummy)
        unregister_action("dummy")
        self.assertIsNone(get_action("dummy"))

    def test_list_actions(self) -> None:
        def _a(ctx: ActionContext) -> ActionResult:
            """Action A doc."""
            return ActionResult(status="ok")

        def _b(ctx: ActionContext) -> ActionResult:
            """Action B doc."""
            return ActionResult(status="ok")

        register_action("a", _a)
        register_action("b", _b)
        actions = list_actions()
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions["a"]["doc"], "Action A doc.")
        self.assertIn("signature", actions["a"])


class TestStepRunner(unittest.TestCase):
    def setUp(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir.cleanup()

    def test_run_standalone_all_ok(self) -> None:
        def _step_a(ctx: ActionContext) -> ActionResult:
            ctx.data["ran_a"] = True
            return ActionResult(status="ok")

        def _step_b(ctx: ActionContext) -> ActionResult:
            ctx.data["ran_b"] = True
            return ActionResult(status="ok")

        register_action("a", _step_a)
        register_action("b", _step_b)
        register_template(
            WorkflowTemplate(
                workflow_id="two_step_v1",
                description="Two-step workflow.",
                deterministic_steps=("a", "b"),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        tmpl = WorkflowTemplate(
            workflow_id="two_step_v1",
            description="x",
            deterministic_steps=("a", "b"),
            agent_cut_points=(),
            supported_task_types=(),
        )
        runner = StepRunner()
        result = runner.run_standalone(self.project, tmpl)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps"][0]["status"], "ok")
        self.assertEqual(result["steps"][1]["status"], "ok")

    def test_run_standalone_stops_on_cut_point(self) -> None:
        def _step_a(ctx: ActionContext) -> ActionResult:
            return ActionResult(status="cut_point", reason="needs_decision", summary="Pick one.")

        register_action("a", _step_a)
        register_template(
            WorkflowTemplate(
                workflow_id="cut_v1",
                description="Has a cut point.",
                deterministic_steps=("a",),
                agent_cut_points=("needs_decision",),
                supported_task_types=("agent_review",),
            )
        )

        tmpl = WorkflowTemplate(
            workflow_id="cut_v1",
            description="x",
            deterministic_steps=("a",),
            agent_cut_points=("needs_decision",),
            supported_task_types=("agent_review",),
        )
        runner = StepRunner()
        result = runner.run_standalone(self.project, tmpl)
        self.assertEqual(result["status"], "cut_point")
        self.assertEqual(result["steps"][0]["status"], "cut_point")

    def test_run_standalone_skips_unregistered_step(self) -> None:
        register_template(
            WorkflowTemplate(
                workflow_id="skip_v1",
                description="Has an unregistered step.",
                deterministic_steps=("no_action",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        tmpl = WorkflowTemplate(
            workflow_id="skip_v1",
            description="x",
            deterministic_steps=("no_action",),
            agent_cut_points=(),
            supported_task_types=(),
        )
        runner = StepRunner()
        result = runner.run_standalone(self.project, tmpl)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps"][0]["status"], "no_action")

    def test_run_standalone_catches_exception(self) -> None:
        def _crashy(ctx: ActionContext) -> ActionResult:
            raise RuntimeError("boom")

        register_action("crash", _crashy)
        tmpl = WorkflowTemplate(
            workflow_id="crash_v1",
            description="x",
            deterministic_steps=("crash",),
            agent_cut_points=(),
            supported_task_types=(),
        )
        runner = StepRunner()
        result = runner.run_standalone(self.project, tmpl)
        self.assertEqual(result["status"], "action_error")
        self.assertIn("boom", result["steps"][0]["reason"])

    def test_context_flows_data_between_steps(self) -> None:
        def _producer(ctx: ActionContext) -> ActionResult:
            return ActionResult(status="ok", data={"key": "from_producer"})

        def _consumer(ctx: ActionContext) -> ActionResult:
            self.assertEqual(ctx.data.get("key"), "from_producer")
            return ActionResult(status="ok", data={"consumed": True})

        register_action("produce", _producer)
        register_action("consume", _consumer)

        tmpl = WorkflowTemplate(
            workflow_id="flow_v1",
            description="x",
            deterministic_steps=("produce", "consume"),
            agent_cut_points=(),
            supported_task_types=(),
        )
        runner = StepRunner()
        result = runner.run_standalone(self.project, tmpl)
        self.assertEqual(result["status"], "completed")

    def test_run_with_service_emits_route_on_cut_point(self) -> None:
        pass  # Requires integration test with AgentWorkflowService — tested in test_agent_workflow


if __name__ == "__main__":
    unittest.main()
