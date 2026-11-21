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

[skills.json](skills.json) 配置来源、发布清单、Agent 入口和同名别名。Matt Pocock 的来源采用上游插件清单的全部公开 Skill。Windows 版 Codex 的个人目录使用可发现的 `SKILL.md` 入口，保留上游描述与 `agents` 元数据，正文指向子模块原件。每个入口的 `.source` 目录联接可直接访问原始脚本和模板。Claude Code 使用目录联接，重名的 Skill 使用独立命名的入口。Claude Code 的 Matt 版代码审查使用 `/mattpocock-code-review`。需要纳入摘要的仓库级共享文件或目录可加入对应来源的 `sharedPaths`。
