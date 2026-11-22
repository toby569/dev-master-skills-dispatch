"""Select this checkout's local Agent skill directories."""
import json
import os
from pathlib import Path
import re
import shutil
import sys

LOCAL_CONFIG = "config/skills.local.json"
CONFIGURE = "python scripts/sync-skills-to-local-agents.py --configure"
LABELS = {"codex": "Codex", "claude": "Claude Code"}


def ask(message):
    value = input(message).strip()
    if value.casefold() == "q":
        raise EOFError
    return value


def yes(message):
    while True:
        reply = ask(message + " [y/N]：").casefold()
        if reply in ("y", "yes", "是"):
            return True
        if reply in ("", "n", "no", "否"):
            return False
        print("请输入 y 或 n，也可输入 q 取消。")


def target_root(home, location):
    if not isinstance(location, str) or not location.strip():
        raise ValueError("Skill 目录必须是非空路径。")
    path = Path(location)
    if path.parts[:1] == ("~",):
        path = Path(*path.parts[1:])
    if path.anchor and not path.is_absolute():
        raise ValueError(f"请使用完整的绝对路径或相对于个人主目录的路径：{location}")
    return (home / path).resolve()


def read_profile(repo):
    path = repo / LOCAL_CONFIG
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
            raise ValueError("需要 agents 对象")
        if not all(name.strip() and isinstance(p, str) and p.strip() for name, p in data["agents"].items()):
            raise ValueError("Agent 名称及目录必须是非空字符串")
        kept = data.get("retainedRoots", [])
        if not isinstance(kept, list) or not all(isinstance(p, str) and p.strip() for p in kept):
            raise ValueError("retainedRoots 应为目录列表")
        return data
    except ValueError as exc:
        raise ValueError(f"请修正 {path}：{exc}") from exc


def directory_groups(home, agents, sources):
    groups, errors = {}, {}
    for agent, location in agents.items():
        try:
            root = target_root(home, location)
        except (ValueError, RuntimeError, OSError) as exc:
            errors[agent] = f"{location} — {exc}"
        else:
            groups.setdefault(root, []).append(agent)
    for root, names in list(groups.items()):
        policies = [(name == "codex", [s.get("aliases", {}).get(name, {}) for s in sources]) for name in names]
        if any(rule != policies[0] for rule in policies[1:]):
            reason = f"{'、'.join(names)} 共用 {root}，但入口格式或别名不同。请为它们指定不同目录。"
            errors.update(dict.fromkeys(names, reason))
            del groups[root]
    return groups, errors


def detected(home, name, path):
    if name in LABELS and ((home / ("." + name)).is_dir() or shutil.which(name)):
        return True
    try:
        return target_root(home, path).is_dir()
    except (ValueError, RuntimeError, OSError):
        return False


def prompt_directory(home, name, default):
    while True:
        suffix = f" [回车使用 {default}]" if default else ""
        location = ask(f"{LABELS.get(name, name)} 的 Skill 目录{suffix}，输入 - 跳过：") or default
        if location == "-":
            return None
        try:
            root = target_root(home, location)
            ancestor = next((p for p in (root, *root.parents) if p.exists()), None)
            if not ancestor or not ancestor.is_dir() or not os.access(ancestor, os.W_OK):
                raise ValueError(f"目录不可用或不可写：{ancestor or root}")
            return location
        except (ValueError, RuntimeError, OSError) as exc:
            print(f"{exc} 请重新输入目录，或输入 q 取消。")


def choose_targets(home, config, current):
    candidates = {**config.get("agents", {}), **(current or {})}
    print("选择本机要同步的 Agent。可以多选，也可以添加支持 SKILL.md 的其他工具。输入 q 可取消。")
    while True:
        names = list(candidates)
        defaults = []
        for i, name in enumerate(names, 1):
            found = detected(home, name, candidates[name])
            selected = name in current if current is not None else found
            if selected:
                defaults.append(str(i))
            mark = "x" if selected else " "
            hint = "，检测到本机工具或目录" if found else ""
            print(f"  {i}. [{mark}] {LABELS.get(name, name)}  {candidates[name]}{hint}")
        print("  +. 添加自定义 Agent     0. 暂不同步到任何 Agent")
        raw = ask("输入编号（如 1,2 或 1,+），回车采用勾选项：")
        picks = re.split(r"[\s,，]+", raw) if raw else defaults
        if picks == ["0"]:
            return {}
        choices = {str(i) for i in range(1, len(names) + 1)} | {"+"}
        if not picks or not choices.issuperset(picks):
            print("请选择列表中的编号、+ 或 0。")
            continue
        chosen = {}
        for i, name in enumerate(names, 1):
            if str(i) in picks:
                location = prompt_directory(home, name, candidates[name])
                if location:
                    chosen[name] = location
        if "+" in picks:
            while True:
                name = ask("自定义 Agent 标识（如 team-agent）：")
                if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name.casefold() in {n.casefold() for n in candidates}:
                    print("请使用唯一的英文、数字、下划线或短横线标识；现有工具请按编号选择。")
                    continue
                location = prompt_directory(home, name, None)
                if location:
                    candidates[name] = chosen[name] = location
                if not yes("继续添加自定义 Agent 吗？"):
                    break
        groups, issues = directory_groups(home, chosen, config.get("sources", []))
        if issues:
            print("\n".join(dict.fromkeys(issues.values())))
            candidates.update(chosen)
            current = chosen
            continue
        print("本次同步目标：")
        for root, group in groups.items():
            print(f"  {'、'.join(group)} → {root}")
        return chosen


def require_interactive():
    if not sys.stdin.isatty():
        raise ValueError(f"尚未配置本机 Agent。请在终端运行 {CONFIGURE}，"
                         f'或为无人值守运行预先创建 {LOCAL_CONFIG}，例如 {{"agents":{{"claude":".claude/skills"}}}}。')
