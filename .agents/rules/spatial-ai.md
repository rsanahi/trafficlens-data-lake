# Project Context: Synthetic Intelligence & Spatial Orchestration

## 1. Vision & Purpose
Este proyecto evoluciona el análisis de datos de telemetría y video hacia la creación de **Digital Twins** mediante **3D Gaussian Splatting (3DGS)**. El objetivo principal es construir una "Fábrica de Datos Sintéticos" para reentrenar modelos de IA en escenarios de riesgo (accidentes, anomalías, fallos de seguridad), garantizando la **Confiabilidad (Reliability)** y la **Orquestación** del ciclo de vida del dato.

## 2. Core Technical Stack
- **Languages:** Python (Core logic), SQL (dbt/DuckDB).
- **Spatial AI:** 3D Gaussian Splatting (Nerfstudio/splatfacto), COLMAP (SfM).
- **Data Engineering:** Parquet (Storage), DuckDB (OLAP), dbt (Transformations).
- **Inference:** YOLOv10 / RT-DETR (Vision), PyTorch.
- **Hardware:** Optimized for Apple Silicon (MPS/Metal) - MacBook Pro M3 Pro.

## 3. Architecture & Methodology (Non-Negotiable)
- **Domain-Driven Design (DDD):** El código debe organizarse en capas (Domain, Application, Infrastructure). Respetar el Ubiquitous Language (ej. `SplatScene`, `CameraPose`, `InferenceContract`).
- **Clean Architecture:** Las reglas de negocio (orquestación de IA) no deben depender de herramientas externas (ej. Nerfstudio o librerías de visión).
- **Strict TDD:** Seguir el ciclo Red-Green-Refactor. Cada nuevo componente de orquestación debe tener pruebas unitarias que validen la lógica de "confiabilidad".
- **AI Reliability:** El sistema debe priorizar la reducción de falsos positivos y la validación de contratos de datos antes de permitir el reentrenamiento automático.

## 4. Current Domain Focus (Sandbox)
- **Input:** Videos de Dashcam + Telemetría GPS/IMU.
- **Process:** Video -> Extracción de Frames -> COLMAP -> 3DGS Training -> Synthetic Scenario Injection (Lluvia, Accidentes, Robos).
- **Output:** Dataset Sintético etiquetado para reentrenamiento de modelos de visión.

## 5. Future Extensibility
Los patrones de **Simulación de Refuerzo** y **Active Learning** desarrollados aquí deben ser exportables a otros dominios críticos como **Fintech (detección de fraude/anomalías)** y **Logística**.

## 6. Project Rules for AI Agent
1. **Always suggest Clean Architecture:** Si propongo un script rápido, corrígeme para mover la lógica a un Servicio de Aplicación.
2. **Modular 3D Workflows:** Mantener la lógica de procesamiento 3D separada de la lógica de entrenamiento para permitir el intercambio de motores (ej. de NeRF a 3DGS).
3. **Optimización de Memoria:** Dado que uso Apple Silicon, prefiere implementaciones que aprovechen la Memoria Unificada y el backend `mps`.
4. **Data-Centric AI:** Cada paso del pipeline debe generar metadatos (en Parquet) sobre la calidad de la reconstrucción y la confianza del modelo.
