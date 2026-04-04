---
name: frontend-ui-copy
description: Rewrite visible frontend copy into clear, human-facing product language. Use when writing or revising labels, status text, helper text, empty states, errors, toasts, modal copy, onboarding copy, or explanation text shown to end users, especially when the current wording sounds like backend narration, policy defense, raw system output, or internal process notes.
---

# Frontend UI Copy

## Goal

Write UI text as if the product is speaking to the user, not as if the backend is defending itself.

If a string is visible to normal users, optimize for clarity, warmth, and actionability first. Only expose internal terms in debug or admin-only views.

## Core Rules

- Speak to the user's task, not the system's implementation.
- Prefer plain, natural Chinese or plain product English over mixed internal jargon.
- Tell the user what is happening, why it matters, or what they can do next.
- Keep one string focused on one job. Do not stack policy, architecture, and status into one sentence.
- Hide internal concepts such as `chain-of-thought`, `tool call`, `reviewer`, `worker`, `endpoint`, `schema`, `JSON`, `variable`, or file paths unless the view is explicitly technical.
- Avoid "backend辩护式" wording such as "系统只展示..." "不直接暴露..." "当前模块..." unless the page is a technical spec.

## Writing Pattern

Use these defaults:

- Button: verb + object
- Status: current action + expected result
- Empty state: current absence + recommended next step
- Error: what failed + safe next action
- Explanation: what the user will see or get, then the boundary if needed

## Style Targets

- Short and scannable
- Conversational, but not cute
- Clear, but not mechanical
- Interactive, but not verbose
- Honest about limits, but not defensive

## Rewrite Checklist

Before finalizing a user-facing string, check:

1. Is the subject the user's goal instead of "the system"?
2. Did I remove internal roles, pipeline steps, and implementation nouns?
3. Can the user tell what happens next?
4. Would this sound normal inside a product UI, not inside a backend README?

## Good Defaults

- Use `正在整理线索，稍后给你结论` instead of `执行分析流程中`
- Use `这里会展示处理进展和依据摘要` instead of `系统展示公开工作备忘录和工具调用`
- Use `还没有结果，先添加一批数据试试` instead of `当前列表为空`
- Use `这次读取没有完成，请重试` instead of `请求失败`

## Bad vs Better

- Bad: `系统只展示公开工作备忘录、工具调用和 reviewer 裁决，不直接暴露原始 chain-of-thought。`
- Better: `这里会展示处理进展和判断依据，内部推理细节默认不展开。`

- Bad: `后端正在执行热点总览 fast 模式轻量证据抓取。`
- Better: `正在整理热点概览，并补充关键信息。`

- Bad: `已触发 research branch，等待 playwright fallback。`
- Better: `已切换到深入模式，正在继续补充资料。`

- Bad: `工具调用完成，返回空结果。`
- Better: `这次没有找到可展示的结果，你可以换个条件再试。`

## Boundary

Do not use this skill for:

- API docs
- developer logs
- admin-only debug panels
- migration notes
- code comments

For those cases, technical accuracy can stay primary. For normal frontend copy, user readability stays primary.
