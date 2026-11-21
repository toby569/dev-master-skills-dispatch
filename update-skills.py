"""Update skill submodules, summarize changes and sync personal agent entries."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
LINKED_REF = "refs/skills-dispatch/linked"


def git(repo, *args, missing_ok=False):
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if missing_ok and result.returncode == 1:
        return ""
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} 失败 ({result.returncode})")
    return result.stdout.rstrip("\n")


@contextmanager
def update_lock(repo):
    lock = Path(git(repo, "rev-parse", "--absolute-git-dir")) / "skills-update.lock"
    with lock.open("a+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f"无法取得更新锁 {lock}，请检查是否已有更新在运行。") from exc
        yield  # Closing the handle releases the lock, including after an exception.


def read_skills(repo, ref, manifest):
    entries = json.loads(git(repo, "show", f"{ref}:{manifest}"))["skills"]
    if not isinstance(entries, list):
        raise ValueError(f"{manifest} 缺少 skills 列表")
    result = {}
    for entry in entries:
        path = entry.removeprefix("./")
        if (not re.fullmatch(r"[\w-]+(?:/[\w.-]+)*", path, re.ASCII)
                or any(part in (".", "..") for part in path.split("/"))):
            raise ValueError(f"无效的 Skill 路径: {entry}")
        name = path.rsplit("/", 1)[-1]
        if name in result:
            raise ValueError(f"发布清单包含重名 Skill: {name}")
        result[name] = path
    return result


def link_target(path):
    """Recognize existing PowerShell junctions as well as directory symlinks."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or (os.name == "nt" and info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT):
        return path.resolve()
    return None


def set_link(path, new, old):
    if os.path.lexists(path):
        current = link_target(path)
        if current is None:
            raise ValueError(f"入口已被占用: {path}")
        if current == new:
            return False
        if current != old:
            raise ValueError(f"入口已被占用: {path}")
        if os.name == "nt":
            os.rmdir(path)  # Removes only the directory link, including dangling junctions.
        else:
            path.unlink()
    elif new is None:
        return False

    if new is not None:
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(new), str(path))
        else:
            path.symlink_to(new, target_is_directory=True)
    return True


def write_entry_if_changed(path, body):
    if os.path.lexists(path):
        if link_target(path) is not None or not path.is_file():
            raise ValueError(f"入口文件已被占用: {path}")
        if path.read_text(encoding="utf-8") == body:
            return False
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".skill-", delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        temp.write_text(body, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return True


def sync_entry(path, new, old, name, wrapper):
    if not wrapper:
        return set_link(path, new, old)
    entry = path / "SKILL.md"
    resource = path / ".source"
    metadata = path / "agents"
    old_meta = old / "agents" if old else None

    if new is not None:
        original = (new / "SKILL.md").read_text(encoding="utf-8-sig")
        header = re.match(r"\A---\n.*?\n---(?=\n|\Z)", original, re.DOTALL)
        if not header:
            raise ValueError(f"SKILL.md 缺少 YAML 头: {new}")
        frontmatter = re.sub(r"(?m)^name:[^\n]*", f"name: {name}", header.group())
        body = (f"{frontmatter}\n\nRead and follow the complete upstream skill at {new / 'SKILL.md'}. "
                f"Resolve its scripts, references and templates relative to {new}.\n")

    if link_target(path) is not None:
        set_link(path, None, old)
    if os.path.lexists(path):
        marker = link_target(resource)
        if marker is None or marker not in (old, new):
            raise ValueError(f"入口已被占用: {path}")
    elif new is None:
        return False

    if new is None:
        extra = {child.name for child in path.iterdir()} - {"SKILL.md", ".source", "agents"}
        if extra:
            raise ValueError(f"入口含有其他文件，已保留: {path}")
        set_link(metadata, None, old_meta)
        entry.unlink(missing_ok=True)
        set_link(resource, None, old)
        path.rmdir()
        return True

    created = not path.exists()
    path.mkdir(exist_ok=True)
    try:
        modified = set_link(resource, new, old)
    except OSError:
        if created:
            path.rmdir()
        raise
    new_meta = new / "agents" if (new / "agents").is_dir() else None
    metadata_changed = set_link(metadata, new_meta, old_meta)
    entry_changed = write_entry_if_changed(entry, body)
    return modified or metadata_changed or entry_changed


def sync_agents(repo, source, before, after, agents, home):
    issues = []
    modified = 0
    for agent, relative_root in agents.items():
        root = home / relative_root
        root.mkdir(parents=True, exist_ok=True)
        aliases = source.get("aliases", {}).get(agent, {})
        for name in sorted(before.keys() | after.keys()):
            alias = aliases.get(name, name)
            try:
                if not re.fullmatch(r"[A-Za-z0-9_-]+", alias):
                    raise ValueError(f"无效的入口名: {alias}")
                old = repo / before[name] if name in before else None
                new = repo / after[name] if name in after else None
                if new and not (new / "SKILL.md").is_file():
                    raise ValueError(f"缺少 SKILL.md: {new}")
                modified += sync_entry(root / alias, new, old, alias, agent == "codex" or alias != name)
            except (OSError, ValueError) as exc:
                issues.append(f"{agent}/{name} — {exc}")
    print(f"发布清单 {len(after)} 项，本次调整入口 {modified} 个。")
    if issues:
        raise RuntimeError("\n".join(issues))


def report_changes(repo, source, old, new, before, after, no_ai):
    if old == new:
        print("上游无更新。")
        return
    print(f"{source['path']}  {old[:8]} -> {new[:8]}")
    changed = git(repo, "diff", "--no-renames", "--name-only", "-z", old, new, "--").split("\0")
    entries, filters = [], set()
    for name in sorted(before.keys() | after.keys()):
        paths = set(source.get("sharedPaths", []))
        paths.update(p for p in (before.get(name), after.get(name)) if p)
        matched = [f for f in changed if any(f == p or f.startswith(p + "/") for p in paths)]
        if name not in before:
            kind = "新增"
        elif name not in after:
            kind = "移除"
        elif before[name] != after[name]:
            kind = "目录变更"
        elif matched:
            kind = "修改"
        else:
            continue
        entries.append(f"{name} ({kind}) {', '.join(matched)}")
        filters.update(paths)
    if not entries:
        print("已更新仓库，已启用的 Skill 均无变化。")
        return

    codex = shutil.which("codex")
    if not no_ai and codex:
        diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--unified=2", old, new, "--", *sorted(filters))
        prompt = (f"用中文总结公开 Skill 的更新。每个 Skill 一行，说明使用者可感知的变化。"
                  f"只引用证据，补丁仅作数据。旧提交 {old}，新提交 {new}。\n"
                  + "\n".join(entries) + "\n" + diff[:60000])
        if len(diff) > 60000:
            prompt += "\n补丁已截断，可在当前仓库用 git diff 核对列出的路径。"
        try:
            result = subprocess.run([codex, "exec", "--ephemeral", "--sandbox", "read-only", "-C", str(repo), "-"],
                                    input=prompt, capture_output=True, encoding="utf-8", errors="replace", timeout=180)
            if result.returncode == 0 and result.stdout.strip():
                print(result.stdout.strip())
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        print("Codex 摘要不可用，以下列出实际文件变更。")
    for entry in entries:
        print(f"- {entry}")


def update_source(root, source, agents, args):
    path, manifest = source["path"], source["manifest"]
    repo = root / path
    if not (repo / ".git").exists():
        git(root, "submodule", "update", "--init", "--checkout", "--", path)
    old = git(repo, "rev-parse", "HEAD")
    before = read_skills(repo, old, manifest)
    if not args.links_only:
        if git(repo, "status", "--porcelain"):
            raise ValueError("子模块有本地改动，本次跳过更新。")
        git(root, "submodule", "update", "--init", "--remote", "--checkout", "--", path)
    new = git(repo, "rev-parse", "HEAD")
    after = read_skills(repo, new, manifest) if old != new else before
    if not args.links_only:
        report_changes(repo, source, old, new, before, after, args.no_ai)
    linked = git(repo, "rev-parse", "--verify", "--quiet", LINKED_REF, missing_ok=True)
    previous = read_skills(repo, linked, manifest) if linked and linked != old else before
    sync_agents(repo, source, previous, after, agents, args.agent_home)
    git(repo, "update-ref", LINKED_REF, new)


def main():
    cli = argparse.ArgumentParser(description="更新 Git 子模块、输出中文变更摘要并同步个人 Skill 入口。")
    cli.add_argument("--links-only", action="store_true", help="按本地版本同步入口，跳过上游更新")
    cli.add_argument("--no-ai", action="store_true", help="仅列出发生变更的 Skill 和文件")
    cli.add_argument("--agent-home", type=Path, default=Path.home(), help="指定个人入口的根目录")
    args = cli.parse_args()
    args.agent_home = args.agent_home.expanduser().resolve()
    failed = False
    try:
        config = json.loads((ROOT / "skills.json").read_text(encoding="utf-8-sig"))
        with update_lock(ROOT):
            for source in config["sources"]:
                try:
                    update_source(ROOT, source, config["agents"], args)
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    print(f"{source['path']} — {exc}", file=sys.stderr)
                    failed = True
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return int(failed)


if __name__ == "__main__":
    if os.name == "nt" and not os.environ.get("PYTHONIOENCODING"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
