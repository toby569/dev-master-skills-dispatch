"""Exercise the user-facing scripts against local Git repositories and a temporary profile."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/example/demo.git"


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.hub, self.remote, self.home = (base / p for p in ("hub", "remote", "profile"))
        self.env = dict(os.environ, PYTHONUTF8="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_ALLOW_PROTOCOL="file", GIT_AUTHOR_NAME="Test", GIT_COMMITTER_NAME="Test",
                        GIT_AUTHOR_EMAIL="test@example.org", GIT_COMMITTER_EMAIL="test@example.org",
                        GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=f"url.{self.remote.as_uri()}.insteadOf",
                        GIT_CONFIG_VALUE_0=URL)
        for directory in (self.hub, self.remote):
            directory.mkdir()
            self.git(directory, "init", "-q")
        for name in ("skill_dispatch.py", "add-skill-repo.py", "remove-skill-repo.py", "update-skills.py"):
            shutil.copyfile(ROOT / name, self.hub / name)
        (self.hub / "skills.json").write_text(json.dumps({"agents": {"codex": ".agents/skills", "claude": ".claude/skills"}}))
        (self.remote / "SKILL.md").write_text("---\nname: test-skill\ndescription: Example\n---\nDo the work.\n")
        for directory in (self.hub, self.remote):
            self.git(directory, "add", ".")
            self.git(directory, "commit", "-qm", "initial")
        self.source = self.hub / "upstreams/example-demo"
        self.entry = self.home / ".agents/skills/test-skill"
        self.claude = self.home / ".claude/skills/test-skill"

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args], env=self.env, text=True).strip()

    def cli(self, script, answer="", status=0):
        result = subprocess.run([sys.executable, "-B", str(self.hub / script), "--agent-home", str(self.home)],
                                input=answer, text=True, capture_output=True, encoding="utf-8", env=self.env)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_add_duplicate_cancel_keep_and_remove(self):
        self.assertIn("已取消", self.cli("add-skill-repo.py", "q\n"))
        self.assertIn("没有已登记", self.cli("remove-skill-repo.py"))
        added = self.cli("add-skill-repo.py", "bad input\n" + URL + "\n../bad\n\n")
        self.assertIn("test-skill", added)
        self.assertTrue((self.entry / "SKILL.md").is_file())
        self.assertTrue((self.claude / "SKILL.md").is_file())
        self.assertIn("已登记", self.cli("add-skill-repo.py", "git@github.com:example/demo.git\n"))
        self.assertIn("已取消", self.cli("remove-skill-repo.py", "9\n1\ny\nn\n"))
        config_file = self.hub / "skills.json"
        config = json.loads(config_file.read_text())
        config["sources"] = [{"path": "upstreams/example-demo", "sharedPaths": ["shared.md"]}]
        config_file.write_text(json.dumps(config))
        self.git(self.hub, "add", "skills.json")
        self.git(self.hub, "commit", "-qm", "register")
        self.assertIn("已保留", self.cli("remove-skill-repo.py", "1\nn\ny\n"))
        self.assertTrue((self.claude / "SKILL.md").is_file())
        self.assertEqual(json.loads(config_file.read_text()), config)
        self.assertNotIn("160000", self.git(self.hub, "ls-files", "-s", "--", "upstreams"))
        self.assertIn("重新登记", self.cli("add-skill-repo.py", URL + "\n\n"))
        unmanaged = self.home / ".agents/skills/another"
        unmanaged.mkdir()
        self.assertIn("已清理 2", self.cli("remove-skill-repo.py", "1\ny\ny\n"))
        self.assertFalse(os.path.lexists(self.claude))
        self.assertFalse(self.entry.exists())
        self.assertFalse(self.source.exists())
        self.assertTrue(unmanaged.exists())
        self.assertIn("test-skill", self.cli("add-skill-repo.py", URL + "\n\n"))
        self.assertIn("入口 0", self.cli("update-skills.py"))

    def test_dirty_checkout_and_foreign_entries_are_preserved(self):
        self.cli("add-skill-repo.py", URL + "\ncustom-folder\n")
        source = self.hub / "upstreams/custom-folder"
        draft = source / "draft.txt"
        draft.write_text("keep")
        self.assertIn("本地修改", self.cli("remove-skill-repo.py", "1\ny\ny\n", status=1))
        self.assertTrue(draft.is_file())
        draft.unlink()
        note = self.entry / "notes.md"
        note.write_text("personal")
        self.assertIn("额外文件", self.cli("remove-skill-repo.py", "1\ny\ny\n", status=1))
        self.assertTrue(note.is_file())
        self.assertTrue((self.claude / "SKILL.md").is_file())
        note.unlink()
        # An unrelated regular skill with the very same name belongs to the user.
        if os.name == "nt":
            os.rmdir(self.claude)
        else:
            self.claude.unlink()
        self.claude.mkdir()
        foreign = self.claude / "SKILL.md"
        foreign.write_text("team workflow")
        (self.hub / "skills.json").write_text(json.dumps({
            "agents": {"codex": ".agents/skills", "claude": ".claude/skills"},
            "sources": [{"path": "upstreams/custom-folder", "skillRoots": ["."]}, {"path": "other"}]
        }))
        self.assertIn("已清理 1", self.cli("remove-skill-repo.py", "1\ny\ny\n"))
        self.assertEqual(foreign.read_text(), "team workflow")
        self.assertEqual(json.loads((self.hub / "skills.json").read_text())["sources"], [{"path": "other"}])
        self.assertTrue(self.git(self.hub, "diff", "--name-only", "--", "skills.json"))


if __name__ == "__main__":
    unittest.main()
