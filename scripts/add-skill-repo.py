"""Interactively register a Skill repository and install its skills."""
import argparse
import os
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import urlsplit

from internal.skill_dispatch import (
    CONFIG_PATH, ROOT, agent_home_argument, ask, configured_sources, git, read_config,
    registered_submodules, run_cli, update_lock, update_source,
)


def address(value):
    """Return a clone URL, comparison key, and suggested checkout name."""
    segment = r"[A-Za-z0-9_.-]+"
    if re.fullmatch(f"{segment}/{segment}", value):
        value = "https://github.com/" + value
    scp = re.fullmatch(r"([\w.-]+@[\w.-]+):(.+)", value)
    parsed = urlsplit(f"ssh://{scp[1]}/{scp[2]}" if scp else value)
    if (parsed.scheme not in ("https", "ssh") or not parsed.hostname or parsed.query
            or parsed.fragment or parsed.password is not None or (parsed.scheme == "https" and parsed.username)
            or re.search(r"[\s\\\x00-\x1f]", value)):
        raise ValueError("请输入 HTTPS 或 SSH 克隆地址，也可以输入 GitHub 的 owner/repo。")
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    host = parsed.hostname.casefold()
    if any(not p or p in (".", "..") for p in parts) or (host == "github.com" and len(parts) != 2):
        raise ValueError("请输入仓库首页的地址，例如 https://github.com/owner/repo。")
    port = parsed.port
    if port == {"https": 443, "ssh": 22}[parsed.scheme]:
        port = None
    path = "/".join(parts)
    key = (host, port, path.casefold() if host == "github.com" else path)
    default = re.sub(r"[^\w.-]+", "-", "-".join(parts[-2:])).strip("-.") or "skills"
    return value, key, default


def existing_path(modules, key):
    for path, module in modules.items():
        try:
            if address(module.url)[1] == key:
                return path
        except ValueError:
            continue
    return None


def retained_checkout(folder, key):
    if not (folder / ".git").exists() or folder.resolve() != folder:
        return False
    try:
        url = git(folder, "config", "--local", "--get", "remote.origin.url", missing_ok=True)
        return Path(git(folder, "rev-parse", "--show-toplevel")).resolve() == folder and address(url)[1] == key
    except (ValueError, RuntimeError):
        return False


def main():
    cli = argparse.ArgumentParser(description="交互式添加 Skill 仓库，完成后同步到已配置的 Agent。")
    agent_home_argument(cli)
    home = cli.parse_args().agent_home.expanduser().resolve()
    print("添加 Skill 来源。输入 q 可取消。")
    while True:
        try:
            url, key, default = address(ask("仓库地址（如 https://github.com/owner/skills）："))
            break
        except ValueError as exc:
            print(exc)
    modules = registered_submodules(ROOT)
    path = existing_path(modules, key)
    if not path:
        while True:
            name = ask(f"本地目录名（回车使用 upstreams/{default}）：") or default
            if (not re.fullmatch(r"[\w-][\w .-]*", name) or name.endswith(".")
                    or PureWindowsPath(name).is_reserved()):
                print("请输入单个有效的目录名，例如 my-skills。")
                continue
            path = f"upstreams/{name}"
            if path not in modules and (not os.path.lexists(ROOT / path) or retained_checkout(ROOT / path, key)):
                break
            print(f"{path} 已被占用，请换一个目录名。")

    with update_lock(ROOT):
        config = read_config(ROOT)
        modules = registered_submodules(ROOT)
        known = existing_path(modules, key)
        if known:
            path = known
            print(f"该仓库已登记在 {path}，将核对现有入口。")
        else:
            retained = retained_checkout(ROOT / path, key)
            if path in modules or (os.path.lexists(ROOT / path) and not retained):
                raise ValueError(f"目录已被占用，请重新运行并换一个名称：{path}")
            print(f"正在重新登记本地源码 {path} …" if retained else f"正在克隆到 {path} …", flush=True)
            # git rm retains the former module's object store. Leave it intact on re-add.
            cache = Path(git(ROOT, "rev-parse", "--path-format=absolute", "--git-path", "modules"))
            module_name = path
            suffix = 1
            while not retained and (cache / module_name).exists():
                suffix += 1
                module_name = f"{path}-{suffix}"
            try:
                git(ROOT, "submodule", "add", "--name", module_name, "--", url, path)
            except RuntimeError as exc:
                raise RuntimeError(f"添加失败。请核对仓库地址、网络和 Git 访问权限。\n{exc}") from exc
        source = next(s for s in configured_sources(ROOT, config.get("sources", [])) if s["path"] == path)
        try:
            skills = update_source(ROOT, source, config["agents"], home, links_only=True)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise RuntimeError(f"来源已登记，入口同步未完成：{exc}\n修正后重新运行添加脚本即可重试。") from exc
        if skills:
            print("可用 Skill：" + "、".join(sorted(skills)))
        else:
            print(f"已登记来源。该版本未发现标准布局的 Skill，可在 {CONFIG_PATH} 中指定 skillRoots。")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
