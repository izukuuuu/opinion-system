---
name: Database Compatibility
description: Analyzes the dual compatibility logic for PostgreSQL and MySQL in the project, covering connection management, dialect detection, and DDL/DML handling.
---

# Database Dual Compatibility Logic (PostgreSQL & MySQL)

This project achieves complete compatibility from the storage layer to the application layer for both PostgreSQL and MySQL through `SQLAlchemy` as the ORM/Core abstraction layer, combined with explicit **Dialect Detection**.

## 1. Core Abstraction Layer: `DatabaseManager`

All database interactions converge in the `DatabaseManager` class located in `backend/src/utils/io/db.py`.

*   **Unified Connection**: regardless of the underlying database, upper-layer business code only interacts with `DatabaseManager` to obtain a `sqlalchemy.engine.Engine`.
*   **Driver Adaptation**: Automatically adapts the driver based on the `db_url` in the configuration.
    *   PostgreSQL: `postgresql://user:pass@host/db`
    *   MySQL: `mysql+pymysql://user:pass@host/db`

## 2. Dialect Specifics

While SQLAlchemy shields most differences, explicit branching is handled for DDL (Database Management) and specific SQL syntax.

### 2.1 Database Creation & Deletion (DDL)

In the `ensure_database` and `drop_database` methods of `db.py`, code branches based on `engine.dialect.name`:

*   **PostgreSQL**:
    *   **Connection Constraints**: Must connect to the `postgres` system database or another existing database when creating a new one; cannot connect without a database like MySQL.
    *   **Transaction Isolation**: Database creation cannot run within a transaction block, so the code explicitly sets `isolation_level="AUTOCOMMIT"`.
    *   **Deletion Protection**: Existing connections to the database must be terminated (`pg_terminate_backend`) before dropping it.
    *   **Quoting**: Uses double quotes `"` to wrap database names (e.g., `"my-db"`).

*   **MySQL**:
    *   **Flexibility**: Can switch databases via `USE` or connect directly.
    *   **Syntax**: Uses the more general `IF NOT EXISTS` syntax.
    *   **Quoting**: Uses backticks ``` ` ``` to wrap database names (e.g., ``` `my-db` ```).

### 2.2 Data Fetching & Querying

Filename identifiers and connection scopes are handled in `backend/src/fetch/data_fetch.py` and `backend/src/query/data_query.py`:

| Feature | PostgreSQL Strategy | MySQL Strategy | Code Location |
| :--- | :--- | :--- | :--- |
| **Identifier Quoting** | Uses `identifier_preparer.quote` or manual `"` | Uses ``` ` ``` | `_fetch_table_info`, `_quote_identifier` |
| **Cross-DB Query** | **Not supported** directly. Must create a new Engine/Connection pointing to the specific DB. | **Supported**. Reuse the same connection, query using `db.table` format. | `_process_database_metadata` |
| **System Tables** | Queries `pg_tables`, `pg_database` | Queries `information_schema.TABLES`, `SCHEMATA` | `db.py` |

## 3. Implementation Process Patterns

### Pattern: Dynamic Connection Switching

Due to PostgreSQL's strict **Connection Isolation**, when handling multi-project (multi-database) metadata, the code adopts a "Just-In-Time Connection" strategy:

```python
# backend/src/query/data_query.py

if dialect_name == 'postgresql':
    # Must create a new Engine/Manager for the target database
    # And close it after the operation
    base_url = make_url(base_engine_url)
    target_url = base_url.set(database=db_name)
    scope_manager = DatabaseManager(target_url)
else:
    # MySQL can reuse the connection for direct querying
    scope_manager = DatabaseManager(base_engine_url)
```

## 4. Summary

The compatibility of this project usually does not rely solely on ORM, but adopts an **"ORM-First, Manual-Exception"** strategy:

1.  **General Operations** (like `pd.read_sql`, `to_sql`) rely entirely on the unified interface of SQLAlchemy and Pandas.
2.  **Management Operations** (Create/Drop DB) and **Metadata Queries** (Check Table Structure) have specialized SQL logic written for different dialects.

This design allows the project to enjoy the convenience of ORM while handling complex scenarios specific to the underlying database.
