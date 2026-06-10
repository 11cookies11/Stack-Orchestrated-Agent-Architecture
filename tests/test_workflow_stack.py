"""Tests for WorkflowStackStore — the LIFO stack state machine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stack_orchestrated_agent import (
    STACK_FILENAME,
    STACK_SCHEMA_VERSION,
    WorkflowStackStore,
    workflow_stack_path,
)


class TestWorkflowStackStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_initial_load_is_empty(self) -> None:
        store = WorkflowStackStore(self.project)
        payload = store.load()
        self.assertEqual(payload["status"], "idle")
        self.assertEqual(payload["active_workflow"], "")
        self.assertEqual(payload["stack"], [])
        self.assertEqual(payload["schema_version"], STACK_SCHEMA_VERSION)

    def test_ensure_initialises_empty_stack(self) -> None:
        store = WorkflowStackStore(self.project)
        payload = store.ensure("my_workflow")
        self.assertEqual(payload["active_workflow"], "my_workflow")
        self.assertEqual(len(payload["stack"]), 1)
        self.assertEqual(payload["stack"][0]["workflow_id"], "my_workflow")
        self.assertEqual(payload["stack"][0]["status"], "running")

    def test_ensure_is_idempotent(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("first")
        payload = store.ensure("second")
        self.assertEqual(payload["active_workflow"], "first")  # unchanged

    def test_push_and_pop(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("parent")
        store.push("child", reason="needs_selection")
        self.assertEqual(store.depth(), 2)
        self.assertEqual(store.active()["workflow_id"], "child")

        store.pop()
        self.assertEqual(store.depth(), 1)
        self.assertEqual(store.active()["workflow_id"], "parent")

    def test_pop_empty_clears_file(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("only")
        store.pop()
        self.assertTrue(store.is_empty())
        self.assertFalse(workflow_stack_path(self.project).exists())

    def test_parent_is_paused_when_child_pushed(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("parent")
        store.push("child")
        payload = store.load()
        parent = payload["stack"][0]
        self.assertEqual(parent["status"], "paused")
        self.assertEqual(parent["blocked_by"], "child")

    def test_parent_resumes_on_pop(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("parent")
        store.push("child")
        store.pop()
        parent = store.active()
        self.assertEqual(parent["status"], "running")
        self.assertNotIn("blocked_by", parent)

    def test_replace_active(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("original")
        store.replace_active("replaced", reason="reroute")
        self.assertEqual(store.depth(), 1)
        self.assertEqual(store.active()["workflow_id"], "replaced")

    def test_replace_root(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("first")
        store.push("second")
        store.replace_root("new_root")
        self.assertEqual(store.depth(), 1)
        self.assertEqual(store.active()["workflow_id"], "new_root")

    def test_push_placeholder(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("full_build")
        payload = store.push_placeholder(
            reason="needs_selection",
            task_id="route:needs_selection",
        )
        self.assertEqual(payload["active_workflow"], "__route_pending__")
        self.assertEqual(payload["status"], "waiting_for_agent")
        active = store.active()
        self.assertEqual(active["task_id"], "route:needs_selection")
        self.assertEqual(active["status"], "waiting_for_agent")

    def test_update_active(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("test_workflow")
        store.update_active(reason="processing", extra_field="value")
        active = store.active()
        self.assertEqual(active["reason"], "processing")
        self.assertEqual(active["extra_field"], "value")

    def test_clear(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("test")
        self.assertFalse(store.is_empty())
        store.clear()
        self.assertTrue(store.is_empty())

    def test_to_agent_status(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("lcsc_selection")
        status = store.to_agent_status(
            tasks_file="/tmp/tasks.json",
            pending_task_count=3,
            reason="needs_selection",
        )
        # Stack has depth=1 with an active "running" workflow — the
        # pending_task_count override only kicks in when the stack is empty.
        self.assertEqual(status["status"], "running")
        self.assertEqual(status["pending_task_count"], 3)
        self.assertIn("next_action", status)

    def test_payload_persisted_to_disk(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("disk_test")
        path = workflow_stack_path(self.project)
        self.assertTrue(path.exists())
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], STACK_SCHEMA_VERSION)
        self.assertEqual(len(raw["stack"]), 1)

    def test_peek_returns_active(self) -> None:
        store = WorkflowStackStore(self.project)
        store.ensure("only_one")
        self.assertEqual(store.peek(), store.active())


if __name__ == "__main__":
    unittest.main()
