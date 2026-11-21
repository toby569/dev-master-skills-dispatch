"""Update all registered Skill repositories."""
import argparse

from internal.skill_dispatch import agent_home_argument, run_cli, update_sources


def main():
    cli = argparse.ArgumentParser(description="更新 Git 子模块、同步个人 Skill 入口并保存更新明细。")
    cli.add_argument("--links-only", action="store_true", help="按本地版本同步入口，跳过上游更新")
    summary = cli.add_mutually_exclusive_group()
    summary.add_argument("--no-ai", action="store_true", help="保存更新明细并跳过 AI 摘要")
    summary.add_argument("--ai-command", nargs=argparse.REMAINDER, metavar="命令及参数",
                         help="通过指定的命令生成摘要；放在所有更新参数之后，命令从标准输入读取文本")
    agent_home_argument(cli)
    args = cli.parse_args()
    if args.ai_command == []:
        cli.error("--ai-command 后需填写命令名")
    home = args.agent_home.expanduser().resolve()
    return update_sources(home, links_only=args.links_only, no_ai=args.no_ai, ai_command=args.ai_command)


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
