"""CLI entry point for agent action discovery and execution.

Usage::

    python -m stack_orchestrated_agent action list
    python -m stack_orchestrated_agent action run <name> --project /tmp/demo
    python -m stack_orchestrated_agent action info <name>
    python -m stack_orchestrated_agent template list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .actions import ActionContext, get_action, list_actions, result_to_dict
from .workflow_templates import get_template, list_templates
from .step_runner import StepRunner


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
        print(json.dumps({"error": f"action '{name}' not found.  Use 'action list' to see available actions."}, ensure_ascii=False))
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
    tmpl = get_template(template_id)
    if tmpl is None:
        print(json.dumps({"error": f"template '{template_id}' not found"}, ensure_ascii=False))
        return 1

    runner = StepRunner()
    result = runner.run_standalone(Path(project), tmpl)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stack-orchestrated-agent",
        description="Stack-Orchestrated Agent Architecture — CLI for action and template discovery.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- action sub-commands ---
    act = sub.add_parser("action", help="Manage registered actions")
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

    # --- template sub-commands ---
    tmpl = sub.add_parser("template", help="Manage workflow templates")
    tmpl_sub = tmpl.add_subparsers(dest="template_command", required=True)

    tmpl_list = tmpl_sub.add_parser("list", help="List all registered templates")
    tmpl_list.set_defaults(handler=lambda args: _cmd_template_list())

    tmpl_info = tmpl_sub.add_parser("info", help="Show template metadata")
    tmpl_info.add_argument("id", help="Template workflow_id")
    tmpl_info.set_defaults(handler=lambda args: _cmd_template_info(args.id))

    tmpl_run = tmpl_sub.add_parser("run", help="Run a template's steps via StepRunner (standalone)")
    tmpl_run.add_argument("id", help="Template workflow_id")
    tmpl_run.add_argument("--project", default=".", help="Project directory (default: .)")
    tmpl_run.set_defaults(handler=lambda args: _cmd_template_run(args.id, args.project))

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
