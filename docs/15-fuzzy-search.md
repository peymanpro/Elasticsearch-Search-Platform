# Fuzzy Search

## 1. Purpose

This document specifies how the platform tolerates typos in search
input. It covers the roadmap sub-phases:

    * 10.1 -- Edit distance
    * 10.2 -- Fuzziness
    * 10.3 -- Prefix length
    * 10.4 -- Fuzzy search policy
    * 10.5 -- False positive analysis

## 2. Edit Distance (10.1)

### 2.1 What it is

The edit distance between two strings is the minimum number of
single-character operations needed to turn one into the other. The
operations are:

* insertion -- "monitor" -> "monitors"
* deletion -- "monitors" -> "monitor"
* substitution -- "moniter" -> "monitor"
* transposition of two adjacent characters -- "moniotr" -> "monitor"

With transposition, the metric is called Damerau-Levenshtein;
Elasticsearch uses this variant. The distinction matters: common
typing errors ("hte" for "the", "wiht" for "with") are transpositions,
and treating them as two single-character edits (insertion + deletion)
would double their apparent distance.

### 2.2 Why this project cares

A search box must tolerate typing errors. A user who searches for
"keybord" expects to find keyboards. A user who searches for "wusthof"
and types "wustoff" expects to find the brand. Fuzzy matching is the
mechanism that makes this work.

## 3. Fuzziness (10.2)

### 3.1 What fuzziness means in Elasticsearch

The ``fuzziness`` parameter on a match-style query specifies the
maximum edit distance allowed between the query term and an indexed
term for the two to be considered a match.

Values:

| Value | Meaning |
|---|---|
| 0 | exact match only (fuzzy disabled) |
| 1 | one edit distance |
| 2 | two edit distances |
| "AUTO" | a per-term policy based on term length (see below) |

AUTO translates to:

* 0 edits for terms of length 1-2 (fuzzy disabled for very short
  terms)
* 1 edit for terms of length 3-5
* 2 edits for terms of length 6 or more

### 3.2 The choice for this platform

AUTO is chosen. The rationale:

1. **Short terms cannot afford edits.** A query for "tv" with
   fuzziness 1 matches "tv", "to", "ten", "top", and dozens of other
   two-character terms. The false-positive rate at fuzziness 1 for
   two-character terms approaches 100%. AUTO disables fuzziness for
   short terms, which is the correct default.

2. **Long terms tolerate edits well.** "headphones" is eleven
   characters. Two edits cover the vast majority of typing errors
   for words of that length without making the query match unrelated
   words.

3. **Fixed fuzziness 1 is too strict for long terms.** A user
   typing "heandphones" (2 edits: transposition of "ea", deletion of
   "d") would not match under fuzziness 1. AUTO matches it.

### 3.3 What fuzziness does not do

Fuzziness in Elasticsearch operates at the term level, after
analysis. It does not:

* Correct the whole query string as a unit.
* Understand grammar or intent.
* Handle word-order mistakes (that is ``match_phrase`` with slop,
  which is out of scope for this phase).

It is a per-token tolerance, not a spell corrector.

## 4. Prefix Length (10.3)

### 4.1 What it does

The ``prefix_length`` parameter specifies the number of leading
characters of a query term that must match exactly, before the fuzzy
edit distance starts counting. With ``prefix_length: 2`` and
``fuzziness: 1``, the query "moniter" only matches indexed terms
whose first two characters are "mo" and whose remaining characters
are within one edit of "niter".

### 4.2 Why it matters

Without a prefix, short fuzziness allows wild substitutions in the
opening characters. For example, with ``fuzziness: 1`` and no prefix,
the query "monitor" can match:

* "monitor" (0 edits)
* "monitors" (1 edit -- insertion)
* "monitorship" -- not matched, too long
* "conitor" (1 edit -- substitution of "m" for "c"), which is
  probably not a word any user meant to type
* "honitor" (1 edit), similarly

Most typing errors occur in the middle or end of a word, not the
first character. Protecting the first few characters therefore removes
a large class of false positives at almost no cost to genuine typo
tolerance.

### 4.3 The choice for this platform

``prefix_length: 2`` is chosen.

Two characters is the minimum useful protection. It anchors the fuzzy
match to the term's leading consonant cluster. A prefix of three or
more would start to reject legitimate typos in the third character,
which are common.

The setting is coupled to ``fuzziness: AUTO``: short terms (length
1-2) are not fuzzy at all, so ``prefix_length: 2`` is irrelevant for
them. For terms of length 3 or more, the prefix protection applies.

### 4.4 Additional tightening

Two further defaults are used for correctness, not efficiency:

* ``max_expansions: 50`` -- the maximum number of fuzzy variants
  Elasticsearch will consider per term. The default is 50; the
  platform leaves it. Higher values increase recall at the cost of
  query latency, and the platform has no latency budget to spend
  on this at Phase 10.
* ``transpositions: true`` -- the transposition variant of edit
  distance is enabled (Damerau-Levenshtein), which is the default
  and correct for human typing errors.

## 5. Fuzzy Search Policy (10.4)

### 5.1 Where fuzziness is applied

A fuzzy match is applied **only** when the caller explicitly asks
for it, by selecting ``SearchIntent.FUZZY``. The default literal and
normalized strategies are unchanged: they continue to issue exact
term matches.

### 5.2 Why fuzzy is opt-in

Fuzzy matching is expensive. Each fuzzy term expands into up to
``max_expansions`` variants, all of which must be looked up in the
inverted index. For a query with several terms, the cost multiplies.
Making fuzzy the default would make every query pay that cost even
when the input is clean.

More importantly, fuzzy matching changes what "match" means. A
search for "tv" that quietly matches "to" and "ten" is not a search
for "tv". The platform keeps the default honest and exposes fuzziness
as an explicit intent.

### 5.3 How the intent is selected

The API layer (Phase 19) will decide when to set the fuzzy intent.
Two reasonable policies exist:

* **User-driven.** A search box offers a "did you mean" fallback:
  if the exact search returned few or no results, retry with fuzzy.
* **Heuristic.** A term that produces zero exact matches within the
  first N results automatically triggers a fuzzy retry.

Neither policy belongs in Phase 10. The API layer will choose. What
this phase provides is the mechanism: a fuzzy strategy the API can
invoke.

### 5.4 The query shape

The fuzzy strategy issues a multi_match with ``fuzziness: "AUTO"``
and ``prefix_length: 2`` across the same boosted field set the
relevance strategy uses. It does not add the exact-phrase should
clause (a phrase-match on a typo would never fire) and does not add
business signals (ranking among fuzzy candidates is a subtler problem
than this phase attempts to solve).

The strategy is deliberately simpler than the relevance strategy.
When a query is fuzzy, the user is already outside the happy path;
returning the correct product at all is the priority. Ranking polish
is a later refinement.

## 6. False Positive Analysis (10.5)

### 6.1 What "false positive" means here

A fuzzy query returns a document that does not match what the user
intended. The false-positive rate is a function of:

* The query term's length. Shorter terms have fewer neighbours, so
  more of them fall within the edit distance.
* The edit distance allowed. Fuzziness 2 has many more neighbours
  than fuzziness 1.
* The prefix protection. A longer protected prefix reduces the
  search space.

### 6.2 How this platform bounds false positives

Three protections are in place:

1. **AUTO fuzziness.** Short terms are not fuzzed at all. This
   eliminates the worst class of false positives (short-word chaos).
2. **prefix_length: 2.** The first two characters are anchors. This
   eliminates the second-worst class (leading-character substitutions).
3. **Fuzzy is opt-in.** The default search never pays the cost or
   accepts the risk. It is invoked deliberately.

### 6.3 The evidence

The project's noise dataset (``data/search_noise.jsonl``) contains
32 entries, each pairing a misspelling, variant, or reordering with
the canonical term a user would have meant. The fuzzy integration
test (``tests/integration/test_fuzzy.py``) loads the fixture index,
runs each noise variant through the fuzzy strategy, and asserts that
the canonical term's document is in the result set.

What the test does not do is measure a false-positive rate across a
large corpus. That measurement belongs to Phase 22 (benchmarking)
and requires labeled data the platform does not have. This document
records the design decisions that bound the rate; it does not claim
a rate.

### 6.4 Known limitations

The current policy does not:

* Handle multi-word typos ("wireless hadphones" -- the fuzziness
  applies per term, and both terms must match somewhere).
* Distinguish a typo from a real word. If a user types "chair" when
  they meant "chain", fuzziness will find "chain" but also "chair".
  The platform cannot resolve this without intent information.
* Produce suggestions. The fuzzy strategy finds candidate documents;
  producing a "did you mean ..." suggestion is a different mechanism
  (a ``term`` suggester or a completions index), which is out of
  scope for Phase 10.


### 6.5 Spacing variants are out of scope

A specific class of noise is not addressable by fuzzy matching: spacing
variants. Examples from the platform's noise dataset:

    'head phones'        vs  canonical 'headphones'
    'noisecancelling'    vs  canonical 'noise-cancelling'
    'blue tooth'         vs  canonical 'bluetooth'

Fuzzy matching operates **per token**, after analysis. In each of these
cases, the query and the canonical text have different tokenizations:
"head phones" is two tokens, "headphones" is one. A per-token edit
distance cannot bridge this. The query token "head" would need to match
the indexed token "headphon", which is four edits away and outside the
AUTO fuzziness budget for a four-character token.

Two alternative mechanisms exist for spacing variants:

* **Shingle token filter at index time** -- index overlapping sequences
  of tokens so that "head phone" and "headphones" share n-gram
  representations.
* **Custom pre-processing** -- a query-time normalization that inserts
  or removes spaces according to a dictionary. This is a spell-correction
  approach, not a fuzzy-match approach.

Neither is implemented at Phase 10. The reason is scope discipline: fuzzy
matching has a clear, coherent problem (per-token typos) and a clear
mechanism (edit distance). Spacing variants have a different problem
(tokenization) and need a different mechanism. Adding that mechanism now
would mean designing it without the corpus and tests that would justify
its parameters. It is recorded here as a known limitation and a candidate
for a later phase.
