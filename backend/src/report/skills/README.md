# Report Skills

生产环境报告技能默认放在 `backend/src/report/skills/` 下，运行时优先走 Deep Agents 的 skills 机制。

约定：

- 每个技能优先使用独立目录，目录内主文件为 `SKILL.md`
- `SKILL.md` 使用 Markdown 正文，支持 YAML frontmatter
- frontmatter 至少包含 `name`、`description`
- 推荐使用 `allowed_tools` 和 `metadata.report.*`
- 长方法论、示例、模板等支持材料放在 `references/`、`assets/`、`scripts/`

运行时行为：

- `deepagents` 模式下，启动时只暴露 skill catalog，命中后按需读取完整 `SKILL.md`
- `plain` fallback 模式下，agent 通过 `load_skill` 工具按需加载同一套 skill 资产
- 外部技能目录可通过 `backend/configs/llm.yaml` 的 `langchain.report.skills.load.extra_dirs` 注入
- 项目级 `.agents/skills/` 默认关闭，可通过 `langchain.report.skills.load.enable_project_agents_dir` 打开

当前内置技能：

- `sona-feature-analysis`

兼容目标：

- Agent Skills / Deep Agents 兼容的 `SKILL.md`
- OpenClaw 风格的 `metadata.openclaw.skillKey`
- 解包后的 `skills/`、`commands/`、`.cursor/commands/` 目录会被标准化后接入
