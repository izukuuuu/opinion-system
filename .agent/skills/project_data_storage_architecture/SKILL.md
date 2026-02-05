---
name: Project Data Storage Architecture Analysis
description: In-depth analysis of the backend data storage architecture, covering data fetching, querying, local/cloud interaction, and storage structure.
---

# Project Data Storage Architecture Depth Analysis

This skill document aims to help understand the data flow, cloud interaction (Negotiation), and storage logic of the `OpinionSystem` backend.

## Core Design Philosophy: Cloud as Intermediate Layer

The data processing flow of this project follows the core logic of **"Cloud Storage, Local Cache, Local Analysis"**. The cloud database (SQL) acts as the authoritative source and exchange center (Intermediate Layer) for data, while the local environment is responsible for calculation and analysis.

### Data Flow Loop

1.  **Data Upload (Upload)**: Locally cleaned (Clean/Filter) data is not directly used for final analysis but is first uploaded to the cloud database.
    *   **Code Location**: `backend/src/update/data_update.py` (`upload_filtered_excels`)
    *   **Logic**: Read `.jsonl` from the local `filter` bucket -> Follow standard Schema (`get_standard_table_schema`) -> Write to the corresponding channel table in the cloud database.
    *   **Significance**: Ensures the cloud has the latest, standardized, full-scale data.

2.  **Data Downlink (Fetch)**: Before analysis begins, data must be "fetched" from the cloud to local.
    *   **Code Location**: `backend/src/fetch/data_fetch.py` (`fetch_range`)
    *   **Logic**: Query the cloud database via SQL (by time range `published_at`) -> Download and save as local JSONL files (`backend/data/projects/{id}/fetch/{range}/*.jsonl`).
    *   **Significance**: The `fetch` directory acts as a **"Local Cache"**.

3.  **Local Analysis (Analyze)**: The analysis module **ONLY reads** data from the local `fetch` cache and does not connect directly to the database for analysis.
    *   **Code Location** (taking the basic analysis module as an example): `backend/src/analyze/runner.py`
    *   **Logic**: Read JSONL from the `fetch` directory -> Pandas in-memory calculation -> Generate JSON results -> Write to the `analyze` directory.

## Cloud "Negotiation" Mechanism

The interaction between the system and the cloud is not simple reading and writing, but includes "negotiation" logic, mainly reflected in two dimensions:

### 1. Data Availability Negotiation (Data Fetch/Query)

Before executing a Fetch, the system "asks" the cloud what data is available.
*   **Code**: `get_topic_available_date_range` in `backend/src/fetch/data_fetch.py`.
*   **Logic**: Query `information_schema` to confirm if the table exists, query `MIN/MAX(published_at)` to confirm the time span.
*   **Query Module**: `backend/src/query/data_query.py` further provides Preview and Count functions to display the cloud data status on the frontend and decide the Fetch strategy.

### 2. Intelligent Analysis Negotiation (Basic Analysis Insights)

Basic Analysis not only calculates statistical values locally but also "negotiates" with the cloud AI service (LLM) to obtain insights.
*   **Code**: `backend/src/analyze/runner.py` (`_generate_ai_summary`).
*   **Logic**:
    1.  **Local Calculation**: `backend/src/analyze/functions/*.py` (e.g., `volume.py`, `attitude.py`) calculates statistical data (DataFrame).
    2.  **Generate Snapshot**: Convert statistical data into a text summary (Text Snapshot).
    3.  **Cloud Interaction**: Call `get_qwen_client` to send the snapshot to the cloud LLM.
    4.  **Get Insights**: The LLM returns a natural language analysis conclusion (AI Summary).

## Project Storage Structure

The project uses a hybrid storage method of **File System + JSON Metadata**, with all data located in `backend/data/projects/`.

### Storage Path
*   **Root Directory**: `backend/data/projects/{project_id}/`
*   **Key Subdirectories**:
    *   `fetch/`: **Local Data Cache**. Stores `.jsonl` files pulled from the cloud. Direct input source for the analysis module.
    *   `analyze/`: **Analysis Results**. Stores analysis results like `volume.json`, `trends.json`, and AI summaries.
    *   `filter/`: **Cleaning Artifacts**. Input source for the Upload step.
    *   `uploads/`: Upload records and metadata.

### Management Core
*   **Code**: `backend/src/project/manager.py` (`ProjectManager` class).
*   **Metadata**: `projects.json` (and `projects.pkl`) stores a list of all projects, statuses, and operation logs (`OperationRecord`).
*   **Operation Flow**: Every action (Fetch, Analyze, etc.) is appended as an `OperationRecord` to the project's `operations` list, forming a complete audit trail.

## Summary: How Basic Analysis Uses This Logic

The execution flow of `Basic Analysis` perfectly embodies the above architecture:
1.  **Prerequisite**: Even if the user has data locally, they usually `Filter` -> `Upload` (sync to cloud) first.
2.  **Preparation**: User triggers `Fetch`. System pulls cloud data via SQL -> Saves to local `fetch/` directory (cache established).
3.  **Calculation**: `analyze/runner.py` loads JSONL from the `fetch/` directory.
4.  **Distribution**: Calls `functions/volume.py` etc. for Pandas calculation.
5.  **Sublimation**: Sends calculation results back to the cloud (LLM) for qualitative analysis.
6.  **Persisting**: Final results (Quantitative JSON + Qualitative AI Summary) are saved in the local `analyze/` directory for frontend reading.

This architecture ensures data consistency (cloud as the standard) while utilizing the low latency of local computing and the intelligent capabilities of cloud large models.
