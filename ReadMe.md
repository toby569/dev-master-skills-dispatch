# Dev Master Skills Dispatch

如果你在 Codex 和 Claude Code 里用同一个 Skill，又从几个不同作者那里安装了其他 Skill，升级一次就得检查好几个仓库，再给两个工具分别换文件。**这个工具让多个 Agent 共用一份 Skill 源码。运行 `python scripts/update-skills.py`，就能更新所有已登记的来源，并看到这次改动影响了哪些 Skill。**

## 快速开始

准备好 Git 和 Python 3.10 或更高版本，运行以下命令，把本仓库记录的 Skill 版本同步到本机：

```sh
git clone --recurse-submodules https://github.com/toby569/dev-master-skills-dispatch.git
cd dev-master-skills-dispatch
python scripts/sync-skills-to-local-agents.py
```

默认同步到个人目录 `~/.agents/skills`（Codex）和 `~/.claude/skills`（Claude Code）。仓库已收录 Matt Pocock 的开发工作流、Vercel 的 `find-skills` 和 BMAD-METHOD。以后要获取上游新版，在仓库根目录运行：

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
| 移除一个来源 | `python scripts/remove-skill-repo.py` | 按编号选择仓库，再选择是否清理个人 Agent 入口。 |

### 查看更新明细和中文摘要

更新命令会在终端打印报告的完整路径。报告记录各来源的提交、变动文件、受影响的 Skill 和相关 Git 补丁。某个来源拉取失败时，脚本会记录原因，继续处理其余来源，并以非零退出码结束。

Python 和 Git 足以完成添加、更新、同步和移除。AI 只用于解读变更。有变更时，脚本会先保存明细，再尝试本机已配置的 Codex CLI 和 Claude Code CLI，成功后把中文摘要追加到同一份报告。也可以按需选择：

- 只想看 Git 明细时，运行 `python scripts/update-skills.py --no-ai`。
- 要使用其他 AI 工具，可以在更新命令的末尾加 `--ai-command <程序> [参数...]`。程序从标准输入读取变更记录，通过标准输出返回摘要。

### 配置其他 Agent 或非标准仓库

编辑 [config/skills.json](config/skills.json) 的 `agents`。例如，添加 `"my-agent": ".my-agent/skills"`，再运行本地同步命令，就会在个人主目录下创建对应入口。四个命令均支持 `--agent-home <目录>`。若本地同步提示某个子模块尚未检出，可先运行 `git submodule update --init --recursive`。

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
