"""Atomic action layer — typed step functions that compose into workflows.

An **action** is a plain Python function that receives an ``ActionContext``
and returns an ``ActionResult``.  Actions are registered by name so that
``WorkflowTemplate.deterministic_steps`` can reference them, and the
``StepRunner`` can execute them in sequence.

Two usage modes
---------------
1. **Inside the orchestration engine** — ``StepRunner`` is called from within a
   registered workflow handler (or the engine falls back to it automatically).
2. **From outside (agent / CLI)** — ``ActionRegistry`` exposes discovery and
   single-step execution so external agents can inspect and run actions
   without going through the full workflow loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

# ---------------------------------------------------------------------------
# Result & context types
# ---------------------------------------------------------------------------


@dataclass
class ActionResult:
    """Unified return type for every action.

    Attributes:
        status: ``"ok"`` (continue to next step), ``"cut_point"`` (pause and
            wait for agent), or ``"error"`` (recoverable failure that should
            be routed to a repair workflow).
        reason: Machine-readable reason code (e.g. ``"needs_selection"``).
        summary: Human-readable one-liner for agent tasks.
        data: Arbitrary payload to be merged into the shared context for
            downstream steps.
    """

    status: str  # "ok" | "cut_point" | "error"
    reason: str = ""
    summary: str = ""
    data: dict[str, Any] | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_cut_point(self) -> bool:
        return self.status == "cut_point"

    @property
    def is_error(self) -> bool:
        return self.status == "error"


@dataclass
class ActionContext:
    """Mutable context that flows through a sequence of actions.

    Attributes:
        project_path: Project directory (for stack/task/output files).
        data: Shared dictionary — actions read inputs from it and write
            outputs into it.  Upstream actions seed data consumed by
            downstream actions (e.g. ``"model"``, ``"ir"``).
        step_index: Zero-based index of the current step (set by the runner).
        template_id: The ``workflow_id`` of the template being executed.
    """

    project_path: Path
    data: dict[str, Any] = field(default_factory=dict)
    step_index: int = 0
    template_id: str = ""


# ---------------------------------------------------------------------------
# Action function protocol
# ---------------------------------------------------------------------------


class ActionFunc(Protocol):
    """Protocol for a registered action function."""

    def __call__(self, ctx: ActionContext) -> ActionResult: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, ActionFunc] = {}


def register_action(name: str, func: ActionFunc) -> None:
    """Register an action function under *name*.

    Replaces any existing action with the same name.
    """
    _registry[name] = func


def unregister_action(name: str) -> None:
    """Remove a registered action (no-op if not found)."""
    _registry.pop(name, None)


def get_action(name: str) -> ActionFunc | None:
    """Look up an action by name."""
    return _registry.get(name)


def list_actions() -> dict[str, dict[str, Any]]:
    """Return a dict of ``{name: metadata}`` for agent discovery.

    Each value includes the function's docstring so agents can understand
    what the action does without executing it.
    """
    result: dict[str, dict[str, Any]] = {}
    for name, func in _registry.items():
        doc = (func.__doc__ or "").strip()
        result[name] = {
            "name": name,
            "doc": doc,
            "signature": f"({name})(ctx: ActionContext) -> ActionResult",
        }
    return result


def clear_actions() -> None:
    """Remove all registered actions (useful in tests)."""
    _registry.clear()


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------


def result_to_dict(result: ActionResult) -> dict[str, Any]:
    """Serialize an ``ActionResult`` to a plain dict (for CLI / agent output)."""
    out: dict[str, Any] = {
        "status": result.status,
        "reason": result.reason,
        "summary": result.summary,
    }
    if result.data is not None:
        out["data"] = result.data
    return out


def context_to_dict(ctx: ActionContext) -> dict[str, Any]:
    """Serialize an ``ActionContext`` for inspection (excludes large data)."""
    return {
        "project_path": str(ctx.project_path),
        "step_index": ctx.step_index,
        "template_id": ctx.template_id,
        "data_keys": sorted(ctx.data.keys()) if ctx.data else [],
    }


# ---------------------------------------------------------------------------
# Context persistence — survives across run() / agent invocations
# ---------------------------------------------------------------------------

CONTEXT_SCHEMA_VERSION = "action_context.v1"
CONTEXT_FILENAME = "action-context.json"


def context_path(project_path: str | Path) -> Path:
    """Return the path to the persisted action context file."""
    return Path(project_path) / "build" / CONTEXT_FILENAME


def save_context(ctx: ActionContext) -> Path:
    """Persist *ctx* to disk so it survives across ``run()`` calls.

    Called automatically by ``StepRunner`` after every action execution.
    External agents can also call this directly after running an action
    via the CLI to persist state changes for the next workflow run.
    """
    path = context_path(ctx.project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "template_id": ctx.template_id,
        "updated_at": _now_iso(),
        "data": ctx.data,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_context(project_path: str | Path, template_id: str = "") -> ActionContext:
    """Load persisted context from disk, or return a fresh one.

    If the saved ``template_id`` differs from *template_id*, the context
    is considered stale and a fresh one is returned (prevents data from
    a different workflow leaking in).
    """
    path = context_path(project_path)
    project = Path(project_path)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        saved_template = str(payload.get("template_id", ""))
        # If template changed, start fresh
        if template_id and saved_template and saved_template != template_id:
            return ActionContext(project_path=project, template_id=template_id)
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {}
        return ActionContext(
            project_path=project,
            data=data,
            template_id=template_id or saved_template,
        )
    return ActionContext(project_path=project, template_id=template_id)


def clear_context(project_path: str | Path) -> None:
    """Remove the persisted context file (useful in tests or reset)."""
    path = context_path(project_path)
    if path.exists():
        path.unlink()


def _now_iso() -> str:
    """Return current time as ISO-8601 string (UTC, seconds precision)."""
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
