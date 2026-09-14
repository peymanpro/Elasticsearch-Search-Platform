# Analyzer Documentation

## 1. Purpose

This document is the consolidated reference for the platform's text
analysis. It supersedes `docs/13-text-analysis.md` as the authoritative
statement of what each analyzer does and why, and references that
document for the design rationale.

It covers Phase 25.3 of the master roadmap.

## 2. The Four Analyzers

The platform defines four analyzers: two for index-time analysis and
two for search-time analysis. The split between index-time and
search-time is what makes the synonym list changeable without a
reindex (see Section 5).

| Analyzer | Phase | Applied to |
|---|---|---|
| `product_text_analyzer` | index | `name`, `description`, `name_suggest` |
| `product_text_search_analyzer` | search | same fields |
| `product_keyword_analyzer` | index | `brand`, `category`, `tags` |
| `product_keyword_search_analyzer` | search | same fields |

## 3. The Analysis Chain

### 3.1 Text analyzers (`name`, `description`)

    character filters: (none)
    tokenizer:         standard
    token filters:     lowercase -> asciifolding -> [synonym] -> stop -> porter_stem

The search-time variant inserts the synonym filter between
`asciifolding` and `stop`. Everything else is identical, so the
analyzer is symmetric: a token that matched without synonyms still
matches with them, and a token that only matched because of synonyms
now matches too.

### 3.2 Keyword analyzers (`brand`, `category`, `tags`)

    character filters: (none)
    tokenizer:         standard
    token filters:     lowercase -> asciifolding -> [synonym]

The search-time variant inserts the synonym filter at the end. The
`stop` and `porter_stem` filters are deliberately absent: brand names
and category names are short, brand-like values where stemming would
damage the exact form.

## 4. Filter Rationale

| Filter | Purpose | Why this catalog needs it |
|---|---|---|
| `standard` tokenizer | Unicode word boundaries | Handles punctuation, camelCase, and non-Latin without configuration |
| `lowercase` | "Sony" -> "sony" | Case-insensitive matching |
| `asciifolding` | "cafe" <-> "caf?"; "Muller" <-> "M?ller" | Diacritics in product text should not block a match |
| `synonym` | "tv" -> ["tv", "television"] | Vocabulary expansion (see Section 5) |
| `stop` | Removes "the", "and", "of" | High-frequency words carry no signal for short queries |
| `porter_stem` | "monitors" -> "monitor" | Morphological variation should not block a match |

## 5. Synonyms

The synonym list lives at
`infrastructure/elasticsearch/synonyms/products_synonyms.txt` and
contains 21 equivalence groups. It is applied at **search time**, not
index time.

The search-time placement was chosen because the vocabulary changes
more often than the mapping does. Adding a synonym group is a change
to a text file; the index does not need to be rebuilt for it to take
effect. See `docs/16-synonyms.md` section 3.

The loader injects the synonym file content into the index settings
at index-creation time. The settings file declares the filter with an
empty list; the loader populates it. This keeps the synonyms in one
readable file while leaving the settings JSON declarative.

## 6. What the Analyzers Do Not Do

* **They do not normalize Persian characters.** The catalog is
  English-only. Phase 7.6 and 7.7 (Persian analyzer and Persian
  normalization) are out of scope per `docs/09` section 3.1.
* **They do not remove HTML.** No document in the dataset contains
  HTML. If a future ingestion path introduced markup, an
  `html_strip` character filter would be added at that point.
* **They do not lowercase on non-analyzed fields.** Keyword fields
  such as `id`, `sku`, `language`, `currency`, and `availability`
  are not analyzed.
* **They are not applied to numeric or date fields.** Numeric and
  date fields have no analyzer.

## 7. Verification

Every analyzer is verified through the `_analyze` API against the
running cluster. The tests in `tests/integration/test_analyzers.py`
assert the exact token stream for known inputs. An analyzer that is
not verified by a test in that file is not considered implemented.

## 8. Related Documents

* `docs/12-index-design.md` ? how fields are mapped and which
  analyzer each field uses.
* `docs/13-text-analysis.md` ? the design rationale for every
  analyzer choice.
* `docs/16-synonyms.md` ? the synonym list, the search-time decision,
  and the vocabulary.
