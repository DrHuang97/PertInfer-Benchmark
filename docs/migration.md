# Extraction and version boundaries

This repository contains code and synthetic engineering fixtures. Historical
experiments, predictions, model traces, progress reports, biological releases,
caches and paper result tables are not included.

The development project remains in place: its files, environments, data, release
seals and experiments are not modified. The standalone distribution uses the
`pertinfer_benchmark` namespace, avoiding collision with `pertagent`.

## Source mapping

Original SHA256 values are in [source_manifest.json](../provenance/source_manifest.json).
Paths are relative to the development project; no machine-specific paths or
original Git history are published.

| Development source | Destination | Treatment |
|---|---|---|
| `schema.py` | `schema.py` | Scientific graph contract and counting preserved |
| `evaluate.py` | `evaluate.py` | Scientific matcher preserved |
| `views.py` | `views.py` | Legacy record views, reader and grouping preserved |
| Public validation in `release_v57.py` | `tasks.py` | No repository discovery or private scoring imports |
| `score_one`, `summarize_rows` | `scoring.py` | Eligibility and stratified task averaging preserved |
| `io.py` | `io.py` | Standalone API, streamed file hashes and path checks |
| Release/prediction sealing | `freeze.py` | New envelope and explicit run plan |
| `build_material_corpus.py` | `materials.py` | Source packaging; fresh output directory required |
| Benchmark/material tests | `tests/` | Core semantics plus new synthetic integration tests |

The narrow legacy `schema.validate_task` is retained. Use the public
`pertinfer_benchmark.validate_task` (also `tasks.validate_task`) for multi-species
validation.

The new builder packages already-defined questions, graphs, references and
metadata. It does not migrate the discovery/curation workbench or make new
biological annotations. Historical candidate-mapping builders are not exposed as
the end-to-end benchmark builder. Graph-directed search, mechanism generation,
revision, prompts and model adapters remain method responsibilities.

## Historical seals

The graph contract remains `path_transfer_v5.contract_v1`. Package `0.1.0` and
envelope `pertinfer_benchmark.release_v1` identify this software extraction, not
a biological dataset version.

Old releases bind original scoring wrappers and file paths. Moving code or
changing imports changes those hashes. The standalone verifier rejects historical
envelopes and directs users to the archived evaluator. It never removes the
checks, replaces old hashes, edits old releases or claims old experiment outputs
were produced by this toolkit.

Future biological data migration must record its source version, preserve
scientific payload provenance, declare its new packaging version and validate
equivalence. It is outside this code-only release. Scientific baseline adapters
also need portable integration; the abstention template is only an interface example.

Every standalone release binds all package Python source hashes. Build and score
with the same toolkit commit. Hashes check consistency, not authorship or time.
Public export selects files; method filesystem and tool isolation are separate.
Validation runs only new synthetic fixtures in disposable output directories.
