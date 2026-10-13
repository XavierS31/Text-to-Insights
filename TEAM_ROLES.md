# Text-to-Insights — Team Member Roles

This document defines the primary project ownership areas assigned to each member of the Text-to-Insights Senior Design team.

Although each member has a primary responsibility, the project is being developed as one integrated workflow. Team members are expected to coordinate interfaces, review work that affects other components, document important technical decisions, and assist with integration when needed.

---

## Simon Ocampo Millan

### Project Manager and Integration Lead

**Primary ownership:** Project coordination, sponsor communication, planning, and integration across the full pipeline.

### Responsibilities

- Coordinate project deadlines, milestones, and deliverables.
- Serve as a primary point of communication with the sponsor.
- Organize internal team meetings and sponsor meetings.
- Maintain project-management artifacts such as the backlog, sprint planning, and task tracking.
- Coordinate work between the technical components.
- Ensure components use compatible inputs, outputs, and shared interfaces.
- Help identify integration blockers before they affect downstream work.
- Coordinate cross-component testing.
- Help review larger technical changes that could affect the complete workflow.
- Support redistribution of work when a dependency or major deadline requires it.
- Maintain visibility into overall project progress and unresolved issues.
- Help ensure the team reaches an end-to-end working pipeline early rather than integrating only at the end.

### Primary Interfaces

Simon coordinates with every project area, especially when:

- Shared schemas change
- Component interfaces change
- A task blocks another team member
- Sponsor feedback affects multiple components
- A feature must be demonstrated end to end

---

## Brentley Dorsainvil

### AI Workflow and PDF Extraction

**Primary ownership:** Scientific-document ingestion, agentic extraction, structured output, and extraction provenance.

### Responsibilities

- Develop the workflow that processes scientific PDFs.
- Extract structured scientific information from paper content.
- Work with schema-guided and prompt-guided extraction.
- Preserve source provenance for extracted information.
- Ensure downstream components receive structured and traceable outputs.
- Investigate extraction of text, tables, figures, bibliographic information, and other required objects.
- Design extraction behavior that can support multiple scientific subdomains.
- Flag uncertain or incomplete extractions for researcher review.
- Avoid silently passing uncertain information downstream as confirmed data.
- Support constrained output formats where appropriate.
- Coordinate extraction-output formats with storage, evaluation, knowledge-graph, and interface components.
- Help evaluate existing sponsor extraction prototypes and identify improvements needed for the MVP.
- Support both hosted and locally hosted model workflows through the project's model interface.

### Primary Interfaces

Brentley's extraction output feeds directly into:

- Evaluation and optimization
- SQLite storage and provenance
- Knowledge-graph generation
- Researcher review

---

## Wade Zimmerle

### Evaluation and Model Optimization

**Primary ownership:** Measuring extraction/model performance and improving prompts or models based on evaluation results.

### Responsibilities

- Define evaluation procedures for extraction quality.
- Compare model outputs against expert-annotated gold data.
- Evaluate different prompts, models, and extraction configurations.
- Measure performance using metrics such as:
  - Precision
  - Recall
  - F1-score
  - Field-level accuracy
- Track and categorize model/extraction errors.
- Investigate errors such as:
  - Missing information
  - Incorrect information
  - Hallucinations
  - Formatting problems
  - Incorrect extraction
- Help define scoring rules and dataset-separation procedures.
- Compare hosted frontier models with open-weight models.
- Use evaluation results to recommend changes to prompts, models, or extraction configurations.
- Track performance across model and prompt versions.
- Support iterative testing and optimization.
- Contribute to decisions about fine-tuning or post-training when supported by available data.

### Primary Interfaces

Wade works most closely with:

- AI workflow and PDF extraction
- Sponsor/domain experts providing gold data
- Database/provenance for experiment metadata
- Knowledge-graph/querying when query-quality evaluation is needed

---

## Mary-Katherine Hays

### Structured Database and Provenance

**Primary ownership:** Reconfigurable SQLite storage, traceability, and structured data interfaces.

### Responsibilities

- Design the SQLite data model used to store extracted scientific information.
- Support multiple scientific subdomains with differing fields and schemas.
- Maintain publishing and bibliographic metadata.
- Link extracted records to the corresponding source article.
- Preserve extraction-run context.
- Preserve model, prompt, and schema version information.
- Avoid overwriting previous extraction configurations when results should remain comparable.
- Support validated and reviewed records.
- Maintain traceability between:
  - Source papers
  - Extraction runs
  - Structured records
  - Corrections
  - Downstream knowledge-graph data
- Provide reliable structured records to downstream components.
- Coordinate database structure with the knowledge-graph layer.
- Support storage of researcher corrections and review status.
- Help define stable record identifiers and data contracts used by the interface and other services.

### Primary Interfaces

Mary-Katherine's database layer connects:

- Extraction
- Evaluation
- Researcher review
- Knowledge graph
- Analytics

---

## Xavier Andres Soto Baron

### Knowledge Graph and Querying

**Primary ownership:** Ontology development, RDF/OWL knowledge-graph construction, SPARQL querying, and natural-language-to-SPARQL workflows.

### Responsibilities

- Transform validated structured records into a connected knowledge representation.
- Develop ontology structures for the scientific domain with sponsor and domain-expert feedback.
- Define relevant:
  - Entities
  - Classes
  - Properties
  - Relationships
  - Scientific terminology
- Map database records into RDF-compatible representations.
- Support RDF and OWL knowledge-graph structures.
- Use JSON-LD when useful for linked-data exchange between components.
- Preserve provenance links from graph data back to database records and source publications.
- Create manually verified SPARQL queries as a baseline for graph correctness.
- Develop and evaluate natural-language-to-SPARQL querying.
- Provide the query agent with appropriate ontology context.
- Investigate reducing unnecessary model context by selecting only relevant ontology concepts and relationships.
- Compare generated SPARQL queries and answers against expected results.
- Identify common query-generation errors and improve the querying workflow.
- Evaluate whether smaller or open-weight models can perform query generation reliably.
- Use sponsor datasets and expert feedback to improve ontology design and querying.
- Research knowledge-graph extraction and entity-resolution approaches that may improve graph construction.
- Ensure that answers returned from the graph remain connected to supporting sources.

### Primary Interfaces

Xavier works most closely with:

- Structured database and provenance
- Sponsor/domain experts
- Researcher-facing interface
- Evaluation/model optimization

The core knowledge-graph workflow is:

```text
SQLite Records
      |
      v
Ontology + Entity Mapping
      |
      v
RDF/OWL Knowledge Graph
      |
      v
SPARQL
      |
      v
Answer + Sources
```

---

## Damian Lubis

### Researcher-Facing Interface and Analytics

**Primary ownership:** Researcher review experience, source-linked corrections, querying interface, and scientific visualizations.

### Responsibilities

- Develop the researcher-facing web interface.
- Display processing status for scientific papers.
- Allow researchers to inspect extracted values together with source evidence.
- Show relevant provenance such as:
  - Source article
  - Page or table reference when available
  - Prompt version
  - Model
- Support accepting, correcting, and rejecting extracted results.
- Record researcher feedback and corrections.
- Display validation problems and explain why a value may require review.
- Connect the interface to natural-language querying.
- Present knowledge-graph answers with citations and supporting records.
- Support filtering reviewed scientific records.
- Create useful scientific visualizations.
- Support descriptive statistical analyses.
- Ensure charts remain connected to their underlying records and source papers.
- Include units, record counts, and filters in analytical results.
- Keep missing data distinct from zero.
- Support export of analysis results with reproducibility metadata.
- Adapt interface fields as schemas and scientific subdomains change.
- Gather sponsor and researcher feedback early through working prototypes.

### Primary Interfaces

Damian integrates outputs from:

- Extraction
- Validation
- SQLite/provenance
- Knowledge-graph querying

and returns researcher corrections and feedback to the rest of the pipeline.

---

# Shared Team Responsibilities

Regardless of primary role, every member is expected to:

- Research the problem within their assigned area.
- Complete assigned development work.
- Test their work.
- Document important technical decisions.
- Communicate progress and blockers.
- Keep code and project files accessible to the team.
- Push code regularly to the shared repository.
- Coordinate changes that affect shared interfaces.
- Participate in peer review where practical.
- Demonstrate progress through working code, tests, schemas, prototypes, documentation, or research findings.
- Help maintain compatibility between project components.
- Support the complete end-to-end workflow when integration work is required.

# Team Structure Summary

| Team Member | Primary Role |
|---|---|
| Simon Ocampo Millan | Project Manager and Integration Lead |
| Brentley Dorsainvil | AI Workflow and PDF Extraction |
| Wade Zimmerle | Evaluation and Model Optimization |
| Mary-Katherine Hays | Structured Database and Provenance |
| Xavier Andres Soto Baron | Knowledge Graph and Querying |
| Damian Lubis | Researcher-Facing Interface and Analytics |
