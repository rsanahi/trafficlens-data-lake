# TrafficLens: Serverless Data Lake & Object Detection 🚦

![TrafficLens Dashboard](https://img.shields.io/badge/Architecture-Medallion%20Data%20Lake-blue)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![AWS](https://img.shields.io/badge/AWS-Cloud%20Native-orange)
![dbt](https://img.shields.io/badge/dbt-DuckDB-F66?logo=dbt)

**TrafficLens** is an end-to-end Data Engineering and Machine Learning Data Lake designed to ingest, process, and analyze raw dashcam footage at scale. It demonstrates a sophisticated understanding of the **Modern Data Stack** and **AWS Cloud Architecture**.

By seamlessly bridging the gap between Computer Vision (YOLOv8) and Analytical Engineering (dbt), TrafficLens transforms unstructured video bytes into queryable, curated Parquet datasets visualizing traffic congestion and trip history on an interactive dashboard.

---

## 🧠 Project Philosophy & Engineering Highlights

This project was built from the ground up to showcase production-grade Data Engineering best practices:

*   **Cloud-Native & Serverless Architecture:** Designed with AWS Serverless principles in mind. Storage and compute are strictly decoupled, treating Amazon S3 (simulated locally via the `datalake/` directory) as the single source of truth, and query engines (DuckDB/Amazon Athena) for transformation.
*   **Medallion Data Lake:** Data is aggressively modeled into **Bronze** (Raw CSVs & Images), **Staging** (Cleaned, Typed, Deduplicated), and **Curated** (Star Schema Business Aggregates).
*   **Domain-Driven Design (DDD) & Clean Architecture:** The python ingestion pipeline is built using strict DDD. Business logic (Domain) is isolated from external dependencies (Infrastructure) via Interface Ports. This means swapping local YOLO detection for **AWS Rekognition** or **Amazon SageMaker** requires zero changes to the core application logic.
*   **Infrastructure as Code (IaC):** AWS infrastructure provisioning is handled structurally through **AWS CDK** (Python) located in the `infra/` stack.
*   **Test-Driven Development (TDD):** The core pipeline behavior is validated through a suite of robust unit tests prioritizing dependency injection and in-memory fakes.

---

## 🏛️ Project Structure

The repository is structured to prioritize separation of concerns, ensuring scalability and maintainability:

```text
trafficlens-data-lake/
├── core/
│   ├── domain/               # Core entities, Value Objects, & Port Interfaces (DDD)
│   ├── application/          # TDD-driven Use Cases (ExtractTelemetry, VehicleCounts)
│   ├── infrastructure/       # Concrete Adapters (LocalYoloDetector, OcrVideoReader)
│   ├── dbt_project/          # SQL transformations (dbt + duckdb)
│   │   ├── models/           # src/, stg/, and marts/
│   │   └── dbt_project.yml
│   └── batch_ingest.py       # Main presentation/ingestion CLI orchestration
├── frontend/                 # Premium Streamlit UI & PyDeck Interactive Map
├── infra/                    # AWS CDK (Infrastructure as Code) definitions
├── docs/                     # Interactive Architecture documentation & diagrams
├── scripts/                  # Helper & debugging data generation scripts
├── tests/                    # Robust test suite covering Domain & Application layers
└── datalake/                 # Local simulated S3 Storage (Bronze, Staging, Curated)
```

---

## 📚 Deep-Dive Architecture Documentation

The complete architectural breakdown, including the pipeline Data Flow (Bronze ➜ Staging ➜ Curated), Visual DAG Diagrams, and OCR extraction examples, has been extensively documented in an Interactive Jupyter Notebook. 

👉 **[View the Architectural Data Flow Notebook](docs/architecture.ipynb)**

---

## 🚀 Quick Start Guide

### 1. Environment Setup

```bash
# 1. Create and activate conda environment
conda create -n datalake python=3.12
conda activate datalake

# 2. Install dependencies
pip install -r infra/requirements.txt
pip install pydantic opencv-python-headless pytesseract dbt-duckdb streamlit pydeck duckdb pandas plotly ultralytics
```

### 2. Running the Data Pipeline (Ingestion -> dbt)

```bash
# Run the Computer Vision extraction from raw videos to Bronze
python core/batch_ingest.py /absolute/path/to/dashcam/videos/

# Run the dbt ELT pipeline to process Bronze -> Staging -> Curated
cd core/dbt_project
dbt run --profiles-dir .
```

### 3. Launching the TrafficLens Dashboard

Visualize the final Object Detections and Trip metrics dynamically:

```bash
streamlit run frontend/app.py
```

### 4. Running the Test Suite

Execute the TDD suite covering the Domain and Application architectures:

```bash
python -m pytest tests/ -v
```
