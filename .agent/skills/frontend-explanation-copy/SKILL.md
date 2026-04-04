---
name: frontend-explanation-copy
description: Rewrite visible frontend explanation text into clear, user-facing product language. Use when editing helper paragraphs, run instructions, status descriptions, empty states, onboarding tips, or other explanatory text shown to end users, especially when the current wording sounds like backend narration, debugging hints, internal process notes, or implementation detail.
---

# Frontend Explanation Copy

## Goal

Write explanatory UI text for users, not for engineers.

Make each sentence answer one of these questions:

- What is happening?
- Why does it matter?
- What can the user do next?

## Rules

- Start from the user's task or outcome.
- Describe visible behavior, benefit, or next step.
- Avoid backend terms, internal role names, file paths, ports, prompt internals, or execution breadcrumbs.
- If a limit or boundary is needed, state it in plain product language.
- Keep each sentence short and meaningful.
- Prefer "what happens next" over "what the system hides".

## Rewrite Pattern

- Bad: `系统只展示公开工作备忘录、工具调用和产物状态，不直接暴露原始 chain-of-thought。`
- Good: `这里会展示任务进展、关键回执和成果状态，方便你随时了解运行到哪一步。`

- Bad: `请查看后端 8001 端口返回的调试信息。`
- Good: `你可以在这里查看当前任务的运行结果和更新进度。`

- Bad: `已触发 research branch，等待 playwright fallback。`
- Good: `已切换到深入模式，正在继续补充资料。`

## Use When

Use this skill for:

- page descriptions
- section introductions
- helper text
- process notes visible to end users
- empty-state hints
- loading and progress explanations

Do not use it for:

- developer logs
- API docs
- admin-only diagnostics
- code comments

## Check

Before finalizing a string, check whether a normal user would find it:

- understandable without backend context
- useful for deciding what to do next
- specific to the visible screen
- free of internal implementation hints
