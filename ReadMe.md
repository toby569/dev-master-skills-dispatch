# 版本记录

|    日期    | 版本  |   说明   | 作者 |
| :--------: | :---: | :------: | :--: |
| 2023-10-11 | 1.0.0 | 初始版本 | toby |
|            |       |          |      |
|            |       |          |      |

# 目录

[toc]



## 使用方法

### 添加 Skill 来源

运行独立的添加脚本：

```sh
python scripts/add-skill-repo.py
```

粘贴 Git 仓库的 HTTPS 或 SSH 克隆地址，也可以输入 GitHub 的 `owner/repo`。脚本会建议本地目录名，回车即可接受，也可以输入其他名称。添加成功后会显示发现的 Skill，并同步到配置的个人 Agent。已登记的地址会复用原有目录。输入 `q` 可以取消。

默认按各子模块的提交内容发现 Skill：

1. 优先使用 `.claude-plugin/plugin.json` 或 `.codex-plugin/plugin.json` 的 `skills` 声明，仅分发声明的目录。
2. 仓库根目录含有 `SKILL.md` 时，按文件头的 `name` 分发这个单独的 Skill。
3. 其他仓库从 `skills/` 递归查找 `SKILL.md`。每个 Skill 自带的示例和隐藏子目录均跳过。没有匹配项的仓库仍更新，入口数显示为 0。

[config/skills.json](config/skills.json) 的 `agents` 定义个人入口位置，`sources` 只需填写有例外配置的子模块。来源的 `path` 相对于仓库根目录。例如，使用非标准目录时可添加 `{"path":"upstreams/example","skillRoots":["packages/public-skills"]}`。也可以通过 `manifest` 指定其他发布清单。每个来源可以设置 `aliases` 解决同名冲突，用 `sharedPaths` 将共享文件纳入变更摘要。

当前 Matt Pocock 来源按其插件发布清单分发，Vercel 来源从 `skills/find-skills` 分发 `find-skills`。

### 更新 Skill

需要 Python 3.10 或以上版本和 Git。在仓库根目录运行：

```sh
python scripts/update-skills.py
```

脚本更新子模块，并把公开 Skill 同步到已配置的 Agent。每次更新都在仓库的 `reports/` 目录生成一份带时间戳的 UTF-8 文本文件（`skill-updates-*.txt`），终端会显示完整路径。文件记录各来源的版本、变动文件、受影响的 Skill 和相关 Git 补丁。上游获取失败时，脚本会记录具体来源，继续处理其余来源，最后返回非零退出码。

有更新时，脚本先保存明细，再依次尝试本机已配置的 Codex CLI 和 Claude Code CLI 生成中文摘要。成功后，摘要会显示在终端并追加到同一份文件。两个工具都不可用时，按终端提示打开明细即可。要直接生成明细并跳过 AI，运行 `python scripts/update-skills.py --no-ai`。添加、移除和只同步入口均只需 Python 和 Git。

使用其他 AI 工具时，可在更新命令末尾加上 `--ai-command <程序> [参数...]`。脚本只运行指定程序，通过标准输入传入变更记录，从标准输出读取摘要。

首次换机可以使用 `git clone --recurse-submodules <本仓库地址>`，然后运行 `python scripts/sync-skills-to-local-agents.py`，按本地检出的版本创建个人入口。需要使用其他个人目录时，可传入 `--agent-home <目录>`。日常更新后，在主仓库提交变更的子模块指针即可保存这组版本。

### 将当前 Skill 同步到本地 Agent

在 [config/skills.json](config/skills.json) 的 `agents` 对象中添加新工具及其 Skill 目录，例如 `"my-agent": ".my-agent/skills"`。保存后从仓库根目录运行：

```sh
python scripts/sync-skills-to-local-agents.py
```

脚本按本地已检出的版本，将各来源的公开 Skill 同步到所有已配置的 Agent。示例中的目录会自动创建在个人主目录下，也可以用 `--agent-home <目录>` 指定其他根目录。重复运行只会调整有变化的入口。如果某个来源尚未检出，脚本会提示该来源，并继续同步其他来源。需要拉取上游新版本时，运行 `python scripts/update-skills.py`。



### 移除 Skill 来源

```sh
python scripts/remove-skill-repo.py
```

脚本列出已登记的子模块。输入编号，选择是否同步清理个人 Agent 入口，再确认移除。回车或输入 `q` 可以在选择阶段退出。

- **清理入口**会移除所选子模块的工作目录和指向它的受管入口。同名的其他来源和手工安装的目录会保留。子模块内有本地修改或未提交的文件时，脚本会提示先保存。
- **保留入口**会取消 Git 子模块登记，保留已有入口、本地源码和该来源的别名等配置。源码目录此时是未跟踪目录，再次添加同一仓库可重新登记它。提交移除操作时，只提交计划中的文件，避免把保留的目录重新加入索引。

来源登记的改动保存在本地 Git 仓库中。完成后用 `git status` 查看改动，再按需提交和推送。添加和移除命令均支持 `--agent-home <目录>`。日常更新仍使用 `python scripts/update-skills.py`。

Windows 版 Codex 的个人目录使用可发现的 `SKILL.md` 入口，保留上游描述与 `agents` 元数据，正文指向子模块原件。每个入口的 `.source` 目录联接可直接访问原始脚本和模板。Claude Code 使用目录联接，重名的 Skill 使用独立命名的入口。Claude Code 的 Matt 版代码审查使用 `/mattpocock-code-review`。
