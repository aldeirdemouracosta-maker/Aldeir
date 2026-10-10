import json
import unittest
from pathlib import Path
from unittest.mock import patch

from support import WorkspaceTemp

from aether.skills import SkillError, SkillLoader


class SkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.loader = SkillLoader(self.root)
        self.folder = self.root / ".aether" / "skills" / "test-skill"
        self.folder.mkdir(parents=True)
        self.write()

    def write(self, body="Read the project and make a plan.", **manifest):
        (self.folder / "SKILL.md").write_text(
            '---\nname: test-skill\ndescription: "A test skill"\n---\n' + body, encoding="utf-8")
        data = {"version": "1.0.0", "required_tools": ["read_file"],
                "os": ["windows", "linux", "darwin"], "network": False}
        data.update(manifest)
        (self.folder / "aether.json").write_text(json.dumps(data), encoding="utf-8")

    def test_discovery_reads_frontmatter_only(self):
        self.write(body="\x00BODY_NOT_READ")
        (self.folder / "aether.json").write_text("invalid JSON")
        self.assertEqual(self.loader.discover()[0].description, "A test skill")
        with self.assertRaises(ValueError):
            self.loader.load("test-skill", {"read_file"})

    def test_lazy_selection(self):
        skill = self.loader.load("test-skill", {"read_file"})
        self.assertEqual(skill.version, "1.0.0")
        self.assertIn("make a plan", skill.instructions)

    def test_multiline_description(self):
        (self.folder / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: >-\n  First line\n  second line\n---\nBody", encoding="utf-8")
        self.assertEqual(self.loader.discover()[0].description, "First line second line")

    def test_invalid_frontmatter(self):
        for text in ["No frontmatter", "---\nname: test-skill\n---\nbody",
                     "---\nname: other\ndescription: test\n---\nbody",
                     "---\nname: test-skill\ndescription: true\n---\nbody",
                     "---\nname: test-skill\ndescription: !exec bad\n---\nbody",
                     "---\nname: test-skill\nname: test-skill\ndescription: x\n---\nbody"]:
            (self.folder / "SKILL.md").write_text(text, encoding="utf-8")
            self.assertEqual(self.loader.discover(), [])
            self.assertIn("test-skill", self.loader.errors)

    def test_names_and_size(self):
        for name in ["../outside", "../test-skill", "BadName", "a/b", "a" * 65]:
            with self.assertRaises(SkillError):
                self.loader.load(name, {"read_file"})
        self.write("x" * 70000)
        self.assertEqual(self.loader.discover(), [])

    def test_external_references(self):
        for body in ["[outside](../outside.md)", "[outside](/etc/passwd)",
                     "[outside](C:\\secret.txt)", "Read `../../secret`",
                     "[outside](https://example.org/doc)", "Read /etc/passwd"]:
            self.write(body)
            with self.assertRaises(SkillError):
                self.loader.load("test-skill", {"read_file"})

    def test_valid_resource_never_executes(self):
        self.write("Read [notes](notes.md) and inspect `scripts/check.py`.")
        (self.folder / "notes.md").write_text("notes")
        (self.folder / "scripts").mkdir()
        (self.folder / "scripts" / "check.py").write_text("raise RuntimeError('must not execute')")
        with patch("subprocess.Popen") as popen:
            self.loader.load("test-skill", {"read_file"})
            popen.assert_not_called()

    def test_missing_tools(self):
        with self.assertRaisesRegex(SkillError, "Missing dependencies: read_file"):
            self.loader.load("test-skill", set())

    def test_missing_executable(self):
        self.write(required_executables=["aether-nonexistent-executable"])
        with self.assertRaisesRegex(SkillError, "Missing dependencies"):
            self.loader.load("test-skill", {"read_file"})

    def test_skill_cannot_grant_permissions(self):
        self.write(permissions={"terminal": True})
        with self.assertRaisesRegex(SkillError, "permissions"):
            self.loader.load("test-skill", {"read_file"})
        self.write(network=True)
        with self.assertRaisesRegex(SkillError, "current permissions"):
            self.loader.load("test-skill", {"read_file"})

    def test_os_and_version_validation(self):
        self.write(os=["linux"])
        with self.assertRaisesRegex(SkillError, "Unsupported OS"):
            self.loader.load("test-skill", {"read_file"}, platform="windows")
        self.write(version="latest")
        with self.assertRaisesRegex(SkillError, "version"):
            self.loader.load("test-skill", {"read_file"})

    def test_link_rejection_without_host_privileges(self):
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path == self.folder / "SKILL.md"
                          or original(path)), self.assertRaisesRegex(SkillError, "links"):
            self.loader.load("test-skill", {"read_file"})

    def test_real_symlink_escape(self):
        try:
            (self.folder / "escape").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not allow symlink creation")
        with self.assertRaises(SkillError):
            self.loader.load("test-skill", {"read_file"})

    def test_shipped_skills_load(self):
        loader = SkillLoader(Path(__file__).resolve().parents[1])
        names = loader.discover()
        self.assertEqual(len(names), 5)
        self.assertEqual(loader.errors, {})
        tools = {"read_file", "list_dir", "edit_file", "record_evidence", "git_status", "git_diff"}
        for metadata in names:
            self.assertEqual(loader.load(metadata.name, tools).version, "1.0.0")
