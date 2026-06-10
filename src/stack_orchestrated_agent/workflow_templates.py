"""Workflow template registry for agent-assisted orchestration.

A WorkflowTemplate declares the *deterministic steps* a program can execute
and the *agent cut-points* where human/agent judgment is required. Templates
are domain-agnostic — register your own via ``register()``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class WorkflowTemplate:
    """Static metadata for an agent-facing workflow template.

    Attributes:
        workflow_id: Unique identifier (e.g. ``"full_build_v1"``).
        description: Human-readable one-liner.
        deterministic_steps: Ordered steps the program handles automatically.
        agent_cut_points: Conditions that pause the workflow and wait for an agent.
        supported_task_types: Task types this workflow may emit
            (``agent_decision``, ``agent_repair``, ``agent_review``).
    """

    workflow_id: str
    description: str
    deterministic_steps: tuple[str, ...]
    agent_cut_points: tuple[str, ...]
    supported_task_types: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Thread-safe registry
# ---------------------------------------------------------------------------

_registry: dict[str, WorkflowTemplate] = {}


def register(template: WorkflowTemplate) -> None:
    """Register a workflow template.  Replaces any existing entry with the same id."""
    _registry[template.workflow_id] = template


def unregister(workflow_id: str) -> None:
    """Remove a previously registered template (no-op if not found)."""
    _registry.pop(workflow_id, None)


def get_template(workflow_id: str) -> WorkflowTemplate | None:
    """Look up a template by id."""
    return _registry.get(workflow_id)


def list_templates() -> list[dict[str, object]]:
    """Return every registered template as a list of dicts."""
    return [tmpl.to_dict() for tmpl in _registry.values()]


def clear() -> None:
    """Remove all registered templates (useful in tests)."""
    _registry.clear()
