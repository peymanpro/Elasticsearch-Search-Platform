# Autocomplete

## 1. Purpose

This document specifies how the platform returns suggestions for
partial user input -- the "search as you type" behavior. It covers
the roadmap sub-phases:

    * 12.1 -- Search-as-you-type requirement
    * 12.2 -- search_as_you_type
    * 12.3 -- Completion Suggester evaluation
    * 12.4 -- Suggest API

It is also the first phase that creates a new index version. The
reason and the procedure are documented in Section 6.

## 2. The Search-as-You-Type Requirement (12.1)

### 2.1 What the user does

A user types characters into a search box. After each keystroke, the
platform returns a short list of product names that begin with (or
contain) what the user has typed. The user picks one, and the search
box is filled with the full suggestion.

### 2.2 What makes this different from search

An autocomplete query differs from a search query in three ways:

1. **The input is a prefix, not a term.** The last token may be
   incomplete ("headph" for "headphones"). The analyzer that
   handles a search term may produce a stem that does not exist as
   a prefix in any indexed document.
2. **Latency is far more visible.** The suggestion appears on every
   keystroke, so it must be fast. A search that takes 100 ms is
   fine; a suggestion that takes 100 ms feels sluggish because it
   happens repeatedly within a single query the user is composing.
3. **Only names matter, not descriptions.** The result of an
   autocomplete is a list of completions for a text box, not a
   ranked list of products. Descriptions and relevance scoring are
   irrelevant to this task.

### 2.3 What a naive prefix query would do

One could serve autocomplete with a `prefix` query on the existing
`name` field:

    { "prefix": { "name.keyword": "headph" } }

This works for the simplest case but fails in three ways:

* **It matches only the first word of the field.** "noise cancel"
  would not find "Wireless Noise-Cancelling Headphones" because the
  prefix does not start the full name.
* **It has no multi-word awareness.** The user typing "wireless
  head" expects to match the above product; a simple prefix does
  not.
* **It scores every prefix match equally.** Prefix queries do not
  rank; they filter. The suggestion list would be alphabetical or
  arbitrary.

A mechanism designed for autocomplete handles all three.

## 3. Two Mechanisms (12.2 and 12.3)

### 3.1 search_as_you_type

Elasticsearch's `search_as_you_type` field type generates, for one
declared field, a family of subfields:

    name_suggest                    base field (whole-text tokens)
    name_suggest._2gram             all adjacent 2-grams
    name_suggest._3gram             all adjacent 3-grams
    name_suggest._index_prefix      the first 10 characters as a prefix field

A query for a partial input uses the `bool_prefix` query type,
which is a specialized query that matches the input tokens as a
prefix against the corresponding n-gram subfield. It:

* Handles multi-word input.
* Ranks matches by which n-gram field produced them (whole-text >
  3-gram > 2-gram), giving a natural relevance order,
* Runs efficiently because the n-grams are pre-computed at index
  time.

### 3.2 The completion suggester

The completion suggester is a separate mechanism built on a
dedicated in-memory data structure that Elasticsearch maintains
beside the inverted index. A field of type `completion` stores a
list of suggested phrases; the suggest API looks them up by prefix
and returns them in a specialized response.

Its strengths:

* Extremely fast (the structure is optimized for prefix lookup).
* Supports weighted suggestions (a `weight` per phrase).
* Supports "contexts" for filtered suggestion.

Its weaknesses:

* The suggestion list is **declared, not derived.** Every suggested
  phrase must be added to the completion field. A new product name
  must be added to the field; otherwise the product is not
  suggestible.
* The completion field duplicates the product name. It is not a
  searchable field; it exists only for suggestions.
* Prefix-only matching. The suggester can match "headph" against
  "headphones" but not "phones" against the same term.

### 3.3 The choice

The platform uses `search_as_you_type` with the `bool_prefix` query.

### 3.4 Why not the completion suggester

The completion suggester is faster, but speed is not the platform's
constraint. The catalog is small; suggestion latency is dominated by
network round-trip, not by the query itself. The suggester's
advantage does not materialize.

The suggester's disadvantage does materialize. Every suggestion
phrase must be declared in the completion field. Every product name
added to the catalog must also be added to its completion field, in
the same bulk operation, or the product silently disappears from
suggestions. That is a second source of truth for the same data.

The `search_as_you_type` approach derives suggestions from the same
`name` field that search uses. There is no second copy, no
declaration step, and no drift between what is searchable and what
is suggestible.

The completion suggester is documented here so that a reader knows
it was considered and why it was not chosen. It remains the right
answer for a catalog where suggestions are curated (a list of
categories, a list of brands) rather than derived (a product name).

## 4. The Suggest API (12.4)

### 4.1 The domain port

Autocomplete is a distinct capability from search. It has a
different input (a prefix, not a query), a different output (a list
of suggestions, not documents), and a different performance profile.
It therefore gets its own domain port:

    ProductSuggester
        suggest(prefix, limit) -> tuple[str, ...]

The method returns a tuple of suggestion strings -- product names
that match the prefix. It does not return documents, scores, or
anything else. A suggestion is a string; that is the whole contract.

### 4.2 The adapter

The infrastructure adapter issues a `bool_prefix` query against the
`name_suggest` field of the products index and maps the response to
a tuple of suggestion strings. It draws from the same client and
index configuration as the search gateway, so there is one place
where the index name comes from.

### 4.3 The use case

A `GetSuggestionsUseCase` in the application layer takes a prefix
and a limit, validates them (a prefix must be non-empty; a limit
must be between 1 and a documented maximum), and returns the
suggestions. It depends only on the `ProductSuggester` Protocol.

### 4.4 What the API layer will do

The HTTP endpoint (Phase 19) will expose the use case at
`GET /api/suggest?q=...&limit=...`. This phase does not implement
the endpoint; it implements the mechanism the endpoint will use.

## 5. Index Version v2

### 5.1 Why a new version

The `name_suggest` field is new. Elasticsearch forbids adding fields
to an existing index after it has documents. The only options are:

1. Delete v1 and recreate it. Only valid if v1 has no live consumers.
2. Create a new version (v2) with the new field, reindex the
   documents from v1, and switch the alias.

Option 2 is the standard procedure and is what Phase 18 formalizes.
Phase 12 lays the groundwork by creating v2's settings and mapping
and by bumping the `CURRENT_INDEX_VERSION` constant. From this
point on, the platform's tests create v2.

### 5.2 What changes between v1 and v2

Only one thing: the addition of `name_suggest` as a
`search_as_you_type` field. The field is configured with:

* `analyzer: product_text_analyzer` -- same analyzer as `name`, so
  that suggestion tokens are formed the same way search tokens are.
* `search_analyzer: product_text_search_analyzer` -- same search
  analyzer, so that synonym expansion applies to suggestions too.
* `max_shingle_size: 3` -- the default. Generates `._2gram` and
  `._3gram` subfields automatically.

Everything else -- settings, other fields, analyzers -- is
identical to v1. The v2 files are complete copies of the v1 files
with the one addition.

### 5.3 Why not modify v1 in place

Modifying v1 would mean editing a mapping that has already been
used to create an index. Even in a development environment with no
live data, the pattern of immutability is worth establishing: a
mapping is a versioned artifact, and changes produce a new version.
Phase 18 depends on this pattern being in place.

## 6. Testing

Autocomplete has three things worth testing:

1. **The use case.** Given a fake suggester and a prefix, the use
   case returns the fake's suggestions, validates the prefix and
   the limit, and propagates errors from the suggester.
2. **The adapter.** Against a real index loaded with the fixture
   catalog, the adapter returns suggestion strings for a prefix.
3. **The end-to-end behavior.** A prefix of a known product name
   returns that product name among the suggestions.

The tests use the same products-v2 index the search tests will use.
They skip cleanly when no cluster is reachable.

