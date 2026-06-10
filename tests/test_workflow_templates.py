"""Tests for WorkflowTemplate registry."""

from __future__ import annotations

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stack_orchestrated_agent import (
    WorkflowTemplate,
    clear,
    get_template,
    list_templates,
    register,
    unregister,
)


class TestWorkflowTemplate(unittest.TestCase):
    def setUp(self) -> None:
        clear()

    def tearDown(self) -> None:
        clear()

    def _sample(self, workflow_id: str = "test_v1") -> WorkflowTemplate:
        return WorkflowTemplate(
            workflow_id=workflow_id,
            description="A test workflow.",
            deterministic_steps=("step_a", "step_b"),
            agent_cut_points=("needs_decision",),
            supported_task_types=("agent_review",),
        )

    def test_register_and_retrieve(self) -> None:
        register(self._sample())
        tmpl = get_template("test_v1")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.workflow_id, "test_v1")
        self.assertEqual(tmpl.deterministic_steps, ("step_a", "step_b"))

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(get_template("does_not_exist"))

    def test_register_replaces_existing(self) -> None:
        register(self._sample())
        register(self._sample("test_v1"))  # same id
        self.assertEqual(len(list_templates()), 1)

    def test_unregister(self) -> None:
        register(self._sample())
        unregister("test_v1")
        self.assertIsNone(get_template("test_v1"))

    def test_unregister_nonexistent_noop(self) -> None:
        unregister("ghost")  # should not raise

    def test_list_templates(self) -> None:
        register(self._sample("a"))
        register(self._sample("b"))
        items = list_templates()
        ids = {item["workflow_id"] for item in items}
        self.assertEqual(ids, {"a", "b"})

    def test_clear(self) -> None:
        register(self._sample())
        clear()
        self.assertEqual(len(list_templates()), 0)

    def test_to_dict_roundtrip(self) -> None:
        tmpl = self._sample()
        d = tmpl.to_dict()
        self.assertEqual(d["workflow_id"], "test_v1")
        self.assertIsInstance(d["deterministic_steps"], tuple)
        self.assertIsInstance(d["agent_cut_points"], tuple)

    def test_immutable(self) -> None:
        tmpl = self._sample()
        with self.assertRaises(Exception):
            tmpl.workflow_id = "hacked"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
