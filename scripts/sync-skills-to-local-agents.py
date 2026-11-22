"""Sync the checked-out Skills to all configured agents."""
import argparse

from internal.skill_dispatch import agent_home_argument, run_cli, update_sources


def main():
    cli = argparse.ArgumentParser(description="按当前配置，将本地已检出的 Skill 同步到所有 Agent 目录。")
    agent_home_argument(cli)
    cli.add_argument("--configure", action="store_true", help="选择本机 Agent 和目录，保存后同步")
    args = cli.parse_args()
    home = args.agent_home.expanduser().resolve()
    return update_sources(home, configure=args.configure, links_only=True, init_missing=False)


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
