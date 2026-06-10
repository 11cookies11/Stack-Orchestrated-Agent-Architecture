"""CLI entry point — the agent's control panel.

Discovery::

    python -m stack_orchestrated_agent action list
    python -m stack_orchestrated_agent template list

Single-step execution::

    python -m stack_orchestrated_agent action run <name> --project /tmp/demo

Workflow orchestration (the primary agent loop)::

    python -m stack_orchestrated_agent workflow run --project /tmp/demo --template my_workflow_v1
    python -m stack_orchestrated_agent workflow status --project /tmp/demo
    python -m stack_orchestrated_agent workflow choose-route --project /tmp/demo --workflow child_v1
    python -m stack_orchestrated_agent workflow propose --project /tmp/demo --file plan.json
    python -m stack_orchestrated_agent workflow push --project /tmp/demo --workflow child_v1
    python -m stack_orchestrated_agent workflow pop --project /tmp/demo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .actions import ActionContext, get_action, list_actions, result_to_dict
from .workflow_templates import get_template, list_templates
from .step_runner import StepRunner


# ======================================================================
# Action commands
# ======================================================================


def _cmd_action_list() -> int:
    actions = list_actions()
    print(json.dumps(actions, ensure_ascii=False, indent=2))
    return 0


def _cmd_action_info(name: str) -> int:
    action = get_action(name)
    if action is None:
        print(json.dumps({"error": f"action '{name}' not found"}, ensure_ascii=False))
        return 1
    doc = (action.__doc__ or "").strip()
    print(
        json.dumps(
            {
                "name": name,
                "doc": doc,
                "signature": f"({name})(ctx: ActionContext) -> ActionResult",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_action_run(name: str, project: str) -> int:
    action = get_action(name)
    if action is None:
        print(
            json.dumps(
                {"error": f"action '{name}' not found.  Use 'action list' to see available actions."},
                ensure_ascii=False,
            )
        )
        return 1

    ctx = ActionContext(project_path=Path(project))
    try:
        result = action(ctx)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "action_error",
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))
    return 0 if result.is_ok else 2


# ======================================================================
# Template commands
# ======================================================================


def _cmd_template_list() -> int:
    templates = list_templates()
    print(json.dumps(templates, ensure_ascii=False, indent=2))
    return 0


def _cmd_template_info(template_id: str) -> int:
    tmpl = get_template(template_id)
    if tmpl is None:
        print(json.dumps({"error": f"template '{template_id}' not found"}, ensure_ascii=False))
        return 1
    print(json.dumps(tmpl.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_template_run(template_id: str, project: str) -> int:
    """Run a template's steps via StepRunner (standalone, no orchestration)."""
    tmpl = get_template(template_id)
    if tmpl is None:
        print(json.dumps({"error": f"template '{template_id}' not found"}, ensure_ascii=False))
        return 1

    runner = StepRunner()
    result = runner.run_standalone(Path(project), tmpl)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


# ======================================================================
# Workflow orchestration commands (primary agent-facing)
# ======================================================================


def _cmd_workflow_run(project: str, template: str) -> int:
    """Run the orchestration engine.  This is the main agent entry point."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.run(Path(project), template=template)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


def _cmd_workflow_status(project: str) -> int:
    """Return current orchestration state: stack, tasks, templates, handlers."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.status(Path(project))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_workflow_choose_route(project: str, workflow_id: str, reason: str) -> int:
    """Resolve a __route_pending__ placeholder."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.choose_route(Path(project), workflow_id=workflow_id, reason=reason)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_workflow_propose(project: str, file: str) -> int:
    """Accept an agent-authored workflow plan file."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.propose_workflow(Path(project), proposal_file=Path(file))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_workflow_push(project: str, workflow_id: str, reason: str) -> int:
    """Manually push a child workflow onto the stack."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.push_workflow(Path(project), workflow_id=workflow_id, reason=reason)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _cmd_workflow_pop(project: str, reason: str) -> int:
    """Manually pop the active workflow from the stack."""
    from .agent_workflow import AgentWorkflowService  # noqa: PLC0415

    svc = AgentWorkflowService()
    result = svc.pop_workflow(Path(project), reason=reason)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


# ======================================================================
# CLI wiring
# ======================================================================


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stack-orchestrated-agent",
        description="Stack-Orchestrated Agent Architecture — CLI for agent orchestration.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- action ---
    act = sub.add_parser("action", help="Discover and run registered actions")
    act_sub = act.add_subparsers(dest="action_command", required=True)

    act_list = act_sub.add_parser("list", help="List all registered actions")
    act_list.set_defaults(handler=lambda args: _cmd_action_list())

    act_info = act_sub.add_parser("info", help="Show action metadata")
    act_info.add_argument("name", help="Action name")
    act_info.set_defaults(handler=lambda args: _cmd_action_info(args.name))

    act_run = act_sub.add_parser("run", help="Execute a single action standalone")
    act_run.add_argument("name", help="Action name")
    act_run.add_argument("--project", default=".", help="Project directory (default: .)")
    act_run.set_defaults(handler=lambda args: _cmd_action_run(args.name, args.project))

    # --- template ---
    tmpl = sub.add_parser("template", help="List and inspect workflow templates")
    tmpl_sub = tmpl.add_subparsers(dest="template_command", required=True)

    tmpl_list = tmpl_sub.add_parser("list", help="List all registered templates")
    tmpl_list.set_defaults(handler=lambda args: _cmd_template_list())

    tmpl_info = tmpl_sub.add_parser("info", help="Show template metadata")
    tmpl_info.add_argument("id", help="Template workflow_id")
    tmpl_info.set_defaults(handler=lambda args: _cmd_template_info(args.id))

    tmpl_run = tmpl_sub.add_parser("run", help="Run template steps standalone (no engine)")
    tmpl_run.add_argument("id", help="Template workflow_id")
    tmpl_run.add_argument("--project", default=".", help="Project directory (default: .)")
    tmpl_run.set_defaults(handler=lambda args: _cmd_template_run(args.id, args.project))

    # --- workflow ---
    wf = sub.add_parser("workflow", help="Workflow orchestration (primary agent entry)")
    wf_sub = wf.add_subparsers(dest="workflow_command", required=True)

    wf_run = wf_sub.add_parser("run", help="Run a workflow through the orchestration engine")
    wf_run.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_run.add_argument("--template", required=True, help="Workflow template id to run")
    wf_run.set_defaults(handler=lambda args: _cmd_workflow_run(args.project, args.template))

    wf_status = wf_sub.add_parser("status", help="Show current orchestration state")
    wf_status.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_status.set_defaults(handler=lambda args: _cmd_workflow_status(args.project))

    wf_route = wf_sub.add_parser("choose-route", help="Resolve a route-pending placeholder")
    wf_route.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_route.add_argument("--workflow", required=True, help="Concrete workflow id to route to")
    wf_route.add_argument("--reason", default="agent_routed", help="Why this route was chosen")
    wf_route.set_defaults(
        handler=lambda args: _cmd_workflow_choose_route(args.project, args.workflow, args.reason)
    )

    wf_propose = wf_sub.add_parser("propose", help="Submit an agent-authored workflow plan")
    wf_propose.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_propose.add_argument("--file", required=True, help="Path to proposed workflow JSON file")
    wf_propose.set_defaults(handler=lambda args: _cmd_workflow_propose(args.project, args.file))

    wf_push = wf_sub.add_parser("push", help="Manually push a child workflow onto the stack")
    wf_push.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_push.add_argument("--workflow", required=True, help="Workflow id to push")
    wf_push.add_argument("--reason", default="", help="Why this push is happening")
    wf_push.set_defaults(
        handler=lambda args: _cmd_workflow_push(args.project, args.workflow, args.reason)
    )

    wf_pop = wf_sub.add_parser("pop", help="Manually pop the active workflow")
    wf_pop.add_argument("--project", default=".", help="Project directory (default: .)")
    wf_pop.add_argument("--reason", default="", help="Why this pop is happening")
    wf_pop.set_defaults(handler=lambda args: _cmd_workflow_pop(args.project, args.reason))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
