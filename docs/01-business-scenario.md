# Business Scenario — Medical Product Search

## 1. Purpose

This document defines the business scenario the platform serves and derives
the concrete search requirements that the Elasticsearch implementation must
satisfy. It is the bridge between the project identity (Phase 0.1) and the
technical design decisions that follow (mapping, analyzers, relevance,
index lifecycle).

Every Elasticsearch capability implemented in this project must trace back
to a requirement in this document. Conversely, no requirement listed here
may be silently dropped from the roadmap.

## 2. Domain

The platform serves search over a catalog of **medical products** —
equipment, consumables, and supplies used in hospitals, clinics, labs, and
emergency care. The catalog is multi-brand and multi-category, and contains
both English and Persian product descriptions.

Representative categories:

- Patient monitoring (vital-sign monitors, ECG, SpO2, NIBP)
- Imaging (ultrasound, X-ray accessories)
- Diagnostic equipment (glucometers, blood pressure devices)
- Surgical instruments and consumables
- Laboratory equipment and reagents
- Emergency and resuscitation equipment
- Hospital furniture and mobility aids

## 3. Users and Their Search Behavior

The platform serves four distinct search personas. Each stresses a
different Elasticsearch capability, and all four must be supported.

### 3.1 Clinician / Nurse

**Goal:** rapidly locate a specific product at the point of care.

- Knows the product by brand, model, or common name.
- Often searches with partial terms or typos under time pressure.
- Needs autocomplete and tolerant fuzzy matching.

### 3.2 Procurement Officer

**Goal:** build a compliant purchase list.

- Filters by category, brand, price range, and availability.
- Compares candidates and needs faceted counts to reason about the market.
- Needs reliable filtering, sorting, and aggregations.

### 3.3 Biomedical Engineer

**Goal:** find equipment that meets a technical specification.

- Searches by structured attributes (battery life, weight, display size).
- Needs range filters, numeric sorting, and structured-spec search.

### 3.4 Persian-Language User

**Goal:** search the same catalog in Persian.

- Types Persian terms with common character variance (Arabic vs Persian
  yeh/kaf, ZWNJ, diacritics, Western vs Eastern digits).
- Needs a Persian-aware analyzer, not the default English one.

## 4. Search Intents

The following intents must be supported. Each intent maps to specific
Elasticsearch query patterns, documented in later phases.

- **Exact / navigational** — "Mindray uMEC 12"
- **Full-text / exploratory** — "portable patient monitor for emergency"
- **Synonym-driven** — "ECG" vs "electrocardiogram"; "BP" vs "blood pressure"
- **Phrase-sensitive** — "blood pressure monitor" (order matters)
- **Typo-tolerant** — "mindrey", "moniter"
- **Prefix / autocomplete** — "moni" leading to "monitor", "monitoring"
- **Faceted** — brand=Mindray, category=Patient Monitoring, price<3000
- **Structured** — battery_hours >= 6, weight <= 5
- **Multilingual** — "مانیتور علائم حیاتی"

## 5. Concrete Search Scenarios

These scenarios become the workload for relevance tests and benchmarks.

| ID  | Query                                             | Intent                |
|-----|---------------------------------------------------|-----------------------|
| S1  | "patient monitor"                                 | full-text             |
| S2  | "portable patient monitor for emergency care"     | full-text + phrase    |
| S3  | "ECG"                                             | synonym               |
| S4  | "electrocardiogram"                               | synonym               |
| S5  | "BP monitor"                                      | synonym (BP)          |
| S6  | "mindrey umec"                                    | fuzzy + prefix        |
| S7  | "moni"                                            | autocomplete          |
| S8  | "blood pressure monitor"                          | phrase                |
| S9  | "monitor" filtered by brand=Mindray               | filter                |
| S10 | "monitor" sorted by price ascending               | sort                  |
| S11 | price in [500,3000] and category=PatientMonitoring| range + facet         |
| S12 | rating >= 4.5 and availability=in_stock           | range + filter        |
| S13 | "مانیتور بیمار"                                   | Persian full-text     |
| S14 | "مانيتور" (Arabic yeh) vs "مانیتور" (Persian yeh)| Persian normalization |

## 6. Functional Requirements

- **FR-1** Full-text search across name, description, brand, category, and
  tags with field weighting.
- **FR-2** Phrase-aware matching for multi-word queries.
- **FR-3** Fuzzy matching with controlled fuzziness and false-positive
  containment.
- **FR-4** Synonym expansion driven by a domain vocabulary (medical terms,
  abbreviations, brand aliases).
- **FR-5** Autocomplete / search-as-you-type over product name and brand.
- **FR-6** Filtering by category, brand, availability, price range, rating
  range.
- **FR-7** Aggregations producing category, brand, availability, and price
  buckets for faceted navigation.
- **FR-8** Sorting by relevance, price, rating, and recency, with stable
  tie-breaking.
- **FR-9** Pagination including a deep-pagination path.
- **FR-10** Highlighting of matched terms in the response.
- **FR-11** Explainability: return the scoring explanation for a
  (query, document) pair.
- **FR-12** English and Persian treated as first-class languages.

## 7. Non-Functional Requirements

- **NFR-1** Bulk ingestion must be idempotent and tolerate partial failures.
- **NFR-2** Index evolution must support zero-downtime reindexing and
  rollback.
- **NFR-3** The API must degrade predictably when Elasticsearch is
  unavailable, slow, or missing an index.
- **NFR-4** Search and indexing operations must be observable via
  structured logs and metrics.
- **NFR-5** Search latency must be measured under defined workloads; no
  universal performance claim is made.

## 8. Domain Vocabulary

A partial controlled vocabulary that the search layer must respect:

| Term          | Synonyms / Variants                                  |
|---------------|------------------------------------------------------|
| ECG           | electrocardiogram, EKG, 12-lead                      |
| SpO2          | pulse oximetry, oxygen saturation                    |
| NIBP          | non-invasive blood pressure, BP, blood pressure      |
| monitor       | patient monitor, vital-signs monitor, multiparameter |
| portable      | mobile, handheld, transport                          |
| ultrasound    | sonography, echo                                     |
| glucometer    | blood glucose meter, glucose monitor                 |

Persian vocabulary will be defined in Phase 11 (Synonym Engineering) using
the same structure.

## 9. Mapping to Elasticsearch Capabilities

Each requirement above maps to a concrete Elasticsearch capability covered
by the master roadmap:

| Requirement | Elasticsearch capability                            | Phase |
|-------------|-----------------------------------------------------|-------|
| FR-1        | multi_match, field boosting, BM25                   | 8, 9  |
| FR-2        | match_phrase                                        | 8     |
| FR-3        | fuzziness, prefix_length, fuzzy policy              | 10    |
| FR-4        | synonym token filter (search-time)                  | 11    |
| FR-5        | search_as_you_type / suggest                        | 12    |
| FR-6        | term, terms, range queries inside bool.filter       | 8, 14 |
| FR-7        | terms / range aggregations                          | 14    |
| FR-8        | sort clauses, tie-breakers                          | 15    |
| FR-9        | from/size, search_after                             | 15    |
| FR-10       | highlighting                                        | 13    |
| FR-11       | _explain API                                        | 16    |
| FR-12       | custom analyzers (English + Persian)                | 7     |
| NFR-1       | Bulk API, idempotent IDs, partial-failure handling  | 17    |
| NFR-2       | aliases, versioned indices, reindex, rollback       | 18    |
| NFR-3       | connection / timeout / error handling               | 23    |
| NFR-4       | structured logging and metrics                      | 24    |
| NFR-5       | benchmark harness                                   | 22    |

## 10. Out of Scope

The following business features are excluded to protect the search focus:

- User accounts, authentication, and personalization.
- Shopping cart, checkout, and payment.
- Order management and inventory transactions.
- Admin UI beyond Swagger.
- Recommendation and ML-based ranking.

Each exclusion may be revisited only if it becomes necessary to demonstrate
a specific Elasticsearch capability from the roadmap.
