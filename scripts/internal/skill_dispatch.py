"""Update skill submodules, summarize changes and sync personal agent entries."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import NamedTuple

from .agent_targets import (
    LOCAL_CONFIG, ask, choose_targets, directory_groups, read_profile, require_interactive, target_root, yes,
)
from .update_report import UpdateReport

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = "config/skills.json"
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


class Submodule(NamedTuple):
    name: str
    url: str


def registered_submodules(repo):
    """Return registered paths and URLs, respecting custom Git subsection names."""
    if not (repo / ".gitmodules").is_file():
        return {}
    records = git(repo, "config", "--null", "--file", ".gitmodules", "--get-regexp",
                  r"^submodule\..*\.(path|url)$", missing_ok=True)
    sections = {}
    for record in records.split("\0"):
        if record:
            key, value = record.split("\n", 1)
            section, field = key.rsplit(".", 1)
            sections.setdefault(section, {})[field] = value
    return {s["path"]: Submodule(key.removeprefix("submodule."), s.get("url", ""))
            for key, s in sections.items() if "path" in s}


def configured_sources(repo, overrides):
    options = {item["path"]: item for item in overrides}
    paths = registered_submodules(repo)
    for stale in sorted(options.keys() - set(paths)):
        print(f"忽略未登记的子模块配置: {stale}", file=sys.stderr)
    return [options.get(path, {"path": path}) for path in paths]


def relative_dir(entry):
    if not isinstance(entry, str):
        raise ValueError(f"Skill 目录必须是相对路径: {entry!r}")
    path = entry.removeprefix("./").rstrip("/")
    if entry in (".", "./"):
        return "."
    if (not path or "\\" in path or ":" in path
            or any(part in ("", ".", "..") for part in path.split("/"))):
        raise ValueError(f"无效的 Skill 路径: {entry!r}")
    return path


def read_skills(repo, ref, source):
    # Resolve the catalog at the requested commit, including removed or moved skills.
    tree = git(repo, "ls-tree", "-r", "-z", "--full-tree", ref)
    files = {record.split("\t", 1)[1] for record in tree.split("\0") if record.startswith("100")}
    skill_files = {p for p in files if p == "SKILL.md" or p.endswith("/SKILL.md")}
    if "skillRoots" in source and "manifest" in source:
        raise ValueError("每个来源只能指定 manifest 或 skillRoots 中的一项")
    roots = source.get("skillRoots")
    explicit_manifest = source.get("manifest")
    if roots is None:
        candidates = [explicit_manifest] if explicit_manifest else [
            ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
        ]
        for manifest in candidates:
            if manifest not in files and not explicit_manifest:
                continue
            data = json.loads(git(repo, "show", f"{ref}:{manifest}"))
            if not isinstance(data, dict):
                raise ValueError(f"{manifest} 必须是 JSON 对象")
            if "skills" not in data and not explicit_manifest:
                continue
            roots = data["skills"]
            if isinstance(roots, str):
                roots = [roots]
            if not isinstance(roots, list):
                raise ValueError(f"{manifest} 的 skills 必须是目录或目录列表")
            for entry in roots:
                directory = relative_dir(entry)
                if directory != "." and not any(p.startswith(directory + "/") for p in files):
                    raise ValueError(f"{manifest} 指向不存在的目录: {entry}")
            break
    if roots is None:
        roots = ["."] if "SKILL.md" in files else ["skills"]
    if not isinstance(roots, list):
        raise ValueError("skillRoots 必须是相对目录列表")

    selected = set()
    for entry in roots:
        directory = relative_dir(entry)
        prefix = "" if directory == "." else directory + "/"
        for p in skill_files:
            if not p.startswith(prefix):
                continue
            parts = p[len(prefix):].split("/")
            # A skill owns its resources. Do not publish nested examples as separate entries.
            if (any(part.startswith(".") for part in parts[:-1])
                    or any(prefix + "/".join(parts[:i] + ["SKILL.md"]) in skill_files
                           for i in range(len(parts) - 1))):
                continue
            selected.add(p)

    result = {}
    for p in sorted(selected):
        directory, _, _ = p.rpartition("/")
        if directory:
            name = directory.rsplit("/", 1)[-1]
        else:
            text = git(repo, "show", f"{ref}:SKILL.md").lstrip("\ufeff")
            header = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
            match = header and re.search(r"""(?m)^name:[ \t]*(['"]?)([A-Za-z0-9_-]+)\1[ \t]*(?:#[^\n]*)?$""", header[1])
            if not match:
                raise ValueError("根目录 SKILL.md 缺少有效的 name 字段")
            name = match[2]
        if name in result:
            raise ValueError(f"同一来源的两个 Skill 重名: {name} ({result[name]}, {directory})")
        result[name] = directory or "."
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


def write_text_if_changed(path, body):
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


def wrapper_text(target, name):
    original = (target / "SKILL.md").read_text(encoding="utf-8-sig")
    header = re.match(r"\A---\n.*?\n---(?=\n|\Z)", original, re.DOTALL)
    if not header:
        raise ValueError(f"SKILL.md 缺少 YAML 头: {target}")
    frontmatter = re.sub(r"(?m)^name:[^\n]*", f"name: {name}", header.group())
    return (f"{frontmatter}\n\nRead and follow the complete upstream skill at {target / 'SKILL.md'}. "
            f"Resolve its scripts, references and templates relative to {target}.\n")


def sync_entry(path, new, old, name, wrapper):
    if not wrapper:
        return set_link(path, new, old)
    entry = path / "SKILL.md"
    resource = path / ".source"
    metadata = path / "agents"
    old_meta = old / "agents" if old else None

    if new is not None:
        body = wrapper_text(new, name)

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
    entry_changed = write_text_if_changed(entry, body)
    return modified or metadata_changed or entry_changed


def owned_entries(roots, repo):
    entries = {}
    for root in roots:
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


def validate_entries(entries):
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


@contextmanager
def remove_owned_entries(entries):
    """Restore removed entries if a later removal or its associated operation fails."""
    validate_entries(entries)
    removed = []
    try:
        for entry, (target, wrapper) in entries.items():
            sync_entry(entry, None, target, entry.name, wrapper)
            removed.append((entry, target, wrapper))
        yield
    except (ValueError, OSError, RuntimeError, KeyboardInterrupt):
        for entry, target, wrapper in removed:
            if (target / "SKILL.md").is_file():
                sync_entry(entry, target, None, entry.name, wrapper)
        raise


def profile_roots(home, profile):
    locations = [*profile["agents"].values(), *profile.get("retainedRoots", [])]
    return {target_root(home, location) for location in locations}


def local_profile(repo, home, shared, *, configure=False):
    previous = read_profile(repo)
    if previous is not None and not configure:
        return previous
    if not configure:
        require_interactive()
    sources = configured_sources(repo, shared.get("sources", []))
    chosen = choose_targets(home, {**shared, "sources": sources}, previous["agents"] if previous is not None else None)
    active = {target_root(home, p) for p in chosen.values()}
    # Check known legacy directories on first setup so existing installs stay discoverable.
    old = previous if previous is not None else {"agents": shared.get("agents", {})}
    old_locations = [*old["agents"].values(), *old.get("retainedRoots", [])]
    entries, kept, unreadable = {}, [], []
    source_paths = [(repo / source["path"]).resolve() for source in sources]
    seen = set(active)
    for location in old_locations:
        try:
            root = target_root(home, location)
            if root in seen:
                continue
            seen.add(root)
            owned = {}
            for source in source_paths:
                owned.update(owned_entries([root], source))
            if owned:
                entries.update(owned)
                kept.append(location)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"无法检查已停用目录 {location}：{exc}。已记住位置，稍后可重试。")
            unreadable.append(location)
    cleanup = False
    if kept:
        print("下列目录已停用，含有受管入口：" + "、".join(str(target_root(home, p)) for p in kept))
        cleanup = yes(f"清理其中 {len(entries)} 个受管入口吗？回车保留")
    if not chosen:
        print("本次未选择 Agent。来源仍可更新。")
    if not yes("保存本机配置并继续吗？"):
        raise EOFError
    profile = {"agents": chosen}
    retained = unreadable + ([] if cleanup else kept)
    if retained:
        profile["retainedRoots"] = retained
    with remove_owned_entries(entries if cleanup else {}):
        write_text_if_changed(repo / LOCAL_CONFIG, json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    print(f"本机配置已保存到 {repo / LOCAL_CONFIG}")
    return profile


def sync_directory(repo, source, before, after, agent, root):
    root.mkdir(parents=True, exist_ok=True)
    aliases = source.get("aliases", {}).get(agent, {})
    count, errors = 0, []
    for name in sorted(before.keys() | after.keys()):
        alias = aliases.get(name, name)
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", alias):
                raise ValueError(f"无效的入口名: {alias}")
            old = repo / before[name] if name in before else None
            new = repo / after[name] if name in after else None
            if new and not (new / "SKILL.md").is_file():
                raise ValueError(f"缺少 SKILL.md: {new}")
            count += sync_entry(root / alias, new, old, alias, agent == "codex" or alias != name)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{name} — {exc}")
    return count, errors


def sync_agents(repo, source, targets, old, new, before, after, completed):
    groups, target_errors = targets
    issues = [f"{name} — {error}" for name, error in target_errors.items()]
    modified = 0
    # Each physical directory may have missed different updates while offline or disabled.
    checkpoints = dict(line.split() for line in git(
        repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/skills-dispatch/"
    ).splitlines())
    catalogs = {old: before, new: after}
    for root, group in groups.items():
        label = "、".join(group)
        key = hashlib.sha256(os.fsencode(os.path.normcase(str(root)))).hexdigest()
        ref = "refs/skills-dispatch/targets/" + key
        previous = checkpoints.get(ref, checkpoints.get(LINKED_REF, old))
        try:
            if previous not in catalogs:
                catalogs[previous] = read_skills(repo, previous, source)
            count, errors = sync_directory(repo, source, catalogs[previous], after, group[0], root)
            modified += count
            if errors:
                raise ValueError("\n".join(errors))
            if checkpoints.get(ref) != new:
                git(repo, "update-ref", ref, new)
            if completed is not None:
                for agent in group:
                    completed[agent] += 1
            print(f"  {label} → {root}：同步成功，本次调整 {count} 个入口。")
        except (OSError, ValueError, RuntimeError) as exc:
            issues.append(f"{label} ({root}) — {exc}")
    print(f"发布清单 {len(after)} 项，本次调整入口 {modified} 个。")
    if issues:
        raise RuntimeError("\n".join(issues))


def report_changes(repo, source, old, new, before, after, report):
    if old == new:
        report.record(source["path"], f"{new}\n上游无更新。")
        print("上游无更新。")
        return
    print(f"{source['path']}  {old[:8]} -> {new[:8]}")
    changed = git(repo, "diff", "--no-renames", "--name-only", "-z", old, new, "--").split("\0")
    entries, filters = [], set()
    for name in sorted(before.keys() | after.keys()):
        paths = set(source.get("sharedPaths", []))
        paths.update(p for p in (before.get(name), after.get(name)) if p)
        matched = [f for f in changed if f and any(p == "." or f == p or f.startswith(p + "/") for p in paths)]
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
    overview = "\n".join(f"- {entry}" for entry in entries) or "已更新仓库，已启用的 Skill 均无变化。"
    print(overview)
    details = f"{old} -> {new}\n{overview}\n\n变动文件\n" + "\n".join(filter(None, changed))
    patch = ""
    if filters:
        patch = git(repo, "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv", "--no-color",
                    "--unified=2", old, new, "--", *sorted(filters))
    report.record(source["path"], details, changed=True, patch=patch)


def update_source(root, source, targets, *, links_only=False, init_missing=True, report=None, completed=None):
    path = source["path"]
    print(f"\n[{path}]", flush=True)
    repo = root / path
    if not (repo / ".git").exists():
        if not init_missing:
            raise ValueError("子模块尚未检出。可运行 git submodule update --init 后重新同步。")
        git(root, "submodule", "update", "--init", "--checkout", "--", path)
    old = git(repo, "rev-parse", "HEAD")
    before = read_skills(repo, old, source)
    if not links_only:
        if git(repo, "status", "--porcelain"):
            raise ValueError("子模块有本地改动，本次跳过更新。")
        git(root, "submodule", "update", "--init", "--remote", "--checkout", "--", path)
    new = git(repo, "rev-parse", "HEAD")
    after = read_skills(repo, new, source) if old != new else before
    if report is not None:
        report_changes(repo, source, old, new, before, after, report)
    sync_agents(repo, source, targets, old, new, before, after, completed)
    git(repo, "update-ref", LINKED_REF, new)
    return after


def update_sources(home, *, configure=False, links_only=False, init_missing=True, no_ai=False, ai_command=None):
    """Apply the requested operation to each registered source under the shared lock."""
    failed = False
    with update_lock(ROOT):
        config = read_config(ROOT)
        profile = local_profile(ROOT, home, config, configure=configure)
        sources = configured_sources(ROOT, config.get("sources", []))
        targets = directory_groups(home, profile["agents"], sources)
        report = None if links_only else UpdateReport(ROOT)
        if not sources:
            print("当前没有已登记的 Skill 来源。")
            for agent, error in targets[1].items():
                print(f"{agent} — {error}", file=sys.stderr)
            failed = bool(targets[1])
        if not sources and report is not None:
            report.record("来源", "当前没有已登记的 Skill 来源。")
        completed = dict.fromkeys(profile["agents"], 0)
        for source in sources:
            try:
                update_source(ROOT, source, targets, links_only=links_only,
                              init_missing=init_missing, report=report, completed=completed)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                print(f"{source['path']} — {exc}", file=sys.stderr)
                if report is not None:
                    report.record(source["path"], f"处理失败：{exc}")
                failed = True
        if sources and completed:
            print("\n各 Agent 同步结果")
            for agent, count in completed.items():
                print(f"  {agent}：{count}/{len(sources)} 个来源已同步")
    if report is not None:
        report.finish(no_ai, ai_command)
    return int(failed)


def read_config(root):
    return json.loads((root / CONFIG_PATH).read_text(encoding="utf-8-sig"))


def agent_home_argument(parser):
    parser.add_argument("--agent-home", type=Path, default=Path.home(), help="指定个人入口的根目录")


def run_cli(main):
    if os.name == "nt" and not os.environ.get("PYTHONIOENCODING"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        return main()
    except EOFError:
        print("\n已取消。")
        return 0
    except KeyboardInterrupt:
        print("\n已中止。")
        return 130
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
