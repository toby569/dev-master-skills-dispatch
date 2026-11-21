# 版本记录

|    日期    | 版本  |   说明   | 作者 |
| :--------: | :---: | :------: | :--: |
| 2023-10-11 | 1.0.0 | 初始版本 | toby |
|            |       |          |      |
|            |       |          |      |

# 目录

[toc]









## 开始

## 使用方法

需要 Python 3.10 或以上版本和 Git。在仓库根目录运行：

```sh
python update-skills.py
```

脚本更新子模块，把每个公开 Skill 同步到个人 Codex 和 Claude Code，并在终端显示中文变更摘要。行为摘要使用本机已登录的 Codex CLI。使用 `python update-skills.py --no-ai` 可只列出变动的 Skill 和文件。上游获取失败时，脚本会报告具体来源，继续处理其余来源，最后返回非零退出码。

首次换机可以使用 `git clone --recurse-submodules <本仓库地址>`，然后运行 `python update-skills.py --links-only`，按本地检出的版本创建个人入口。需要使用其他个人目录时，可传入 `--agent-home <目录>`。日常更新后，在主仓库提交变更的子模块指针即可保存这组版本。

原 PowerShell 命令仍可使用，它会把参数转交给 Python 脚本。

### 添加 Skill 来源

运行独立的添加脚本：

```sh
python add-skill-repo.py
```

粘贴 Git 仓库的 HTTPS 或 SSH 克隆地址，也可以输入 GitHub 的 `owner/repo`。脚本会建议本地目录名，回车即可接受，也可以输入其他名称。添加成功后会显示发现的 Skill，并同步到配置的个人 Agent。已登记的地址会复用原有目录。输入 `q` 可以取消。

默认按各子模块的提交内容发现 Skill：

1. 优先使用 `.claude-plugin/plugin.json` 或 `.codex-plugin/plugin.json` 的 `skills` 声明，仅分发声明的目录。
2. 仓库根目录含有 `SKILL.md` 时，按文件头的 `name` 分发这个单独的 Skill。
3. 其他仓库从 `skills/` 递归查找 `SKILL.md`。每个 Skill 自带的示例和隐藏子目录均跳过。没有匹配项的仓库仍更新，入口数显示为 0。

[skills.json](skills.json) 的 `agents` 定义个人入口位置，`sources` 只需填写有例外配置的子模块。例如，使用非标准目录时可添加 `{"path":"upstreams/example","skillRoots":["packages/public-skills"]}`。也可以通过 `manifest` 指定其他发布清单。每个来源可以设置 `aliases` 解决同名冲突，用 `sharedPaths` 将共享文件纳入变更摘要。

当前 Matt Pocock 来源按其插件发布清单分发，Vercel 来源从 `skills/find-skills` 分发 `find-skills`。

### 移除 Skill 来源

```sh
python remove-skill-repo.py
```

脚本列出已登记的子模块。输入编号，选择是否同步清理个人 Agent 入口，再确认移除。回车或输入 `q` 可以在选择阶段退出。

- **清理入口**会移除所选子模块的工作目录和指向它的受管入口。同名的其他来源和手工安装的目录会保留。子模块内有本地修改或未提交的文件时，脚本会提示先保存。
- **保留入口**会取消 Git 子模块登记，保留已有入口、本地源码和该来源的别名等配置。源码目录此时是未跟踪目录，再次添加同一仓库可重新登记它。提交移除操作时，只提交计划中的文件，避免把保留的目录重新加入索引。

来源登记的改动保存在本地 Git 仓库中。完成后用 `git status` 查看改动，再按需提交和推送。两个脚本共用 `skill_dispatch.py`，均支持 `--agent-home <目录>`。日常更新仍使用 `python update-skills.py`。

Windows 版 Codex 的个人目录使用可发现的 `SKILL.md` 入口，保留上游描述与 `agents` 元数据，正文指向子模块原件。每个入口的 `.source` 目录联接可直接访问原始脚本和模板。Claude Code 使用目录联接，重名的 Skill 使用独立命名的入口。Claude Code 的 Matt 版代码审查使用 `/mattpocock-code-review`。
