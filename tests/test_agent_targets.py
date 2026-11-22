"""Cover first-run detection and multiple tools sharing a physical directory."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from internal import agent_targets, skill_dispatch


class AgentTargetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "hub"
        self.home = self.root / "home"
        (self.repo / "config").mkdir(parents=True)
        self.home.mkdir()
        self.shared = {"agents": {"codex": ".agents/skills", "claude": ".claude/skills"}}

    def test_first_run_prompts_with_detected_agent_only(self):
        (self.home / ".claude").mkdir()
        with patch.object(sys.stdin, "isatty", return_value=True), patch("shutil.which", return_value=None), \
                patch("builtins.input", side_effect=["", "", "y"]), redirect_stdout(io.StringIO()):
            saved = skill_dispatch.local_profile(self.repo, self.home, self.shared)
        self.assertEqual(saved["agents"], {"claude": ".claude/skills"})
        with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
            self.assertEqual(skill_dispatch.local_profile(self.repo, self.home, self.shared), saved)

    def test_wizard_can_skip_a_directory_blocked_by_a_file(self):
        (self.home / ".agents").write_text("keep")
        with patch("builtins.input", side_effect=["1,2", "", "-", ""]), redirect_stdout(io.StringIO()) as log:
            chosen = agent_targets.choose_targets(self.home, self.shared, {})
        self.assertEqual(chosen, {"claude": ".claude/skills"})
        self.assertIn("目录不可用", log.getvalue())

    def test_alias_conflicts_through_a_directory_link(self):
        root = self.home / "team"
        root.mkdir()
        linked = self.home / "other"
        skill_dispatch.set_link(linked, root, None)
        self.addCleanup(skill_dispatch.set_link, linked, None, root)
        agents = {"editor": "team", "claude": "other"}
        groups, errors = agent_targets.directory_groups(self.home, agents, [])
        self.assertEqual(groups, {root.resolve(): ["editor", "claude"]})
        self.assertEqual(errors, {})
        aliases = {"aliases": {"claude": {"review": "team-review"}}}
        groups, errors = agent_targets.directory_groups(self.home, agents, [aliases])
        self.assertEqual(groups, {})
        self.assertEqual(set(errors), set(agents))

    def test_zero_targets_are_saved_explicitly(self):
        with patch("builtins.input", side_effect=["0", "y"]), redirect_stdout(io.StringIO()):
            saved = skill_dispatch.local_profile(self.repo, self.home, self.shared, configure=True)
        self.assertEqual(saved, {"agents": {}})
