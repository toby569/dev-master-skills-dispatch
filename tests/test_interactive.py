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
        shutil.copytree(ROOT / "scripts", self.hub / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.hub / "config").mkdir()
        self.config_file = self.hub / "config" / "skills.json"
        self.config_file.write_text(json.dumps({"agents": {"codex": ".agents/skills", "claude": ".claude/skills"}}))
        (self.remote / "SKILL.md").write_text("---\nname: test-skill\ndescription: Example\n---\nDo the work.\n")
        for directory in (self.hub, self.remote):
            self.git(directory, "add", ".")
            self.git(directory, "commit", "-qm", "initial")
        self.source = self.hub / "upstreams/example-demo"
        self.entry = self.home / ".agents/skills/test-skill"
        self.claude = self.home / ".claude/skills/test-skill"

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args], env=self.env, text=True).strip()

    def cli(self, script, answer="", status=0, *, args=()):
        result = subprocess.run([sys.executable, "-B", str(self.hub / "scripts" / script), "--agent-home", str(self.home), *args],
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
        config = json.loads(self.config_file.read_text())
        config["sources"] = [{"path": "upstreams/example-demo", "sharedPaths": ["shared.md"]}]
        self.config_file.write_text(json.dumps(config))
        self.git(self.hub, "add", "config/skills.json")
        self.git(self.hub, "commit", "-qm", "register")
        self.assertIn("已保留", self.cli("remove-skill-repo.py", "1\nn\ny\n"))
        self.assertTrue((self.claude / "SKILL.md").is_file())
        self.assertEqual(json.loads(self.config_file.read_text()), config)
        self.assertNotIn("160000", self.git(self.hub, "ls-files", "-s", "--", "upstreams"))
        self.assertIn("重新登记", self.cli("add-skill-repo.py", URL + "\n\n"))
        unmanaged = self.home / ".agents/skills/another"
        unmanaged.mkdir()
        self.assertIn("已清理 2", self.cli("remove-skill-repo.py", "1\ny\ny\n"))
        self.assertEqual(json.loads(self.config_file.read_text())["sources"], [])
        self.assertIn("config/skills.json", self.git(self.hub, "diff", "--cached", "--name-only").splitlines())
        self.assertFalse(os.path.lexists(self.claude))
        self.assertFalse(self.entry.exists())
        self.assertFalse(self.source.exists())
        self.assertTrue(unmanaged.exists())
        self.assertIn("test-skill", self.cli("add-skill-repo.py", URL + "\n\n"))
        self.assertIn("入口 0", self.cli("update-skills.py"))

    def test_sync_installs_current_skills_for_a_new_agent_offline(self):
        self.cli("add-skill-repo.py", URL + "\n\n")
        config = json.loads(self.config_file.read_text())
        config["agents"]["example"] = ".example/skills"
        self.config_file.write_text(json.dumps(config))
        self.env["GIT_ALLOW_PROTOCOL"] = "none"
        revision = self.git(self.source, "rev-parse", "HEAD")

        self.assertIn("调整入口 1 个", self.cli("sync-skills.py"))
        entry = self.home / ".example/skills/test-skill"
        self.assertEqual(entry.resolve(), self.source.resolve())
        self.assertTrue((entry / "SKILL.md").is_file())
        self.assertEqual(self.git(self.source, "rev-parse", "HEAD"), revision)
        self.assertIn("调整入口 0 个", self.cli("sync-skills.py"))
        self.assertFalse((self.hub / "reports").exists())

    def test_update_writes_a_report_and_syncs_without_ai(self):
        self.cli("add-skill-repo.py", URL + "\n\n")
        old = self.git(self.source, "rev-parse", "HEAD")
        (self.remote / "guide.txt").write_text("Updated instructions\n")
        self.git(self.remote, "add", "guide.txt")
        self.git(self.remote, "commit", "-qm", "Update instructions")
        new = self.git(self.remote, "rev-parse", "HEAD")

        output = self.cli("update-skills.py", args=("--no-ai",))
        report, = (self.hub / "reports").glob("skill-updates-*.txt")
        self.assertIn(str(report), output)
        details = report.read_text(encoding="utf-8")
        for value in ("upstreams/example-demo", old, new, "test-skill (修改) guide.txt", "+Updated instructions"):
            self.assertIn(value, details)
        self.assertEqual((self.claude / "guide.txt").read_text(), "Updated instructions\n")
        self.cli("update-skills.py", args=("--no-ai",))
        other, = set(report.parent.glob("*.txt")) - {report}
        self.assertIn("上游无更新", other.read_text(encoding="utf-8"))
        self.assertEqual(report.read_text(encoding="utf-8"), details)

        (self.remote / "guide.txt").write_text("Another update\n")
        self.git(self.remote, "commit", "-qam", "Revise instructions")
        # A local stdin/stdout command exercises the AI interface without using an account.
        summarize = "import sys; assert '+Another update' in sys.stdin.buffer.read().decode('utf-8'); print('Summary OK')"
        output = self.cli("update-skills.py", args=("--ai-command", sys.executable, "-c", summarize))
        latest, = set(report.parent.glob("*.txt")) - {report, other}
        self.assertIn("Summary OK", output)
        self.assertIn("Summary OK", latest.read_text(encoding="utf-8"))

    def test_sync_reports_a_missing_checkout_and_processes_other_sources(self):
        self.cli("add-skill-repo.py", URL + "\n\n")
        modules = self.hub / ".gitmodules"
        modules.write_text('[submodule "missing"]\n\tpath = upstreams/missing\n\turl = ' + URL + '\n'
                           + modules.read_text())
        config = json.loads(self.config_file.read_text())
        config["agents"]["example"] = ".example/skills"
        self.config_file.write_text(json.dumps(config))

        output = self.cli("sync-skills.py", status=1)
        self.assertIn("upstreams/missing — 子模块尚未检出", output)
        self.assertFalse((self.hub / "upstreams/missing").exists())
        self.assertTrue((self.home / ".example/skills/test-skill/SKILL.md").is_file())

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
        self.config_file.write_text(json.dumps({
            "agents": {"codex": ".agents/skills", "claude": ".claude/skills"},
            "sources": [{"path": "upstreams/custom-folder", "skillRoots": ["."]}, {"path": "other"}]
        }))
        self.assertIn("已清理 1", self.cli("remove-skill-repo.py", "1\ny\ny\n"))
        self.assertEqual(foreign.read_text(), "team workflow")
        self.assertEqual(json.loads(self.config_file.read_text())["sources"], [{"path": "other"}])
        self.assertTrue(self.git(self.hub, "diff", "--name-only", "--", "config/skills.json"))


if __name__ == "__main__":
    unittest.main()
