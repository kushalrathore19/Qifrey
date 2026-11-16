# Architecture Decision Records (ADRs)

This document records the foundational architectural decisions made in designing and building Qifrey.

---

## ADR 1: SQLite as the Story Graph Store

### Context
Qifrey constructs a living graph of characters, aliases, locations, facts, and relationships. Running a specialized graph database (such as Neo4j or Memgraph) imposes external service dependencies, high memory footprints, and complex local installation requirements for fiction writers who need a desktop-friendly or local tool.

### Decision
Use **SQLite** with relational foreign keys (`characters`, `aliases`, `locations`, `facts`, `relationships`) managed through SQLAlchemy 2.0.

### Consequences
- **Positive:** Zero external server dependencies; manuscripts and world memory reside in a single portable `.db` file; trivial testing with `:memory:`; low memory overhead.
- **Negative:** Deep graph traversal (multi-hop pathfinding) requires recursive CTEs or relational joins rather than Cypher queries. Suitable for the MVP graph requirements; Neo4j remains a future roadmap option for deeply nested social networks.

---

## ADR 2: Strict Verbatim Evidence-Quote Validation

### Context
Large Language Models are prone to hallucinating facts or inferring unstated details (e.g. guessing that a dark robe implies black hair or making up eye colors).

### Decision
Every extracted fact must include an `evidence_quote`. Before any fact is admitted to the story graph, the algorithmic validator verifies that the quote exists **verbatim** in the source chapter text (using case-insensitive substring searching). Facts with hallucinated quotes are rejected immediately.

### Consequences
- **Positive:** Guarantees graph provenance and grounds every single attribute in text the author actually wrote. Eliminates false-positive hallucinations at the ingestion boundary.
- **Negative:** Extractions where the LLM paraphrased the evidence rather than copying it verbatim are rejected. Mitigated by explicit prompt instructions emphasizing exact quotes.

---

## ADR 3: Algorithmic Grouping + LLM Semantic Adjudication for Contradictions

### Context
Simple string inequality creates catastrophic false-positive rates for fiction (e.g., character starts with long hair and later gets a haircut; character turns 30; character moves from an apartment to a house; or "blue eyes" vs "deep cobalt eyes").

### Decision
Two-tier contradiction detection:
1. **Algorithmic Grouping:** Normalize and group facts by `(character_id, normalized_attribute)`. Identify candidate conflicting pairs. Filter out fact pairs that the author previously dismissed or marked as intentional.
2. **LLM Adjudication:** Dispatch candidate pairs with chapter references and verbatim context to an LLM adjudicator prompted to distinguish genuine contradictions from legitimate temporal changes (haircuts, aging, moving house) and different referents.

### Consequences
- **Positive:** Low false-positive rate on legitimate narrative progression; respects author intent and dismissals; provides clear natural language explanations to the writer.
- **Negative:** Requires an LLM completion for each candidate pair; mitigated by strict value normalization before candidate generation.

---

## ADR 4: Incremental Re-Analysis via Chapter Content Hashing

### Context
Analyzing full manuscripts (50k–100k+ words) with an LLM is token-intensive and slow. Authors frequently edit single chapters in write mode.

### Decision
Compute a SHA-256 `content_hash` for each chapter. Store `analyzed_hash` alongside `content_hash`. On subsequent analysis runs:
- Chapters where `content_hash == analyzed_hash` are completely skipped.
- Only modified or newly added chapters are analyzed. Stale facts for modified chapters are purged via `delete_chapter_data` before new facts are extracted.
- Contradiction detection and summarization re-run only if at least one chapter's content hash changed.

### Consequences
- **Positive:** Near-instant re-analysis during authoring; dramatic reduction in LLM token consumption and cost; prevents stale fact duplication.
- **Negative:** Requires careful cache invalidation when chapters are deleted or reordered.
