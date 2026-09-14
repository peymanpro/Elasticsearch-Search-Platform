# Highlighting

## 1. Purpose

This document specifies how the platform returns, alongside each
search hit, the matched fragments of the document that produced
the match. It covers the roadmap sub-phases:

    * 13.1 -- Basic highlighting
    * 13.2 -- Field-specific highlighting
    * 13.3 -- Response mapping

## 2. What Highlighting Is

When Elasticsearch matches a document against a query, it can return
not only the document but also the specific fragments of the text
where the match occurred. Each fragment is a small excerpt,
typically a sentence or two, with the matching terms wrapped in
markup:

    "Over-ear <em>wireless</em> headphones with active noise
     cancellation."

The user interface then renders the fragment with the emphasized
terms visually distinct. The effect is that a user sees *why* a
result matched, in the result list itself, without opening the
document.

Highlighting is a read-time annotation. It does not affect the
index, the ranking, or which documents match. It only changes what
the response carries.

## 3. What the Response Carries (13.1)

### 3.1 The Elasticsearch shape

When the search request includes a ``highlight`` block, each hit in
the response may carry a ``highlight`` field:

    {
      "_id": "SKU-1001",
      "_score": 4.2,
      "_source": { ... },
      "highlight": {
        "name": ["<em>Wireless</em> Noise-Cancelling Headphones"],
        "description": ["Over-ear <em>wireless</em> headphones with active noise cancellation."]
      }
    }

The ``highlight`` object maps each field name to an array of
fragments. A field may have zero fragments (no match in that field),
one fragment (a short field), or several (a long description with
the query term appearing multiple times).

### 3.2 Why a field may have several fragments

For a long field, Elasticsearch returns multiple excerpts so the
user sees each place the term appears. The number is bounded by
``number_of_fragments`` in the highlight configuration. For short
fields, the default is one fragment containing the whole field.

### 3.3 What the platform carries

The platform exposes the fragments as a mapping of field name to
tuple of strings. It does not carry the fragment index, the
matched-terms list, or any other metadata. The fragments themselves
are what the front end renders, and the mapping form is enough to
express "this field matched here, and here."

## 4. Field-Specific Highlighting (13.2)

### 4.1 Which fields are highlighted

The platform highlights the same five text-searchable fields the
search queries target:

    name, brand, category, description, tags

These are exactly the fields that participate in ``multi_match``.
Highlighting a field that no query matched would produce empty
fragments and waste response size.

### 4.2 Which fields are not highlighted

The following fields are not highlighted:

* **Filterable keyword fields** (``sku``, ``language``, ``currency``,
  ``availability``). These are not searched; they are filtered. A
  filter produces a match but does not produce fragments, and the
  user does not benefit from seeing them highlighted.
* **Numeric fields** (``price``, ``rating``, ``popularity``). Numeric
  fields cannot be highlighted.
* **Date fields.** Highlighting a date has no useful visual effect.
* **The ``specifications`` flattened field.** Flattened fields do
  not support highlighting because the original structure is not
  preserved after flattening.

### 4.3 Why field-specific rather than "highlight everything"

A highlight block that names every field would still return empty
fragments for fields that were not searched, but Elasticsearch
would spend time computing them and the response would carry the
empty keys. Naming the five fields explicitly is both correct and
cheaper.

## 5. The Highlight Configuration

### 5.1 The block the platform sends

    "highlight": {
      "fields": {
        "name": {},
        "brand": {},
        "category": {},
        "description": { "number_of_fragments": 3 },
        "tags": {}
      },
      "pre_tags": ["<em>"],
      "post_tags": ["</em>"]
    }

### 5.2 Choices and rationale

**pre_tags / post_tags = `<em>` / `</em>`.** The default is
`<em>...</em>`, so this setting is technically redundant. It is
declared explicitly so that a future change -- to `<mark>`, to a
`<span class="hl">` -- is a change to one place, and so a reader
of the query does not have to know the default. `<em>` is chosen
over `<mark>` because the fragments are inserted into arbitrary
front-end contexts and `<em>` is the more conservative choice.

The tags are HTML-shaped but the platform does not guarantee HTML
output. The fragments are strings; the caller is responsible for
how they are rendered. If a caller renders them in a non-HTML
context, they strip or transform the tags themselves.

**`number_of_fragments: 3` on description only.** The description
is the longest field and the one where a query term can appear in
several places. Three fragments is a reasonable upper bound for a
result row. For the shorter fields, the default of one fragment
per field is kept: the fragment is typically the whole field.

**No `fragment_size` override.** The default is 100 characters per
fragment. That is a sensible length for a result row. Changing it
would require a reason the platform does not have.

**No `require_field_match`.** The default is true, which means a
fragment is returned only for a field that the query actually
matched. A false value would return fragments for every field,
including fields the query did not touch. The default is correct.

### 5.3 The highlight block is added in one place

The gateway is the only component that issues a search request. It
adds the highlight block to every request it makes, whether the
caller asked for it or not. There is no separate "search with
highlighting" and "search without highlighting" method; the
response always includes fragments for the fields that matched.

The reason: the cost of computing highlights for the small result
set the platform returns (at most a page of 100 documents) is
negligible. The benefit is a simpler gateway with one code path.
If a future phase measures a cost and decides to make it opt-in,
that is a change to the gateway's request builder in one place.

## 6. Response Mapping (13.3)

### 6.1 The domain extension

The domain's ``SearchHit`` value object gains one optional field:

    highlights: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

The mapping is from field name to the tuple of fragments
Elasticsearch returned for that field. Fields with no fragments are
absent from the mapping (not present with an empty tuple). This is
the standard shape: "this field has these fragments" versus "this
field has no fragments" are different statements, and the second is
expressed by absence.

### 6.2 Why this shape

**A mapping, not a list.** The field name is the key. A caller that
wants "the highlighted fragments for the description" reads
``hit.highlights.get("description", ())``. A list of ``(field_name,
fragments)`` tuples would also work but is less direct.

**Tuples, not lists.** The domain is frozen throughout. A tuple is
the frozen counterpart of a list, and using it keeps ``SearchHit``
hashable and immutable.

**Empty mapping, not None.** The default is an empty mapping. A
caller reads ``hit.highlights`` and never has to distinguish
``None`` from "no fragments".

### 6.3 Backwards compatibility

Every existing construction of ``SearchHit`` continues to work
because the new field has a default. Existing tests that construct
``SearchHit(document_id=..., score=..., source=...)`` do not need
updating. The gateway is the only place that populates the new
field.

### 6.4 What the domain does not do

The domain does not:

* Parse the fragments. The pre-tags and post-tags are kept as-is.
  Stripping them is a presentation concern.
* Decide which fields to highlight. That is the gateway's query.
* Score or rank by highlighting. Fragments are metadata attached
  to a ranked hit, not a ranking input.

## 7. Testing

### 7.1 What is tested

Three properties are verified against a real cluster:

1. **A field that matched has fragments.** A query for "wireless"
   against a document whose name contains "Wireless" produces a
   ``name`` key in the hit's highlights.
2. **The fragments contain the emphasized query term.** The fragment
   strings include the pre-tag, the matched term, and the post-tag.
3. **A field that did not match has no fragments.** A query for
   "wireless" against a document whose brand is "Sony" produces no
   ``brand`` key in the highlights.

The tests use the same fixture catalog as the query-DSL tests
(Phase 8) and are marked integration.

### 7.2 What is not tested

Fragment content beyond the tag and the matched term is not asserted.
Fragment length, fragment count for short fields, and the exact
text around the match are Elasticsearch's behavior; the platform
has no control over them and no reason to depend on them.

## 8. Rule for Changing Highlighting

A change to the pre-tags, post-tags, or the set of highlighted
fields is a change to this document and to the gateway's query
builder, in the same commit. A change to the shape of the
``highlights`` field on ``SearchHit`` is a domain change and
requires the same discipline as any other domain extension: it is
recorded here first.

