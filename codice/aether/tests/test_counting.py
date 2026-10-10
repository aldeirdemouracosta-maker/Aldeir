import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from support import WorkspaceTemp

from aether.agent import AetherAgent
from aether.agent.counting import count_python_paths, is_project_python_count
from aether.agent.tools import get_default_tools
from aether.config import AetherConfig

TASK = "Olá, me diga quantos arquivos Python existem neste projeto"


class CountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, path):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")

    def test_scopes_exclusions_and_legitimate_tmp_code(self):
        for path in ["one.py", "src/two.PY", "tmp/legit.py", "src/tmp/other.py"]:
            self.file(path)
        for path in [".git/a.py", ".venv/a.py", "__pycache__/a.py", ".pytest_cache/a.py",
                     ".mypy_cache/a.py", ".ruff_cache/a.py", ".aether/evidence/generated.py"]:
            self.file(path)
        self.file("notes.txt")
        report = count_python_paths(self.root)
        self.assertEqual(report["count"], 4)
        self.assertFalse(report["partial"])
        self.assertEqual(report["scope"], ".")
        self.assertEqual(count_python_paths(self.root, "src")["count"], 2)
        self.assertEqual(count_python_paths(self.root, ".venv")["count"], 0)

    def test_inaccessible_directory_is_reported_and_count_is_partial(self):
        self.file("one.py")
        self.file("private/hidden.py")
        scandir = os.scandir

        def blocked(path):
            if Path(path).name == "private":
                raise PermissionError("access denied")
            return scandir(path)

        with patch("aether.agent.counting.os.scandir", side_effect=blocked):
            report = count_python_paths(self.root)
        self.assertEqual(report["count"], 1)
        self.assertTrue(report["partial"])
        self.assertEqual(report["inaccessible_paths"][0]["path"], "private")

    def test_outside_paths_and_junctions_remain_blocked(self):
        tools = get_default_tools(self.root)
        self.assertFalse(tools.execute("count_python_files", {"path": ".."}).success)
        self.file("linked/hidden.py")
        with patch.object(Path, "is_junction", lambda path: path.name == "linked"):
            report = count_python_paths(self.root)
            self.assertEqual(report["count"], 0)
            self.assertEqual(report["excluded_paths"][0]["reason"], "link")
            with self.assertRaisesRegex(ValueError, "vinculado"):
                count_python_paths(self.root, "linked")
        self.assertNotIn("run_terminal", tools.available_tools)

    def test_exact_task_completes_without_model_counting_or_inference(self):
        self.file("tmp/legit.py")

        class NoModel:
            def chat(self, *args, **kwargs):
                raise AssertionError("The model must not count paths")

        agent = AetherAgent(AetherConfig(project_root=self.root), llm=NoModel(),
                            on_plan=lambda _: None)
        result = agent.run(TASK)
        self.assertIn("1 arquivos Python", result)
        self.assertEqual(agent.last_outcome.status, "completed")
        payload = json.loads((self.root / ".aether/evidence" /
                              f"{agent.last_evidence.task_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["task_outcome"]["code"], "completed")
        self.assertEqual(payload["tool_events"][0]["data"]["count"], 1)

    def test_partial_task_returns_observed_count_and_reason(self):
        self.file("one.py")
        self.file("private/hidden.py")
        agent = AetherAgent(AetherConfig(project_root=self.root), llm=object(),
                            on_plan=lambda _: None)
        scandir = os.scandir

        def blocked(path):
            if Path(path).name == "private":
                raise PermissionError("access denied")
            return scandir(path)

        with patch("aether.agent.counting.os.scandir", side_effect=blocked):
            result = agent.run(TASK)
        self.assertIn("Contagem parcial", result)
        self.assertIn("private", result)
        self.assertEqual(agent.last_outcome.code, "partial_count")

    def test_matcher_does_not_route_unrelated_or_subdirectory_tasks(self):
        self.assertTrue(is_project_python_count(TASK))
        self.assertFalse(is_project_python_count("Quantos arquivos Python existem em tests?"))
        self.assertFalse(is_project_python_count(TASK + "; edite a configuração"))

    def test_count_path_does_not_bypass_context_or_response_limits(self):
        config = AetherConfig(project_root=self.root)
        agent = AetherAgent(config, llm=object(), on_plan=lambda _: None)
        agent.messages.append({"role": "user", "content": "x" * 48001})
        self.assertIn("Limite de contexto", agent.run(TASK))
        self.assertEqual(agent.last_outcome.code, "context_limit")
        agent.reset()
        config.agent.max_response_chars = 128
        self.assertIn("Relatório de contagem", agent.run(TASK))
        self.assertEqual(agent.last_outcome.code, "count_report_limit")

    def test_failed_count_reports_cause_without_marking_completion(self):
        agent = AetherAgent(AetherConfig(project_root=self.root), llm=object(),
                            on_plan=lambda _: None)
        agent.tools.disabled_tools.add("count_python_files")
        self.assertIn("desabilitada", agent.run(TASK))
        self.assertEqual(agent.last_outcome.code, "count_failed")

    def test_plan_approval_is_preserved_for_deterministic_count(self):
        config = AetherConfig(project_root=self.root)
        config.agent.require_plan_approval = True
        agent = AetherAgent(config, llm=object(), ask_user=lambda _: "não", on_plan=lambda _: None)
        self.assertIn("não aprovado", agent.run(TASK))
        self.assertEqual(agent.last_outcome.code, "plan_not_approved")
        self.assertEqual(agent.last_evidence.tool_events, [])
