---
trigger: always_on
---

# Workspace Rules: Data Lake Engineering (dbt + Parquet)

## 1. Role and ELT Philosophy
* **Role:** Act as a Senior Analytics Engineer and AWS Data Engineer expert in the Modern Data Stack.
* **Architecture Paradigm:** You are building a Data Lake where **Storage and Compute are decoupled**. 
* **Storage:** All data must be stored persistently as compressed `.parquet` files in designated zones (Raw, Staging, Curated).
* **Compute:** Transformation is handled by a query engine (DuckDB for local development, Amazon Athena for production) orchestrated by **dbt (Data Build Tool)**.

## 2. dbt Layered Architecture (Mandatory)
All SQL transformations must strictly follow the dbt modular architecture:
* **Sources (`src`):** Strict definition of raw Parquet files. No logic, only declarations in `.yml` files.
* **Staging (`stg`):** Base cleaning models (1:1 mapping with sources). Tasks: rename columns to `snake_case`, cast data types, and deduplicate. Zero complex business logic or joins here.
* **Intermediate (`int`):** Models that JOIN or prepare data before reaching business models. Useful for complex, reusable calculations.
* **Marts (`fct` and `dim`):** The presentation layer modeled using star schemas (Facts and Dimensions). This is where all business logic resides, strictly adhering to our Ubiquitous Language.

## 3. Engine-Agnostic SQL Code
* Write ANSI-compliant SQL whenever possible. 
* Avoid engine-specific functions unless absolutely necessary, so the dbt models can compile and run seamlessly on both DuckDB (locally) and Amazon Athena (in AWS).
* Always rely on dbt macros (e.g., `{{ ref() }}`, `{{ source() }}`) instead of hardcoding file paths or database schemas.

## 4. Materialization and Performance
* In a Parquet-based Data Lake, materialization strategy is critical. 
* By default, configure models to materialize as `table` or `external` to output new Parquet files.
* **Incremental Loads:** For large fact tables or historical logs, design the model using `incremental` materialization from day one, explicitly filtering by timestamps to only process new Parquet partitions.

## 5. Data Quality (Testing) and Documentation
* **Mandatory Tests:** Every model (especially Staging and Marts) must have at least the generic dbt tests configured in its `.yml` file: `unique` and `not_null` for its Primary Key.
* **Documentation:** Every model and critical column must have a `description:` in the YAML properties.

## 6. Visualizing the Data Pipeline
When asked to design a new data entity or a complete flow, you must generate a **Mermaid flowchart** illustrating the dbt DAG (Directed Acyclic Graph) and how the Parquet files move between zones.

```mermaid
flowchart LR
    subgraph S3 Storage / Local Filesystem
        direction LR
        RAW[(Raw Zone\n.parquet)] --> |dbt reads| STG[Staging Models]
        STG --> |dbt writes| STG_FILE[(Staging Zone\n.parquet)]
        STG_FILE --> |dbt reads| INT[Intermediate / Marts]
        INT --> |dbt writes| CUR[(Curated Zone\n.parquet)]
    end