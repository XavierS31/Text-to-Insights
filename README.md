# Text-to-Insights

**An Agentic Workflow for Mining the Scientific Literature**

Text-to-Insights is a University of Central Florida Senior Design project sponsored by **Prof. Kristopher O. Davis** and the **Data-Enabled Photovoltaics (DPV) Research Group** in the Department of Materials Science and Engineering.

The project is focused on building a reusable, end-to-end AI workflow that transforms scientific literature into structured, traceable, queryable data and research insights.

## Project Overview

Thousands of peer-reviewed papers in photovoltaics and materials science contain valuable experimental information such as:

- Device architectures
- Processing conditions
- Performance measurements
- Degradation data
- Material properties
- Tables, figures, and bibliographic information

Much of this information remains locked inside PDF documents and is difficult to compare manually at scale.

Text-to-Insights extends existing sponsor-developed LLM extraction prototypes into a complete research workflow capable of:

1. Ingesting scientific PDF documents
2. Extracting structured scientific information with AI agents
3. Preserving provenance for every extracted result
4. Validating and storing structured records
5. Building knowledge graphs from validated scientific data
6. Translating natural-language questions into SPARQL queries
7. Returning answers linked to their original sources
8. Supporting researcher review, correction, visualization, and statistical analysis
9. Evaluating extraction and query quality against expert-verified data
10. Supporting both hosted frontier models and locally hosted open-weight models

## Proposed End-to-End Workflow

```text
Scientific PDFs
      |
      v
PDF Processing
      |
      v
AI Extraction
      |
      v
Validation / Evaluation
      |
      v
Structured SQLite Storage
      |
      v
Ontology + Entity Mapping
      |
      v
RDF/OWL Knowledge Graph
      |
      v
SPARQL Querying
      |
      v
Natural-Language Answers + Citations
      |
      v
Research Interface + Analytics
```

The goal is to develop the project as one connected workflow rather than as isolated components.

## Core Capabilities

### Scientific PDF Ingestion and Extraction

The system will process expert-selected scientific papers and use versioned prompts and schemas to extract structured information from text, tables, and other document content.

The extraction workflow is intended to preserve:

- Source article
- Bibliographic metadata
- DOI information when available
- Prompt version
- Schema version
- Model used
- Supporting page, passage, or table information when available

### Structured Storage and Provenance

Validated scientific records will be stored in **SQLite**.

The data model is intended to support changing scientific subdomains and schemas without requiring the entire system to be rebuilt. Extraction runs should remain distinguishable so that results generated using different prompts, schemas, or models can be compared.

Provenance is a core requirement rather than optional metadata.

### Knowledge Graph

Validated records will be transformed into linked representations suitable for a scientific knowledge graph.

Primary technologies include:

- RDF
- OWL
- JSON-LD where useful
- SPARQL

The knowledge graph will represent relationships among scientific entities rather than storing only isolated values.

### Natural-Language Querying

Researchers should be able to ask normal-language questions about the scientific corpus.

The proposed query workflow is:

```text
Natural-Language Question
        |
        v
Relevant Ontology Context
        |
        v
AI Query Agent
        |
        v
Generated SPARQL
        |
        v
Knowledge Graph
        |
        v
Answer + Supporting Sources
```

Manually written and verified SPARQL queries can first be used as a baseline before evaluating natural-language-to-SPARQL generation.

### Researcher Review

Researchers should be able to inspect extracted values together with their supporting source material.

The proposed interface should support:

- Reviewing extracted records
- Viewing source evidence
- Accepting results
- Correcting results
- Rejecting results
- Recording feedback
- Identifying missing or inconsistent information
- Tracking whether reviewed information has reached downstream components

### Analytics and Scientific Insights

Researchers should be able to filter reviewed records and create analyses such as:

- Scatter plots
- Distributions
- Grouped comparisons
- Means
- Medians
- Other deterministic statistical analyses

LLMs may help suggest analyses, but calculations that can be performed deterministically should be handled by software rather than by the language model.

Charts and exported results should remain connected to the records and sources used to produce them.

## Minimum Viable Product

The end-of-Senior-Design-II MVP is intended to demonstrate one complete photovoltaics/materials-science use case from ingestion through querying and analysis.

The MVP should be able to:

- Process a sponsor-selected PDF corpus
- Extract structured records using versioned prompts and schemas
- Preserve tables, figures, and bibliographic information where required
- Store validated records in SQLite
- Preserve source, prompt-version, and model provenance
- Provide a basic researcher review workflow
- Support locally hosted open-weight models through an OpenAI-compatible interface
- Allow hosted models to be selected through configuration
- Represent agreed entities and relationships in RDF/OWL
- Translate an agreed set of natural-language questions into SPARQL
- Return query answers with source citations
- Produce agreed visualizations and statistical analyses
- Evaluate extraction quality against an expert-annotated gold dataset when available
- Verify answers against an agreed query set
- Provide documentation for reproducing the workflow

## Proposed Technology Stack

### Primary Language

- Python

### Structured Data

- SQLite

### Knowledge Graph

- RDF
- OWL
- JSON-LD
- SPARQL

### AI / Model Integration

- Hosted frontier LLMs
- Locally hosted open-weight models
- OpenAI-compatible inference interface

### Supporting System Areas

- PDF parsing
- Agent orchestration
- Schema-guided structured extraction
- Model evaluation
- Researcher feedback
- Visualization and analytics
- Reproducible pipelines

## Design Constraints

The project is intentionally open-ended, but several sponsor requirements guide the architecture:

- Python should be the primary development language.
- SQLite should be used for structured storage.
- RDF/OWL and SPARQL should be used for the knowledge-graph layer.
- Model providers should be accessed through an OpenAI-compatible interface where possible.
- Every extracted value must preserve provenance.
- Deterministic calculations should be performed by software rather than by an LLM.
- The workflow should remain reusable as new scientific subdomains are introduced.
- Code, prompts, and schemas are intended for open-source release.
- The sponsor's private PDF corpus must remain private.

## Evaluation

The project will be evaluated using a combination of extraction quality, query correctness, reproducibility, and scientific usefulness.

Planned evaluation areas include:

- Precision
- Recall
- F1-score
- Field-level accuracy
- Missing-information errors
- Incorrect-information errors
- Hallucinations
- Formatting problems
- Incorrect extraction
- Correctness of natural-language-to-SPARQL answers
- Reproducibility on a new scientific subdomain
- Quality of resulting scientific insights

An expert-annotated gold dataset is expected to provide a baseline for evaluating model and prompt performance.

## Research Direction

The system is intended to support iterative experimentation with:

- Prompt design
- Schema design
- Ontology design
- Model selection
- Open-weight models
- Fine-tuning
- Entity and relation normalization
- Knowledge-graph generation
- Query generation
- Expert feedback
- Provenance-aware evaluation

Research into approaches such as multi-stage entity/relation extraction and entity-resolution workflows may inform the project, but any external method must be adapted to the project's RDF/OWL, SPARQL, provenance, and scientific-domain requirements.

## Sponsor

**Prof. Kristopher O. Davis**  
Data-Enabled Photovoltaics Research Group  
Department of Materials Science and Engineering  
University of Central Florida

## Course

**COP 4934 — Senior Design I**  
University of Central Florida  
2026–2027
