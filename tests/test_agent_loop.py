"""Integration test — full agent loop through CLI.

Simulates what a real external agent does:
1. Discover actions and templates
2. Run workflow → hit cut_point
3. Read status → find pending task
4. Choose route → workflow resumes
5. Run again → completes
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stack_orchestrated_agent import (
    ActionContext,
    ActionResult,
    AgentWorkflowService,
    StepRunner,
    WorkflowTemplate,
    clear_actions,
    clear_templates,
    get_action,
    register_action,
    register_template,
)
from stack_orchestrated_agent.__main__ import _build_parser


class TestAgentLoopEndToEnd(unittest.TestCase):
    """Run the full agent loop programmatically (Python API)."""

    def setUp(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir.cleanup()

    def test_full_agent_loop(self) -> None:
        """Agent discovers a cut_point, reads the task, routes, completes."""
        # --- Setup: register a two-step workflow with a cut_point ---
        # The gate action is idempotent via persisted context data.
        # Context now survives across run() calls automatically.
        def _gate(ctx: ActionContext) -> ActionResult:
            """First step — requires agent confirmation on first pass only."""
            if ctx.data.get("gate_passed"):
                return ActionResult(status="ok")
            return ActionResult(
                status="cut_point",
                reason="needs_permission",
                summary="Agent must confirm before proceeding.",
            )

        def _pass_gate(ctx: ActionContext) -> ActionResult:
            """Mark the gate as passed — called by agent via action run.
            Writes to context data which is auto-persisted by the framework."""
            ctx.data["gate_passed"] = True
            return ActionResult(status="ok")

        def _worker(ctx: ActionContext) -> ActionResult:
            """Second step — runs after agent routes back."""
            ctx.data["worker_ran"] = True
            return ActionResult(status="ok")

        register_action("gate", _gate)
        register_action("pass_gate", _pass_gate)
        register_action("work", _worker)

        register_template(
            WorkflowTemplate(
                workflow_id="gated_v1",
                description="A gated workflow that requires agent confirmation.",
                deterministic_steps=("gate", "work"),
                agent_cut_points=("needs_permission",),
                supported_task_types=("agent_review",),
            )
        )
        register_template(
            WorkflowTemplate(
                workflow_id="worker_v1",
                description="The worker sub-workflow.",
                deterministic_steps=("work",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        # --- Agent step 1: run workflow → should hit cut_point ---
        svc = AgentWorkflowService()
        result = svc.run(self.project, template="gated_v1")
        self.assertEqual(result["status"], "waiting_for_agent")
        self.assertTrue(result["rerun_after_agent"])
        self.assertIn("tasks_file", result)

        # --- Agent step 2: read workflow status ---
        status = svc.status(self.project)
        self.assertEqual(status["workflow"]["status"], "waiting_for_agent")
        pending = status["workflow"]["pending_task_count"]
        self.assertGreaterEqual(pending, 1)

        # Agent reads the task file and sees:
        #   task_id: "route:needs_permission:gate"
        #   recommended_workflow: "gated_v1"
        #   allowed_actions: ["confirm_route", "choose_alternative", ...]

        # --- Agent step 3: mark gate as passed via persisted context + resolve route ---
        from stack_orchestrated_agent import load_context, save_context
        ctx = load_context(self.project)
        pass_result = _pass_gate(ctx)
        save_context(ctx)
        self.assertEqual(pass_result.status, "ok")
        route_result = svc.choose_route(
            self.project,
            workflow_id="gated_v1",
            reason="agent_approved",
        )
        self.assertTrue(route_result["ok"])

        # --- Agent step 4: rerun workflow → gate passes, work runs → completed ---
        result2 = svc.run(self.project, template="gated_v1")
        self.assertEqual(result2["status"], "completed")
        self.assertEqual(result2["workflow"]["depth"], 0)


class TestAgentLoopViaCLI(unittest.TestCase):
    """Simulate agent interactions through the CLI argument parser.

    These tests call the same handler functions that ``__main__`` uses,
    so they verify the CLI protocol without spawning subprocesses.
    """

    def setUp(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = str(Path(self.tmpdir.name).resolve())

    def tearDown(self) -> None:
        clear_actions()
        clear_templates()
        self.tmpdir.cleanup()

    def test_agent_discovers_actions(self) -> None:
        def _dummy(ctx: ActionContext) -> ActionResult:
            """Dummy action for discovery."""
            return ActionResult(status="ok")

        register_action("discover_me", _dummy)
        parser = _build_parser()
        args = parser.parse_args(["action", "list"])
        self.assertEqual(args.handler(args), 0)

    def test_agent_discovers_templates(self) -> None:
        register_template(
            WorkflowTemplate(
                workflow_id="discover_v1",
                description="A discoverable template.",
                deterministic_steps=(),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )
        parser = _build_parser()
        args = parser.parse_args(["template", "list"])
        self.assertEqual(args.handler(args), 0)

    def test_agent_runs_single_action(self) -> None:
        def _greet(ctx: ActionContext) -> ActionResult:
            ctx.data["greeted"] = True
            return ActionResult(status="ok", reason="done", summary="Greeting complete.")

        register_action("greet", _greet)
        parser = _build_parser()
        args = parser.parse_args(["action", "run", "greet", "--project", self.project])
        self.assertEqual(args.handler(args), 0)

    def test_agent_full_loop_via_cli(self) -> None:
        """CLI-level agent loop: register → run → cut → route → complete."""
        # --- Setup templates and actions ---
        def _review(ctx: ActionContext) -> ActionResult:
            if ctx.data.get("reviewed"):
                return ActionResult(status="ok")
            return ActionResult(
                status="cut_point",
                reason="needs_review",
                summary="Agent must review.",
            )

        def _approve(ctx: ActionContext) -> ActionResult:
            ctx.data["reviewed"] = True
            return ActionResult(status="ok")

        def _finalize(ctx: ActionContext) -> ActionResult:
            return ActionResult(status="ok", data={"done": True})

        register_action("review", _review)
        register_action("approve", _approve)
        register_action("finalize", _finalize)

        register_template(
            WorkflowTemplate(
                workflow_id="review_gated_v1",
                description="Review-gated workflow.",
                deterministic_steps=("review", "finalize"),
                agent_cut_points=("needs_review",),
                supported_task_types=("agent_review",),
            )
        )
        register_template(
            WorkflowTemplate(
                workflow_id="finalize_v1",
                description="Finalize only.",
                deterministic_steps=("finalize",),
                agent_cut_points=(),
                supported_task_types=(),
            )
        )

        parser = _build_parser()

        # --- Agent: workflow run → cut_point ---
        args = parser.parse_args(
            ["workflow", "run", "--project", self.project, "--template", "review_gated_v1"]
        )
        # Capture stdout by patching — for now just verify no exception
        exit_code = args.handler(args)
        self.assertEqual(exit_code, 2)  # 2 = cut_point / not ok

        # --- Agent: check status ---
        args = parser.parse_args(["workflow", "status", "--project", self.project])
        exit_code = args.handler(args)
        self.assertEqual(exit_code, 0)

        # --- Agent: choose route ---
        args = parser.parse_args(
            [
                "workflow",
                "choose-route",
                "--project",
                self.project,
                "--workflow",
                "review_gated_v1",
                "--reason",
                "agent_approved",
            ]
        )
        exit_code = args.handler(args)
        self.assertEqual(exit_code, 0)

        # --- Agent: call the "approve" action to satisfy the gate ---
        args = parser.parse_args(
            ["action", "run", "approve", "--project", self.project]
        )
        exit_code = args.handler(args)
        self.assertEqual(exit_code, 0)  # 0 = ok

        # --- Agent: rerun → completed ---
        args = parser.parse_args(
            ["workflow", "run", "--project", self.project, "--template", "review_gated_v1"]
        )
        exit_code = args.handler(args)
        self.assertEqual(exit_code, 0)  # 0 = completed


if __name__ == "__main__":
    unittest.main()
