"""Regression tests for discovering skills from Git history and submodule registrations."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("dispatcher", Path(__file__).resolve().parents[1] / "skill_dispatch.py")
dispatcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatcher)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name)
        dispatcher.git(self.repo, "init", "-q")

    def write(self, path, text):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")

    def snapshot(self):
        dispatcher.git(self.repo, "add", ".")
        return dispatcher.git(self.repo, "write-tree")

    def skill(self, path, name):
        self.write(path, f"---\nname: {name}\ndescription: Test skill\n---\n")

    def test_submodule_names_are_taken_from_git(self):
        self.write(".gitmodules", '[submodule "short-name"]\n\tpath = upstreams/foo bar\n'
                    '[submodule "second"]\n\tpath = vendors/another\n')
        custom = {"path": "vendors/another", "skillRoots": ["published"]}
        self.assertEqual(dispatcher.configured_sources(self.repo, [custom]),
                         [{"path": "upstreams/foo bar"}, custom])

    def test_only_public_skills_at_each_revision(self):
        self.skill("skills/group/one/SKILL.md", "one")
        self.skill("skills/group/one/examples/demo/SKILL.md", "demo")
        self.skill(".automations/helper/SKILL.md", "helper")
        self.skill("skills/.draft/unfinished/SKILL.md", "unfinished")
        before = self.snapshot()
        self.skill("skills/two/SKILL.md", "two")
        self.write(".claude-plugin/plugin.json", json.dumps({"skills": ["./skills/two"]}))
        after = self.snapshot()
        self.assertEqual(dispatcher.read_skills(self.repo, before, {}), {"one": "skills/group/one"})
        self.assertEqual(dispatcher.read_skills(self.repo, after, {}), {"two": "skills/two"})
        self.assertEqual(dispatcher.read_skills(self.repo, after, {"manifest": ".claude-plugin/plugin.json"}),
                         {"two": "skills/two"})
        self.assertEqual(dispatcher.read_skills(self.repo, after, {"skillRoots": ["skills/group"]}),
                         {"one": "skills/group/one"})

    def test_codex_manifest_can_declare_a_collection(self):
        self.skill("release/one/SKILL.md", "one")
        self.skill("release/two/SKILL.md", "two")
        self.skill("skills/unlisted/SKILL.md", "unlisted")
        self.write(".codex-plugin/plugin.json", json.dumps({"skills": "./release"}))
        self.assertEqual(dispatcher.read_skills(self.repo, self.snapshot(), {}),
                         {"one": "release/one", "two": "release/two"})

    def test_single_skill_at_root(self):
        self.skill("SKILL.md", "root-skill")
        self.skill("examples/demo/SKILL.md", "demo")
        before = self.snapshot()
        skills = dispatcher.read_skills(self.repo, before, {})
        self.assertEqual(skills, {"root-skill": "."})
        self.write("scripts/run.py", "# Changed relative to the root skill")
        output = io.StringIO()
        with redirect_stdout(output):
            dispatcher.report_changes(self.repo, {"path": "source"}, before, self.snapshot(), skills, skills, True)
        self.assertIn("root-skill (修改) scripts/run.py", output.getvalue())


if __name__ == "__main__":
    unittest.main()
