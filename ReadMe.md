# Dev Master Skills Dispatch

如果你在 Codex 和 Claude Code 里用同一个 Skill，又从几个不同作者那里安装了其他 Skill，升级一次就得检查好几个仓库，再给两个工具分别换文件。**这个工具让多个 Agent 共用一份 Skill 源码。运行 `python scripts/update-skills.py`，就能更新所有已登记的来源，并看到这次改动影响了哪些 Skill。**

## 快速开始

准备好 Git 和 Python 3.10 或更高版本，运行以下命令，把本仓库记录的 Skill 版本同步到本机：

```sh
git clone --recurse-submodules https://github.com/toby569/dev-master-skills-dispatch.git
cd dev-master-skills-dispatch
python scripts/sync-skills-to-local-agents.py
```

首次在终端运行时，按编号选择这台电脑上的 Agent。只用 Claude Code 就输入 `2`，同时用 Codex 和 Claude Code 就输入 `1,2`，还有其他工具就输入 `1,2,+`。逐个确认 Skill 目录，输入 `-` 可跳过某个工具。预览实际路径后输入 `y` 保存并同步。下次运行会直接使用已保存的选择。

仓库已收录 Matt Pocock 的开发工作流、Vercel 的 `find-skills` 和 BMAD-METHOD。以后要获取上游新版，在仓库根目录运行：

```sh
python scripts/update-skills.py
```

## 说明

**更新后能知道使用方式有什么变化。** 例如，Matt Pocock 的 `tdd` 曾改过一行指令。以前只问“要测试哪些接口？”，更新后还会说明在每个候选接口上测试能发现什么、会漏掉什么。更新明细会列出受影响的 Skill、前后提交和相关补丁。配置好 AI 命令行工具后，还可以直接看这样的中文解读。[查看这次上游改动](https://github.com/mattpocock/skills/commit/3f599139104dfceabc7754eeb91319802f85e042)

**换电脑或与同事分享时能复现同一套版本。** 每个来源都是 Git 子模块。把更新后的子模块指针提交并推送到自己的管理仓库，另一台电脑按“快速开始”克隆和同步，拿到的就是你记录的版本。

## 常用命令

| 我想做什么 | 在仓库根目录运行 | 结果 |
| --- | --- | --- |
| 添加一个作者的仓库 | `python scripts/add-skill-repo.py` | 输入 HTTPS、SSH 地址或 GitHub 的 `owner/repo`，回车接受建议目录，发现的 Skill 会同步到个人 Agent。 |
| 更新全部来源 | `python scripts/update-skills.py` | 拉取新版、同步入口，把明细保存到 `reports/skill-updates-*.txt`。 |
| 在另一台电脑或新配置的 Agent 上启用当前版本 | `python scripts/sync-skills-to-local-agents.py` | 按本地已检出的版本创建或修复入口。重复运行只调整有变化的入口。 |
| 新增、停用 Agent 或更换目录 | `python scripts/sync-skills-to-local-agents.py --configure` | 重新选择本机目标，确认后按当前版本同步。 |
| 移除一个来源 | `python scripts/remove-skill-repo.py` | 按编号选择仓库，再选择是否清理个人 Agent 入口。 |

### 查看更新明细和中文摘要

更新命令会在终端打印报告的完整路径。报告记录各来源的提交、变动文件、受影响的 Skill 和相关 Git 补丁。某个来源拉取失败时，脚本会记录原因，继续处理其余来源，并以非零退出码结束。

Python 和 Git 足以完成添加、更新、同步和移除。AI 只用于解读变更。有变更时，脚本会先保存明细，再尝试本机已配置的 Codex CLI 和 Claude Code CLI，成功后把中文摘要追加到同一份报告。也可以按需选择：

- 只想看 Git 明细时，运行 `python scripts/update-skills.py --no-ai`。
- 要使用其他 AI 工具，可以在更新命令的末尾加 `--ai-command <程序> [参数...]`。程序从标准输入读取变更记录，通过标准输出返回摘要。

### 一台电脑上使用多个 Agent

四个命令共用本机配置。交互菜单会参考已有目录和可用的命令行程序预先勾选候选项。只安装了桌面版或使用自定义目录的工具，也可以手动选中。工具需要支持从本地目录读取 `SKILL.md`。

| 你的选择 | 将会发生什么 |
| --- | --- |
| 仅选 Claude Code | 默认安装到 `~/.claude/skills`。 |
| 选 Codex 和 Claude Code | 每个公开 Skill 各有一个入口，分别放在 `~/.agents/skills` 和 `~/.claude/skills`，共用同一份源码。仓库配置的别名按 Agent 生效。 |
| 再添加其他工具 | 在编号中加入 `+`，输入自定义标识（如 `team-agent`）及该工具读取 Skill 的目录。可连续添加多个。 |
| 两个工具读取同一个目录 | 入口格式及别名一致时只写入一次。规则冲突时，向导会列出工具名并请你重新选目录。 |
| 暂时只想更新来源 | 输入 `0`。更新命令仍会拉取上游并生成变更报告。 |

相对路径以个人主目录为起点，也可输入绝对路径。四个命令均支持 `--agent-home <目录>` 来指定相对路径的起点。工具和目录选择保存在当前克隆的 `config/skills.local.json`，Git 会忽略它。共享的 [config/skills.json](config/skills.json) 负责候选工具的建议路径，以及各来源的发现规则和别名。

以后要增加工具、停用工具或迁移目录，重新运行：

```sh
python scripts/sync-skills-to-local-agents.py --configure
```

停用工具时，若旧目录有指向已登记来源的受管入口，向导会询问是否清理。回车保留入口，脚本会记住旧目录，供以后移除来源时核对。选 `y` 清理只会移除受管入口。仍有其他已选 Agent 使用的目录会继续同步。例如，两个编辑器都使用 `~/team-skills`，取消其中一个后，另一个仍可使用目录中的 Skill。

**无人值守运行。** 在 CI 或没有交互终端时，先创建 `config/skills.local.json`，再运行同步或更新命令。例如，下面的配置会同时启用 Claude Code 和一个团队工具：

```json
{
  "agents": {
    "claude": ".claude/skills",
    "team-agent": ".team/skills"
  }
}
```

缺少本机配置时，非交互同步会退出并显示配置方法。同步时若某个目标不可写，终端会显示失败的 Agent 和路径，并继续处理可用目标，最终返回非零退出码。修复目录后重新运行同步即可。若提示子模块尚未检出，先运行 `git submodule update --init --recursive`。

### 配置非标准仓库和别名

添加来源时，脚本优先读取 Claude 或 Codex 插件清单中的 `skills` 声明，其次识别根目录里的单个 `SKILL.md`，最后从 `skills/` 递归发现 Skill。标准布局只需提供仓库地址。特殊情况在配置文件的 `sources` 中指定：

- `skillRoots` 或 `manifest` 指定非标准技能目录或发布清单。例如 `{"path":"upstreams/example","skillRoots":["packages/public-skills"]}`。
- `aliases` 处理同名入口。例如 Claude Code 中的 `/mattpocock-code-review` 可以和团队自己的 `/code-review` 共存。
- `sharedPaths` 把多个 Skill 共用的文件纳入更新摘要。

Windows 上，Codex 使用保留上游描述和 `agents` 元数据的 `SKILL.md` 入口，`.source` 目录联接指向原始脚本与模板。Claude Code 使用目录联接，同名 Skill 使用单独命名的入口。

### 移除来源时如何选择

- **清理入口**适合以后也不用这个来源的情况。脚本会移除子模块工作目录，以及个人 Agent 中指向它的受管入口，保留其他来源和手动安装的同名目录。若子模块有本地修改，脚本会提示先保存。
- **保留入口**适合想继续用当前版本、停止跟进上游的情况。脚本取消子模块登记，保留现有入口、别名配置和本地源码。源码目录会变成未跟踪目录。提交移除操作时，只暂存本次计划提交的文件。

添加或移除后，用 `git status` 检查管理仓库的改动，再按需提交和推送。交互式菜单中输入 `q` 可以取消。

## 版本记录

| 日期 | 版本 | 说明 | 作者 |
| --- | --- | --- | --- |
| 2023-10-11 | 1.0.0 | 初始版本 | toby |
