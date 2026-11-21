"""Update all registered Skill repositories."""
import argparse
import sys

from skill_dispatch import ROOT, agent_home_argument, configured_sources, read_config, run_cli, update_lock, update_source


def main():
    cli = argparse.ArgumentParser(description="更新 Git 子模块、输出中文变更摘要并同步个人 Skill 入口。")
    cli.add_argument("--links-only", action="store_true", help="按本地版本同步入口，跳过上游更新")
    cli.add_argument("--no-ai", action="store_true", help="仅列出发生变更的 Skill 和文件")
    agent_home_argument(cli)
    args = cli.parse_args()
    home = args.agent_home.expanduser().resolve()
    failed = False
    with update_lock(ROOT):
        config = read_config(ROOT)
        for source in configured_sources(ROOT, config.get("sources", [])):
            try:
                update_source(ROOT, source, config["agents"], home, links_only=args.links_only, no_ai=args.no_ai)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                print(f"{source['path']} — {exc}", file=sys.stderr)
                failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
