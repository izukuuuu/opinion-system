# Frontend/Backend DB Call Flow (Pages + Endpoints)

This document maps **which frontend pages call which backend endpoints**, and how those endpoints hit **remote databases** or **local caches**. It is intended as a companion to `docs/remote-database-sql-usage.md` (SQL statement inventory).

Legend:
- **Remote DB** = SQL database via SQLAlchemy (MySQL by default)
- **Local cache** = `backend/data/projects/<bucket>/...`
- **Dual link** = `topic` (remote DB name) + `project` (local bucket)


## 0) Shared HTTP client

File: `frontend/src/composables/useApiBase.js`
- `callApi(path, options)` builds URL from `VITE_API_BASE_URL` or local storage override.
- All frontend requests below go through this helper.


## 1) Basic Analysis (核心：远程 DB + 本地缓存)

### Page: Run Analysis
- View: `frontend/src/views/analysis/basic/ProjectBasicAnalysisRun.vue`
- Composable: `frontend/src/composables/useBasicAnalysis.js`

Remote DB calls:
1. **Load topics** (remote DB list)
   - `POST /api/query` with `{ include_counts: false }`
   - Backend: `backend/server.py -> /api/query -> src/query/data_query.py`

2. **Check available date range**
   - `GET /api/fetch/availability?topic=<db>`
   - Backend: `backend/server.py -> /api/fetch/availability -> src/fetch/data_fetch.py:get_topic_available_date_range`

3. **Fetch remote data to local cache**
   - `POST /api/fetch` with `{ topic, start, end }`
   - Backend: `backend/server.py -> /api/fetch -> src/fetch/data_fetch.py:fetch_range`

4. **Run analysis on local cache**
   - `POST /api/analyze` with `{ topic, start, end, function }`
   - Backend: `backend/server.py -> /api/analyze -> src/analyze/run_Analyze`

Local cache paths used by backend:
- Fetch output: `backend/data/projects/<topic>/fetch/<start>_<end>/`
- Analyze output: `backend/data/projects/<topic>/analyze/<start>_<end>/`

### Page: View Analysis Results
- View: `frontend/src/views/analysis/basic/ProjectBasicAnalysisResults.vue`
- Composable: `frontend/src/composables/useBasicAnalysis.js`

Calls:
- `GET /api/analyze/history?topic=<topic>`
- `GET /api/analyze/results?topic=<topic>&start=<start>&end=<end>`
- Fallback: `GET /api/projects/<topic>/archives?layers=analyze`


## 2) BERTopic (aligned with basic analysis; supports dual link)

### Page: Run BERTopic
- View: `frontend/src/views/analysis/topic/TopicBertopicRun.vue`
- Composable: `frontend/src/composables/useTopicBertopicAnalysis.js`

Remote DB calls:
1. **Load topics** (same as basic analysis)
   - `POST /api/query` with `{ include_counts: false }`

2. **Check date range** (now supports dual link)
   - `GET /api/fetch/availability?topic=<remote_db>&project=<local_bucket?>`
   - Fallback: `GET /api/analysis/topic/bertopic/availability?topic=<remote_db>&project=<local_bucket?>`

3. **Fetch remote data to local cache** (same as basic analysis)
   - `POST /api/fetch` with `{ topic, project?, start, end }`

4. **Run BERTopic**
   - `POST /api/analysis/topic/bertopic/run` with `{ topic, project?, start_date, end_date, ... }`
   - Backend: `backend/server.py::_run_topic_bertopic_api -> src/topic/data_bertopic_qwen_v2.py:run_topic_bertopic`
   - If local cache exists, backend reuses it; otherwise it triggers `fetch_range` internally.

Local cache paths used by backend:
- Fetch output: `backend/data/projects/<bucket>/fetch/<start>_<end>/`
- BERTopic output: `backend/data/projects/<bucket>/topic/<start>_<end>/`

**Dual link rule**
- `topic` = remote DB name (used for SQL fetch)
- `project` = local bucket name (used for cache + results storage)

If `project` is omitted, the backend uses `topic` for both remote DB and local bucket.

### Page: View BERTopic Results
- View: `frontend/src/views/analysis/topic/TopicBertopicResults.vue`
- Composable: `frontend/src/composables/useTopicBertopicView.js`

Calls:
- `GET /api/analyze/history?topic=<topic>&project=<bucket?>` (used to build time range list)
- Fallback: `GET /api/projects/<bucket>/archives?layers=analyze`
- `GET /api/analysis/topic/bertopic/results?topic=<remote_db>&project=<bucket?>&start=<start>&end=<end>`

Note: BERTopic history is currently inferred from analyze archives. There is no dedicated BERTopic history endpoint.


## 3) Remote DB Exploration / Caching Tools

### Page: Database Overview
- View: `frontend/src/views/DatabaseOverviewView.vue`
- Call: `POST /api/query`
- Backend: `src/query/data_query.py` (information_schema + preview rows)

### Page: Database Datasets
- View: `frontend/src/views/DatabaseDatasetsView.vue`
- Call: `POST /api/query`

### Page: Project Data -> Remote Cache
- View: `frontend/src/views/project-data/ProjectDataRemoteCacheView.vue`
- Calls:
  - `POST /api/query` (topics)
  - `GET /api/fetch/availability?topic=<db>`
  - `GET /api/fetch/cache?topic=<db>`
  - `POST /api/fetch` (remote -> local)


## 4) RAG (TagRAG / RouterRAG)

### Retrieval pages
- Views: `frontend/src/views/retrieval/TagRAGView.vue`, `RouterRAGView.vue`
- Composable: `frontend/src/composables/useRAGTopics.js`

Calls:
- `GET /api/rag/topics` (lists TagRAG/RouterRAG topics)
- `POST /api/rag/tagrag/retrieve`
- `POST /api/rag/routerrag/retrieve`
- `POST /api/rag/universal/retrieve`

These do **not** execute SQL queries by default. They read from local RAG stores:
- TagRAG JSON: `backend/src/utils/rag/tagrag/format_db/*.json`
- RouterRAG LanceDB: `backend/src/utils/rag/ragrouter/<topic>数据库/`

### Settings page
- View: `frontend/src/views/settings/SettingsRAGView.vue`
- Calls:
  - `GET /api/rag/config`
  - `POST /api/rag/config`


## 5) Backend SQL touchpoints (summary)

Refer to `docs/remote-database-sql-usage.md` for full SQL statements. Key modules:
- `backend/src/query/data_query.py` (list schemas, tables, previews)
- `backend/src/fetch/data_fetch.py` (SELECT by published_at range)
- `backend/src/update/data_update.py` (CREATE DB/TABLE, INSERT via pandas)
- `backend/src/utils/io/db.py` (generic SQL helpers)


## 6) Known pitfalls and fixes applied

Fixed (Jan 2026):
- `frontend/src/composables/useTopicBertopicView.js`: typo `bertopic.value` -> `bertopicData.value`
- `frontend/src/composables/useTopicBertopicAnalysis.js`: `availableRange.loading` was reset to false while request was in-flight
- BERTopic now sends `project` along with `topic` so **remote DB + local bucket** can be separated
- BERTopic run now prefetches remote data via `/api/fetch` (same as basic analysis)

Open questions / gaps:
- BERTopic “history” uses analyze archives; there is no dedicated BERTopic history API.
- RAG `POST /api/rag/test` is a stub; actual retrieval uses `/api/rag/*/retrieve` only.


## 7) Recommended debugging checklist (BERTopic + remote DB)

1. Confirm remote DB is reachable: `POST /api/query`.
2. Confirm range: `GET /api/fetch/availability?topic=<db>&project=<bucket?>`.
3. Trigger fetch: `POST /api/fetch` (ensure `总体.jsonl` exists in bucket).
4. Run BERTopic: `POST /api/analysis/topic/bertopic/run` (uses same bucket).
5. Read results: `GET /api/analysis/topic/bertopic/results`.

