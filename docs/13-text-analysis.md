# Text Analysis

## 1. Purpose

This document specifies how the platform turns text into tokens. It
covers the roadmap sub-phases:

    * 7.1 -- Tokenization
    * 7.2 -- Character Filters
    * 7.3 -- Token Filters
    * 7.4 -- Custom Analyzer
    * 7.5 -- English Analyzer
    * 7.8 -- Analyzer Testing

The Persian-language sub-phases (7.6, 7.7) are out of scope: the
catalog is English-only. See docs/09 section 3.1 and the Phase 4.3
decision recorded there.

## 2. What Analysis Is, and Why It Matters

An **analyzer** turns a string into a stream of tokens. Elasticsearch
uses analyzers in two places:

    * At **index time** -- the tokens that go into the inverted
      index for a text field.
    * At **search time** -- the tokens that a query is compared
      against the inverted index.

For a search to find a document, the tokens at index time and the
tokens at search time must overlap. Analysis is therefore not a
cosmetic choice: it is the mechanism that decides which queries match
which documents.

Three consequences follow:

1. Analyzers must be **symmetric**. If the index-side analyzer
   lowercases but the search-side analyzer does not, a query for
   "Sony" will not find a document indexed as "sony".
2. Analysis choices are **hard to reverse**. Changing an analyzer
   requires reindexing, because the inverted index is derived from
   the current analyzer.
3. Analysis choices are **field-specific**. A product description
   and a brand name deserve different treatment.

## 3. The Analysis Chain

An analyzer is a pipeline of three stages:

    character filters -> tokenizer -> token filters

**Character filters** transform the raw string before tokenization.
They see the whole text and can remove or replace characters. They
are rarely used in a search catalog.

**The tokenizer** splits the string into tokens. The `standard`
tokenizer follows Unicode word boundaries and is the default for
almost every text field.

**Token filters** transform each token individually. Lowercasing,
accent folding, stopword removal, and stemming are all token filters.

## 4. Decisions

### 4.1 Tokenizer: `standard`

The `standard` tokenizer splits on Unicode word boundaries. It
handles punctuation, camelCase, and non-Latin scripts sensibly without
requiring configuration.

**Alternatives considered.**

* `whitespace` -- splits on space only. Rejected: leaves punctuation
  attached to tokens, so "headphones." and "headphones" would be
  different tokens.
* `keyword` -- treats the entire input as one token. Rejected for
  text fields: it would prevent any multi-word match.

### 4.2 Character filters: none

No character filter is applied to the text fields.

**Why not.** The dataset is well-formed JSON with clean text. There
is no HTML to strip, no known character substitution to apply. Adding
a character filter would be configuration without a problem to solve.
If a future ingestion path introduces HTML or known substitutions, a
character filter is added at that point with a recorded rationale.

The `html_strip` character filter is worth mentioning as the one that
would be first if the ingestion story changed: product descriptions
pulled from an HTML store often carry markup that should not become
tokens.

### 4.3 Token filters for the searchable text fields

Two custom analyzers are defined. Their filters differ by field
purpose.

**`product_text_analyzer`** -- for `name`, `description`.

Filters, in order:

| Filter | Effect | Why |
|---|---|---|
| `lowercase` | "Sony" -> "sony" | Case-insensitive matching |
| `asciifolding` | "cafe" -> "cafe"; accents stripped | Diacritics in product text should not block matches |
| `stop` | removes "the", "and", "of" | High-frequency words carry no signal for short queries |
| `porter_stem` | "monitors" -> "monitor" | Suffix variation should not block a match |

**`product_keyword_analyzer`** -- for `brand`, `category`.

Filters, in order:

| Filter | Effect | Why |
|---|---|---|
| `lowercase` | "Sony" -> "sony" | Case-insensitive matching |
| `asciifolding` | diacritics stripped | Consistent with product_text_analyzer |

**Why brand and category do not stem.** Stemming "Sony" produces
"soni", and stemming "Books" produces "book". Both are losses for
short, brand-like values where the exact form is meaningful. The
stemming filter is reserved for the fields where morphological
variation actually appears (names, descriptions).

**Why brand and category drop stopwords is not needed.** Stopword
removal is a filter that affects multi-word tokens. Brand and
category values in this catalog are one or two words; no stopword
will be present. The filter is omitted to keep the chain minimal.

### 4.4 Why the analyzer chain is asymmetric across fields

Three different analyzer choices exist for four different purposes:

| Field purpose | Analyzer |
|---|---|
| Full-text narrative (name, description) | product_text_analyzer |
| Brand and category (searchable, also filterable) | product_keyword_analyzer |
| Tags (searchable, array of short phrases) | product_keyword_analyzer |
| Filter and aggregation fields (sku, language, currency, availability) | not analyzed (keyword) |

The asymmetry is deliberate: analysis choices serve the queries that
will run against each field.

### 4.5 Analyzer symmetry between index time and search time

Elasticsearch applies the analyzer to a field automatically in three
situations:

    * When indexing a document (index-time analysis).
    * When a `match` query runs against the field (search-time
      analysis).
    * When a `multi_match` query includes the field.

For `term`, `terms`, and `range` queries, no analysis is applied: the
query value is compared literally against the inverted index. A
`term` query on an analyzed field will usually miss, because the
indexed token is not the raw input.

This is why fields that need exact filter behaviour are mapped as
`keyword`, not `text`. The `dynamic: strict` policy of the mapping
enforces that a text field always goes through the text-analyzer,
and a keyword field never does.

## 5. Analyzer Testing

Every analyzer is verified through the `_analyze` API. The tests in
`tests/integration/test_analyzers.py` assert the exact tokens each
analyzer produces for known inputs. This is the only way to be
certain that analysis actually behaves as the design says: the
inverted index does not expose its tokens, but `_analyze` does.

## 6. Where This Is Configured

The analyzer definitions live in the `analysis` block of
`products_v1.settings.json`. The mapping attaches them per field
through the `analyzer` key. The loader in
`infrastructure/elasticsearch/indices/__init__.py` returns both as
plain dictionaries, and the manager passes them to
`indices.create`.

## 7. Rule for Changing an Analyzer

An analyzer change requires a new index version and a reindex. The
procedure is the same as for any mapping change (docs/12 section 7).
The change is recorded here first, then implemented in the settings
file, then validated by the analyzer tests, then rolled out through
the alias mechanism of Phase 18.

Analyzers that appear in the settings file without a corresponding
test are not considered implemented.

