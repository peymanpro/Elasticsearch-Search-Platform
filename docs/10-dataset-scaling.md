# Dataset Scaling

## Purpose

The demonstration catalog is available at three fixed sizes. Each size
has a specific purpose. Choosing a size is a matter of which question
is being asked, not of resources.

## The Three Tiers

| Tier | Count | Location | Use |
|---|---|---|---|
| small | 12 | data/products.jsonl (hand-authored) | Reader tests, correctness assertions, human inspection |
| medium | 1000 | data/generated/products-1k.jsonl | Relevance experiments, analyzer comparison, faceted search demos |
| large | 100000 | data/generated/products-100k.jsonl | Latency measurement, bulk indexing throughput, deep pagination |

All three obey the same schema (docs/09-product-document-model.md).
The reader, mapping, analyzers, and queries are identical across
sizes.

## Why the Small Tier Is Hand-Authored

The 12-document file is written by hand, not generated. This is
deliberate. Small datasets are read by humans -- during code review,
during mapping design, during a relevance discussion. A hand-authored
file is inspectable: every line was chosen for a reason. The generator
produces volume; it does not produce human-legible examples.

## Why the Medium and Large Tiers Are Generated

Once the schema is stable (which Phase 4.1 established), variety is
the only thing large datasets add. The generator in
scripts/generate_products.py produces that variety deterministically:
same seed, same output, byte for byte. Benchmarks and relevance
experiments therefore run against a dataset that can be reproduced
exactly.

## Producing Each Tier

The generator is not run automatically. Each tier is produced on
demand, when a phase or a test needs it.

Medium tier:

```
python scripts/generate_products.py \
    --seed 42 \
    --count 1000 \
    --out data/generated/products-1k.jsonl
```

Large tier:

```
python scripts/generate_products.py \
    --seed 42 \
    --count 100000 \
    --out data/generated/products-100k.jsonl
```

The seed is fixed at 42 for the canonical medium and large datasets.
A different seed produces a different (still valid) catalog. The seed
is not a secret; it is a reproducibility handle.

## What Is Not Committed

Generated datasets are not committed to the repository. The
.gitignore excludes data/generated/. Committing a 100,000-line JSONL
file would bloat the repository without adding information: the
generator and its seed reproduce the file exactly.

The 12-document hand-authored file is committed because it is small,
stable, and read by tests.

## Storage and Time

Roughly:

- 1,000 documents: about 800 KB on disk, under a second to generate.
- 100,000 documents: about 80 MB on disk, several seconds to generate.

Bulk indexing these tiers (Phase 17) is the first point where index
throughput becomes measurable. Until then, the tiers exist as data on
disk, not as data in an index.

## Which Tier Each Phase Uses

| Phase | Tier | Why |
|---|---|---|
| 7 (analyzers) | small | A handful of representative texts demonstrate analyzer behavior |
| 8-9 (query and relevance) | small and medium | Small for hand-verifiable results, medium for ranking to be non-trivial |
| 10-11 (fuzzy, synonyms) | small | The noise dataset is the corpus, not the catalog |
| 12 (autocomplete) | medium | Prefix collisions become interesting only with volume |
| 13-15 (highlight, filter, sort) | medium | Facets need distribution to be meaningful |
| 16 (explain) | small | Explanations are read one document at a time |
| 17 (bulk indexing) | medium and large | Throughput is a function of volume |
| 18 (reindex) | medium | Reindex duration is measured, but not on the largest tier |
| 21 (tests) | small | Tests must be fast and deterministic |
| 22 (benchmarks) | medium and large | Benchmarks characterize behavior at scale |

## Rule for Adding a Tier

A fourth tier is added only when a phase requires a size that neither
of the current tiers serves. The rule is the same as for any other
addition: a concrete problem, not a hypothetical need.

