---
name: agenda-frame-builder
description: Build issue-attribute-frame maps from conflict graphs, actor positions, and timeline nodes. Distinguish core issues from spillover issues and require timestamped evidence for frame shifts.
allowed_tools: build_agenda_frame_map
metadata:
  report:
    skillKey: agenda_frame_builder
    goal: 从冲突图、主体立场、时间线中识别议题节点、属性节点、框架记录，以及框架转换和反框架，不输出 prose。
---

# Agenda Frame Builder

## Goal

- 从上游结构化分析结果（冲突图、主体立场、时间线）中识别并构建议题-属性-框架图。
- 区分"核心议题"（事件本体：当事人、具体行为、直接后果）与"外溢议题"（制度性追问、价值争论、监管讨论）。
- 每个框架记录必须有时间戳和跨主体的支撑证据，不能只靠单一主体的声明。
- 框架转换事件必须指向具体的触发媒体/账号/内容节点，不能只写"框架从 A 转为 B"。

## Reasoning Style

- 先识别哪些主体在争夺议题定义权，再看他们各自使用的框架（"个人失责" vs "制度漏洞" vs "监管缺位"）。
- 框架差异的判断标准：同一事件，不同主体强调的**因果归因**不同，而非仅表述方式不同。
- 外溢议题的判断标准：原始事件本体争议已相对稳定，但讨论已延伸至更大范围的制度/价值命题。
- 如果所有主体的框架高度一致，应在输出中显式标注"无框架冲突"，而非强行构造差异。

## Current Backend Contract

**读取（只读，不可修改）：**
- `/workspace/state/normalized_task.json` → 提取顶层对象，传给 `normalized_task_json`
- `/workspace/state/evidence_cards.json` → 提取 `.result[*].evidence_id` 字符串列表，传给 `evidence_ids_json`
- `/workspace/state/actor_positions.json` → 提取 `.result` 数组（完整 actor 对象列表），传给 `actor_positions_json`
- `/workspace/state/conflict_map.json` → 提取 `.result` 内层核心对象，传给 `conflict_map_json`
- `/workspace/state/timeline_nodes.json` → 提取 `.result` 数组（完整节点对象列表），传给 `timeline_nodes_json`

**写入：**
- `/workspace/state/agenda_frame_map.json`，格式：
  ```json
  {
    "status": "ok",
    "result": {
      "issue_nodes": [...],
      "frame_records": [...],
      "frame_shifts": [...],
      "counter_frames": [...]
    }
  }
  ```

**空结果格式（上游为空时）：**
```json
{
  "status": "empty",
  "reason": "<具体原因>",
  "result": { "issue_nodes": [], "frame_records": [], "frame_shifts": [], "counter_frames": [] },
  "skipped_due_to": ["upstream_empty"]
}
```

## Constraints

- 禁止只输出 prose 摘要（必须输出结构化框架对象）。
- 框架差异必须有跨主体的证据支撑，不能只靠推断。
- 不要把"各方说法不同"直接等同于"框架冲突"——框架冲突需要不同的因果归因，不只是表述差异。
- 框架转换必须指向具体触发节点（媒体报道/关键账号发言/官方声明），不能只写时间段。
- 若依赖文件不存在或为空，生成标准化空结构，禁止输出警告性提示或反复重试。

## Expected Output Shape

```json
{
  "issue_nodes": [
    {
      "issue_id": "iss-001",
      "label": "议题标签",
      "type": "core | spillover",
      "time_range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
      "evidence_ids": ["ev-001"]
    }
  ],
  "frame_records": [
    {
      "frame_id": "frm-001",
      "issue_id": "iss-001",
      "actor_id": "act-001",
      "frame_label": "框架名称",
      "causal_attribution": "因果归因描述",
      "timestamp": "YYYY-MM-DD",
      "evidence_ids": ["ev-002"]
    }
  ],
  "frame_shifts": [
    {
      "from_frame": "frm-001",
      "to_frame": "frm-002",
      "trigger_node": "触发节点描述（媒体/账号/内容）",
      "timestamp": "YYYY-MM-DD",
      "evidence_ids": ["ev-003"]
    }
  ],
  "counter_frames": [
    {
      "counter_frame_id": "cf-001",
      "target_frame_id": "frm-001",
      "counter_actor_id": "act-002",
      "counter_label": "反框架标签",
      "evidence_ids": ["ev-004"]
    }
  ]
}
```
