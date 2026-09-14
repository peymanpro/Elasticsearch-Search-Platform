# Synonym Engineering

## 1. Purpose

This document specifies how the platform expands a user's query to
include terms they did not type but that mean the same thing. It
covers the roadmap sub-phases:

    * 11.1 -- Define synonyms
    * 11.2 -- Synonym strategy
    * 11.3 -- Search-time vs. index-time
    * 11.4 -- Synonym testing
    * 11.5 -- Domain vocabulary

## 2. What a Synonym Is, and What It Is Not

### 2.1 The problem

A user searching for "tv" expects to find products whose names say
"television". A user searching for "earphones" expects to find
"headphones". A user searching for "BP monitor" expects to find
"blood pressure monitor". In each case, the query term and the
indexed term are different strings that refer to the same concept.

Without a synonym mechanism, Elasticsearch matches only what the
user actually typed. Coverage is lost.

### 2.2 What synonyms are

A synonym is a pair (or group) of terms that should be treated as
equivalent at query time. The platform's mechanism of choice is the
Elasticsearch `synonym` token filter. The filter is configured with
a list of equivalence groups, and it rewrites query tokens to include
every member of the group.

    "tv,television"              -> "tv"     becomes ["tv","television"]
                                     "telly"  becomes ["tv","television"]

    "headphones,earphones"       -> "headphones" becomes ["headphones","earphones"]

The filter operates during analysis, not during scoring. Once the
query has been analyzed, the resulting tokens compete against the
inverted index in the usual way. BM25 ranks the results; synonym
expansion only changes which terms participate.

### 2.3 What synonyms are not

Synonyms are not:

* **Stemming.** A synonym filter knows nothing of word morphology.
  "phones" and "phone" are handled by the `porter_stem` filter; a
  synonym list that contained them would be redundant.
* **Fuzzy matching.** A synonym filter does not bridge typos.
  "televison" and "television" is a Phase 10 problem.
* **Query rewriting in the application.** The filter runs inside
  Elasticsearch, not in Python. The application's strategies are
  unchanged by this phase.

The three mechanisms are complementary and are used together:
stemming handles morphology, fuzzy handles typos, synonyms handle
vocabulary.

## 3. Search-Time vs. Index-Time (11.3)

### 3.1 The two placements

A synonym filter can be attached to two analyzers:

* **Index-time analyzer** -- runs when a document is indexed. The
  filter rewrites the document's tokens before they enter the
  inverted index. A query then matches expanded tokens without
  itself being expanded.

* **Search-time analyzer** -- runs when a query is analyzed. The
  filter rewrites the query's tokens before they are compared
  against the index. Documents are stored unexpanded.

### 3.2 The trade-offs

| Aspect | Index-time | Search-time |
|---|---|---|
| Reindex required to change synonyms | yes | no |
| Index size | larger (more tokens per document) | unchanged |
| Query cost | lower | higher (expansion happens per query) |
| Phrase queries | work as expected | phrase queries degrade (see below) |
| Update procedure | reindex + alias switch | update the synonym file, reload the index |

### 3.3 The choice

Search-time synonyms are used.

### 3.4 Why

**Synonyms change.** An e-commerce vocabulary is not static: new
abbreviations appear, brands add nicknames, seasonal terminology
shifts. A synonym list is edited far more often than a mapping.
Search-time placement means an edit takes effect on the next query.
Index-time placement means every synonym edit costs a full reindex
and an alias switch (Phase 18).

**Index size matters less than query cost here.** The platform's
corpus is small (thousands of documents). Doubling the tokens per
document is a rounding error. Query cost -- which search-time
synonyms pay -- is bounded by the synonym list itself and is
amortized across a query that would already be scanning the index.

**Phrase queries are not a concern for this catalog.** Search-time
synonyms have a known weakness: a multi-word phrase query is
expanded to a disjunction of phrases, which multiplies the query
cost and can surprise ranking. The platform uses `match_phrase`
only for the exact-name boost (Phase 9.3), which targets the
unboosted name field. Synonyms are applied to `name`'s
`search_analyzer`, so the phrase query does see them -- but the
name field is short, and the fixture is small, so the cost is
negligible.

### 3.5 What search-time placement requires

Two analyzers per text field:

* `analyzer` -- the index-time analyzer, used when a document is
  indexed. Unchanged from Phase 7.
* `search_analyzer` -- the search-time analyzer, used when a query
  is analyzed. This one includes the synonym filter.

Both analyzers share the same tokenizer, the same lowercasing, and
the same accent folding. They differ only in the presence of the
synonym filter at the end. That symmetry keeps the index and the
query aligned: a token that would match without synonyms still
matches after; a token that only matches because of synonyms now
matches too.

## 4. The Synonym File (11.1)

### 4.1 Format

The synonym list is a plain text file with one rule per line. Two
rule syntaxes are supported by Elasticsearch:

* **Equivalence:** `tv,television,telly` -- all three terms are
  mutually equivalent. A query for any of them expands to all of
  them.
* **Explicit mapping:** `tv => television` -- the left side expands
  to the right side only. A query for "television" does not expand
  to "tv".

The platform uses equivalence throughout. Explicit mapping is useful
when one direction is meaningful and the other is not (an acronym
whose expansion is a phrase), but the platform's vocabulary is
symmetric: the user may type either form, and both should match the
same documents.

### 4.2 File location

The synonym file lives at `infrastructure/elasticsearch/synonyms/
products_synonyms.txt`. It is loaded into the index settings when
the index is created. Elasticsearch reads the file at index-creation
time and stores its content in the index; a change to the file does
not affect an existing index until the index is closed and reopened,
or recreated.

This is a limitation of the inline synonym format. The alternative --
a synonyms resource hosted by an HTTP service -- would let an index
pick up changes on `_reload_search_analyzers`, but introduces an
external dependency (a web server) that is out of scope for this
project. The trade-off is documented here: synonyms are changeable,
but a synonym change requires an index reopen or recreate, not just
a file edit.

In Phase 18, the reindex workflow is the mechanism that propagates
a synonym change to a live index: build a new index version, reindex,
switch the alias.

### 4.3 What belongs in the list

Only terms whose equivalence is unambiguous in the catalog context.
Overly broad synonym lists are a common source of false positives:
a rule that says "monitor,display" makes every query for "display"
return every monitor. The list below is deliberately narrow.

## 5. Domain Vocabulary (11.5)

### 5.1 The list

The platform's synonym list is organized by concept groups. Each
group is a single line; the terms within it are mutually equivalent.

    # Electronics
    tv,television,telly
    headphones,headphone,earphones,earphone
    speaker,speakers,loudspeaker
    laptop,laptops,notebook,notebooks
    keyboard,keyboards
    mouse,mice
    tablet,tablets
    charger,chargers,adapter,adapters
    cable,cables,cord,cords

    # Home and kitchen
    knife,knives
    pan,pans,frying-pan,frying-pans
    pot,pots,cookware
    espresso,espresso-machine,coffee-machine,coffee-maker

    # Office
    desk,desks,table,tables
    chair,chairs,seat,seats

    # Sports
    shoe,shoes,footwear
    mat,mats,yoga-mat,yoga-mats

    # Generic retail terms
    wireless,cordless
    portable,mobile,handheld
    cheap,affordable,budget,inexpensive
    premium,high-end,luxury

### 5.2 Why each group is safe

Every group satisfies two properties:

1. **Within a category, the terms are truly interchangeable.**
   "TV" and "television" name the same object; a user who types
   either expects the same result set. There is no context in this
   catalog in which the two words mean different products.
2. **The group is not so broad that it crosses categories.**
   "Portable, mobile, handheld" is safe because no electronics
   product in the catalog is portable in one sense and not the
   other. "Monitor, display" was rejected precisely because it
   would cross into contexts where "display" is an attribute rather
   than a product type.

### 5.3 What is deliberately absent

The list excludes several synonym pairs that would be tempting:

* **Brand names as synonyms.** "Apple" is not a synonym for "iPad".
  A user searching for "Apple" should find every Apple product, not
  every tablet.
* **Model numbers.** "uMEC12" is not a synonym for "patient
  monitor". A user searching for a specific SKU wants that SKU.
* **Hierarchical categories.** "Electronics" is not a synonym for
  "TV". A category is not a product term; category filtering is a
  Phase 14 concern.
* **Spelling variants.** "color" and "colour" are handled by the
  ASCII-folding filter (Phase 7), not by synonyms.
* **Singular and plural forms.** "speaker" and "speakers" appear in
  the same group above for one reason: the analyzer chain uses the
  `porter_stem` filter on `name` and `description`, but the platform
  wanted to be explicit that both forms are the same concept for
  `brand` and `category` fields, which do not stem. The stemmer
  handles the rest.

## 6. Synonym Testing (11.4)

### 6.1 What is tested

Two properties are tested:

1. **Every group in the file is loaded.** The synonym filter reads
   the file at index time; if the file has a syntax error, the
   index creation fails. A test that reads the file and asserts its
   line count catches accidental truncation.
2. **Each group produces equivalent results.** For every group in
   the file, the test issues a search for one member of the group
   and a search for another member of the same group, and asserts
   that the two result sets are identical.

The second property is the interesting one. It is what a user would
actually rely on: if they type "tv" or they type "television", the
same products should appear.

### 6.2 What is not tested

The test does not assert that a specific synonym group produces
specific documents. It asserts equivalence of results. This is
deliberately weaker: it does not depend on which documents exist in
the fixture, only on the fact that the two query terms behave the
same way against the same index.

### 6.3 The fixture

The test creates a small fixture index whose documents mention both
members of every synonym group. This guarantees that a non-expanded
query would find only some documents, while an expanded query finds
all of them. If the synonym filter were not working, the equivalence
test would fail.

## 7. Rule for Changing the Vocabulary

Adding a synonym group, removing one, or editing one is a change to
this document and to the synonym file, in the same commit. The test
that asserts equivalence applies automatically to any new group.

Because search-time synonyms are in use, a change takes effect on
the next index creation. For a live index, the change is propagated
through the reindex workflow of Phase 18.

