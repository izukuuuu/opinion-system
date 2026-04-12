# Shared Tool Authoring Standard

适用范围：`backend/src/report/tools` 以及 `deep_report/agent_tools.py` 中所有会被 LangGraph 或 Deep Agents 消费的工具。

## Core Rule

工具必须写成 shared LangChain tool abstraction，而不是框架私有节点语义：

- 统一暴露 `tool name + description + args schema + return contract`
- 允许 Deep Agents 和 LangGraph 复用同一 `BaseTool`
- 不把 graph sequencing、审批恢复、cache 生命周期、报告编译流程塞进 tool body

## Required Structure

1. 底层是纯业务函数：只处理检索、聚合、数据库、payload transform、对象构建。
2. 中间层是 typed schema：复杂参数用 Pydantic / typed contract。
3. 最外层是薄 `@tool` wrapper：只负责把业务逻辑暴露给模型。

## Tool Classes

- `read`: retrieval / lookup / snapshot / metrics fetch
- `synthesis`: typed semantic transform or deterministic object builder
- `state_mutating`: 修改共享状态但不属于高风险外部副作用
- `manual`: 高风险或需人工批准的调用；默认不进入 autonomous runtime surface

## Boundary Rules

- 固定顺序步骤必须留在 LangGraph node / subgraph：
  - report compile
  - semantic gate
  - repair / retry loop
  - cache persistence
  - approval resume
- 适合做 tool 的只包括：
  - 原子环境动作
  - 证据读取与查询
  - typed semantic object construction
  - 可复用的局部 state/object transform

## Skill Contract Rules

- `allowed_tools` 是唯一的 authored tool 声明
- 没有工具契约的 skill 必须显式 `guidance_only: true`
- skill 只能声明 canonical tool ids
- skill 只能绑定已声明的 capability/runtime/agent family

## Runtime Projection Rules

- coordinator / subagent / agent runtime / manual-only surface 都从 capability manifest 投影
- runtime code 不允许再维护独立 tool registry
- subagent 只能看到其 method contract 对应的最小工具切片
