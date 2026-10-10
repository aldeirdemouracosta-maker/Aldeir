import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from support import WorkspaceTemp

from aether.agent.tools import get_default_tools
from aether.llm.local import ensure_local_model
from aether.security import local_url


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.tools = get_default_tools(self.root)

    def test_sibling_prefix_escape(self):
        result = self.tools.execute("write_file", {"path": "../project-other/a", "content": "x"})
        self.assertFalse(result.success)
        self.assertFalse((self.root.parent / "project-other").exists())

    def test_disabled_tool_cannot_execute_by_name(self):
        self.tools.disabled_tools.add("write_file")
        self.assertNotIn("write_file", self.tools.available_tools)
        result = self.tools.execute("write_file", {"path": "blocked.py", "content": "x"})
        self.assertFalse(result.success)
        self.assertIn("write_file", result.error)
        self.assertFalse((self.root / "blocked.py").exists())

    def test_absolute_escape(self):
        self.assertFalse(self.tools.execute("read_file", {"path": str(self.root.parent / "a")}).success)

    def test_symlink_escape(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        try:
            (self.root / "link").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Sistema não permite criar symlink")
        self.assertFalse(self.tools.execute("write_file", {"path": "link/a", "content": "x"}).success)

    def test_unknown_tool(self):
        self.assertFalse(self.tools.execute("unknown", {}).success)

    def test_argument_object_required(self):
        for args in [None, [], 1, "{}"]:
            self.assertFalse(self.tools.execute("list_dir", args).success)

    def test_argument_types(self):
        for value in [True, "1", 0, -1]:
            self.assertFalse(self.tools.execute("read_file", {"path": "a", "start_line": value}).success)

    def test_extra_argument(self):
        self.assertFalse(self.tools.execute("list_dir", {"bogus": "a"}).success)

    def test_missing_argument(self):
        self.assertFalse(self.tools.execute("write_file", {"path": "a"}).success)

    def test_write_and_read_range(self):
        self.assertTrue(self.tools.execute("write_file", {"path": "nested/a", "content": "one\ntwo\nthree"}).success)
        result = self.tools.execute("read_file", {"path": "nested/a", "start_line": 2, "end_line": 2})
        self.assertEqual(result.output, "   2 | two")

    def test_invalid_range(self):
        (self.root / "a").write_text("a")
        self.assertFalse(self.tools.execute("read_file", {"path": "a", "start_line": 2, "end_line": 1}).success)

    def test_unique_edit(self):
        (self.root / "a").write_text("abc")
        self.assertTrue(self.tools.execute("edit_file", {"path": "a", "old_text": "b", "new_text": "B"}).success)
        self.assertEqual((self.root / "a").read_text(), "aBc")

    def test_ambiguous_edit_preserves_file(self):
        (self.root / "a").write_text("aaa")
        for old in ["a", "missing", ""]:
            self.assertFalse(self.tools.execute("edit_file", {"path": "a", "old_text": old, "new_text": "b"}).success)
        self.assertEqual((self.root / "a").read_text(), "aaa")

    def test_metadata_write_blocked(self):
        self.assertFalse(self.tools.execute("write_file", {"path": ".git/config", "content": "x"}).success)

    def test_terminal_disabled(self):
        with patch("subprocess.Popen") as popen:
            self.assertFalse(self.tools.execute("run_terminal", {"command": ["anything"]}).success)
            popen.assert_not_called()

    def test_terminal_no_shell_and_literal_arguments(self):
        tools = get_default_tools(self.root, allow_unisolated_terminal=True)
        result = tools.execute("run_terminal", {"command": [sys.executable, "-c", "import sys; print(sys.argv[1])", "a; echo b"]})
        self.assertTrue(result.success)
        self.assertEqual(result.output.strip(), "a; echo b")

    def test_terminal_output_bound(self):
        tools = get_default_tools(self.root, allow_unisolated_terminal=True, max_output_chars=128)
        result = tools.execute("run_terminal", {"command": [sys.executable, "-c", "print('x'*100000)"]})
        self.assertTrue(result.success)
        self.assertEqual(len(result.output), 128)

    def test_terminal_timeout(self):
        tools = get_default_tools(self.root, allow_unisolated_terminal=True, terminal_timeout=1)
        result = tools.execute("run_terminal", {"command": [sys.executable, "-c", "import time; time.sleep(10)"]})
        self.assertFalse(result.success)
        self.assertIn("Timeout", result.error)

    def test_terminal_bad_argv(self):
        tools = get_default_tools(self.root, allow_unisolated_terminal=True)
        for command in [[], [1], [""], "echo hi"]:
            self.assertFalse(tools.execute("run_terminal", {"command": command}).success)

    def test_git_read_tools(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "a").write_text("abc")
        subprocess.run(["git", "-C", str(self.root), "add", "a"], check=True)
        (self.root / "a").write_text("changed")
        status = self.tools.execute("git_status", {})
        diff = self.tools.execute("git_diff", {})
        self.assertTrue(status.success)
        self.assertIn("a", status.output)
        self.assertTrue(diff.success)
        self.assertIn("+changed", diff.output)

    def test_remote_model_metadata_blocked(self):
        class Response:
            def raise_for_status(self):
                pass
            def json(self):
                return {"remote_host": "https://cloud.example"}
        class Client:
            def post(self, url, json):
                self.url = url
                return Response()
        client = Client()
        with self.assertRaises(ValueError):
            ensure_local_model(client, "http://localhost:11434", "model")
        self.assertEqual(client.url, "http://localhost:11434/api/show")

    def test_local_endpoint(self):
        for url in ["http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:11434"]:
            self.assertTrue(local_url(url))
        for url in ["https://ollama.com", "http://example.com", "http://localhost.evil", "http://user@localhost", "http://localhost/api", "http://localhost?x=1"]:
            with self.assertRaises(ValueError):
                local_url(url)


if __name__ == "__main__":
    unittest.main()
