# Report RAG Knowledge Base

该目录是 `report` 模块唯一的正式 RAG 入库根目录。

类型元信息由同级 [manifest.json](/F:/opinion-system/backend/knowledge_base/report/rag/manifest.json) 驱动，包含：
- `directory`
- `label`
- `description`
- `writer_auto_allowed`

允许的知识库类型固定为：
- `methodology`
- `cases`
- `expert_notes`
- `youth_insight`
- `policy`

目录约束：
- 每个 `knowledge_type` 必须使用独立子目录。
- 每个 `knowledge_type` 的目录名由 `manifest.json` 中的 `directory` 指定。
- RAG 检索器只会读取 `backend/knowledge_base/report/rag/<knowledge_type>/`。
- 不允许跨目录猜路径或扫描 skill reference 目录。
- 文档应保留原始文件名，便于回溯。

建议入库规则：
- `methodology`：方法论、理论框架、研究资料、综述型材料。
- `cases`：历史案例、事件复盘、典型争议事件。
- `expert_notes`：专家研判、专题笔记、内部分析沉淀。
- `youth_insight`：青年群体画像、青年心态、代际特征材料。
- `policy`：政策、法规、治理规范、官方制度文件。

当前实现边界：
- RAG 结果只作为 `background_context` 使用。
- 不得直接进入 `evidence_cards`、`verify_claim_v2` 或正式事实锚点。
