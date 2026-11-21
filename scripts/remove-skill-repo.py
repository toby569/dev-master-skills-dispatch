"""Interactively unregister a Skill repository, optionally removing its agent entries."""
import argparse
import json

from internal.skill_dispatch import (
    CONFIG_PATH, ROOT, agent_home_argument, ask, git, link_target, read_config, registered_submodules,
    run_cli, sync_entry, update_lock, wrapper_text, write_text_if_changed,
)


def yes(message):
    while True:
        answer = ask(message + " [y/N]：").casefold()
        if answer in ("y", "yes", "是"):
            return True
        if answer in ("", "n", "no", "否"):
            return False
        print("请输入 y 或 n，也可输入 q 取消。")


def owned_entries(home, agents, repo):
    entries = {}
    for location in agents.values():
        root = home / location
        if not root.is_dir():
            continue
        for path in root.iterdir():
            target = link_target(path)
            wrapper = target is None
            if wrapper and path.is_dir():
                target = link_target(path / ".source")
            if target and target.is_relative_to(repo):
                entries[path] = (target, wrapper)
    return entries


def remove_source(path, module, cleanup, home, config):
    repo = (ROOT / path).resolve()
    if (not repo.is_relative_to(ROOT) or repo == ROOT or repo.is_relative_to(ROOT / ".git")
            or repo != ROOT / path):
        raise ValueError(f"子模块路径不是管理仓库内的独立目录：{path}")
    entries = owned_entries(home, config["agents"], repo)
    keep_checkout = bool(entries) and not cleanup
    if git(ROOT, "diff", "--name-only", "--", ".gitmodules"):
        raise ValueError(".gitmodules 有未暂存编辑，请先处理后再移除来源。")

    rm_options = ["--cached"] if keep_checkout else []
    if not keep_checkout and repo.is_dir():
        if (repo / ".git").exists():
            if git(repo, "status", "--porcelain", "--ignored", "--untracked-files=normal"):
                raise ValueError(f"{path} 有本地修改、未跟踪或忽略文件，请先保存；本次未移除。")
            # Git requires -f to undo a freshly staged add. Verify its exact index
            # commit, its clean worktree and that no version existed in parent HEAD.
            parent_head = git(ROOT, "rev-parse", "-q", "--verify", "HEAD", missing_ok=True)
            tracked = parent_head and git(ROOT, "ls-tree", "HEAD", "--", path)
            index_entry = git(ROOT, "ls-files", "--stage", "--", path)
            if not tracked and index_entry.startswith("160000 " + git(repo, "rev-parse", "HEAD") + " 0\t"):
                rm_options.append("-f")
        elif any(repo.iterdir()):
            raise ValueError(f"{path} 含有未识别的本地文件，本次未移除。")

    git(ROOT, "rm", "--dry-run", *rm_options, "--", path)
    if keep_checkout:
        # --cached preserves the checkout and agent links; Git leaves .gitmodules
        # to the caller in this mode. Preserve other sections including staged adds.
        modules_file = ROOT / ".gitmodules"
        original = modules_file.read_bytes()
        try:
            git(ROOT, "config", "--file", ".gitmodules", "--remove-section", "submodule." + module.name)
            git(ROOT, "add", "--", ".gitmodules")
            git(ROOT, "rm", "--cached", "--", path)
        except (OSError, RuntimeError):
            modules_file.write_bytes(original)
            git(ROOT, "add", "--", ".gitmodules")
            raise
    else:
        for entry, (target, wrapper) in entries.items():
            if not wrapper:
                continue
            if any(child.name not in {"SKILL.md", ".source", "agents"} for child in entry.iterdir()):
                raise ValueError(f"入口中有额外文件，已保留：{entry}")
            definition = entry / "SKILL.md"
            if definition.is_file():
                text = definition.read_text(encoding="utf-8-sig")
                if (target / "SKILL.md").is_file():
                    generated = text == wrapper_text(target, entry.name)
                else:
                    generated = text.rstrip().endswith(f"Resolve its scripts, references and templates relative to {target}.")
                if not generated:
                    raise ValueError(f"入口文件有自定义内容，已保留：{definition}")
        removed = []
        try:
            for entry, (target, wrapper) in entries.items():
                sync_entry(entry, None, target, entry.name, wrapper)
                removed.append((entry, target, wrapper))
            git(ROOT, "rm", *rm_options, "--", path)
        except (OSError, ValueError, RuntimeError):
            for entry, target, wrapper in removed:
                if (target / "SKILL.md").is_file():
                    sync_entry(entry, target, None, entry.name, wrapper)
            raise

    overrides = config.get("sources", [])
    remaining = [item for item in overrides if item["path"] != path]
    if not keep_checkout and len(remaining) != len(overrides):
        stage = not git(ROOT, "diff", "--name-only", "--", CONFIG_PATH)
        config["sources"] = remaining
        write_text_if_changed(ROOT / CONFIG_PATH, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        if stage:
            git(ROOT, "add", "--", CONFIG_PATH)
    print(f"已从管理仓库移除 {path}。")
    if keep_checkout:
        print(f"已保留 {len(entries)} 个入口和本地源码 {repo}；该目录现为未跟踪目录，入口仍可使用。")
    else:
        print(f"已清理 {len(entries)} 个 Agent 入口。")


def main():
    cli = argparse.ArgumentParser(description="从已登记的子模块中选择来源并移除。")
    agent_home_argument(cli)
    home = cli.parse_args().agent_home.expanduser().resolve()
    modules = registered_submodules(ROOT)
    if not modules:
        print("当前没有已登记的 Skill 来源。")
        return 0
    print("已登记的 Skill 来源")
    paths = list(modules)
    for index, path in enumerate(paths, 1):
        print(f"  {index}. {path}  {modules[path].url}")
    while True:
        choice = ask("请输入要移除的编号（回车或 q 取消）：")
        if not choice:
            print("已取消。")
            return 0
        if choice.isascii() and choice.isdecimal() and 1 <= int(choice) <= len(paths):
            break
        print(f"请输入 1 到 {len(paths)} 之间的编号。")
    path = paths[int(choice) - 1]
    config = read_config(ROOT)
    repo = (ROOT / path).resolve()
    entries = owned_entries(home, config["agents"], repo)
    print(f"选中 {path}，找到 {len(entries)} 个指向此来源的个人入口。")
    cleanup = True
    if entries:
        print("选择 y 会删除这些入口和子模块工作目录；选择 n 会保留入口及其本地源码。")
        cleanup = yes("同步清理这些 Agent 入口吗？")
    if not yes(f"确认从管理仓库移除 {path} 吗？"):
        print("已取消。")
        return 0
    with update_lock(ROOT):
        module = registered_submodules(ROOT).get(path)
        config = read_config(ROOT)
        if module != modules[path] or owned_entries(home, config["agents"], repo) != entries:
            raise ValueError("来源或个人入口已变化，请重新选择。")
        remove_source(path, module, cleanup, home, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
