# Explainability

## 1. Purpose

This document specifies how the platform exposes why a given
document matched a given query and what its score was composed of.
It covers the roadmap sub-phases:

    * 16.1 -- _explain
    * 16.2 -- Score inspection
    * 16.3 -- Ranking analysis
    * 16.4 -- Explain API

## 2. The Problem

A relevance ranker is opaque by default. A user sees results in an
order and does not know why. A developer tuning field weights sees
a document at rank 3 and does not know whether that came from the
name boost, the phrase boost, or a business signal. Without a
mechanism to inspect the score, every relevance change is guesswork.

Elasticsearch exposes this mechanism: the `_explain` API. It
returns, for a given (query, document) pair, the full recursive
breakdown of how the score was computed.

## 3. The `_explain` API (16.1)

### 3.1 What it returns

The response is a JSON object with, at its core, a recursive
"explanation" tree:

    {
      "_index": "products-v2",
      "_id": "SKU-1001",
      "matched": true,
      "explanation": {
        "value": 12.5,
        "description": "sum of:",
        "details": [
          {
            "value": 7.5,
            "description": "weight(name:wireless in 3) [PerFieldSimilarity]...",
            "details": [...]
          },
          {
            "value": 5.0,
            "description": "Function for field rating:...",
            "details": [...]
          }
        ]
      }
    }

Each node has three fields:

* `value`: the numeric contribution of this node.
* `description`: a human-readable description of what the node is.
* `details`: an optional array of child nodes.

A leaf node has no `details`. An internal node sums or multiplies
its children, depending on its type.

### 3.2 Why this shape is worth preserving

The tree is the point. A flat score loses the information that
makes the explanation useful: which clause contributed what. The
platform preserves the tree end to end.

## 4. The Domain Shape (16.3)

### 4.1 Two value objects

The domain wraps the response in a small typed structure:

    ScoreExplanation
        value: float
        description: str
        details: tuple[ScoreExplanation, ...]

    ExplainResult
        matched: bool
        explanation: ScoreExplanation | None

`ScoreExplanation` is recursive: a node carries its children as a
tuple of the same type. `ExplainResult` is the top-level wrapper.

### 4.2 Why recursive, and why frozen

Recursive, because the underlying structure is a tree and a flat
list would lose depth information. A caller that wants only the
top-level score reads `explanation.value`. A caller that wants to
drill down recurses into `details`. Both are expressible.

Frozen, because every value object in this project is frozen. An
explanation is a snapshot of a scoring decision; it does not change
after it is built.

### 4.3 Why `explanation` is optional

A document that does not match the query has `matched: false` and
no `explanation` key. Elasticsearch omits the field entirely in
that case. The domain models this as `explanation=None`, not as an
empty tree, because the two states mean different things:
"no match" versus "matched but scored zero".

## 5. The Port and the Adapter (16.4)

### 5.1 `ProductExplainer`

The explain capability is distinct from search: the input is a
query and a specific document id (not a text), and the output is
an explanation, not a result set. It gets its own domain Protocol:

    ProductExplainer
        explain(query, document_id) -> ExplainResult

The query is a pre-composed DSL dictionary. The explainer does not
build queries; it forwards them to Elasticsearch and translates
the response.

### 5.2 The adapter

`ElasticsearchProductExplainer` calls `client.explain()` with the
index, the document id, and the query, then recursively converts
the response into `ScoreExplanation` and `ExplainResult`.

### 5.3 The use case

`ExplainScoreUseCase` takes a search query (text) and a document
id, composes the query through the platform's relevance composer,
and asks the explainer for the result. This is the mechanism the
API layer will expose in Phase 19.

## 6. What Explainability Does Not Do

The platform does not:

* Render the explanation for display. That is a frontend concern.
* Cache explanations. Each explain call is cheap; caching them
  would add invalidation complexity for no benefit.
* Compare explanations across documents automatically. A user can
  call explain twice and compare; the platform does not do it for
  them.
* Expose explanations for every search hit. The default search
  response does not carry them; a caller must request explain for
  a specific (query, document) pair.

## 7. Testing

The tests verify:

1. **The recursive structure.** A known (query, document) pair
   produces an explanation whose top-level description and value
   match what Elasticsearch returns, and whose children are
   themselves `ScoreExplanation` instances.
2. **Non-matching documents.** A query that does not match a
   document returns `matched=False` and `explanation=None`.
3. **The use case.** Given a query and document id, the use case
   composes the query through the platform's relevance builder
   and returns the explainer's result.

## 8. Rule for Changing Explainability

A change to the domain shape of `ScoreExplanation` or
`ExplainResult` is a change to this document and to the code, in
the same commit. The rule mirrors the other design documents.

