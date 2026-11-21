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

在 Windows PowerShell 中，从本仓库运行 `.\update-skills.ps1`。脚本先更新子模块，再核对本次更新前后的提交，按启用的 Skill 输出中文摘要。行为摘要使用本机已登录的 Codex CLI；使用 `-NoAI` 可只列出变动文件。获取上游失败时会列出失败的仓库并返回非零退出码。

如果 Windows PowerShell 提示脚本策略受限，可执行 `powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\update-skills.ps1`。此选项只影响该次启动的 PowerShell 进程。

首次换机可以使用 `git clone --recurse-submodules <本仓库地址>`，然后运行 `.\update-skills.ps1 -LinksOnly`，按主仓库记录的版本创建个人入口。日常更新后，在主仓库提交变更的子模块指针即可保存这组版本。

[skills.json](skills.json) 配置来源、发布清单、Agent 入口和同名别名。Matt Pocock 的来源采用上游插件清单的全部公开 Skill。Windows 版 Codex 的个人目录使用可发现的 `SKILL.md` 入口，保留上游描述与 `agents` 元数据，正文指向子模块原件。每个入口的 `.source` 目录联接可直接访问原始脚本和模板。Claude Code 使用目录联接，重名的 Skill 使用独立命名的入口。Claude Code 的 Matt 版代码审查使用 `/mattpocock-code-review`。需要纳入摘要的仓库级共享文件或目录可加入对应来源的 `sharedPaths`。
