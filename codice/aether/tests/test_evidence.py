import json
import sys
import unittest
from pathlib import Path

from support import WorkspaceTemp

from aether.agent.tools import get_default_tools
from aether.evidence import EvidenceRecorder


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recorder = EvidenceRecorder(self.root, "task", task_id="task-one")

    def record(self, **options):
        values = {"artifact": "code.py", "phase": "verification", "command": ["check"],
                  "executed": False, "exit_code": None, "duration_seconds": 0}
        values.update(options)
        return self.recorder.record(**values)

    def test_not_executed_is_blocked(self):
        record = self.record(limitations=["Terminal disabled"])
        self.assertEqual(record.status, "BLOCKED")
        self.assertIsNone(record.exit_code)
        self.assertEqual(record.task_id, "task-one")

    def test_pass_fail_and_na(self):
        self.assertEqual(self.record(executed=True, exit_code=0).status, "PASS")
        self.assertEqual(self.record(executed=True, exit_code=1).status, "FAIL")
        self.assertEqual(self.record(applicable=False, limitations=["No tests for this artifact"]).status, "N/A")
        with self.assertRaises(ValueError):
            self.record(executed=False, exit_code=0)

    def test_correct_task_artifact_json_and_summary(self):
        self.record(executed=True, exit_code=0, duration_seconds=0.2)
        json_path, text_path = self.recorder.export()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["records"][0]["artifact"], "code.py")
        self.assertEqual(payload["records"][0]["task_id"], payload["task_id"])
        self.assertIsNone(payload["human_validation"])
        self.assertIn("PASS", text_path.read_text())

    def test_secrets_redacted(self):
        self.record(command=["check", "--token", "raw-secret-value"],
                    output="password=hidden sk-abcdefghijklmnop")
        path, _ = self.recorder.export()
        data = path.read_text()
        self.assertNotIn("raw-secret-value", data)
        self.assertNotIn("hidden", data)
        self.assertNotIn("sk-abcdefghijklmnop", data)

    def test_bearer_and_json_credentials_redacted(self):
        self.record(output='Authorization: Bearer sensitive-bearer\n{"token": "sensitive-json"}')
        path, _ = self.recorder.export()
        data = path.read_text()
        self.assertNotIn("sensitive-bearer", data)
        self.assertNotIn("sensitive-json", data)

    def test_artifact_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.record(artifact="../outside")

    def test_before_after_comparison(self):
        self.record(phase="before", executed=True, exit_code=0)
        self.record(phase="after", executed=True, exit_code=1)
        self.assertEqual(self.recorder.comparisons()[0]["result"], "REGRESSION")
        self.record(artifact="other.py", phase="after", executed=True, exit_code=0)
        self.assertEqual(self.recorder.comparisons()[1]["result"], "NO_BASELINE")

    def test_disabled_terminal_records_blocked(self):
        tools = get_default_tools(self.root)
        tools.evidence = self.recorder
        result = tools.execute("run_terminal", {"command": [sys.executable, "-c", "print(1)"],
                                                 "artifact": "code.py"})
        self.assertFalse(result.success)
        self.assertEqual(self.recorder.records[0].status, "BLOCKED")
        self.assertFalse(self.recorder.records[0].executed)

    def test_real_local_execution_records_metadata(self):
        tools = get_default_tools(self.root, allow_unisolated_terminal=True)
        tools.evidence = self.recorder
        result = tools.execute("run_terminal", {"command": [sys.executable, "-c", "print('observed')"],
                                                 "artifact": "code.py", "phase": "after"})
        self.assertTrue(result.success)
        record = self.recorder.records[0]
        self.assertEqual(record.status, "PASS")
        self.assertEqual(record.exit_code, 0)
        self.assertGreater(record.duration_seconds, 0)
        self.assertIn("observed", record.output)

    def test_model_cannot_assert_pass(self):
        tools = get_default_tools(self.root)
        tools.evidence = self.recorder
        self.assertFalse(tools.execute("record_evidence", {"artifact": "code.py",
            "reason": "Model says pass", "status": "PASS"}).success)
        self.assertTrue(tools.execute("record_evidence", {"artifact": "code.py",
            "reason": "Command unavailable", "command": ["check"]}).success)
        self.assertEqual(self.recorder.records[0].status, "BLOCKED")
        self.assertTrue(tools.execute("record_evidence", {"artifact": "code.py",
            "reason": "Inapplicable", "applicable": False}).success)
        self.assertEqual(self.recorder.records[1].status, "N/A")
