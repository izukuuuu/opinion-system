# Remote Database SQL Inventory

This document enumerates every code path that reaches a remote SQL database and lists the SQL statements executed. It traces each SQL statement back to its entry point so you can follow the flow end-to-end.

Scope:
- Primary target is MySQL (based on current queries and schema usage).
- SQL is executed via SQLAlchemy (Core + ORM) and pandas `to_sql`.
- RAG storage can use SQLite/PostgreSQL/MySQL; it is included as an optional path.

Note: Do not commit real credentials into docs. Use placeholders when documenting connection strings.


## 1) Connection sources and config

### Static config
- `backend/configs/databases.yaml`
  - `db_url`: main SQLAlchemy URL used by query/fetch/update modules.
  - `connections`: list of named connection entries (`id`, `name`, `engine`, `url`, `description`).
  - `active`: active connection id for UI selection.

Example (redacted):
```
mysql+pymysql://<user>:<password>@<host>:<port>
```

### Runtime config API
- `backend/server.py`
  - `/api/settings/databases` (GET/POST/PUT/DELETE/activate)
  - These endpoints call helpers in `backend/server_support/configuration.py` to load/save YAML config.

### Settings loader
- `backend/src/utils/setting/settings.py`
  - Loads `*.yaml` in `backend/configs/` into `settings`.
  - Only environment variables with prefix `OPINION_` are collected.

### Database manager
- `backend/src/utils/io/db.py` (`DatabaseManager`)
  - `db_url` selection order: explicit arg -> `settings.get('env.DB_URL')` -> `databases.db_url` -> `defaults.db_url`.
  - Creates engines via `sqlalchemy.create_engine`.
  - Provides helpers for `execute_query`, `execute_update`, `ensure_database`, and `table_exists`.


## 2) Entry points that trigger remote SQL

### API endpoints
- `POST /api/query` -> `src.query.run_query` -> `query_database_info` (metadata + previews)
- `POST /api/fetch` -> `src.fetch.run_fetch` -> `fetch_range` (data pull)
- `GET /api/fetch/availability` -> `src.fetch.get_topic_available_date_range` (date range probe)
- `POST /api/upload` -> `src.update.run_update` -> `upload_filtered_excels` (data push)
- `GET /api/analysis/topic/bertopic/topics` uses `run_query` to list available DBs


## 3) SQL statements by module

### A) Database bootstrap and generic helpers
File: `backend/src/utils/io/db.py`

1. Create database (MySQL-specific)
```
CREATE DATABASE IF NOT EXISTS `<database_name>`
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
```
- Called by `DatabaseManager.ensure_database`.
- Used from `upload_filtered_excels` before writing tables.

2. Check table exists (current database)
```
SELECT COUNT(*)
FROM information_schema.tables
WHERE table_name = :table_name AND table_schema = DATABASE()
```
- `DatabaseManager.table_exists`.

3. Generic execution helpers
- `execute_query(query, params)` uses `conn.execute(text(query), params)`.
- `execute_update(query, params)` uses `conn.execute(text(query), params)` + `commit`.

4. Create table with arbitrary columns
```
CREATE TABLE IF NOT EXISTS <table_name> (<column_defs...>)
```
- `DatabaseManager.create_table`.


### B) Query module (metadata + preview)
File: `backend/src/query/data_query.py`

Entry point: `run_query()` -> `query_database_info()`

1. List databases (filter system schemas)
```
SELECT SCHEMA_NAME as database_name
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME NOT IN (
  'information_schema','performance_schema','mysql','sys','test','phpmyadmin'
)
ORDER BY SCHEMA_NAME
```

2. List tables (approx row counts) for each database
```
SELECT TABLE_NAME as table_name, TABLE_ROWS as table_rows
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = :db_name
ORDER BY TABLE_NAME
```

3. Count rows per table (optional)
```
SELECT COUNT(*) as record_count
FROM `<db_name>`.`<table_name>`
```
- Only executed when `include_counts=True`.

4. Preview rows per table
```
SELECT *
FROM `<db_name>`.`<table_name>`
LIMIT 20
```


### C) Fetch module (pull data to local JSONL)
File: `backend/src/fetch/data_fetch.py`

Entry point: `run_fetch()` -> `fetch_range()`

1. Check table exists (per channel)
```
SELECT COUNT(*)
FROM information_schema.tables
WHERE table_schema = :schema AND table_name = :table
```

2. Fetch data for a date range
```
SELECT *
FROM <table_name>
WHERE DATE(published_at) BETWEEN :start_date AND :end_date
ORDER BY published_at DESC
```
- `table_name` comes from `channels.keep` config.

3. Get date range for one table
```
SELECT
  MIN(DATE(published_at)) AS start_date,
  MAX(DATE(published_at)) AS end_date
FROM <table_name>
```

4. List tables that contain `published_at`
```
SELECT DISTINCT TABLE_NAME AS table_name
FROM information_schema.columns
WHERE table_schema = :schema AND column_name = 'published_at'
ORDER BY TABLE_NAME
```
- Used by `get_topic_available_date_range` to discover tables to scan.


### D) Update module (push data into DB)
File: `backend/src/update/data_update.py`

Entry point: `run_update()` -> `upload_filtered_excels()`

1. Ensure database exists
- Calls `DatabaseManager.ensure_database` (see section 3A-1).

2. Create table with standard schema (MySQL-specific)
```
CREATE TABLE IF NOT EXISTS `<table_name>` (
  `id` VARCHAR(64) PRIMARY KEY,
  `title` LONGTEXT,
  `contents` LONGTEXT,
  `platform` VARCHAR(50),
  `author` LONGTEXT,
  `published_at` DATETIME,
  `url` LONGTEXT,
  `region` VARCHAR(100),
  `hit_words` TEXT,
  `polarity` VARCHAR(20),
  `classification` VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
```
- Column definitions come from `backend/src/utils/io/excel.py:get_standard_table_schema()`.

3. Insert rows (generated by SQLAlchemy via pandas)
- `DataFrame.to_sql(..., if_exists="append", method="multi", chunksize=1000)`
- Generates `INSERT` statements in batches using SQLAlchemy + PyMySQL.

4. Check table exists (before creation)
```
SELECT COUNT(*)
FROM information_schema.tables
WHERE table_schema = :schema AND table_name = :table
```


### E) RAG database storage (optional)
File: `backend/src/rag/storage/database_storage.py`

- Uses SQLAlchemy ORM; no explicit SQL strings.
- On init, `Base.metadata.create_all(engine)` creates the `embeddings` table.
- Supports `sqlite`, `postgresql`, `mysql` depending on config:
  - `storage.connection_string` in `backend/src/rag/config/default.json` (or runtime config).


## 4) Flow traces from API to SQL

### /api/query
1. `backend/server.py:query_endpoint`
2. `src.query.run_query` -> `query_database_info`
3. SQL:
   - List databases (SCHEMATA)
   - List tables (TABLES)
   - Optional COUNT(*) per table
   - Preview SELECT * LIMIT 20

### /api/fetch
1. `backend/server.py:fetch_endpoint`
2. `src.fetch.run_fetch` -> `fetch_range`
3. SQL per channel:
   - Table existence check
   - SELECT * WHERE DATE(published_at) BETWEEN ...

### /api/fetch/availability
1. `backend/server.py:fetch_availability_endpoint`
2. `src.fetch.get_topic_available_date_range`
3. SQL:
   - List tables with published_at
   - For each table: MIN/MAX of DATE(published_at)

### /api/upload
1. `backend/server.py:upload_endpoint`
2. `src.update.run_update` -> `upload_filtered_excels`
3. SQL:
   - CREATE DATABASE IF NOT EXISTS
   - CREATE TABLE IF NOT EXISTS (standard schema)
   - INSERT via pandas `to_sql`


## 5) MySQL-specific assumptions and constraints

- Backticks and `information_schema` usage assume MySQL-compatible servers.
- `CREATE DATABASE ... DEFAULT CHARSET utf8mb4` is MySQL syntax.
- `DATE(published_at)` assumes MySQL DATE() function.

If you plan to run these flows on PostgreSQL, you must adapt SQL templates and schema checks.


## 6) Quick checklist for auditing remote DB usage

- Config: confirm `backend/configs/databases.yaml` has the expected `db_url` and active connection.
- Query: `POST /api/query` should return database list; watch for `information_schema` access.
- Fetch: `POST /api/fetch` should pull rows by `published_at` date range.
- Upload: `POST /api/upload` should create DB + tables and write rows.
- RAG: only uses DB if `storage.connection_string` is configured for SQL storage.
